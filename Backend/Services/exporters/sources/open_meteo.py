from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))

try:
    import openmeteo_requests
except ModuleNotFoundError:
    openmeteo_requests = None

try:
    import requests_cache
except ModuleNotFoundError:
    requests_cache = None

try:
    from retry_requests import retry
except ModuleNotFoundError:
    retry = None

try:
    from Core.utils.common import iso_utc_now
    from Core.utils.storage import read_json, write_json
except ModuleNotFoundError:
    from ....Core.utils.common import iso_utc_now
    from ....Core.utils.storage import read_json, write_json

try:
    from Services.config.settings import SETTINGS as EXPORT_SETTINGS
except ModuleNotFoundError:
    from ...config.settings import SETTINGS as EXPORT_SETTINGS

DEFAULT_START_DATE = date(2026, 3, 16)
DEFAULT_TIMEZONE = "Asia/Ho_Chi_Minh"
ARCHIVE_API_URL = "https://archive-api.open-meteo.com/v1/archive"
ECMWF_FORECAST_API_URL = "https://api.open-meteo.com/v1/ecmwf"
HOURLY_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "rain",
    "soil_temperature_0_to_7cm",
    "weather_code",
    "cloud_cover_high",
    "et0_fao_evapotranspiration",
    "is_day",
    "dew_point_2m",
    "cloud_cover",
    "precipitation",
)


@dataclass(frozen=True)
class MeteoStorageSettings:
    backend_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[3])
    latitude: float = 10.0853
    longitude: float = 105.8678
    timezone_name: str = DEFAULT_TIMEZONE
    model_name: str = "era5"
    source_mode: str = "archive_era5"
    api_url: str = ARCHIVE_API_URL
    source_name: str = "open-meteo-era5"
    sensor_type: str = "open_meteo_archive_hourly"
    location_slug: str = "open_meteo_era5_10.0853_105.8678"
    default_start_date: date = DEFAULT_START_DATE
    base_dir_override: Path | None = None
    forecast_past_hours: int = 72
    forecast_hours: int = 1

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @property
    def base_dir(self) -> Path:
        if self.base_dir_override is not None:
            return self.base_dir_override
        if self.source_mode == "forecast_ifs":
            return EXPORT_SETTINGS.meteo_forecast_root
        return EXPORT_SETTINGS.meteo_archive_root

    @property
    def history_root(self) -> Path:
        return self.base_dir / "history"

    @property
    def latest_payload_path(self) -> Path:
        return self.base_dir / "new_raw" / "latest.json"

    @property
    def latest_meta_path(self) -> Path:
        return self.base_dir / "new_raw" / "latest_meta.json"

    @property
    def sync_state_path(self) -> Path:
        return self.base_dir / "new_raw" / "sync_state.json"

    @property
    def cache_path(self) -> Path:
        return self.backend_root / ".cache" / "openmeteo_cache"


@dataclass(frozen=True)
class FetchWindow:
    start_date: date
    end_date: date
    force_full_sync: bool
    checkpoint_ts: int | None
    explicit_date_range: bool = False


def build_archive_era5_settings() -> MeteoStorageSettings:
    return MeteoStorageSettings(
        model_name="era5",
        source_mode="archive_era5",
        api_url=ARCHIVE_API_URL,
        source_name="open-meteo-era5",
        sensor_type="open_meteo_archive_hourly",
        location_slug="open_meteo_era5_10.0853_105.8678",
        base_dir_override=EXPORT_SETTINGS.meteo_archive_root,
    )


def build_forecast_ifs_settings() -> MeteoStorageSettings:
    return MeteoStorageSettings(
        model_name="ifs_hres",
        source_mode="forecast_ifs",
        api_url=ECMWF_FORECAST_API_URL,
        source_name="open-meteo-ifs",
        sensor_type="open_meteo_ifs_forecast_hourly",
        location_slug="open_meteo_ifs_10.0853_105.8678",
        base_dir_override=EXPORT_SETTINGS.meteo_forecast_root,
    )


def parse_iso_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def get_local_today(settings: MeteoStorageSettings) -> date:
    return datetime.now(settings.timezone).date()


def build_client(settings: MeteoStorageSettings) -> Any:
    missing_packages: list[str] = []
    if openmeteo_requests is None:
        missing_packages.append("openmeteo-requests")
    if requests_cache is None:
        missing_packages.append("requests-cache")
    if retry is None:
        missing_packages.append("retry-requests")
    if missing_packages:
        raise ModuleNotFoundError(
            "Thieu package Python de chay meteorology_flux.py: "
            f"{', '.join(missing_packages)}. "
            "Hay cai bang lenh `pip install -r Backend/requirements.txt`."
        )

    assert openmeteo_requests is not None
    assert requests_cache is not None
    assert retry is not None

    settings.cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_session = requests_cache.CachedSession(str(settings.cache_path), expire_after=-1)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    return openmeteo_requests.Client(session=retry_session)


def load_checkpoint_state(settings: MeteoStorageSettings) -> dict[str, Any]:
    for path in (settings.sync_state_path, settings.latest_meta_path):
        payload = read_json(path, default={})
        if isinstance(payload, dict) and payload.get("latest_event_key"):
            return payload

    history_files = sorted(settings.history_root.rglob("*.json"))
    if not history_files:
        return {}

    latest_history = read_json(history_files[-1], default={})
    if not isinstance(latest_history, dict):
        return {}

    record_payload = latest_history.get("record")
    if not isinstance(record_payload, dict):
        return {}

    return {
        "latest_event_key": latest_history.get("event_key"),
        "latest_date_key": latest_history.get("date_key"),
        "latest_ts_server": record_payload.get("ts_server"),
        "latest_local_iso": record_payload.get("observed_at_local"),
    }


def resolve_fetch_window(
    settings: MeteoStorageSettings,
    force_full_sync: bool = False,
    start_date_override: date | None = None,
    end_date_override: date | None = None,
) -> FetchWindow:
    end_date = end_date_override or get_local_today(settings)

    if settings.source_mode == "forecast_ifs":
        if start_date_override is not None or end_date_override is not None:
            return FetchWindow(
                start_date=min(start_date_override or end_date, end_date),
                end_date=end_date,
                force_full_sync=True,
                checkpoint_ts=None,
                explicit_date_range=True,
            )
        today = get_local_today(settings)
        return FetchWindow(
            start_date=today,
            end_date=today,
            force_full_sync=True,
            checkpoint_ts=None,
            explicit_date_range=False,
        )

    if start_date_override is not None:
        return FetchWindow(
            start_date=min(start_date_override, end_date),
            end_date=end_date,
            force_full_sync=force_full_sync,
            checkpoint_ts=None,
            explicit_date_range=True,
        )

    checkpoint_state = load_checkpoint_state(settings)
    checkpoint_ts = checkpoint_state.get("latest_ts_server")
    checkpoint_ts = int(checkpoint_ts) if checkpoint_ts is not None else None

    if force_full_sync or checkpoint_ts is None:
        return FetchWindow(
            start_date=min(settings.default_start_date, end_date),
            end_date=end_date,
            force_full_sync=True if checkpoint_ts is None else force_full_sync,
            checkpoint_ts=None if force_full_sync else checkpoint_ts,
            explicit_date_range=False,
        )

    checkpoint_local_dt = datetime.fromtimestamp(checkpoint_ts, tz=timezone.utc).astimezone(
        settings.timezone
    )
    return FetchWindow(
        start_date=min(checkpoint_local_dt.date(), end_date),
        end_date=end_date,
        force_full_sync=False,
        checkpoint_ts=checkpoint_ts,
        explicit_date_range=False,
    )


def normalize_metric_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float):
        if math.isnan(value):
            return None
        return round(value, 4)
    if isinstance(value, (int, str, bool)):
        return value
    return value


def fetch_hourly_rows(settings: MeteoStorageSettings, window: FetchWindow) -> list[dict[str, Any]]:
    client = build_client(settings)
    params: dict[str, Any] = {
        "latitude": settings.latitude,
        "longitude": settings.longitude,
        "hourly": list(HOURLY_VARIABLES),
        "timezone": settings.timezone_name,
    }
    if settings.source_mode == "forecast_ifs":
        if window.explicit_date_range:
            params.update(
                {
                    "start_date": window.start_date.isoformat(),
                    "end_date": window.end_date.isoformat(),
                }
            )
        else:
            params.update(
                {
                    "past_hours": settings.forecast_past_hours,
                    "forecast_hours": settings.forecast_hours,
                }
            )
    else:
        params.update(
            {
                "start_date": window.start_date.isoformat(),
                "end_date": window.end_date.isoformat(),
                "models": settings.model_name,
            }
        )

    responses = client.weather_api(
        settings.api_url,
        params=params,
    )
    if not responses:
        return []

    response = responses[0]
    hourly = response.Hourly()
    interval = timedelta(seconds=hourly.Interval())
    start_local = datetime.fromtimestamp(
        hourly.Time() + response.UtcOffsetSeconds(),
        tz=timezone.utc,
    ).replace(tzinfo=None)
    variable_arrays = {
        variable_name: hourly.Variables(index).ValuesAsNumpy()
        for index, variable_name in enumerate(HOURLY_VARIABLES)
    }
    sample_count = len(next(iter(variable_arrays.values()), []))

    rows: list[dict[str, Any]] = []
    for idx in range(sample_count):
        observed_at_local = (start_local + (interval * idx)).replace(tzinfo=settings.timezone)
        metrics = {
            variable_name: normalize_metric_value(variable_arrays[variable_name][idx])
            for variable_name in HOURLY_VARIABLES
        }
        rows.append({"observed_at_local": observed_at_local, "metrics": metrics})
    return rows


def build_raw_record(
    settings: MeteoStorageSettings,
    observed_at_local: datetime,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    observed_at_utc = observed_at_local.astimezone(timezone.utc)
    ts_server = int(observed_at_utc.timestamp())

    packet_payload = {
        "sensor_id": settings.location_slug,
        "sensor_type": settings.sensor_type,
        "sample_interval_ms": 3600000,
        "timezone": settings.timezone_name,
        "provider": settings.source_name,
        "source_mode": settings.source_mode,
        "model": settings.model_name,
        "is_observed_truth": settings.source_mode == "archive_era5",
        **metrics,
    }

    return {
        "schema_version": 1,
        "_meta_seed": {
            "provider": settings.source_name,
            "model": settings.model_name,
            "source_mode": settings.source_mode,
            "location_slug": settings.location_slug,
            "latitude": settings.latitude,
            "longitude": settings.longitude,
            "timezone": settings.timezone_name,
        },
        "ts_device": ts_server,
        "ts_server": ts_server,
        "observed_at_local": observed_at_local.isoformat(),
        "packet": {
            "meteo_data": packet_payload,
        },
    }


def record_is_usable(record: dict[str, Any]) -> bool:
    packet_payload = record.get("packet", {}).get("meteo_data", {})
    if packet_payload.get("temperature_2m") is None:
        return False
    if packet_payload.get("relative_humidity_2m") is None:
        return False
    if packet_payload.get("precipitation") is None and packet_payload.get("rain") is None:
        return False
    return True


def filter_new_records(records: list[dict[str, Any]], checkpoint_ts: int | None) -> list[dict[str, Any]]:
    filtered_records = [record for record in records if record_is_usable(record)]
    if checkpoint_ts is None:
        return filtered_records
    return [
        record
        for record in filtered_records
        if int(record.get("ts_server") or 0) > checkpoint_ts
    ]


def filter_forecast_records_to_now(
    records: list[dict[str, Any]],
    checked_at_utc: str,
) -> list[dict[str, Any]]:
    checked_dt = parse_iso_datetime(checked_at_utc)
    if checked_dt is None:
        return records
    checked_ts = int(checked_dt.astimezone(timezone.utc).timestamp())
    return [
        record
        for record in records
        if int(record.get("ts_server") or 0) <= checked_ts
    ]


def build_history_path(settings: MeteoStorageSettings, date_key: str, event_key: str) -> Path:
    dt = datetime.strptime(date_key, "%Y-%m-%d")
    return (
        settings.history_root
        / dt.strftime("%Y")
        / dt.strftime("%m")
        / dt.strftime("%d")
        / f"{settings.location_slug}_{event_key}.json"
    )


def write_history_records(
    settings: MeteoStorageSettings,
    records: list[dict[str, Any]],
    checked_at_utc: str,
) -> list[Path]:
    written_paths: list[Path] = []
    for record in records:
        event_key = str(record["ts_server"])
        date_key = datetime.fromtimestamp(record["ts_server"], tz=timezone.utc).astimezone(
            settings.timezone
        ).strftime("%Y-%m-%d")
        history_path = build_history_path(settings=settings, date_key=date_key, event_key=event_key)
        write_json(
            history_path,
            {
                "event_key": event_key,
                "date_key": date_key,
                "path": f"weather/{settings.location_slug}/{date_key}/{event_key}",
                "synced_at_utc": checked_at_utc,
                "record": record,
            },
        )
        written_paths.append(history_path)
    return written_paths


def build_latest_meta(
    settings: MeteoStorageSettings,
    latest_record: dict[str, Any],
    previous_event_key: str | None,
    checked_at_utc: str,
    window: FetchWindow,
    fetched_record_count: int,
    written_record_count: int,
) -> dict[str, Any]:
    latest_ts = int(latest_record["ts_server"])
    latest_dt = datetime.fromtimestamp(latest_ts, tz=timezone.utc).astimezone(settings.timezone)
    date_key = latest_dt.strftime("%Y-%m-%d")
    event_key = str(latest_ts)
    return {
        "schema_version": 1,
        "source_name": settings.source_name,
        "source_mode": settings.source_mode,
        "model": settings.model_name,
        "api_url": settings.api_url,
        "location_slug": settings.location_slug,
        "latest_event_key": event_key,
        "latest_date_key": date_key,
        "latest_path": f"weather/{settings.location_slug}/{date_key}/{event_key}",
        "latest_ts_server": latest_record["ts_server"],
        "latest_local_iso": latest_record["observed_at_local"],
        "previous_event_key": previous_event_key,
        "fetch_start_date": window.start_date.isoformat(),
        "fetch_end_date": window.end_date.isoformat(),
        "fetched_record_count": fetched_record_count,
        "written_record_count": written_record_count,
        "skipped_unusable_count": max(0, fetched_record_count - written_record_count),
        "updated_at_utc": checked_at_utc,
    }


def build_sync_state(
    settings: MeteoStorageSettings,
    latest_record: dict[str, Any] | None,
    previous_event_key: str | None,
    checked_at_utc: str,
    window: FetchWindow,
    fetched_record_count: int,
    written_record_count: int,
) -> dict[str, Any]:
    latest_ts_server = None if latest_record is None else latest_record["ts_server"]
    latest_local_iso = None if latest_record is None else latest_record["observed_at_local"]
    latest_date_key = None
    latest_event_key = None
    latest_path = None
    if latest_ts_server is not None:
        latest_dt = datetime.fromtimestamp(latest_ts_server, tz=timezone.utc).astimezone(
            settings.timezone
        )
        latest_date_key = latest_dt.strftime("%Y-%m-%d")
        latest_event_key = str(latest_ts_server)
        latest_path = f"weather/{settings.location_slug}/{latest_date_key}/{latest_event_key}"

    return {
        "schema_version": 1,
        "source_name": settings.source_name,
        "source_mode": settings.source_mode,
        "model": settings.model_name,
        "api_url": settings.api_url,
        "location_slug": settings.location_slug,
        "status": "no_new_data" if written_record_count == 0 else "synced",
        "run_mode": "full_history" if window.force_full_sync else "incremental",
        "checked_at_utc": checked_at_utc,
        "default_start_date": settings.default_start_date.isoformat(),
        "fetch_start_date": window.start_date.isoformat(),
        "fetch_end_date": window.end_date.isoformat(),
        "checkpoint_ts": window.checkpoint_ts,
        "history_root": str(settings.history_root),
        "latest_payload_path": str(settings.latest_payload_path),
        "latest_meta_path": str(settings.latest_meta_path),
        "sync_state_path": str(settings.sync_state_path),
        "fetched_record_count": fetched_record_count,
        "written_record_count": written_record_count,
        "skipped_unusable_count": max(0, fetched_record_count - written_record_count),
        "latest_event_key": latest_event_key,
        "latest_date_key": latest_date_key,
        "latest_path": latest_path,
        "latest_ts_server": latest_ts_server,
        "latest_local_iso": latest_local_iso,
        "previous_event_key": previous_event_key,
    }


def run_sync(
    settings: MeteoStorageSettings = MeteoStorageSettings(),
    force_full_sync: bool = False,
    start_date_override: date | None = None,
    end_date_override: date | None = None,
) -> dict[str, Any]:
    checked_at_utc = iso_utc_now()
    previous_state = load_checkpoint_state(settings)
    previous_event_key = None if not isinstance(previous_state, dict) else previous_state.get("latest_event_key")

    window = resolve_fetch_window(
        settings=settings,
        force_full_sync=force_full_sync,
        start_date_override=start_date_override,
        end_date_override=end_date_override,
    )
    fetched_rows = fetch_hourly_rows(settings=settings, window=window)
    fetched_records = [
        build_raw_record(
            settings=settings,
            observed_at_local=row["observed_at_local"],
            metrics=row["metrics"],
        )
        for row in fetched_rows
    ]
    if settings.source_mode == "forecast_ifs" and not window.explicit_date_range:
        fetched_records = filter_forecast_records_to_now(
            records=fetched_records,
            checked_at_utc=checked_at_utc,
        )
    records_to_write = filter_new_records(records=fetched_records, checkpoint_ts=window.checkpoint_ts)
    written_paths = write_history_records(settings=settings, records=records_to_write, checked_at_utc=checked_at_utc)

    latest_record = records_to_write[-1] if records_to_write else None
    if latest_record is None:
        usable_records = [record for record in fetched_records if record_is_usable(record)]
        latest_record = usable_records[-1] if usable_records else None
    if latest_record is not None:
        write_json(settings.latest_payload_path, latest_record)
        write_json(
            settings.latest_meta_path,
            build_latest_meta(
                settings=settings,
                latest_record=latest_record,
                previous_event_key=previous_event_key,
                checked_at_utc=checked_at_utc,
                window=window,
                fetched_record_count=len(fetched_records),
                written_record_count=len(records_to_write),
            ),
        )

    sync_state = build_sync_state(
        settings=settings,
        latest_record=latest_record,
        previous_event_key=previous_event_key,
        checked_at_utc=checked_at_utc,
        window=window,
        fetched_record_count=len(fetched_records),
        written_record_count=len(records_to_write),
    )
    write_json(settings.sync_state_path, sync_state)

    return {
        "status": sync_state["status"],
        "run_mode": sync_state["run_mode"],
        "fetch_start_date": window.start_date.isoformat(),
        "fetch_end_date": window.end_date.isoformat(),
        "fetched_record_count": len(fetched_records),
        "written_record_count": len(records_to_write),
        "history_root": str(settings.history_root),
        "latest_payload_path": str(settings.latest_payload_path),
        "latest_meta_path": str(settings.latest_meta_path),
        "sync_state_path": str(settings.sync_state_path),
        "last_history_path": None if not written_paths else str(written_paths[-1]),
        "latest_record": latest_record,
    }


def run_archive_era5_sync(
    force_full_sync: bool = False,
    start_date_override: date | None = None,
    end_date_override: date | None = None,
) -> dict[str, Any]:
    return run_sync(
        settings=build_archive_era5_settings(),
        force_full_sync=force_full_sync,
        start_date_override=start_date_override,
        end_date_override=end_date_override,
    )


def run_forecast_ifs_sync() -> dict[str, Any]:
    return run_sync(
        settings=build_forecast_ifs_settings(),
        force_full_sync=True,
    )


def run_forecast_ifs_range_sync(
    start_date_override: date,
    end_date_override: date,
) -> dict[str, Any]:
    return run_sync(
        settings=build_forecast_ifs_settings(),
        force_full_sync=True,
        start_date_override=start_date_override,
        end_date_override=end_date_override,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Dong bo du lieu Open-Meteo ERA5 vao "
            "Backend/Output_data/Layer0/OpenMeteo_Data/Meteo_archive_era5 "
            "voi layout history/new_raw tuong tu Firebase raw."
        )
    )
    parser.add_argument(
        "--full-history",
        action="store_true",
        help="Ep keo lai toan bo du lieu tu 2026-03-16 den hien tai.",
    )
    parser.add_argument("--start-date", type=str, default=None, help="Ngay bat dau theo YYYY-MM-DD.")
    parser.add_argument("--end-date", type=str, default=None, help="Ngay ket thuc theo YYYY-MM-DD.")
    return parser.parse_args()


def parse_date_argument(value: str | None, field_name: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} phai theo dinh dang YYYY-MM-DD, nhan duoc: {value}") from exc


def main() -> None:
    try:
        args = parse_args()
        result = run_sync(
            force_full_sync=args.full_history,
            start_date_override=parse_date_argument(args.start_date, "start-date"),
            end_date_override=parse_date_argument(args.end_date, "end-date"),
        )
    except (ModuleNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Sync status: {result['status']}")
    print(f"Run mode: {result['run_mode']}")
    print(f"Fetch window: {result['fetch_start_date']} -> {result['fetch_end_date']}")
    print(f"Fetched records: {result['fetched_record_count']}")
    print(f"Written records: {result['written_record_count']}")
    print(f"History root: {result['history_root']}")
    print(f"Latest payload: {result['latest_payload_path']}")
    print(f"Latest meta: {result['latest_meta_path']}")
    print(f"Sync state: {result['sync_state_path']}")
    if result["last_history_path"] is not None:
        print(f"Last history snapshot: {result['last_history_path']}")
    latest_record = result["latest_record"]
    if latest_record is not None:
        print(f"Latest ts_server: {latest_record['ts_server']}")


if __name__ == "__main__":
    main()

