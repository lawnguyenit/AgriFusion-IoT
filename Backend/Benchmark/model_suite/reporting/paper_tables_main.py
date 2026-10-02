from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pandas as pd

from .paper_tables import build_paper_agri_table, build_paper_stuard_table, build_paper_uci_table


def _read_bytes(archive: zipfile.ZipFile, path: str) -> bytes:
    try:
        return archive.read(path)
    except KeyError as error:
        raise ValueError(f"Reproducibility bundle is missing {path!r}.") from error


def _verify_bundle(archive: zipfile.ZipFile) -> None:
    manifest = json.loads(_read_bytes(archive, "package_manifest.json"))
    expected = {str(row["path"]): row for row in manifest["files"]}
    actual = set(archive.namelist()) - {"package_manifest.json"}
    if actual != set(expected):
        missing = sorted(set(expected) - actual)
        unexpected = sorted(actual - set(expected))
        raise ValueError(f"Bundle file inventory mismatch; missing={missing}, unexpected={unexpected}.")
    for path, row in expected.items():
        payload = _read_bytes(archive, path)
        digest = hashlib.sha256(payload).hexdigest()
        if len(payload) != int(row["size_bytes"]) or digest != row["sha256"]:
            raise ValueError(f"Bundle integrity check failed for {path!r}.")


def _read_csv(archive: zipfile.ZipFile, path: str) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(_read_bytes(archive, path)))


def _read_parquet(archive: zipfile.ZipFile, path: str) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(_read_bytes(archive, path)))


def _markdown_table(frame: pd.DataFrame, columns: list[str], formats: dict[str, str]) -> str:
    visible = frame.loc[:, columns]
    headers = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    rows = []
    for _, row in visible.iterrows():
        values = []
        for column in columns:
            value = row[column]
            if pd.isna(value):
                rendered = "–"
            elif column in formats:
                rendered = format(float(value), formats[column])
            else:
                rendered = str(value)
            values.append(rendered)
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join([headers, separator, *rows])


def build_paper_tables(bundle_path: Path, output_dir: Path) -> None:
    with zipfile.ZipFile(bundle_path) as archive:
        _verify_bundle(archive)
        root = "datasets/agri_fusion/rq1_structured_run/"
        agri = build_paper_agri_table(
            _read_parquet(archive, root + "primary_heldout_predictions.parquet"),
            _read_parquet(archive, root + "primary_per_anchor_losses.parquet"),
            json.loads(_read_bytes(archive, root + "feature_contract.json")),
        )
        uci = build_paper_uci_table(_read_csv(archive, "metrics_summary.csv"))
        stuard = build_paper_stuard_table(
            _read_csv(archive, "datasets/stuard/acquisition_controls/control_metrics.csv"),
            _read_csv(archive, "datasets/stuard/acquisition_controls/control_contrasts.csv"),
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    agri.to_csv(output_dir / "table-2-agrifusion.csv", index=False)
    uci.to_csv(output_dir / "table-3-uci.csv", index=False)
    stuard.to_csv(output_dir / "table-4-stuard.csv", index=False)
    markdown = "\n".join(
        [
            "# Frozen paper tables",
            "",
            "## Table 2. AgriFusion online target",
            "",
            _markdown_table(
                agri,
                ["representation", "features", "log_loss", "macro_f1_mean_across_folds"],
                {"log_loss": ".4f", "macro_f1_mean_across_folds": ".4f"},
            ),
            "",
            "Log-loss is pooled across the frozen held-out anchors; macro-F1 is the unweighted mean across the three temporal folds.",
            "",
            "## Table 3. UCI test results",
            "",
            _markdown_table(
                uci,
                ["head", "prevalence", "balanced_accuracy", "roc_auc", "average_precision", "log_loss"],
                {column: ".3f" for column in ["prevalence", "balanced_accuracy", "roc_auc", "average_precision", "log_loss"]},
            ),
            "",
            "## Table 4. Stuard nested test controls",
            "",
            _markdown_table(
                stuard,
                ["arm", "log_loss", "delta_log_loss_vs_base", "ci_low", "ci_high"],
                {column: ".3f" for column in ["log_loss", "delta_log_loss_vs_base", "ci_low", "ci_high"]},
            ),
            "",
            "The reported contrasts and intervals use the persisted 1,000-repetition UTC-day bootstrap outputs. No model is fit by this command.",
            "",
        ]
    )
    (output_dir / "tables-2-to-4.md").write_text(markdown, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild WADE paper Tables 2–4 from the frozen result bundle.")
    parser.add_argument("--bundle", type=Path, required=True, help="Path to the paper reproducibility ZIP.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for regenerated CSV and Markdown tables.")
    args = parser.parse_args()
    build_paper_tables(args.bundle.resolve(), args.output_dir.resolve())
    print(f"Paper tables written to {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
