from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import average_precision_score, f1_score, roc_auc_score
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from Backend.Benchmark.model_suite.evaluation.metrics import summarize_protocol_classification
from Backend.Benchmark.model_suite.pipeline.training_job import train_tabular_classifier
from Backend.Benchmark.model_suite.registries import resolve_model_profile

from .embedding import SequenceBundle, SequencePreprocessor
from .runner import LOW_LABEL, REF_LABEL, REPORT_LABELS, UNRES_LABEL
from .semantic_targets import Y_EVENT, Y_ONLINE
from .semantic_runner import _depth_bin, _provenance_stratum


@dataclass(frozen=True)
class EmbeddingVariant:
    variant_id: str
    target_view_id: str
    label_column: str


class CausalGRUEncoder(nn.Module):
    def __init__(self, *, input_size: int, hidden_size: int, class_count: int) -> None:
        super().__init__()
        self.gru = nn.GRU(input_size=input_size, hidden_size=hidden_size, batch_first=True)
        self.head = nn.Linear(hidden_size, class_count)

    def forward(self, inputs: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        outputs, _ = self.gru(inputs)
        embedding = outputs[:, -1, :]
        return self.head(embedding), embedding


def run_embedding_variants(
    *,
    sequence_bundle: SequenceBundle,
    target_frame: pd.DataFrame,
    output_dir: Path,
    random_seed: int,
    thread_count: int,
    embedding_size: int = 32,
    max_epochs: int = 120,
    patience: int = 18,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    _set_deterministic_seed(random_seed)
    torch.set_num_threads(max(1, int(thread_count)))
    sample_to_sequence = {sample_id: index for index, sample_id in enumerate(sequence_bundle.sample_ids)}
    trainable = (
        target_frame["final_trainability"].fillna(False).astype(bool)
        & target_frame["label_status_online"].astype("string").eq("LABELED")
        & target_frame["label_status_event"].astype("string").eq("LABELED")
    )
    eligible = target_frame.loc[trainable].copy()
    missing = sorted(set(eligible["sample_id"].astype(str)).difference(sample_to_sequence))[:5]
    if missing:
        raise ValueError(f"Sequence bundle does not cover trainable target rows: {missing}")
    ordered_ids = eligible["sample_id"].astype(str).tolist()
    sequence_indices = np.asarray([sample_to_sequence[sample_id] for sample_id in ordered_ids], dtype=int)
    sequence_preprocessor = SequencePreprocessor.fit(
        sequence_bundle,
        train_indices=sequence_indices[eligible["partition"].astype("string").eq("train").to_numpy()],
    )
    transformed_sequences = sequence_preprocessor.transform(sequence_bundle)[sequence_indices]
    partition_masks = {
        name: eligible["partition"].astype("string").eq(name).to_numpy()
        for name in ("train", "validation", "test")
    }
    variants = (
        EmbeddingVariant("gru_embedding_online_k3", Y_ONLINE, "label_online"),
        EmbeddingVariant("gru_embedding_event_k3", Y_EVENT, "label_event"),
    )
    metrics_rows: list[dict[str, object]] = []
    per_class_rows: list[dict[str, object]] = []
    confusion_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    stratum_rows: list[pd.DataFrame] = []
    embedding_rows: list[pd.DataFrame] = []
    profile = resolve_model_profile("xgboost")

    for variant in variants:
        target_labels = eligible[variant.label_column].astype("string").to_numpy()
        class_names = sorted(np.unique(target_labels).tolist())
        if class_names != sorted(REPORT_LABELS):
            raise ValueError(f"Embedding target has incomplete classes: {variant.variant_id} -> {class_names}")
        class_lookup = {label: index for index, label in enumerate(class_names)}
        model, history = _fit_encoder(
            inputs=transformed_sequences,
            labels=np.asarray([class_lookup[label] for label in target_labels], dtype=np.int64),
            train_mask=partition_masks["train"],
            validation_mask=partition_masks["validation"],
            input_size=transformed_sequences.shape[2],
            embedding_size=embedding_size,
            class_count=len(class_names),
            random_seed=random_seed,
            max_epochs=max_epochs,
            patience=patience,
        )
        encoder_dir = output_dir / "encoders" / variant.variant_id
        encoder_dir.mkdir(parents=True, exist_ok=True)
        torch.save(model.state_dict(), encoder_dir / "encoder.pt")
        (encoder_dir / "training_history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
        embeddings = _extract_embeddings(model, transformed_sequences)
        embedding_frame = pd.DataFrame(
            embeddings,
            columns=[f"embedding_{index:03d}" for index in range(embeddings.shape[1])],
        )
        embedding_frame.insert(0, "sample_id", ordered_ids)
        embedding_frame.insert(1, "target_view_id", variant.target_view_id)
        embedding_rows.append(embedding_frame)
        feature_names = [column for column in embedding_frame.columns if column not in {"sample_id", "target_view_id"}]
        feature_lookup = embedding_frame.set_index("sample_id", drop=False)
        train_frame = eligible.loc[partition_masks["train"]].copy()
        eval_frames = {name: eligible.loc[partition_masks[name]].copy() for name in ("validation", "test")}
        train_ids = train_frame["sample_id"].astype(str).tolist()
        result = train_tabular_classifier(
            profile=profile,
            train_features=feature_lookup.loc[train_ids, feature_names].to_numpy(dtype=np.float32),
            evaluation_features={
                name: feature_lookup.loc[frame["sample_id"].astype(str).tolist(), feature_names].to_numpy(dtype=np.float32)
                for name, frame in eval_frames.items()
            },
            train_labels=train_frame[variant.label_column].astype("string"),
            allowed_feature_columns=feature_names,
            train_sample_ids=train_ids,
            output_dir=output_dir / "jobs" / variant.variant_id,
            random_seed=random_seed,
            thread_count=thread_count,
            task_metadata={
                "variant_id": variant.variant_id,
                "target_view_id": variant.target_view_id,
                "representation": "causal_sequence_gru_embedding",
                "sequence_length": sequence_bundle.sequence_length,
                "embedding_size": embedding_size,
                "encoder_fit_partition": "train",
                "future_used_for": "event_label_only" if variant.target_view_id == Y_EVENT else "none",
            },
        )
        for partition, partition_frame in eval_frames.items():
            y_true = partition_frame[variant.label_column].map(class_lookup).to_numpy(dtype=np.int64)
            y_pred = np.asarray(result.evaluation_predictions[partition], dtype=np.int64)
            probabilities = result.evaluation_probabilities.get(partition)
            metrics = summarize_protocol_classification(y_true, y_pred, class_names)
            metrics.update(_probability_metrics(y_true, probabilities, class_names))
            metrics_rows.append({
                "variant_id": variant.variant_id,
                "target_view_id": variant.target_view_id,
                "representation": "causal_sequence_gru_embedding",
                "feature_count": len(feature_names),
                "embedding_size": embedding_size,
                "partition": partition,
                "train_count": len(train_frame),
                "evaluation_count": len(partition_frame),
                "encoder_best_epoch": history["best_epoch"],
                "encoder_best_validation_macro_f1": history["best_validation_macro_f1"],
                "accuracy": metrics["accuracy"],
                "balanced_accuracy": metrics["supported_class_balanced_accuracy"],
                "macro_f1": metrics["supported_class_macro_f1"],
                "weighted_f1": metrics["weighted_f1"],
                "macro_pr_auc_ovr": metrics["macro_pr_auc_ovr"],
                "macro_roc_auc_ovr": metrics["macro_roc_auc_ovr"],
                "low_recall": metrics["class_metrics"].get(LOW_LABEL, {}).get("recall"),
                "unres_recall": metrics["class_metrics"].get(UNRES_LABEL, {}).get("recall"),
                "ref_recall": metrics["class_metrics"].get(REF_LABEL, {}).get("recall"),
            })
            for class_name, class_metrics in metrics["class_metrics"].items():
                per_class_rows.append({
                    "variant_id": variant.variant_id,
                    "target_view_id": variant.target_view_id,
                    "partition": partition,
                    "class_name": class_name,
                    **class_metrics,
                })
            for true_index, true_name in enumerate(class_names):
                for pred_index, pred_name in enumerate(class_names):
                    confusion_rows.append({
                        "variant_id": variant.variant_id,
                        "target_view_id": variant.target_view_id,
                        "partition": partition,
                        "true_label": true_name,
                        "predicted_label": pred_name,
                        "count": int(metrics["confusion_matrix"][true_index][pred_index]),
                    })
            for index, row in enumerate(partition_frame.to_dict(orient="records")):
                probabilities_map = {}
                if probabilities is not None:
                    probabilities_map = {
                        name: float(value)
                        for name, value in zip(class_names, probabilities[index], strict=True)
                    }
                prediction_rows.append({
                    "variant_id": variant.variant_id,
                    "target_view_id": variant.target_view_id,
                    "partition": partition,
                    "sample_id": str(row["sample_id"]),
                    "label_true": str(row[variant.label_column]),
                    "label_online": str(row["label_online"]),
                    "label_event": str(row["label_event"]),
                    "label_pred": class_names[int(y_pred[index])],
                    "provenance_stratum": _provenance_stratum(row),
                    "depth_bin": _depth_bin(int(row["support_depth_at_anchor"])),
                    "support_depth_at_anchor": int(row["support_depth_at_anchor"]),
                    "eventual_run_length": row["eventual_run_length"],
                    "p_low": probabilities_map.get(LOW_LABEL, np.nan),
                    "p_unres": probabilities_map.get(UNRES_LABEL, np.nan),
                    "p_ref": probabilities_map.get(REF_LABEL, np.nan),
                })

    predictions = pd.DataFrame(prediction_rows).convert_dtypes()
    predictions["online_correct"] = predictions["label_pred"].astype("string").eq(predictions["label_online"].astype("string"))
    predictions["event_correct"] = predictions["label_pred"].astype("string").eq(predictions["label_event"].astype("string"))
    predictions["is_low_pred"] = predictions["label_pred"].astype("string").eq(LOW_LABEL)
    strata = (
        predictions.groupby(
            ["variant_id", "target_view_id", "partition", "provenance_stratum", "depth_bin"],
            dropna=False,
            sort=True,
        )
        .agg(
            prediction_rows=("sample_id", "size"),
            unique_samples=("sample_id", "nunique"),
            hard_low_rate=("is_low_pred", "mean"),
            mean_p_low=("p_low", "mean"),
            mean_p_unres=("p_unres", "mean"),
            mean_p_ref=("p_ref", "mean"),
            online_accuracy=("online_correct", "mean"),
            event_accuracy=("event_correct", "mean"),
        )
        .reset_index()
        .convert_dtypes()
    )
    return (
        pd.DataFrame(metrics_rows).convert_dtypes(),
        pd.DataFrame(per_class_rows).convert_dtypes(),
        pd.DataFrame(confusion_rows).convert_dtypes(),
        predictions,
        strata,
        pd.concat(embedding_rows, ignore_index=True).convert_dtypes(),
    )


def _fit_encoder(
    *,
    inputs: np.ndarray,
    labels: np.ndarray,
    train_mask: np.ndarray,
    validation_mask: np.ndarray,
    input_size: int,
    embedding_size: int,
    class_count: int,
    random_seed: int,
    max_epochs: int,
    patience: int,
) -> tuple[CausalGRUEncoder, dict[str, object]]:
    _set_deterministic_seed(random_seed)
    model = CausalGRUEncoder(input_size=input_size, hidden_size=embedding_size, class_count=class_count)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-4)
    train_labels = labels[train_mask]
    counts = np.bincount(train_labels, minlength=class_count).astype(np.float32)
    weights = counts.sum() / np.maximum(counts, 1.0)
    weights = weights / weights.mean()
    loss_fn = nn.CrossEntropyLoss(weight=torch.tensor(weights, dtype=torch.float32))
    train_x = torch.tensor(inputs[train_mask], dtype=torch.float32)
    train_y = torch.tensor(train_labels, dtype=torch.long)
    validation_x = torch.tensor(inputs[validation_mask], dtype=torch.float32)
    validation_y = torch.tensor(labels[validation_mask], dtype=torch.long)
    loader = DataLoader(
        TensorDataset(train_x, train_y),
        batch_size=min(64, len(train_x)),
        shuffle=True,
        generator=torch.Generator().manual_seed(random_seed),
    )
    best_state = None
    best_score = -np.inf
    best_epoch = 0
    stale = 0
    history_rows: list[dict[str, float]] = []
    for epoch in range(1, max_epochs + 1):
        model.train()
        train_losses = []
        for batch_x, batch_y in loader:
            optimizer.zero_grad()
            logits, _ = model(batch_x)
            loss = loss_fn(logits, batch_y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=2.0)
            optimizer.step()
            train_losses.append(float(loss.detach().cpu()))
        model.eval()
        with torch.no_grad():
            validation_logits, _ = model(validation_x)
            validation_loss = float(loss_fn(validation_logits, validation_y).cpu())
            validation_pred = validation_logits.argmax(dim=1).cpu().numpy()
        validation_macro_f1 = float(f1_score(validation_y.cpu().numpy(), validation_pred, average="macro", zero_division=0))
        history_rows.append({
            "epoch": float(epoch),
            "train_loss": float(np.mean(train_losses)),
            "validation_loss": validation_loss,
            "validation_macro_f1": validation_macro_f1,
        })
        if validation_macro_f1 > best_score + 1e-8:
            best_score = validation_macro_f1
            best_epoch = epoch
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            stale = 0
        else:
            stale += 1
        if stale >= patience:
            break
    if best_state is None:
        raise RuntimeError("GRU encoder did not produce a validation checkpoint.")
    model.load_state_dict(best_state)
    return model, {
        "best_epoch": int(best_epoch),
        "best_validation_macro_f1": float(best_score),
        "epochs_executed": len(history_rows),
        "history": history_rows,
    }


def _extract_embeddings(model: CausalGRUEncoder, inputs: np.ndarray) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        _, embedding = model(torch.tensor(inputs, dtype=torch.float32))
    return embedding.cpu().numpy().astype(np.float32)


def _probability_metrics(y_true: np.ndarray, probabilities: list[list[float]] | None, class_names: list[str]) -> dict[str, float]:
    if probabilities is None:
        return {"macro_pr_auc_ovr": float("nan"), "macro_roc_auc_ovr": float("nan")}
    scores = np.asarray(probabilities, dtype=float)
    one_hot = np.eye(len(class_names), dtype=float)[y_true]
    try:
        pr_auc = float(average_precision_score(one_hot, scores, average="macro"))
    except ValueError:
        pr_auc = float("nan")
    try:
        roc_auc = float(roc_auc_score(y_true, scores, multi_class="ovr", average="macro"))
    except ValueError:
        roc_auc = float("nan")
    return {"macro_pr_auc_ovr": pr_auc, "macro_roc_auc_ovr": roc_auc}


def _set_deterministic_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
