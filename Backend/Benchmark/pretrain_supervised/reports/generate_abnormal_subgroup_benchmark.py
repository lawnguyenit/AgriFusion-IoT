from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

REPORTS_DIR = Path(__file__).resolve().parent
if str(REPORTS_DIR) not in sys.path:
    sys.path.insert(0, str(REPORTS_DIR))

import generate_chapter5_evidence as chapter5
from Backend.Benchmark.common.paths import TABULAR_BENCHMARK_ROOT, PRETRAIN_SUPERVISED_ROOT

ROOT_DIR = Path(__file__).resolve().parents[4]
PRETRAIN_ROOT = PRETRAIN_SUPERVISED_ROOT
DIRECT_ROOT = TABULAR_BENCHMARK_ROOT
OUTPUT_ROOT = PRETRAIN_SUPERVISED_ROOT / "chapter5_evidence"


@dataclass(frozen=True)
class BenchmarkContext:
    benchmark_version: str
    experiment_name: str
    run_context: chapter5.RunContext


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark trained direct/pretrain models on decomposed abnormal subgroups."
    )
    parser.add_argument(
        "--direct-run-dir",
        type=Path,
        default=None,
        help="Optional tabular benchmark run directory. Defaults to latest run under tabular_benchmark/outputs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional output directory. Defaults to chapter5_evidence/<YYYY-MM-DD>-subgroup-benchmark.",
    )
    parser.add_argument(
        "--support-threshold",
        type=int,
        default=3,
        help="Primary support threshold for main-table abnormal subgroup reporting.",
    )
    parser.add_argument(
        "--strict-support-threshold",
        type=int,
        default=5,
        help="Stricter support threshold for more conservative reporting.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite output directory if it already exists.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir or (OUTPUT_ROOT / f"{date.today():%Y-%m-%d}-subgroup-benchmark")
    if output_dir.exists() and not args.force:
        raise FileExistsError(f"{output_dir} already exists. Pass --force to overwrite.")
    output_dir.mkdir(parents=True, exist_ok=True)

    contexts = collect_contexts(args.direct_run_dir)

    subgroup_big_rows: list[dict[str, Any]] = []
    subgroup_event_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    for benchmark_context in contexts:
        report = benchmark_context.run_context.report
        for model_row in report["models"]:
            if not bool(model_row.get("available", False)):
                continue
            model_name = str(model_row["model_name"])
            evaluation = chapter5.evaluate_model_on_test(
                benchmark_context.run_context,
                model_name=model_name,
                role="all_models",
            )
            prediction_frame = pd.DataFrame(evaluation["predictions"])
            big_frame = build_subgroup_frame(
                benchmark_context=benchmark_context,
                prediction_frame=prediction_frame,
                model_name=model_name,
                grouping_column="big_label",
                support_threshold=args.support_threshold,
                strict_support_threshold=args.strict_support_threshold,
            )
            event_frame = build_subgroup_frame(
                benchmark_context=benchmark_context,
                prediction_frame=prediction_frame,
                model_name=model_name,
                grouping_column="event_primary",
                support_threshold=args.support_threshold,
                strict_support_threshold=args.strict_support_threshold,
            )
            subgroup_big_rows.extend(big_frame.to_dict(orient="records"))
            subgroup_event_rows.extend(event_frame.to_dict(orient="records"))
            summary_rows.append(
                build_summary_row(
                    benchmark_context=benchmark_context,
                    evaluation_summary=evaluation["summary"],
                    big_label_frame=big_frame,
                    support_threshold=args.support_threshold,
                    strict_support_threshold=args.strict_support_threshold,
                )
            )

    big_frame = pd.DataFrame(subgroup_big_rows)
    event_frame = pd.DataFrame(subgroup_event_rows)
    summary_frame = pd.DataFrame(summary_rows).sort_values(
        by=["main_supported_group_count", "macro_recall_main_threshold", "overall_abnormal_recall"],
        ascending=[False, False, False],
    )

    big_frame.to_csv(output_dir / "abnormal_big_label_recall.csv", index=False)
    event_frame.to_csv(output_dir / "abnormal_event_primary_recall.csv", index=False)
    summary_frame.to_csv(output_dir / "abnormal_model_summary.csv", index=False)

    chapter5.write_markdown(
        output_dir / "subgroup_benchmark_vi.md",
        build_markdown_report(
            summary_frame=summary_frame,
            big_frame=big_frame,
            support_threshold=args.support_threshold,
            strict_support_threshold=args.strict_support_threshold,
        ),
    )
    chapter5.write_json(
        output_dir / "manifest.json",
        {
            "generated_on": f"{date.today():%Y-%m-%d}",
            "support_threshold": args.support_threshold,
            "strict_support_threshold": args.strict_support_threshold,
            "direct_run_dir": str(args.direct_run_dir) if args.direct_run_dir else None,
            "context_count": len(contexts),
            "files": [
                "abnormal_big_label_recall.csv",
                "abnormal_event_primary_recall.csv",
                "abnormal_model_summary.csv",
                "subgroup_benchmark_vi.md",
            ],
        },
    )


def collect_contexts(direct_run_dir: Path | None) -> list[BenchmarkContext]:
    contexts: list[BenchmarkContext] = []

    resolved_direct_run = direct_run_dir or chapter5.find_latest_leaf_run(DIRECT_ROOT / "outputs")
    for experiment_dir in sorted((resolved_direct_run / "experiments").iterdir()):
        if not experiment_dir.is_dir():
            continue
        experiment_name = experiment_dir.name
        contexts.append(
            BenchmarkContext(
                benchmark_version="direct",
                experiment_name=experiment_name,
                run_context=chapter5.build_direct_context(resolved_direct_run, experiment_name),
            )
        )

    for version_name in ["v0", "v1", "v2", "v3", "v4"]:
        run_dir = chapter5.find_latest_leaf_run(PRETRAIN_ROOT / version_name / "outputs")
        if version_name == "v1":
            contexts.append(
                BenchmarkContext(
                    benchmark_version="v1",
                    experiment_name="v1",
                    run_context=chapter5.build_pretrain_context(run_dir),
                )
            )
            continue

        experiments_dir = run_dir / "experiments"
        for experiment_dir in sorted(experiments_dir.iterdir()):
            if not experiment_dir.is_dir():
                continue
            report = chapter5.load_json(experiment_dir / "training_report.json")
            feature_columns = [str(column) for column in report["embedding_columns"]]
            scaled_feature_columns = [f"scaled_{column}" for column in feature_columns]
            class_names = [str(name) for name in report["label_policy"]["class_names"]]
            contexts.append(
                BenchmarkContext(
                    benchmark_version=version_name,
                    experiment_name=experiment_dir.name,
                    run_context=chapter5.RunContext(
                        arm="pretrain",
                        label=f"{version_name}::{experiment_dir.name}",
                        run_dir=run_dir,
                        experiment_dir=experiment_dir,
                        report=report,
                        dataset_path=experiment_dir / "embedding_dataset.csv",
                        split_column="embedding_split",
                        feature_columns=feature_columns,
                        scaled_feature_columns=scaled_feature_columns,
                        label_column="selected_label_id",
                        class_names=class_names,
                    ),
                )
            )
    return contexts


def build_subgroup_frame(
    benchmark_context: BenchmarkContext,
    prediction_frame: pd.DataFrame,
    model_name: str,
    grouping_column: str,
    support_threshold: int,
    strict_support_threshold: int,
) -> pd.DataFrame:
    abnormal_frame = prediction_frame.loc[prediction_frame["true_label_name"] == "abnormal"].copy()
    if abnormal_frame.empty:
        return pd.DataFrame()
    grouped = (
        abnormal_frame.groupby(grouping_column, dropna=False)
        .agg(
            support=(grouping_column, "size"),
            tp=("pred_label_name", lambda values: int((values == "abnormal").sum())),
            fn=("pred_label_name", lambda values: int((values == "normal").sum())),
        )
        .reset_index()
    )
    grouped["group_value"] = grouped[grouping_column].fillna("missing")
    grouped["recall"] = grouped["tp"] / grouped["support"]
    grouped["benchmark_arm"] = benchmark_context.run_context.arm
    grouped["benchmark_version"] = benchmark_context.benchmark_version
    grouped["experiment_name"] = benchmark_context.experiment_name
    grouped["model_name"] = model_name
    grouped["grouping_column"] = grouping_column
    grouped["is_main_support"] = grouped["support"] >= support_threshold
    grouped["is_strict_support"] = grouped["support"] >= strict_support_threshold
    grouped["support_bucket"] = grouped["support"].map(
        lambda value: (
            f">={strict_support_threshold}"
            if value >= strict_support_threshold
            else f">={support_threshold}"
            if value >= support_threshold
            else f"<{support_threshold}"
        )
    )
    return grouped[
        [
            "benchmark_arm",
            "benchmark_version",
            "experiment_name",
            "model_name",
            "grouping_column",
            "group_value",
            "support",
            "tp",
            "fn",
            "recall",
            "is_main_support",
            "is_strict_support",
            "support_bucket",
        ]
    ]


def build_summary_row(
    benchmark_context: BenchmarkContext,
    evaluation_summary: dict[str, Any],
    big_label_frame: pd.DataFrame,
    support_threshold: int,
    strict_support_threshold: int,
) -> dict[str, Any]:
    main_frame = big_label_frame.loc[big_label_frame["support"] >= support_threshold].copy()
    strict_frame = big_label_frame.loc[big_label_frame["support"] >= strict_support_threshold].copy()
    return {
        "benchmark_arm": benchmark_context.run_context.arm,
        "benchmark_version": benchmark_context.benchmark_version,
        "experiment_name": benchmark_context.experiment_name,
        "model_name": evaluation_summary["model_name"],
        "overall_test_macro_f1": float(evaluation_summary["test_macro_f1"]),
        "overall_abnormal_precision": float(evaluation_summary["abnormal_precision"]),
        "overall_abnormal_recall": float(evaluation_summary["abnormal_recall"]),
        "overall_abnormal_f1": float(evaluation_summary["abnormal_f1"]),
        "overall_abnormal_support": int(evaluation_summary["abnormal_support"]),
        "main_supported_group_count": int(len(main_frame)),
        "strict_supported_group_count": int(len(strict_frame)),
        "macro_recall_main_threshold": float(main_frame["recall"].mean()) if not main_frame.empty else float("nan"),
        "macro_recall_strict_threshold": float(strict_frame["recall"].mean()) if not strict_frame.empty else float("nan"),
        "unsupported_group_count": int((big_label_frame["support"] < support_threshold).sum()),
    }


def build_markdown_report(
    summary_frame: pd.DataFrame,
    big_frame: pd.DataFrame,
    support_threshold: int,
    strict_support_threshold: int,
) -> str:
    main_big = big_frame.loc[big_frame["support"] >= support_threshold].copy()
    low_support = big_frame.loc[big_frame["support"] < support_threshold].copy()
    lines = [
        "# Abnormal Subgroup Benchmark",
        "",
        f"- Main support threshold: `support >= {support_threshold}`",
        f"- Strict support threshold: `support >= {strict_support_threshold}`",
        "",
        "## Model summary",
        "",
        chapter5.dataframe_to_markdown(summary_frame),
        "",
        "## Big-label recall (main threshold)",
        "",
        chapter5.dataframe_to_markdown(main_big),
        "",
        "## Big-label recall (low support / exploratory only)",
        "",
        chapter5.dataframe_to_markdown(low_support),
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
