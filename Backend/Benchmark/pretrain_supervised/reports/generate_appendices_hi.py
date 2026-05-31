from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[4]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.common.paths import DIRECT_BENCHMARK_ROOT, PRETRAIN_SUPERVISED_ROOT

REPORTS_ROOT = Path(__file__).resolve().parent
PRETRAIN_ROOT = PRETRAIN_SUPERVISED_ROOT
DIRECT_ROOT = DIRECT_BENCHMARK_ROOT
CHAPTER5_ROOT = PRETRAIN_SUPERVISED_ROOT / "chapter5_evidence"
OUTPUT_ROOT = CHAPTER5_ROOT / f"{date.today().isoformat()}-appendices-hi"


@dataclass(frozen=True)
class RunPointer:
    arm: str
    version: str
    run_dir: Path


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def latest_dated_run(outputs_root: Path) -> Path:
    date_buckets = [item for item in outputs_root.iterdir() if item.is_dir()]
    if not date_buckets:
        raise FileNotFoundError(f"No date buckets found under: {outputs_root}")
    latest_bucket = sorted(date_buckets, key=lambda item: item.name)[-1]
    runs = [item for item in latest_bucket.iterdir() if item.is_dir()]
    if not runs:
        raise FileNotFoundError(f"No run directories found under: {latest_bucket}")
    return sorted(runs, key=lambda item: item.name)[-1]


def latest_chapter5_dir(suffix: str) -> Path:
    candidates = [item for item in CHAPTER5_ROOT.iterdir() if item.is_dir() and item.name.endswith(suffix)]
    if not candidates:
        raise FileNotFoundError(f"No chapter5 evidence folder with suffix '{suffix}' under: {CHAPTER5_ROOT}")
    return sorted(candidates, key=lambda item: item.name)[-1]


def discover_runs() -> dict[str, RunPointer]:
    return {
        "direct": RunPointer("direct", "direct", latest_dated_run(DIRECT_ROOT / "outputs")),
        "v0": RunPointer("pretrain", "v0", latest_dated_run(PRETRAIN_ROOT / "v0" / "outputs")),
        "v1": RunPointer("pretrain", "v1", latest_dated_run(PRETRAIN_ROOT / "v1" / "outputs")),
        "v2": RunPointer("pretrain", "v2", latest_dated_run(PRETRAIN_ROOT / "v2" / "outputs")),
        "v3": RunPointer("pretrain", "v3", latest_dated_run(PRETRAIN_ROOT / "v3" / "outputs")),
        "v4": RunPointer("pretrain", "v4", latest_dated_run(PRETRAIN_ROOT / "v4" / "outputs")),
    }


def build_model_config_rows() -> list[dict[str, Any]]:
    return [
        {
            "model": "Majority baseline",
            "scope": "conceptual baseline",
            "main_parameters": "predict majority class only",
            "seed": "n/a",
            "implemented_in_final_suite": "no",
            "notes": "Khong co trong batch final hien tai; chi nen neu nhu baseline toi thieu ve mat khai niem.",
        },
        {
            "model": "Linear probe",
            "scope": "direct + pretrain downstream",
            "main_parameters": "LogisticRegression(max_iter=2000, C=1.0 default, random_state=42)",
            "seed": "42",
            "implemented_in_final_suite": "yes",
            "notes": "Class imbalance duoc xu ly bang compute_sample_weight(class_weight='balanced').",
        },
        {
            "model": "XGBoost",
            "scope": "direct + pretrain downstream",
            "main_parameters": (
                "n_estimators=250, max_depth=5, learning_rate=0.05, "
                "subsample=0.9, colsample_bytree=0.9, reg_lambda=1.0, "
                "objective=binary:logistic, eval_metric=logloss, random_state=42"
            ),
            "seed": "42",
            "implemented_in_final_suite": "yes",
            "notes": "Khong dat scale_pos_weight rieng; imbalance duoc truyen qua sample_weight khi fit.",
        },
        {
            "model": "TabNet classifier",
            "scope": "direct benchmark only",
            "main_parameters": (
                "n_d=16, n_a=16, n_steps=4, gamma=1.3, "
                "batch_size=64, virtual_batch_size=32, lr=0.001, "
                "weight_decay=1e-4, epochs=120, patience=16, mask_type=sparsemax"
            ),
            "seed": "42",
            "implemented_in_final_suite": "yes",
            "notes": "DL control arm tren raw/control features.",
        },
        {
            "model": "TabNet pretrainer",
            "scope": "pretrain stage",
            "main_parameters": (
                "mask_ratio=0.2, reconstruction_loss=masked MSE, "
                "n_d=16, n_a=16, n_steps=4, gamma=1.3, "
                "batch_size=256, virtual_batch_size=128, lr=0.002, "
                "weight_decay=1e-5, epochs=100, patience=8, mask_type=sparsemax"
            ),
            "seed": "42",
            "implemented_in_final_suite": "yes",
            "notes": "Hoc bieu dien tu giam sat; test khong duoc dung de toi uu.",
        },
        {
            "model": "Torch/MLP probe",
            "scope": "pretrain downstream only",
            "main_parameters": (
                "hidden_dim=64, dropout=0.2, batch_size=64, lr=0.001, "
                "weight_decay=1e-4, epochs=100, patience=8, max_grad_norm=1.0"
            ),
            "seed": "42",
            "implemented_in_final_suite": "yes",
            "notes": "MLP tren embedding; duoc chon theo validation nhu cac model khac.",
        },
    ]


def flatten_direct_results(run_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    training_report = load_json(run_dir / "training_report.json")
    aggregate_rows = load_csv(run_dir / "aggregate_model_metrics.csv")
    result_rows: list[dict[str, Any]] = []
    split_rows: list[dict[str, Any]] = []
    exploratory_rows: list[dict[str, Any]] = []

    best_by_version: dict[str, dict[str, Any]] = {}

    for experiment_report in training_report["experiment_reports"]:
        experiment_name = str(experiment_report["experiment_name"])
        experiment_training_report = load_json(Path(experiment_report["report_path"]))
        split_policy = experiment_training_report["split_policy"]
        split_counts = experiment_training_report["split_counts"]
        split_rows.append(
            {
                "benchmark_arm": "direct",
                "version": experiment_name,
                "experiment": experiment_name,
                "input_rows": experiment_training_report["aligned_rows"],
                "train_rows": split_counts["train"],
                "validation_rows": split_counts["validation"],
                "test_rows": split_counts["test"],
                "excluded_gap_rows": split_policy["excluded_row_count"],
                "split_strategy": split_policy["strategy_name"],
                "gap_minutes": split_policy["gap_minutes"],
                "selected_model": experiment_training_report["selected_model"]["model_name"],
                "selected_validation_macro_f1": round(float(experiment_training_report["selected_model"]["validation_macro_f1"]), 6),
            }
        )

    for row in aggregate_rows:
        version = str(row["experiment_name"])
        payload = {
            "benchmark_arm": "direct",
            "version": version,
            "experiment": version,
            "feature_set": version,
            "model": str(row["model_name"]),
            "validation_macro_f1": round(float(row["validation_macro_f1"]), 6),
            "test_macro_f1": round(float(row["test_macro_f1"]), 6),
            "validation_balanced_accuracy": round(float(row["validation_balanced_accuracy"]), 6),
            "test_balanced_accuracy": round(float(row["test_balanced_accuracy"]), 6),
            "validation_test_gap_macro_f1": round(float(row["test_macro_f1"]) - float(row["validation_macro_f1"]), 6),
            "notes": str(row.get("notes", "")),
            "artifact_path": str(row["artifact_path"]),
        }
        result_rows.append(payload)
        current_best = best_by_version.get(version)
        if current_best is None or float(row["test_macro_f1"]) > float(current_best["test_macro_f1"]):
            best_by_version[version] = payload

    for version, payload in sorted(best_by_version.items()):
        exploratory_rows.append(payload | {"selection_role": "best_test_exploratory"})

    return result_rows, split_rows, exploratory_rows


def flatten_pretrain_results(run_map: dict[str, RunPointer]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    result_rows: list[dict[str, Any]] = []
    split_rows: list[dict[str, Any]] = []
    exploratory_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    best_by_version: dict[str, dict[str, Any]] = {}

    for version in ("v0", "v1", "v2", "v3", "v4"):
        run_dir = run_map[version].run_dir
        training_report = load_json(run_dir / "training_report.json")

        if version == "v1":
            split_policy = training_report["split_policy"]
            split_counts = training_report["split_counts"]
            split_rows.append(
                {
                    "benchmark_arm": "pretrain",
                    "version": "v1",
                    "experiment": "v1",
                    "input_rows": training_report["input_rows"],
                    "train_rows": split_counts["train"],
                    "validation_rows": split_counts["validation"],
                    "test_rows": split_counts["test"],
                    "excluded_gap_rows": split_policy["excluded_row_count"],
                    "split_strategy": split_policy["strategy_name"],
                    "gap_minutes": split_policy["gap_minutes"],
                    "selected_model": training_report["selected_model"]["model_name"],
                    "selected_validation_macro_f1": round(float(training_report["selected_model"]["validation_macro_f1"]), 6),
                }
            )
            checkpoint_config = training_report["pretrain_checkpoint_config"]
            source_rows.append(
                {
                    "version": "v1",
                    "experiment": "v1",
                    "source_kind": checkpoint_config["source_kind"],
                    "feature_count": len(checkpoint_config["feature_columns"]),
                    "feature_columns": ", ".join(checkpoint_config["feature_columns"]),
                    "required_columns": ", ".join(checkpoint_config["required_columns"]),
                    "mask_ratio": checkpoint_config["mask_ratio"],
                    "pretrain_epochs": checkpoint_config["max_epochs"],
                    "pretrain_lr": checkpoint_config["learning_rate"],
                    "pretrain_seed": checkpoint_config["seed"],
                }
            )
            for model_payload in training_report["models"]:
                payload = {
                    "benchmark_arm": "pretrain",
                    "version": "v1",
                    "experiment": "v1",
                    "feature_set": "layer1 embedding",
                    "model": str(model_payload["model_name"]),
                    "validation_macro_f1": round(float(model_payload["validation_macro_f1"]), 6),
                    "test_macro_f1": round(float(model_payload["test_macro_f1"]), 6),
                    "validation_balanced_accuracy": round(float(model_payload["validation_balanced_accuracy"]), 6),
                    "test_balanced_accuracy": round(float(model_payload["test_balanced_accuracy"]), 6),
                    "validation_test_gap_macro_f1": round(float(model_payload["test_macro_f1"]) - float(model_payload["validation_macro_f1"]), 6),
                    "notes": str(model_payload.get("notes", "")),
                    "artifact_path": str(model_payload["artifact_path"]),
                    "checkpoint_path": str(training_report["pretrain_checkpoint"]),
                }
                result_rows.append(payload)
                current_best = best_by_version.get("v1")
                if current_best is None or float(model_payload["test_macro_f1"]) > float(current_best["test_macro_f1"]):
                    best_by_version["v1"] = payload
            continue

        for experiment_report in training_report["experiment_reports"]:
            experiment_name = str(experiment_report["experiment_name"])
            split_policy = experiment_report["split_policy"]
            split_counts = experiment_report["split_counts"]
            split_rows.append(
                {
                    "benchmark_arm": "pretrain",
                    "version": version,
                    "experiment": experiment_name,
                    "input_rows": experiment_report["input_rows"],
                    "train_rows": split_counts["train"],
                    "validation_rows": split_counts["validation"],
                    "test_rows": split_counts["test"],
                    "excluded_gap_rows": split_policy["excluded_row_count"],
                    "split_strategy": split_policy["strategy_name"],
                    "gap_minutes": split_policy["gap_minutes"],
                    "selected_model": experiment_report["selected_model"]["model_name"],
                    "selected_validation_macro_f1": round(float(experiment_report["selected_model"]["validation_macro_f1"]), 6),
                }
            )

            checkpoint_config = experiment_report["pretrain_checkpoint_config"]
            source_rows.append(
                {
                    "version": version,
                    "experiment": experiment_name,
                    "source_kind": checkpoint_config["source_kind"],
                    "feature_count": len(checkpoint_config["feature_columns"]),
                    "feature_columns": ", ".join(checkpoint_config["feature_columns"]),
                    "required_columns": ", ".join(checkpoint_config["required_columns"]),
                    "mask_ratio": checkpoint_config["mask_ratio"],
                    "pretrain_epochs": checkpoint_config["max_epochs"],
                    "pretrain_lr": checkpoint_config["learning_rate"],
                    "pretrain_seed": checkpoint_config["seed"],
                }
            )

            for model_payload in experiment_report["models"]:
                payload = {
                    "benchmark_arm": "pretrain",
                    "version": version,
                    "experiment": experiment_name,
                    "feature_set": str(experiment_report["source_kind"]),
                    "model": str(model_payload["model_name"]),
                    "validation_macro_f1": round(float(model_payload["validation_macro_f1"]), 6),
                    "test_macro_f1": round(float(model_payload["test_macro_f1"]), 6),
                    "validation_balanced_accuracy": round(float(model_payload["validation_balanced_accuracy"]), 6),
                    "test_balanced_accuracy": round(float(model_payload["test_balanced_accuracy"]), 6),
                    "validation_test_gap_macro_f1": round(float(model_payload["test_macro_f1"]) - float(model_payload["validation_macro_f1"]), 6),
                    "notes": str(model_payload.get("notes", "")),
                    "artifact_path": str(model_payload["artifact_path"]),
                    "checkpoint_path": str(model_payload["checkpoint_path"]),
                }
                result_rows.append(payload)
                current_best = best_by_version.get(version)
                if current_best is None or float(model_payload["test_macro_f1"]) > float(current_best["test_macro_f1"]):
                    best_by_version[version] = payload

    for version, payload in sorted(best_by_version.items()):
        exploratory_rows.append(payload | {"selection_role": "best_test_exploratory"})

    return result_rows, split_rows, exploratory_rows, source_rows


def append_abnormal_metrics(
    rows: list[dict[str, Any]],
    summary_rows: list[dict[str, str]],
    arm: str,
) -> list[dict[str, Any]]:
    index: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in summary_rows:
        if row["benchmark_arm"] != arm:
            continue
        index[(row["benchmark_version"], row["experiment_name"], row["model_name"])] = row

    enriched: list[dict[str, Any]] = []
    for row in rows:
        experiment = str(row["experiment"])
        version = str(row["version"])
        if arm == "direct":
            key = ("direct", experiment, str(row["model"]))
        else:
            key = (version, experiment, str(row["model"]))
        abnormal = index.get(key)
        payload = dict(row)
        if abnormal is not None:
            payload["abnormal_precision"] = round(float(abnormal["overall_abnormal_precision"]), 6)
            payload["abnormal_recall"] = round(float(abnormal["overall_abnormal_recall"]), 6)
            payload["abnormal_f1"] = round(float(abnormal["overall_abnormal_f1"]), 6)
            payload["subgroup_macro_recall_support_ge_3"] = round(float(abnormal["macro_recall_main_threshold"]), 6)
        else:
            payload["abnormal_precision"] = ""
            payload["abnormal_recall"] = ""
            payload["abnormal_f1"] = ""
            payload["subgroup_macro_recall_support_ge_3"] = ""
        enriched.append(payload)
    return enriched


def build_confusion_index() -> list[dict[str, Any]]:
    chapter5_dir = latest_chapter5_dir("-chapter5")
    charts_dir = chapter5_dir / "charts"
    rows: list[dict[str, Any]] = []
    for path in sorted(charts_dir.glob("*confusion*.png")):
        rows.append(
            {
                "artifact_type": "confusion_matrix_png",
                "path": str(path),
                "source_pack": str(chapter5_dir),
                "notes": "Artifact duoc sinh tu generate_chapter5_evidence.py",
            }
        )
    for path in sorted(charts_dir.glob("*pr_curve*.png")):
        rows.append(
            {
                "artifact_type": "pr_curve_png",
                "path": str(path),
                "source_pack": str(chapter5_dir),
                "notes": "Artifact duoc sinh tu generate_chapter5_evidence.py",
            }
        )
    return rows


def render_appendix_h(
    model_config_rows: list[dict[str, Any]],
    split_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
) -> str:
    model_table = "\n".join(
        f"| {row['model']} | {row['main_parameters']} | {row['notes']} |"
        for row in model_config_rows
    )
    split_preview = "\n".join(
        f"| {row['benchmark_arm']} | {row['version']} | {row['experiment']} | {row['train_rows']} | {row['validation_rows']} | {row['test_rows']} | {row['excluded_gap_rows']} | {row['gap_minutes']} |"
        for row in split_rows[:12]
    )
    return f"""# Phu luc H. Benchmark protocol va cau hinh mo hinh

## H.1. Cach chia train/validation/test

Tat ca cac run final trong phu luc nay deu dung **chronological_with_lookback_gap**. Du lieu duoc sap xep theo `timestamp`, sau do chia:

- `train = 70%`
- `validation = 15%`
- `test = 15%`
- chen them **purge gap 24 gio = 1440 phut** giua train-validation va validation-test

Khong dung `stratified random split` cho batch final.

## H.2. Ly do dung chronological split

Du lieu la chuoi thoi gian va nhieu feature benchmark dung cua so nhin nguoc (`3h`, `8h`, `24h`). Vi vay chia ngau nhien se de lam xao tron cac mau gan nhau theo thoi gian, dan den metric lac quan hon thuc te. Chronological split giu thu tu xuat hien cua du lieu va phu hop hon voi boi canh du bao/nhan dien theo dong thoi gian.

## H.3. Lookback/purge gap 24 gio

Lookback gap 24 gio duoc dat de giam leakage mem giua cac cua so nhin nguoc. Cac ban ghi nam trong vung dem khong thuoc train, validation, hay test.

## H.4. Metric chinh va phu

- **Metric chinh**: `test macro-F1`
- **Metric phu**:
  - `balanced accuracy`
  - `abnormal precision`
  - `abnormal recall`
  - `abnormal F1`
  - `validation-test gap`
  - `confusion matrix`
  - `PR curve` (khi model co score/probability)

Macro-F1 duoc chon lam metric chinh do du lieu lech lop va lop `abnormal` chiem ty le nho.

## H.5. Cau hinh model

| Model | Tham so chinh | Ghi chu |
|---|---|---|
{model_table}

## H.6. Nguyen tac chon mo hinh theo validation

Main result duoc chon theo **validation macro-F1**. Moi run deu luu truong `selected_model` trong `training_report.json` de khoa cach chon nay.

## H.7. Test chi dung danh gia cuoi

Tap test duoc giu rieng cho danh gia cuoi. Checkpoint pretrain duoc chon theo validation reconstruction loss; model downstream duoc chon theo validation macro-F1.

## H.8. Best-test exploratory khong thay the main result

Trong phu luc I van bao cao `best-test exploratory` de tham khao, nhung ket qua nay khong duoc dung thay cho main result. Best-test chi dung de phan tich bo sung, khong phai quy tac chon mo hinh chinh thuc.

## Bang tach split theo version/experiment (trich yeu)

| Arm | Version | Experiment | Train | Validation | Test | Excluded gap | Gap (minutes) |
|---|---|---|---:|---:|---:|---:|---:|
{split_preview}

## Tep CSV di kem

- `H_model_config.csv`
- `H_split_counts.csv`
- `H_pretrain_source_config.csv`
"""


def render_appendix_i(
    direct_rows: list[dict[str, Any]],
    pretrain_rows: list[dict[str, Any]],
    gap_rows: list[dict[str, Any]],
    exploratory_rows: list[dict[str, Any]],
    confusion_index_rows: list[dict[str, Any]],
) -> str:
    direct_count = len(direct_rows)
    pretrain_count = len(pretrain_rows)
    exploratory_preview = "\n".join(
        f"| {row['benchmark_arm']} | {row['version']} | {row['experiment']} | {row['model']} | {row['test_macro_f1']:.6f} |"
        for row in exploratory_rows[:10]
    )
    confusion_preview = "\n".join(
        f"- `{row['artifact_type']}`: `{row['path']}`"
        for row in confusion_index_rows[:8]
    )
    return f"""# Phu luc I. Ket qua benchmark chi tiet

Phu luc nay tap hop ket qua day du cua batch final theo protocol da khoa o Phu luc H.

## I.1. Full result direct benchmark

Toan bo ket qua direct duoc xuat trong `I_direct_full_results.csv` ({direct_count} dong ket qua model).

## I.2. Full result pretrain-downstream

Toan bo ket qua pretrain-downstream duoc xuat trong `I_pretrain_full_results.csv` ({pretrain_count} dong ket qua model/experiment).

## I.3. Validation-test gap

Bang `I_validation_test_gap.csv` ghi ro:

- `validation_macro_f1`
- `test_macro_f1`
- `validation_test_gap_macro_f1`

Muc dich la tach main result theo validation khoi best-test exploratory.

## I.4. Confusion matrix cho cau hinh chinh

Artifact confusion matrix/PR hien co:

{confusion_preview if confusion_preview else '- Chua co artifact confusion/PR trong pack chapter5 hien tai.'}

## I.5. Recall theo big_label

Bang `I_big_label_recall.csv` ghi recall theo `big_label`, gom:

- `support`
- `tp`
- `fn`
- `recall`
- `support_bucket`

Khuyen nghi chi rut ket luan chinh tren cac nhom co `support >= 3`, va chat hon nua la `support >= 5`.

## I.6. Best-test exploratory

Bang `I_best_test_exploratory.csv` giu ket qua best-test theo tung version de phan tich bo sung, nhung khong thay the main result.

| Arm | Version | Experiment | Model | Test macro-F1 |
|---|---|---|---|---:|
{exploratory_preview}

## Tep CSV di kem

- `I_direct_full_results.csv`
- `I_pretrain_full_results.csv`
- `I_validation_test_gap.csv`
- `I_best_test_exploratory.csv`
- `I_big_label_recall.csv`
- `I_confusion_artifact_index.csv`
"""


def main() -> None:
    run_map = discover_runs()
    subgroup_dir = latest_chapter5_dir("-subgroup-benchmark")
    abnormal_summary_rows = load_csv(subgroup_dir / "abnormal_model_summary.csv")
    abnormal_big_label_rows = load_csv(subgroup_dir / "abnormal_big_label_recall.csv")

    direct_rows, direct_split_rows, direct_exploratory = flatten_direct_results(run_map["direct"].run_dir)
    pretrain_rows, pretrain_split_rows, pretrain_exploratory, source_rows = flatten_pretrain_results(run_map)

    direct_rows = append_abnormal_metrics(direct_rows, abnormal_summary_rows, "direct")
    pretrain_rows = append_abnormal_metrics(pretrain_rows, abnormal_summary_rows, "pretrain")

    split_rows = sorted(
        direct_split_rows + pretrain_split_rows,
        key=lambda row: (row["benchmark_arm"], row["version"], row["experiment"]),
    )
    gap_rows = sorted(
        direct_rows + pretrain_rows,
        key=lambda row: (row["benchmark_arm"], row["version"], row["experiment"], row["model"]),
    )
    exploratory_rows = sorted(
        direct_exploratory + pretrain_exploratory,
        key=lambda row: (row["benchmark_arm"], row["version"], row["experiment"]),
    )
    confusion_index_rows = build_confusion_index()
    model_config_rows = build_model_config_rows()

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    write_csv(
        OUTPUT_ROOT / "H_model_config.csv",
        model_config_rows,
        ["model", "scope", "main_parameters", "seed", "implemented_in_final_suite", "notes"],
    )
    write_csv(
        OUTPUT_ROOT / "H_split_counts.csv",
        split_rows,
        [
            "benchmark_arm",
            "version",
            "experiment",
            "input_rows",
            "train_rows",
            "validation_rows",
            "test_rows",
            "excluded_gap_rows",
            "split_strategy",
            "gap_minutes",
            "selected_model",
            "selected_validation_macro_f1",
        ],
    )
    write_csv(
        OUTPUT_ROOT / "H_pretrain_source_config.csv",
        sorted(source_rows, key=lambda row: (row["version"], row["experiment"])),
        [
            "version",
            "experiment",
            "source_kind",
            "feature_count",
            "feature_columns",
            "required_columns",
            "mask_ratio",
            "pretrain_epochs",
            "pretrain_lr",
            "pretrain_seed",
        ],
    )
    write_csv(
        OUTPUT_ROOT / "I_direct_full_results.csv",
        sorted(direct_rows, key=lambda row: (row["version"], row["experiment"], row["model"])),
        [
            "benchmark_arm",
            "version",
            "experiment",
            "feature_set",
            "model",
            "validation_macro_f1",
            "test_macro_f1",
            "validation_balanced_accuracy",
            "test_balanced_accuracy",
            "abnormal_precision",
            "abnormal_recall",
            "abnormal_f1",
            "subgroup_macro_recall_support_ge_3",
            "validation_test_gap_macro_f1",
            "notes",
            "artifact_path",
        ],
    )
    write_csv(
        OUTPUT_ROOT / "I_pretrain_full_results.csv",
        sorted(pretrain_rows, key=lambda row: (row["version"], row["experiment"], row["model"])),
        [
            "benchmark_arm",
            "version",
            "experiment",
            "feature_set",
            "model",
            "validation_macro_f1",
            "test_macro_f1",
            "validation_balanced_accuracy",
            "test_balanced_accuracy",
            "abnormal_precision",
            "abnormal_recall",
            "abnormal_f1",
            "subgroup_macro_recall_support_ge_3",
            "validation_test_gap_macro_f1",
            "notes",
            "artifact_path",
            "checkpoint_path",
        ],
    )
    write_csv(
        OUTPUT_ROOT / "I_validation_test_gap.csv",
        gap_rows,
        [
            "benchmark_arm",
            "version",
            "experiment",
            "model",
            "validation_macro_f1",
            "test_macro_f1",
            "validation_test_gap_macro_f1",
            "validation_balanced_accuracy",
            "test_balanced_accuracy",
        ],
    )
    write_csv(
        OUTPUT_ROOT / "I_best_test_exploratory.csv",
        exploratory_rows,
        [
            "selection_role",
            "benchmark_arm",
            "version",
            "experiment",
            "feature_set",
            "model",
            "validation_macro_f1",
            "test_macro_f1",
            "validation_balanced_accuracy",
            "test_balanced_accuracy",
            "abnormal_precision",
            "abnormal_recall",
            "abnormal_f1",
            "subgroup_macro_recall_support_ge_3",
            "validation_test_gap_macro_f1",
            "notes",
            "artifact_path",
        ],
    )
    write_csv(
        OUTPUT_ROOT / "I_big_label_recall.csv",
        sorted(abnormal_big_label_rows, key=lambda row: (row["benchmark_arm"], row["benchmark_version"], row["experiment_name"], row["model_name"], row["group_value"])),
        [
            "benchmark_arm",
            "benchmark_version",
            "experiment_name",
            "model_name",
            "group_value",
            "support",
            "tp",
            "fn",
            "recall",
            "is_main_support",
            "is_strict_support",
            "support_bucket",
        ],
    )
    write_csv(
        OUTPUT_ROOT / "I_confusion_artifact_index.csv",
        confusion_index_rows,
        ["artifact_type", "path", "source_pack", "notes"],
    )

    write_text(OUTPUT_ROOT / "appendix_H_protocol_vi.md", render_appendix_h(model_config_rows, split_rows, source_rows))
    write_text(OUTPUT_ROOT / "appendix_I_results_vi.md", render_appendix_i(direct_rows, pretrain_rows, gap_rows, exploratory_rows, confusion_index_rows))


if __name__ == "__main__":
    main()
