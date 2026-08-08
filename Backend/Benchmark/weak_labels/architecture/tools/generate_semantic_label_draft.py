"""Generate an implementation-grounded draft of the native label semantics.

This is a reporting tool, not a second label engine.  It reads the frozen
Phase-B contract and a published Phase-C release, validates their core
commitments, and writes a Markdown explanation plus a Mermaid diagram and a
machine-readable summary.  Re-running it against another release preserves
the same provenance/lineage checks without changing label authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

ROOT_DIR = Path(__file__).resolve().parents[5]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from Backend.Benchmark.common.paths import WEAK_LABELS_ROOT
from Backend.Benchmark.dataset_views.configs.feature_arms import FULL_9_FEATURES


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping YAML payload: {path}")
    return payload


def _one_row(frame: pd.DataFrame, key: str, value: str) -> pd.Series:
    rows = frame.loc[frame[key].astype("string") == value]
    if len(rows) != 1:
        raise ValueError(f"Expected one {key}={value!r} row, found {len(rows)}")
    return rows.iloc[0]


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, default=str)


def build_semantic_draft(*, contract_dir: Path, release_dir: Path, output_dir: Path) -> Path:
    contract_dir = contract_dir.resolve()
    release_dir = release_dir.resolve()
    output_dir = output_dir.resolve()
    freeze = _read_yaml(contract_dir / "phase_b_freeze.yaml")
    ontology = _read_yaml(contract_dir / "ontology" / "point_ontology.yaml")
    resolution = _read_yaml(contract_dir / "resolution" / "point_resolution_contract.yaml")
    strict = _read_yaml(contract_dir / "continuity" / "strict_continuity_contract.yaml")
    window = _read_yaml(contract_dir / "continuity" / "window_continuity_contract.yaml")
    q_registry = pd.read_csv(contract_dir / "operationalization" / "q_operationalization_registry.csv")
    op_registry = pd.read_csv(contract_dir / "operationalization" / "operationalization_registry.csv")
    derived_registry = pd.read_csv(contract_dir / "evidence" / "derived_evidence_contract_registry.csv")
    threshold_registry = pd.read_csv(contract_dir / "thresholds" / "frozen_threshold_registry.csv")

    release_manifest_path = release_dir / "run_metadata" / "label_release_manifest.json"
    release_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
    point_path = release_dir / "tasks" / "point" / "assignments.parquet"
    rule_path = release_dir / "audit" / "rule_firings.parquet"
    resolution_path = release_dir / "audit" / "resolutions.parquet"
    assignment_path = release_dir / "audit" / "assignments.parquet"
    point = pd.read_parquet(point_path).convert_dtypes()
    rule_firings = pd.read_parquet(rule_path).convert_dtypes()
    resolutions = pd.read_parquet(resolution_path).convert_dtypes()
    assignments = pd.read_parquet(assignment_path).convert_dtypes()

    primary_id = str(freeze["primary_operationalization_id"])
    primary_op = _one_row(op_registry, "operationalization_id", primary_id)
    q_id = str(primary_op["q_contract_id"])
    q_row = _one_row(q_registry, "q_contract_id", q_id)
    threshold_ids = {
        "low": "LOW_MOISTURE_Q10_E1_DISCOVERY_CANDIDATE",
        "vpd": "THERMAL_VPD_FIXED_2_5_REFERENCE",
        "moisture_rise": "MOISTURE_RISE_FIXED_5PP_REFERENCE",
        "ec_shift": "EC_SHIFT_Q95_E1_DISCOVERY_CANDIDATE",
    }
    thresholds: dict[str, dict[str, object]] = {}
    for role, threshold_id in threshold_ids.items():
        row = _one_row(threshold_registry, "threshold_id", threshold_id)
        thresholds[role] = {
            "threshold_id": threshold_id,
            "value": row["threshold_value"],
            "unit": row["threshold_unit"],
            "comparator": row["comparator"],
        }

    expected_labels = {
        "reference": "reference_context_point",
        "low": "low_relative_moisture_point",
        "unresolved": "unresolved_environmental_evidence_point",
        "context_incomplete": "point_context_incomplete",
        "not_evaluable": "point_not_evaluable",
    }
    observed_label_counts = {
        str(key): int(value)
        for key, value in point["label_name"].astype("string").value_counts(dropna=False).items()
    }
    missing_labels = sorted(set(expected_labels.values()) - set(observed_label_counts))
    if missing_labels:
        raise ValueError(f"Published point release is missing expected label names: {missing_labels}")

    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "generated_at_utc": generated_at,
        "contract_dir": str(contract_dir),
        "release_dir": str(release_dir),
        "contract_hash": str(freeze["semantic_contract_hash"]),
        "semantic_contract_id": str(freeze["semantic_contract_id"]),
        "primary_operationalization_id": primary_id,
        "primary_q": q_id,
        "primary_q_threshold": float(q_row["threshold_value"]),
        "primary_k": int(primary_op["selected_k"]),
        "full_9_sensor_features": list(FULL_9_FEATURES),
        "derived_evidence": derived_registry.to_dict(orient="records"),
        "thresholds": thresholds,
        "point_label_counts": observed_label_counts,
        "rule_firing_counts": {
            str(key): int(value)
            for key, value in rule_firings["rule_id"].astype("string").value_counts(dropna=False).items()
        },
        "point_resolution_counts": {
            str(key): int(value)
            for key, value in resolutions.loc[resolutions["task_id"].astype("string") == "POINT", "resolution_code"].astype("string").value_counts(dropna=False).items()
        },
        "assignment_label_counts": {
            str(key): int(value)
            for key, value in assignments.loc[assignments["task_id"].astype("string") == "POINT", "label"].astype("string").value_counts(dropna=False).items()
        },
        "release_manifest_sha256": _sha256(release_manifest_path),
        "point_assignment_sha256": _sha256(point_path),
        "rule_firing_sha256": _sha256(rule_path),
        "resolution_sha256": _sha256(resolution_path),
        "assignment_sha256": _sha256(assignment_path),
    }
    (output_dir / "semantic_label_summary.json").write_text(_json(summary), encoding="utf-8")

    mmd = f'''flowchart TD
    subgraph INPUT["Input: authorized current E1 record + admissible past context"]
        S["Available canonical sensor values<br/>air T/RH, soil T/moisture, EC, pH, N/P/K proxy"]
        G["Technical / applicability context<br/>canonical validity, timestamp integrity,<br/>deployment/segment, strict predecessor"]
        C["Frozen semantic contract<br/>Q10={float(q_row['threshold_value']):g}; K={int(primary_op['selected_k'])};<br/>VPD=2.5 kPa; rise=5 pp; EC shift=6"]
    end

    S --> V["Canonical validation + applicability + continuity"]
    G --> V
    V --> D["Derived evidence<br/>VPD(T,RH)<br/>moisture rise=current-strict previous<br/>EC shift=abs(current-strict previous)"]
    V --> R["Primitive rule evaluation"]
    S --> R
    D --> R
    C --> R
    R --> RF["RuleFiring<br/>LOW_RELATIVE_MOISTURE<br/>THERMAL_CONTEXT<br/>MOISTURE_RISE<br/>EC_SHIFT"]

    RF --> PR["Point Resolution"]
    C --> PR
    PR -->|resolved| PA["Point Assignment Y_point<br/>REFERENCE<br/>LOW<br/>UNRESOLVED_ENVIRONMENTAL"]
    PR -->|not evaluable / incomplete| EX["Intrinsic technical status<br/>POINT_NOT_EVALUABLE<br/>POINT_CONTEXT_INCOMPLETE"]

    PA --> RUN["Observed LOW-run state<br/>run length / support depth"]
    RUN --> HE["Horizon eligibility<br/>3h / 8h causal coverage"]
    C --> HE
    RUN --> TR["Temporal Resolution<br/>persistence K={int(primary_op['selected_k'])}"]
    HE --> TR
    C --> TR
    TR --> TA["Temporal Assignment Y_temporal"]

    PA --> SY["Same-Y projection<br/>copy Y_point onto 3h/8h representation<br/>no new Y ontology"]
    HE --> SY

    V -.-> AUD["Provenance / audit ledger"]
    D -.-> AUD
    RF -.-> AUD
    PR -.-> AUD
    PA -.-> AUD
    RUN -.-> AUD
    HE -.-> AUD
    TR -.-> AUD
    TA -.-> AUD
    SY -.-> AUD
'''
    (output_dir / "semantic_label_flow.mmd").write_text(mmd, encoding="utf-8")

    derived_rows = []
    for row in derived_registry.to_dict(orient="records"):
        derived_rows.append(
            f"| `{row['derived_evidence_id']}` | `{row['source_field_ids']}` | `{row['formula_expression_or_formula_id']}` | `{row['previous_observation_policy']}` | `{row['threshold_value']} {row['threshold_unit']}` |"
        )
    label_rows = "\n".join(f"| `{name}` | {count} |" for name, count in sorted(observed_label_counts.items()))
    rule_rows = "\n".join(
        f"| `{rule}` | {count} |"
        for rule, count in sorted(summary["rule_firing_counts"].items())
    )
    sensor_names = ", ".join(f"`{name}`" for name in FULL_9_FEATURES)
    markdown = f'''# Draft — Three-label semantic map

> Generated from the frozen contract and published native release. This is a
> reader-facing explanation and diagram; it does not create or modify labels.

## Provenance

- Contract: `{summary['semantic_contract_id']}` (`{summary['contract_hash']}`)
- Primary operationalization: `{primary_id}` (`{q_id}` + `K={int(primary_op['selected_k'])}`)
- Native release: `{release_dir.name}`
- Point release rows: `{len(point)}`
- Release manifest SHA-256: `{summary['release_manifest_sha256']}`
- Generated UTC: `{generated_at}`

## What enters the system

### 1. Collected sensor component: nine values

The full collected sensor snapshot is:

{sensor_names}

These nine values are the measurement/feature source. They are **not all direct
inputs to every label rule**: pH and N/P/K proxies are retained for feature arms,
while the current point ontology directly evaluates soil moisture, air
temperature/humidity, and previous-observation moisture/EC evidence.

### 2. Supporting applicability/context component

This component does not become a fourth label. It determines whether evidence
is evaluable: packet/sensor validity, timestamp integrity, deployment and
segment boundaries, strict previous-observation availability, and continuity.
Invalid or missing required evidence becomes `NOT_EVALUABLE`; it is never
silently converted to a negative rule firing.

### 3. Derived parameters and thresholds

| Derived evidence | Source | Current transformation | Previous policy | Threshold |
|---|---|---|---|---|
{chr(10).join(derived_rows)}

Primary Q/K configuration:

- `Q10 = {float(q_row['threshold_value']):g}` soil-moisture threshold, comparator `<=`.
- `K = {int(primary_op['selected_k'])}` observations; `K` is an observation-count
  persistence rule for temporal assignments, not a fourth point class.
- Strict previous policy: `{strict['policy_id']}`, allowed gap
  `{strict['allowed_gap_minutes']}` minutes, missing slot policy `{strict['missing_slot_policy']}`.
- Window coverage: at least `{window['coverage']['minimum_ratio']}` of expected nominal
  slots; duplicate slots fail closed.

## Tier 1 — evidence construction

1. Validate the authorized canonical record and continuity context.
2. Compute VPD, strict-previous moisture rise, and strict-previous absolute EC
   shift where their dependencies are valid.
3. Evaluate four independent rule firings with state `POSITIVE`, `NEGATIVE`, or
   `NOT_EVALUABLE`:

| Rule | Evidence | Comparator |
|---|---|---|
| `LOW_RELATIVE_MOISTURE` | `npk.soil_moisture_pct` | `<= Q10` |
| `THERMAL_CONTEXT` | `derived.vpd_kpa` | `>= 2.5 kPa` |
| `MOISTURE_RISE` | `moisture_rise_delta` | `>= 5.0 pp` |
| `EC_SHIFT` | `ec_shift_delta_abs` | `>= 6.0` |

The persistent machine-readable result is `audit/rule_firings.parquet`.

## Tier 2 — resolution and assignment

The point resolver combines the four rule states with this precedence:

| Point condition | Canonical point label | Primary training status |
|---|---|---|
| low positive | `low_relative_moisture_point` (`LOW`) | included |
| low negative + any auxiliary positive | `unresolved_environmental_evidence_point` (`UNRESOLVED_ENVIRONMENTAL`) | included |
| low negative + all required auxiliary negative | `reference_context_point` (`REFERENCE`) | included |
| low negative + auxiliary not evaluable | `point_context_incomplete` | excluded from primary ontology |
| low not evaluable / time invalid | `point_not_evaluable` | excluded from primary ontology |

The three primary classes are therefore `REFERENCE`, `LOW`, and
`UNRESOLVED_ENVIRONMENTAL`. `Resolution` records the decision, and `Assignment`
records the label plus provenance. `tasks/point/assignments.parquet` is the
published point label artifact.

Validation/applicability produces evidence states; the final technical statuses
`POINT_CONTEXT_INCOMPLETE` and `POINT_NOT_EVALUABLE` are resolved at the point
resolver from those states, rather than being a fourth class emitted before
RuleFiring. After point assignment, the temporal layer checks window eligibility and
support depth. If a point is LOW and support depth is at least `K`, temporal
resolution yields persistent low; otherwise it yields unresolved insufficient
persistence. Same-Y copies the source point label and does not create a new
ontology.

## Current release counts

### Point labels

| Label | Rows |
|---|---:|
{label_rows}

### Rule firing rows by rule

| Rule | Firings |
|---|---:|
{rule_rows}

## Existing artifacts and rerun behavior

- Core implementation: `lifecycle/phase_c_native/pipeline.py`
- Point resolver: `semantic/point/resolver.py`
- Rule evaluator: `semantic/evidence/rules.py`
- Temporal resolver: `semantic/temporal/resolver.py`
- Published support: `audit/rule_firings.parquet`, `audit/resolutions.parquet`,
  `audit/assignments.parquet`, and `run_metadata/label_release_manifest.json`.
- Re-run this report generator against a new frozen contract/release to refresh
  the explanation without reassigning labels.

## Important interpretation boundary

The model may later consume the nine sensor channels and history features, but
this label map is not an independent agronomic ground-truth definition. It is
the frozen rule-generated semantic boundary whose reproduction is measured by
the evaluation positive controls.
'''
    (output_dir / "semantic_label_draft.md").write_text(markdown, encoding="utf-8")
    return output_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a semantic weak-label map from frozen contract/release artifacts.")
    parser.add_argument("--contract-dir", type=Path, required=True)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    output = build_semantic_draft(
        contract_dir=args.contract_dir,
        release_dir=args.release_dir,
        output_dir=args.output_dir,
    )
    print(output)
