from __future__ import annotations


def build_quality_flags(
    *,
    anchor_ts: int,
    npk_ts: int | None,
    sht_ts: int | None,
    npk_present: bool,
    sht_present: bool,
    ec_flag: str,
    row_missing_fields: list[str],
    source_gap_sec: int | None,
    stale_threshold_sec: int,
    misaligned_threshold_sec: int,
) -> list[str]:
    flags: list[str] = []

    if not npk_present:
        flags.append("missing_npk")
    if not sht_present:
        flags.append("missing_sht30")
    if row_missing_fields:
        flags.append("partial_row")
    if source_gap_sec is not None and source_gap_sec > misaligned_threshold_sec:
        flags.append("source_misaligned")
    if ec_flag != "ok":
        flags.append(f"ec_npk_{ec_flag}")

    if npk_ts is None and sht_ts is None:
        flags.append("no_core_sources")
    elif npk_ts is not None and abs(anchor_ts - npk_ts) > stale_threshold_sec:
        flags.append("npk_stale")
    elif sht_ts is not None and abs(anchor_ts - sht_ts) > stale_threshold_sec:
        flags.append("sht30_stale")

    return flags

