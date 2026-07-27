from __future__ import annotations

from typing import Any

from .common import (
    as_optional_bool,
    derive_protocol_fault,
    normalize_error_code,
    normalize_text,
)


def build_sensor_branch(
    *,
    packet_present: bool,
    sensor_status: dict[str, Any],
    normalized_prefix: str,
    protocol_flags: tuple[bool | None, ...] | None = None,
) -> dict[str, Any]:
    read_ok = as_optional_bool(sensor_status.get("read_ok"))
    sample_valid = as_optional_bool(sensor_status.get("sample_valid"))
    status = normalize_text(sensor_status.get("status"))
    error_code = normalize_error_code(sensor_status.get("error_code"))

    fault_evidence = [
        read_ok is False,
        sample_valid is False,
        status == "error",
        error_code not in {None, "ok"},
    ]
    protocol_fault = None
    if protocol_flags is not None:
        protocol_fault = derive_protocol_fault(protocol_flags)
        fault_evidence.append(protocol_fault is True)

    if any(fault_evidence):
        fault = True
    elif (
        packet_present
        and read_ok is True
        and sample_valid is True
        and status == "ok"
        and protocol_fault in {None, False}
    ):
        fault = False
    else:
        fault = None

    if (
        packet_present
        and read_ok is True
        and sample_valid is True
        and status == "ok"
        and protocol_fault in {None, False}
    ):
        valid = True
    elif fault is True or not packet_present:
        valid = False
    else:
        valid = None

    return {
        f"{normalized_prefix}.read_ok": read_ok,
        f"{normalized_prefix}.sample_valid": sample_valid,
        f"{normalized_prefix}.status": status,
        f"{normalized_prefix}.error_code": error_code,
        f"{normalized_prefix}.valid": valid,
        f"{normalized_prefix}.fault": fault,
        f"{normalized_prefix}.missing_packet": not packet_present,
        **(
            {f"{normalized_prefix}.protocol_fault": protocol_fault}
            if normalized_prefix == "npk"
            else {}
        ),
    }
