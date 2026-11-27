"""Training gate (GD5 s5h, plan decision s2e): no fitting on an unaudited runner contract.

model_suite reads ``<protocol run>/run_metadata/protocol_validation_report.json`` (written by
evaluation_protocols) and trains only when its ``validation_status`` is ``"ready"``. It reads
the file only; it never imports an audit lane. ``allow_unaudited=True`` (CLI
``--allow-unaudited``) lets a run go ahead anyway and the returned record, which callers put in
their run manifest, says so.
"""
from __future__ import annotations

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

GATE_REPORT = Path("run_metadata") / "protocol_validation_report.json"
READY = "ready"


class UnauditedRunError(RuntimeError):
    """Raised when the runner contract is not marked validation_status=ready."""


def check_training_gate(protocol_run_dir: Path, *, allow_unaudited: bool = False) -> dict[str, object]:
    report_path = (Path(protocol_run_dir) / GATE_REPORT).resolve()
    status: str
    if not report_path.is_file():
        status = "missing_report"
    else:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        status = str(payload.get("validation_status") or "missing_validation_status")
    record: dict[str, object] = {
        "gate": "protocol_validation_report.validation_status",
        "report_path": str(report_path),
        "validation_status": status,
        "required_status": READY,
        "override": False,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if status == READY:
        return record
    message = (
        f"Runner contract is not audited: {report_path} has validation_status={status!r} "
        f"(need {READY!r}). Re-run evaluation_protocols, or pass --allow-unaudited to train anyway "
        "(the override is recorded in the run manifest)."
    )
    if not allow_unaudited:
        raise UnauditedRunError(message)
    warnings.warn(message, stacklevel=2)
    record["override"] = True
    record["override_reason"] = "--allow-unaudited"
    return record
