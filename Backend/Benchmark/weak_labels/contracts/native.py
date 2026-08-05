from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pandas as pd
import yaml

from Backend.Benchmark.common.digests import file_sha256, stable_digest


class NativeContractError(ValueError):
    """Raised when a native run cannot be authorized by its frozen contract."""


@dataclass(frozen=True)
class NativeEngineConfig:
    semantic_contract_run_dir: Path
    protocol_registry_run_dir: Path
    canonical_history_path: Path
    canonical_evidence_schema_path: Path
    sensor_dependency_registry_path: Path
    segment_manifest_path: Path
    expected_difference_contract_path: Path | None
    output_root: Path
    operationalization_id: str | None = None
    engine_mode: Literal["NATIVE", "SHADOW"] = "NATIVE"
    expected_difference_contract_hash: str | None = None


@dataclass(frozen=True)
class NativeEngineResult:
    run_id: str
    output_dir: Path
    status: str
    operationalization_id: str
    record_count: int


@dataclass(frozen=True)
class DifferentialAuditResult:
    audit_id: str
    output_dir: Path
    status: str
    unmatched_difference_count: int
    multiply_matched_difference_count: int


@dataclass(frozen=True)
class NativeContract:
    run_dir: Path
    run_manifest: dict[str, object]
    semantic_contract_hash: str
    semantic_contract_id: str
    primary_operationalization_id: str
    operationalizations: pd.DataFrame
    q_registry: pd.DataFrame
    persistence_registry: pd.DataFrame
    derived_evidence_registry: pd.DataFrame
    window_contracts: dict[str, object]
    point_compatibility_matrix: pd.DataFrame
    point_resolution_contract: dict[str, object]
    temporal_resolution_contract: dict[str, object]

    @classmethod
    def load(cls, run_dir: Path) -> "NativeContract":
        run_dir = run_dir.resolve()
        manifest_path = run_dir / "run_metadata" / "run_manifest.json"
        if not manifest_path.exists():
            raise NativeContractError(f"Missing frozen semantic-contract manifest: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        required_flags = {
            "semantic_contract_frozen": True,
            "native_engine_implemented": False,
            "downstream_runners_unlocked": False,
        }
        for key, expected in required_flags.items():
            if manifest.get(key) != expected:
                raise NativeContractError(
                    f"Frozen contract flag {key} must be {expected!r}; got {manifest.get(key)!r}."
                )
        semantic_hash = str(manifest.get("semantic_contract_hash", ""))
        semantic_id = str(manifest.get("semantic_contract_id", ""))
        if not semantic_hash or not semantic_id:
            raise NativeContractError("Frozen contract must contain semantic_contract_id and semantic_contract_hash.")

        operationalizations = _read_required_csv(
            run_dir / "operationalization" / "operationalization_registry.csv",
            "operationalization_registry",
        )
        q_registry = _read_required_csv(
            run_dir / "thresholds" / "frozen_threshold_registry.csv",
            "frozen_threshold_registry",
        )
        persistence = _read_required_csv(
            run_dir / "operationalization" / "persistence_operationalization_registry.csv",
            "persistence_operationalization_registry",
        )
        derived = _read_required_csv(
            run_dir / "evidence" / "derived_evidence_contract_registry.csv",
            "derived_evidence_contract_registry",
        )
        matrix = _read_required_csv(
            run_dir / "resolution" / "point_compatibility_matrix.csv",
            "point_compatibility_matrix",
        )
        point_contract = _read_yaml(run_dir / "resolution" / "point_resolution_contract.yaml")
        temporal_contract = _read_yaml(run_dir / "resolution" / "temporal_resolution_contract.yaml")
        window_contract = _read_yaml(run_dir / "continuity" / "window_continuity_contract.yaml")
        _validate_contract_payloads(
            manifest=manifest,
            operationalizations=operationalizations,
            q_registry=q_registry,
            persistence=persistence,
            derived=derived,
            matrix=matrix,
            window_contract=window_contract,
        )
        primary = operationalizations.loc[
            operationalizations["authority_status"].astype("string") == "PRIMARY_INTERNAL_AUTHORITY"
        ]
        if len(primary) != 1:
            raise NativeContractError("Frozen contract must contain exactly one primary operationalization.")
        return cls(
            run_dir=run_dir,
            run_manifest=manifest,
            semantic_contract_hash=semantic_hash,
            semantic_contract_id=semantic_id,
            primary_operationalization_id=str(primary.iloc[0]["operationalization_id"]),
            operationalizations=operationalizations,
            q_registry=q_registry,
            persistence_registry=persistence,
            derived_evidence_registry=derived,
            window_contracts=window_contract,
            point_compatibility_matrix=matrix,
            point_resolution_contract=point_contract,
            temporal_resolution_contract=temporal_contract,
        )

    def resolve_operationalization(self, requested: str | None) -> pd.Series:
        operationalization_id = requested or self.primary_operationalization_id
        rows = self.operationalizations.loc[
            self.operationalizations["operationalization_id"].astype("string") == operationalization_id
        ]
        if len(rows) != 1:
            raise NativeContractError(f"Operationalization is not unique in frozen contract: {operationalization_id}")
        return rows.iloc[0]

    def threshold_value(self, threshold_id: str) -> float:
        rows = self.q_registry.loc[self.q_registry["threshold_id"].astype("string") == threshold_id]
        if len(rows) != 1:
            raise NativeContractError(f"Threshold is not unique in frozen contract: {threshold_id}")
        value = rows.iloc[0]["threshold_value"]
        if pd.isna(value) or not math.isfinite(float(value)):
            raise NativeContractError(f"Threshold {threshold_id} is not finite.")
        return float(value)


def canonicalize_payload(payload: object) -> bytes:
    normalized = _canonical_value(payload)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def deterministic_id(payload: dict[str, object]) -> str:
    if "object_type" not in payload or "schema_version" not in payload:
        raise ValueError("Deterministic identity payload requires object_type and schema_version.")
    return hashlib.sha256(canonicalize_payload(payload)).hexdigest()


def dataframe_set_hash(frame: pd.DataFrame, columns: list[str]) -> str:
    rows = frame.loc[:, columns].copy().sort_values(columns, kind="stable").to_dict(orient="records")
    return stable_digest({"columns": columns, "rows": rows})


def expected_difference_contract_hash(path: Path) -> str:
    return file_sha256(path.resolve())


def _canonical_value(value: object) -> object:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("NaN and infinity are not valid deterministic identity values.")
        return format(value, ".15g")
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if pd.isna(value) if not isinstance(value, (str, bool, int)) else False:
        return None
    return value


def _read_required_csv(path: Path, name: str) -> pd.DataFrame:
    if not path.exists():
        raise NativeContractError(f"Frozen contract is missing {name}: {path}")
    frame = pd.read_csv(path).convert_dtypes()
    if frame.empty:
        raise NativeContractError(f"Frozen contract artifact is empty: {path}")
    return frame


def _read_yaml(path: Path) -> dict[str, object]:
    if not path.exists():
        raise NativeContractError(f"Frozen contract is missing YAML artifact: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise NativeContractError(f"Frozen contract YAML must be a mapping: {path}")
    return payload


def _validate_contract_payloads(
    *,
    manifest: dict[str, object],
    operationalizations: pd.DataFrame,
    q_registry: pd.DataFrame,
    persistence: pd.DataFrame,
    derived: pd.DataFrame,
    matrix: pd.DataFrame,
    window_contract: dict[str, object],
) -> None:
    if not manifest.get("semantic_contract_hash"):
        raise NativeContractError("semantic_contract_hash is required.")
    required_op = {"operationalization_id", "authority_status", "q_contract_id", "persistence_contract_id"}
    if not required_op.issubset(operationalizations.columns):
        raise NativeContractError(f"Operationalization registry missing columns: {sorted(required_op - set(operationalizations.columns))}")
    required_derived = {
        "derived_evidence_id", "transform_id", "transform_version", "source_field_ids", "source_units",
        "output_unit", "formula_expression_or_formula_id", "previous_observation_policy",
        "absolute_value_applied", "clipping_policy", "null_policy", "infinity_policy",
        "rounding_policy", "comparison_precision", "code_reference_hash",
    }
    if not required_derived.issubset(derived.columns):
        raise NativeContractError(f"Derived-evidence registry missing columns: {sorted(required_derived - set(derived.columns))}")
    if not {"threshold_id", "threshold_value"}.issubset(q_registry.columns):
        raise NativeContractError("Frozen threshold registry must contain threshold_id and threshold_value.")
    if not {"contract_id", "selected_k"}.issubset(persistence.columns):
        raise NativeContractError("Persistence registry must contain contract_id and selected_k.")
    if not {"low_state", "thermal_state", "rise_state", "ec_state", "resolution_id"}.issubset(matrix.columns):
        raise NativeContractError("Point compatibility matrix is incomplete.")
    required_window = {
        "window_interval", "timestamp_authority", "nominal_cadence_minutes", "expected_slot_formula",
        "anchor_inclusion", "slot_assignment", "duplicate_slot_policy", "coverage",
        "max_internal_gap", "tie_order",
    }
    if not required_window.issubset(window_contract):
        raise NativeContractError(f"Window contract is incomplete: {sorted(required_window - set(window_contract))}")
