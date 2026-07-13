from datetime import datetime


def format_export_stamp(export_dt: datetime) -> str:
    return export_dt.strftime("%Y%m%dT%H%M%SZ")


def format_iso_utc(export_dt: datetime) -> str:
    return export_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
