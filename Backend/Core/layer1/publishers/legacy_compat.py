from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

try:
    from Config.runtime import BACKEND_SETTINGS
except ModuleNotFoundError:
    from ....Config.runtime import BACKEND_SETTINGS

from ...utils.common import iso_utc_now
from ...utils.storage import write_json, write_jsonl


class LegacyCompatibilityPublisher:
    def __init__(self, output_root: Path):
        self.output_root = output_root.resolve()

    def publish(self, canonical_df: pd.DataFrame) -> None:
        self._write_legacy_stream(
            canonical_df=canonical_df,
            stream_name="sht30",
            latest_path=self.output_root / "sht30" / "latest.json",
            history_path=self.output_root / "sht30" / "history.jsonl",
            state_path=self.output_root / "sht30" / "state.json",
            builder=self._build_legacy_sht_row,
        )
        self._write_legacy_stream(
            canonical_df=canonical_df,
            stream_name="npk",
            latest_path=self.output_root / "npk" / "latest.json",
            history_path=self.output_root / "npk" / "history.jsonl",
            state_path=self.output_root / "npk" / "state.json",
            builder=self._build_legacy_npk_row,
        )
        meteo_dir = self.output_root / "meteo"
        meteo_dir.mkdir(parents=True, exist_ok=True)
        write_json(meteo_dir / "latest.json", {})
        write_json(
            meteo_dir / "state.json",
            {
                "schema_version": 2,
                "processor_name": "canonical_compat_meteo",
                "last_processed_server_ts": None,
                "last_processed_event_key": None,
                "processed_record_count": 0,
                "last_updated_utc": iso_utc_now(),
            },
        )
        write_jsonl(meteo_dir / "history.jsonl", [])

    def _write_legacy_stream(
        self,
        *,
        canonical_df: pd.DataFrame,
        stream_name: str,
        latest_path: Path,
        history_path: Path,
        state_path: Path,
        builder: Any,
    ) -> None:
        stream_rows = [builder(row) for row in canonical_df.to_dict(orient="records")]
        stream_rows = [row for row in stream_rows if row is not None]
        history_path.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl(history_path, stream_rows)
        latest_row = stream_rows[-1] if stream_rows else {}
        write_json(latest_path, latest_row)
        write_json(
            state_path,
            {
                "schema_version": 2,
                "processor_name": f"canonical_compat_{stream_name}",
                "last_processed_server_ts": latest_row.get("timestamps", {}).get("ts_server")
                if latest_row
                else None,
                "last_processed_event_key": latest_row.get("source", {}).get("event_key")
                if latest_row
                else None,
                "processed_record_count": len(stream_rows),
                "last_updated_utc": iso_utc_now(),
            },
        )

    def _build_legacy_sht_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "layer": "layer1_compat",
            "processor_name": "canonical_compat_sht30",
            "sensor_id": BACKEND_SETTINGS.sht30_sensor_id,
            "sensor_type": BACKEND_SETTINGS.sht30_sensor_type,
            "source": {
                "event_key": row.get("record.event_key"),
                "date_key": row.get("record.date_key"),
                "path": row.get("record.source_path"),
                "origin": row.get("record.source_kind"),
                "source_name": "firebase",
            },
            "timestamps": {
                "ts_device": row.get("record.ts_device"),
                "ts_server": row.get("record.ts_server"),
                "observed_at_local": row.get("record.sample_time_local"),
            },
            "perception": {
                "temp_air_c": row.get("sht.temp_c"),
                "humidity_air_pct": row.get("sht.humidity_pct"),
            },
            "status": {
                "read_ok": row.get("sht.read_ok"),
                "sample_valid": row.get("sht.sample_valid"),
                "status": row.get("sht.status"),
                "error_code": row.get("sht.error_code"),
            },
        }

    def _build_legacy_npk_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "layer": "layer1_compat",
            "processor_name": "canonical_compat_npk",
            "sensor_id": BACKEND_SETTINGS.npk_sensor_id,
            "sensor_type": BACKEND_SETTINGS.npk_sensor_type,
            "source": {
                "event_key": row.get("record.event_key"),
                "date_key": row.get("record.date_key"),
                "path": row.get("record.source_path"),
                "origin": row.get("record.source_kind"),
                "source_name": "firebase",
            },
            "timestamps": {
                "ts_device": row.get("record.ts_device"),
                "ts_server": row.get("record.ts_server"),
                "observed_at_local": row.get("record.sample_time_local"),
            },
            "perception": {
                "n_ppm": row.get("npk.n_proxy"),
                "p_ppm": row.get("npk.p_proxy"),
                "k_ppm": row.get("npk.k_proxy"),
                "soil_temp_c": row.get("npk.soil_temp_c"),
                "soil_humidity_pct": row.get("npk.soil_moisture_pct"),
                "soil_ph": row.get("npk.ph"),
                "soil_ec_us_cm": row.get("npk.ec"),
            },
            "status": {
                "read_ok": row.get("npk.read_ok"),
                "sample_valid": row.get("npk.sample_valid"),
                "status": row.get("npk.status"),
                "error_code": row.get("npk.error_code"),
                "protocol_fault": row.get("npk.protocol_fault"),
            },
        }
