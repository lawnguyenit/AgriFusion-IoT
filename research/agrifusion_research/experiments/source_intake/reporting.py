from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


def write_intake_artifact(
    *,
    output_root: Path,
    source_path: Path,
    old_canonical_path: Path,
    source: pd.DataFrame,
    candidate: pd.DataFrame,
    legacy_projection: pd.DataFrame,
    auxiliary: pd.DataFrame,
    segment_manifest: dict[str, object],
    summary: dict[str, Any],
    details: dict[str, pd.DataFrame],
) -> tuple[str, Path, Path]:
    run_id = "new_firebase_csv_audit_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = output_root.resolve() / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=False)

    candidate_path = output_dir / "canonical_candidate.csv"
    legacy_path = output_dir / "canonical_legacy_compatible.csv"
    auxiliary_path = output_dir / "source_auxiliary.csv"
    segment_manifest_path = output_dir / "segments_manifest.json"
    candidate_layer1_manifest_path = output_dir / "candidate_layer1_manifest.json"
    candidate.to_csv(candidate_path, index=False)
    legacy_projection.to_csv(legacy_path, index=False)
    auxiliary.to_csv(auxiliary_path, index=False)
    segment_manifest_path.write_text(
        json.dumps(segment_manifest, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )
    candidate_layer1_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "pipeline": "layer1_flattened_csv_candidate",
                "processed_source_records": int(len(candidate)),
                "canonical_record_count": int(len(candidate)),
                "output_paths": {
                    "canonical_history_path": str(candidate_path.resolve()),
                    "segment_manifest_path": str(segment_manifest_path.resolve()),
                },
                "warnings": [
                    "Candidate is additive and was not promoted to Backend/Output_data/Layer1.",
                    "Feature catalog remains the existing Layer1 catalog until source promotion is approved.",
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    detail_paths: dict[str, str] = {}
    for name, frame in details.items():
        path = tables_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        detail_paths[name] = str(path.resolve())

    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": {
            "path": str(source_path.resolve()),
            "sha256": sha256(source_path),
            "rows": int(len(source)),
            "columns": [column for column in source.columns if column != "record.id"],
        },
        "old_canonical": {
            "path": str(old_canonical_path.resolve()),
            "sha256": sha256(old_canonical_path),
            "rows": int(summary["old_rows"]),
        },
        "outputs": {
            "canonical_candidate": str(candidate_path.resolve()),
            "canonical_legacy_compatible": str(legacy_path.resolve()),
            "source_auxiliary": str(auxiliary_path.resolve()),
            "segments_manifest": str(segment_manifest_path.resolve()),
            "candidate_layer1_manifest": str(candidate_layer1_manifest_path.resolve()),
            "tables": detail_paths,
        },
        "summary": summary,
        "promotion_status": "not_promoted",
        "promotion_note": "Candidate is additive; existing Layer1 canonical history was not modified.",
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=_json_default), encoding="utf-8")

    report_path = output_dir / "report.md"
    report_path.write_text(_render_report(manifest, summary, candidate_path, legacy_path, auxiliary_path), encoding="utf-8")
    return run_id, output_dir, report_path


def _render_report(
    manifest: dict[str, Any],
    summary: dict[str, Any],
    candidate_path: Path,
    legacy_path: Path,
    auxiliary_path: Path,
) -> str:
    comparisons_path = Path(manifest["outputs"]["tables"]["value_comparison"])
    comparison = pd.read_csv(comparisons_path)
    exact_all = bool((comparison["mismatch_rows"] == 0).all())
    source_all_null = ", ".join(summary["source_all_null_columns"]) or "none"
    max_gap_start = summary.get("largest_gap_start_local") or "unknown"
    max_gap_end = summary.get("largest_gap_end_local") or "unknown"
    max_sensorless_start = summary.get("sensorless_run_max_start_local") or "unknown"
    max_sensorless_end = summary.get("sensorless_run_max_end_local") or "unknown"
    max_sensorless_rows_start = summary.get("sensorless_run_max_rows_start_local") or "unknown"
    max_sensorless_rows_end = summary.get("sensorless_run_max_rows_end_local") or "unknown"
    max_replay_delay_days = float(summary.get("replay_delay_proxy_max_sec", 0.0)) / 86400.0
    return f"""# New Firebase CSV intake audit

## Decision summary

The new export is structurally compatible as an additive canonical candidate,
but it should not replace the old source automatically. All {summary['shared_key_count']:,}
old record identities are present and checked sensor values are exact; the
important change is the additional {summary['new_only_key_count']:,} rows and
their replay/buffer provenance.

## Source and overlap

| Item | Value |
|---|---:|
| New source rows | {summary['source_rows']:,} |
| Candidate rows | {summary['candidate_rows']:,} |
| Old canonical rows | {summary['old_rows']:,} |
| Shared record IDs | {summary['shared_key_count']:,} |
| New-only record IDs | {summary['new_only_key_count']:,} |
| Old-only record IDs | {summary['old_only_key_count']:,} |
| New coverage | {summary['source_date_min']} → {summary['source_date_max']} |
| Old coverage | {summary['old_date_min']} → {summary['old_date_max']} |
| Shared-value mismatches | {int(comparison['mismatch_rows'].sum())} |

## Data-quality findings

- Buffered/replayed rows: **{summary['buffered_or_replayed_rows']:,}**.
- Rows with all six core sensor values missing: **{summary['all_core_sensor_missing_rows']:,}**.
- Replayed rows that still contain at least one sensor value: **{summary['replayed_rows_with_any_sensor_value']:,}**.
- Duplicate sample timestamps: **{summary['source_duplicate_ts_sample_rows']:,} rows** across
  {summary['source_duplicate_ts_sample_values']:,} timestamp values; event IDs remain unique.
- Rows with any missing status flag: **{summary['rows_with_any_missing_status_flag']:,}**.
- Recomputed `delta_min` mismatches: **{summary['delta_recompute_mismatch_rows']:,}**;
  maximum absolute difference is `{summary['delta_recompute_max_abs_diff_min']}` minutes.
- Range anomalies for moisture/RH/pH: **{summary['out_of_range_rows']:,}**.
- Sample-timeline gap episodes above 30 minutes: **{summary['gap_event_count_gt_30m']:,}**;
  above 60 minutes: **{summary['gap_event_count_gt_60m']:,}**. The largest gap is
  **{summary['gap_event_max_minutes']:,.2f} minutes** ({max_gap_start} → {max_gap_end}).
- Gap recovery classes: **{summary['gap_into_direct_sensorful_count']:,}** into direct
  sensorful rows, **{summary['gap_into_replay_sensorful_count']:,}** into replay sensorful
  rows, **{summary['gap_into_replay_sensorless_count']:,}** into replay sensorless rows,
  and **{summary['gap_into_direct_sensorless_count']:,}** into direct sensorless rows.
- Sensorless runs: **{summary['sensorless_run_count']:,}** total; **{summary['sensorless_run_gt_6h']:,}**
  exceed 6 hours and **{summary['sensorless_run_gt_24h']:,}** exceed 24 hours. The longest
  consecutive sensorless run spans **{summary['sensorless_run_max_minutes']:,.2f} minutes**
  ({max_sensorless_start} → {max_sensorless_end}); the densest run contains
  **{summary['sensorless_run_max_rows']:,} rows** ({max_sensorless_rows_start} →
  {max_sensorless_rows_end}, spanning {summary['sensorless_run_max_rows_span_minutes']:,.2f} minutes).
- The `event_key - ts_sample` value is reported only as a **replay-delay proxy** because
  the flat export has no authoritative server/upload timestamp: **{summary['replay_delay_proxy_gt_120_sec']:,}**
  replay/buffered rows exceed 2 minutes, **{summary['replay_delay_proxy_gt_1h']:,}** exceed 1 hour,
  and **{summary['replay_delay_proxy_gt_1d']:,}** exceed 1 day (maximum proxy
  **{summary['replay_delay_proxy_max_sec']:,.0f} seconds ≈ {max_replay_delay_days:,.2f} days).
- Median observed cadence is **{summary['direct_median_interval_sec']} seconds** for direct rows versus
  **{summary['replay_median_interval_sec']} seconds** for buffered/replayed rows; these are
  distinct transport/cadence regimes and should not be silently merged.
- The flat source has no `ts_server`/upload timestamp. The candidate therefore
  leaves `record.ts_server`, `record.upload_time_local`, and derived upload
  delay unknown; `event_key` is retained only as identity.
- Entirely empty source columns: {source_all_null}.

The missing-sensor rows are retained in the candidate for continuity and
delivery audit purposes. The dataset-view validity masks should exclude their
measurements from sensor features; this must be verified before training.
Do not delete gap rows before temporal processing: doing so can make two far
apart observations look adjacent. Instead, use the gap-event and sensorless-run
sidecars to gate or flag benchmark anchors/windows whose history crosses an
insufficient-coverage episode.

## Shared-value comparison

All checked channel comparisons are exact: **{exact_all}**. See
`tables/value_comparison.csv` for per-channel supports and null asymmetries.

## Generated artifacts

- Current-schema candidate: `{candidate_path}`
- Exact old-column projection: `{legacy_path}`
- Source-only provenance sidecar: `{auxiliary_path}`
- Candidate segment cadence sidecar: `{manifest['outputs']['segments_manifest']}`
- Candidate Layer1 manifest for opt-in view validation: `{manifest['outputs']['candidate_layer1_manifest']}`
- Gap episodes above 30 minutes: `{manifest['outputs']['tables']['gap_events']}`
- Sensorless runs: `{manifest['outputs']['tables']['sensorless_runs']}`
- Replay-delay proxy rows: `{manifest['outputs']['tables']['replay_delay']}`
- Full machine-readable manifest: `{manifest['outputs']['tables'] and Path(manifest['outputs']['tables']['value_comparison']).parent.parent / 'manifest.json'}`

## Promotion recommendation

Keep the old canonical source as the benchmark baseline. Treat this run as a
candidate extension and make the next decision explicitly:

1. append/replace the canonical source only after deciding how replayed
   sensorless rows and gap-crossing windows are handled;
2. regenerate labels for the extended time range rather than reusing the old
   label release blindly; and
3. retain all source rows for provenance, but train/evaluate only after an
   explicit continuity/coverage gate is applied to each history window; and
4. rerun dataset views and the benchmark only after source promotion and the
   gap policy are approved.
"""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Cannot JSON encode {type(value).__name__}")
