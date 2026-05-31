from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

try:
    from Config.runtime import BackendSettings
except ModuleNotFoundError:
    from ...Config.runtime import BackendSettings


TEMPLATE_ID_TO_NAME = {
    0: "normal_context",
    1: "packet_loss_outage",
    2: "water_deficit",
    3: "rain_humid_context",
    4: "fertigation_spike",
}
DEFAULT_MOCK_DATE_KEY = "2026-05-20"
DEMO_BASELINE_START_HOUR = 0
DEMO_BASELINE_END_HOUR = 12
DEMO_STEP_MINUTES = 15


@dataclass(frozen=True)
class TelemetryRuntimeInjectResult:
    template_id: int
    template_name: str
    telemetry_path: str
    sample_ts: int
    server_ts: int
    latest_meta_path: str


@dataclass(frozen=True)
class TelemetryRuntimeBatchInjectResult:
    template_id: int
    template_name: str
    date_key: str
    telemetry_paths: tuple[str, ...]
    record_count: int
    start_sample_ts: int
    end_sample_ts: int
    latest_meta_path: str


class TelemetryRuntimeTemplateInjector:
    def __init__(self, *, settings: BackendSettings, firebase_service: Any):
        self.settings = settings
        self.firebase_service = firebase_service

    def run(
        self,
        *,
        template_id: int,
        packet_gap_minutes: int = 64,
        inject_date_key: str = DEFAULT_MOCK_DATE_KEY,
    ) -> TelemetryRuntimeInjectResult:
        if template_id not in TEMPLATE_ID_TO_NAME:
            raise ValueError(f"Unsupported telemetry template id: {template_id}")

        runtime_context = self._load_runtime_context(inject_date_key=inject_date_key)
        start_dt_local = self._resolve_single_record_time(
            template_id=template_id,
            runtime_context=runtime_context,
            inject_date_key=inject_date_key,
            packet_gap_minutes=packet_gap_minutes,
        )
        sequence = self._build_demo_sequence(
            runtime_context=runtime_context,
            template_id=template_id,
            inject_date_key=inject_date_key,
            start_sample_dt_local=start_dt_local,
            total_steps=1,
            step_minutes=DEMO_STEP_MINUTES,
            anchor_to_seed=False,
        )
        batch = self._persist_sequence(
            runtime_context=runtime_context,
            template_id=template_id,
            inject_date_key=inject_date_key,
            sequence=sequence,
            status_reason=f"runtime template injected: {TEMPLATE_ID_TO_NAME[template_id]}",
        )
        return TelemetryRuntimeInjectResult(
            template_id=batch.template_id,
            template_name=batch.template_name,
            telemetry_path=batch.telemetry_paths[-1],
            sample_ts=batch.end_sample_ts,
            server_ts=self._resolve_server_ts_from_path(batch.telemetry_paths[-1]),
            latest_meta_path=batch.latest_meta_path,
        )

    def run_bootstrap_day(
        self,
        *,
        inject_date_key: str = DEFAULT_MOCK_DATE_KEY,
        start_hour: int = DEMO_BASELINE_START_HOUR,
        end_hour: int = DEMO_BASELINE_END_HOUR,
        step_minutes: int = DEMO_STEP_MINUTES,
    ) -> TelemetryRuntimeBatchInjectResult:
        runtime_context = self._load_runtime_context(inject_date_key=inject_date_key)
        sequence = self._build_demo_sequence(
            runtime_context=runtime_context,
            template_id=0,
            inject_date_key=inject_date_key,
            start_sample_dt_local=self._local_datetime(inject_date_key, hour=start_hour, minute=0),
            total_steps=((end_hour * 60) // step_minutes) + 1,
            step_minutes=step_minutes,
            anchor_to_seed=False,
        )
        return self._persist_sequence(
            runtime_context=runtime_context,
            template_id=0,
            inject_date_key=inject_date_key,
            sequence=sequence,
            status_reason="runtime demo bootstrap baseline",
        )

    def run_episode(
        self,
        *,
        template_id: int,
        packet_gap_minutes: int = 64,
        inject_date_key: str = DEFAULT_MOCK_DATE_KEY,
    ) -> TelemetryRuntimeBatchInjectResult:
        if template_id not in TEMPLATE_ID_TO_NAME:
            raise ValueError(f"Unsupported telemetry template id: {template_id}")

        runtime_context = self._load_runtime_context(inject_date_key=inject_date_key)
        start_dt_local, total_steps, step_minutes = self._resolve_episode_plan(
            template_id=template_id,
            packet_gap_minutes=packet_gap_minutes,
            inject_date_key=inject_date_key,
        )
        sequence = self._build_demo_sequence(
            runtime_context=runtime_context,
            template_id=template_id,
            inject_date_key=inject_date_key,
            start_sample_dt_local=start_dt_local,
            total_steps=total_steps,
            step_minutes=step_minutes,
            anchor_to_seed=True,
        )
        return self._persist_sequence(
            runtime_context=runtime_context,
            template_id=template_id,
            inject_date_key=inject_date_key,
            sequence=sequence,
            status_reason=f"runtime template episode injected: {TEMPLATE_ID_TO_NAME[template_id]}",
        )

    def _load_runtime_context(self, *, inject_date_key: str) -> dict[str, Any]:
        latest_current = self.firebase_service.pull_data(node_path=self.settings.latest_current_path)
        if not isinstance(latest_current, dict):
            raise ValueError("Firebase latest current payload is missing or malformed.")

        latest_meta = self.firebase_service.pull_data(node_path=self.settings.latest_meta_path)
        if latest_meta is None:
            latest_meta = {}
        if not isinstance(latest_meta, dict):
            raise ValueError("Firebase latest meta payload must be a JSON object.")

        live_root = self.firebase_service.pull_data(node_path=f"{self.settings.node_id}/live")
        if live_root is None:
            live_root = {}
        if not isinstance(live_root, dict):
            raise ValueError("Firebase live payload must be a JSON object.")

        day_payload = self.firebase_service.pull_data(node_path=f"{self.settings.telemetry_root_path}/{inject_date_key}")
        if day_payload is None:
            day_payload = {}
        if not isinstance(day_payload, dict):
            raise ValueError("Firebase telemetry day payload must be a JSON object.")

        return {
            "latest_current": latest_current,
            "latest_meta": latest_meta,
            "live_root": live_root,
            "day_payload": day_payload,
        }

    def _resolve_episode_plan(
        self,
        *,
        template_id: int,
        packet_gap_minutes: int,
        inject_date_key: str,
    ) -> tuple[datetime, int, int]:
        if template_id == 0:
            return self._local_datetime(inject_date_key, hour=12, minute=15), 8, DEMO_STEP_MINUTES
        if template_id == 1:
            return self._local_datetime(inject_date_key, hour=12, minute=0) + timedelta(minutes=packet_gap_minutes), 4, DEMO_STEP_MINUTES
        if template_id == 2:
            return self._local_datetime(inject_date_key, hour=12, minute=15), 10, DEMO_STEP_MINUTES
        return self._local_datetime(inject_date_key, hour=12, minute=15), 8, DEMO_STEP_MINUTES

    def _resolve_single_record_time(
        self,
        *,
        template_id: int,
        runtime_context: dict[str, Any],
        inject_date_key: str,
        packet_gap_minutes: int,
    ) -> datetime:
        latest_current = runtime_context["latest_current"]
        latest_meta = runtime_context["latest_meta"]
        previous_sample_ts = int(
            latest_current.get("ts_sample")
            or latest_current.get("packet", {}).get("system_data", {}).get("sample_epoch_sec")
            or latest_meta.get("ts_server")
            or 0
        )
        previous_local = datetime.fromtimestamp(previous_sample_ts, tz=self.settings.timezone)
        previous_seconds_of_day = previous_local.hour * 3600 + previous_local.minute * 60 + previous_local.second
        gap_sec = 900 if template_id != 1 else max(1800, int(packet_gap_minutes) * 60)
        target_seconds = min(previous_seconds_of_day + gap_sec, 86399)
        target_dt_local = self._local_datetime(inject_date_key, hour=0, minute=0) + timedelta(seconds=target_seconds)
        return target_dt_local

    def _build_demo_sequence(
        self,
        *,
        runtime_context: dict[str, Any],
        template_id: int,
        inject_date_key: str,
        start_sample_dt_local: datetime,
        total_steps: int,
        step_minutes: int,
        anchor_to_seed: bool,
    ) -> list[dict[str, Any]]:
        latest_current = runtime_context["latest_current"]
        latest_meta = runtime_context["latest_meta"]
        day_payload = runtime_context["day_payload"]

        anchor_seed = latest_current
        if anchor_to_seed:
            anchor_candidate = self._select_anchor_record(
                day_payload=day_payload,
                boundary_ts=int(start_sample_dt_local.timestamp()),
            )
            if anchor_candidate is not None:
                anchor_seed = anchor_candidate

        previous_record = anchor_seed
        previous_meta = latest_meta
        upload_lag_sec = self._resolve_upload_lag_sec(seed_record=anchor_seed, latest_meta=latest_meta)
        sequence: list[dict[str, Any]] = []
        for step_index in range(total_steps):
            sample_dt_local = start_sample_dt_local + timedelta(minutes=step_index * step_minutes)
            record = self._build_record_at_time(
                seed_record=previous_record,
                previous_meta=previous_meta,
                template_id=template_id,
                inject_date_key=inject_date_key,
                sample_dt_local=sample_dt_local,
                upload_lag_sec=upload_lag_sec,
                step_index=step_index,
                total_steps=total_steps,
                anchor_record=anchor_seed,
            )
            event_key = str(record["ts_server"])
            previous_meta = self._build_latest_meta_payload(
                latest_meta=previous_meta if isinstance(previous_meta, dict) else {},
                latest_record=record,
                event_key=event_key,
                date_key=inject_date_key,
            )
            previous_record = record
            sequence.append(record)

        return sequence

    def _persist_sequence(
        self,
        *,
        runtime_context: dict[str, Any],
        template_id: int,
        inject_date_key: str,
        sequence: list[dict[str, Any]],
        status_reason: str,
    ) -> TelemetryRuntimeBatchInjectResult:
        if not sequence:
            raise ValueError("Telemetry sequence is empty.")

        telemetry_paths: list[str] = []
        latest_meta = runtime_context["latest_meta"]
        live_root = runtime_context["live_root"]
        final_record = sequence[-1]
        final_event_key = str(final_record["ts_server"])
        final_meta_payload: dict[str, Any] | None = None

        for record in sequence:
            date_key = record["packet"]["system_data"]["sample_date_key"]
            event_key = str(record["ts_server"])
            telemetry_path = f"{self.settings.telemetry_root_path}/{date_key}/{event_key}"
            telemetry_paths.append(telemetry_path)
            self.firebase_service.set_data(telemetry_path, record)
            final_meta_payload = self._build_latest_meta_payload(
                latest_meta=latest_meta if isinstance(latest_meta, dict) else {},
                latest_record=record,
                event_key=event_key,
                date_key=date_key,
            )
            latest_meta = final_meta_payload

        live_payload = self._build_live_payload(
            live_root=live_root if isinstance(live_root, dict) else {},
            latest_record=final_record,
            event_key=final_event_key,
        )
        status_event_key = f"{final_event_key}_demo"
        status_event_payload = {
            "component": "simulator",
            "from": "demo",
            "to": "demo",
            "reason": status_reason,
            "severity": "info",
            "ts": int(final_record["ts_server"]),
            "ts_server_ms": int(final_record["ts_server"]) * 1000,
        }

        self.firebase_service.set_data(self.settings.latest_current_path, final_record)
        self.firebase_service.set_data(self.settings.latest_meta_path, final_meta_payload)
        self.firebase_service.set_data(f"{self.settings.node_id}/live", live_payload)
        self.firebase_service.set_data(f"{self.settings.node_id}/status_events/{status_event_key}", status_event_payload)

        return TelemetryRuntimeBatchInjectResult(
            template_id=template_id,
            template_name=TEMPLATE_ID_TO_NAME[template_id],
            date_key=inject_date_key,
            telemetry_paths=tuple(telemetry_paths),
            record_count=len(telemetry_paths),
            start_sample_ts=int(sequence[0]["ts_sample"]),
            end_sample_ts=int(sequence[-1]["ts_sample"]),
            latest_meta_path=self.settings.latest_meta_path,
        )

    def _select_anchor_record(self, *, day_payload: dict[str, Any], boundary_ts: int) -> dict[str, Any] | None:
        candidates: list[tuple[int, dict[str, Any]]] = []
        for _, payload in day_payload.items():
            if not isinstance(payload, dict):
                continue
            sample_ts = int(
                payload.get("ts_sample")
                or payload.get("packet", {}).get("system_data", {}).get("sample_epoch_sec")
                or 0
            )
            if sample_ts <= 0 or sample_ts >= boundary_ts:
                continue
            candidates.append((sample_ts, payload))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return copy.deepcopy(candidates[-1][1])

    def _resolve_upload_lag_sec(self, *, seed_record: dict[str, Any], latest_meta: dict[str, Any]) -> int:
        previous_server_ts = int(seed_record.get("ts_server") or latest_meta.get("ts_server") or 0)
        previous_sample_ts = int(
            seed_record.get("ts_sample")
            or seed_record.get("packet", {}).get("system_data", {}).get("sample_epoch_sec")
            or previous_server_ts
        )
        return max(45, previous_server_ts - previous_sample_ts)

    def _build_record_at_time(
        self,
        *,
        seed_record: dict[str, Any],
        previous_meta: dict[str, Any],
        template_id: int,
        inject_date_key: str,
        sample_dt_local: datetime,
        upload_lag_sec: int,
        step_index: int,
        total_steps: int,
        anchor_record: dict[str, Any],
    ) -> dict[str, Any]:
        record = copy.deepcopy(seed_record)
        next_sample_ts = int(sample_dt_local.timestamp())
        next_server_ts = next_sample_ts + upload_lag_sec
        next_device_ts = next_sample_ts
        date_key = inject_date_key
        sample_label = sample_dt_local.strftime("%H:%M")
        upload_dt_local = datetime.fromtimestamp(next_server_ts, tz=self.settings.timezone)
        upload_label = upload_dt_local.strftime("%H:%M")
        slot_no = int((sample_dt_local.hour * 60 + sample_dt_local.minute) // 15)

        packet = record.setdefault("packet", {})
        npk_data = packet.setdefault("npk_data", {})
        sht30_data = packet.setdefault("sht30_data", {})
        system_data = packet.setdefault("system_data", {})
        event_meta = record.setdefault("event_meta", {})
        health = record.setdefault("health", {})
        health_overall = health.setdefault("overall", {})
        modules = record.setdefault("modules", {})
        modules_sim = modules.setdefault("sim", {})
        sensors = record.setdefault("sensors", {})
        sensors_npk = sensors.setdefault("npk", {})
        sensors_sht30 = sensors.setdefault("sht30", {})

        anchor_packet = anchor_record.get("packet", {})
        anchor_npk = anchor_packet.get("npk_data", {}) if isinstance(anchor_packet, dict) else {}
        anchor_sht30 = anchor_packet.get("sht30_data", {}) if isinstance(anchor_packet, dict) else {}
        self._apply_template_mutation(
            template_id=template_id,
            npk_data=npk_data,
            sht30_data=sht30_data,
            anchor_npk=anchor_npk if isinstance(anchor_npk, dict) else {},
            anchor_sht30=anchor_sht30 if isinstance(anchor_sht30, dict) else {},
            step_index=step_index,
            total_steps=total_steps,
        )

        system_data["sample_date_key"] = date_key
        system_data["sample_epoch_sec"] = next_sample_ts
        system_data["sample_slot_count_day"] = 96
        system_data["sample_slot_no"] = slot_no
        system_data["sample_time_reconstructed"] = True
        system_data["sample_time_valid"] = True
        system_data["transport"] = modules_sim.get("transport", "cellular")

        event_meta["cycle_type"] = "periodic"
        event_meta["duration_ms"] = int(event_meta.get("duration_ms") or 64)
        event_meta["sample_time_label"] = sample_label
        event_meta["upload_time_label"] = upload_label
        event_meta["wake_reason"] = "timer"

        record["sample_time_label"] = sample_label
        record["upload_time_label"] = upload_label
        record["sample_time_local"] = sample_dt_local.strftime("%Y-%m-%d %H:%M:%S")
        record["upload_time_local"] = upload_dt_local.strftime("%Y-%m-%d %H:%M:%S")
        record["sample_time_reconstructed"] = False
        record["schema_version"] = 1
        record["replayed"] = False
        record["was_buffered"] = False
        record["ts_sample"] = next_sample_ts
        record["ts_server"] = next_server_ts
        record["ts_device"] = next_device_ts
        record["demo_template_id"] = template_id
        record["demo_template_name"] = TEMPLATE_ID_TO_NAME[template_id]

        previous_signal = int(modules_sim.get("signal_dbm") or health_overall.get("rssi") or -68)
        health_overall["online"] = True
        health_overall["rssi"] = previous_signal
        health_overall["last_sync_ts"] = next_server_ts

        sensors_npk["sample_valid"] = True
        sensors_npk["read_ok"] = True
        sensors_npk["status"] = "ok"
        sensors_npk["ts_sample"] = next_device_ts

        sensors_sht30["sample_valid"] = True
        sensors_sht30["read_ok"] = True
        sensors_sht30["status"] = "ok"
        sensors_sht30["ts_sample"] = next_device_ts

        modules_sim["network_status"] = "online"
        modules_sim["ts_sample"] = next_device_ts

        return record

    def _apply_template_mutation(
        self,
        *,
        template_id: int,
        npk_data: dict[str, Any],
        sht30_data: dict[str, Any],
        anchor_npk: dict[str, Any],
        anchor_sht30: dict[str, Any],
        step_index: int,
        total_steps: int,
    ) -> None:
        progress = 0.0 if total_steps <= 1 else step_index / max(1, total_steps - 1)
        oscillation = (-0.9, -0.3, 0.3, 0.9)[step_index % 4]

        current_soil_temp = float(anchor_npk.get("temp") or npk_data.get("temp") or 29.0)
        current_soil_humidity = float(anchor_npk.get("hum") or npk_data.get("hum") or 63.0)
        current_ec = float(anchor_npk.get("ec") or npk_data.get("ec") or 500.0)
        current_ph = float(anchor_npk.get("ph") or npk_data.get("ph") or 6.5)
        current_n = float(anchor_npk.get("N") or npk_data.get("N") or 70.0)
        current_p = float(anchor_npk.get("P") or npk_data.get("P") or 200.0)
        current_k = float(anchor_npk.get("K") or npk_data.get("K") or 200.0)
        current_air_temp = float(anchor_sht30.get("sht_temp_c") or sht30_data.get("sht_temp_c") or 30.0)
        current_air_humidity = float(anchor_sht30.get("sht_hum_pct") or sht30_data.get("sht_hum_pct") or 80.0)

        if template_id == 0:
            soil_temp = current_soil_temp + 0.25 * oscillation
            soil_humidity = current_soil_humidity + 0.8 * oscillation
            ec_value = current_ec + 4.0 * oscillation
            ph_value = current_ph + 0.03 * oscillation
            n_value = current_n + 1.5 * oscillation
            p_value = current_p + 2.0 * oscillation
            k_value = current_k + 1.5 * oscillation
            air_temp = current_air_temp + 0.35 * oscillation
            air_humidity = current_air_humidity - 1.2 * oscillation
        elif template_id == 1:
            soil_temp = current_soil_temp - 0.15 + 0.08 * oscillation
            soil_humidity = current_soil_humidity + 1.2 + 0.4 * oscillation
            ec_value = current_ec + 5.0 * oscillation
            ph_value = current_ph
            n_value = current_n
            p_value = current_p
            k_value = current_k
            air_temp = max(23.5, current_air_temp - 0.6 + 0.1 * oscillation)
            air_humidity = min(99.99, current_air_humidity + 3.5 + 0.8 * abs(oscillation))
        elif template_id == 2:
            soil_temp = current_soil_temp + 0.9 + (1.6 * progress)
            soil_humidity = max(24.0, current_soil_humidity - (7.0 + 14.0 * progress))
            ec_value = current_ec + (45.0 + 110.0 * progress)
            ph_value = max(5.8, current_ph - (0.05 + 0.1 * progress))
            n_value = max(10.0, current_n - (4.0 + 6.0 * progress))
            p_value = max(20.0, current_p - (6.0 + 10.0 * progress))
            k_value = max(20.0, current_k - (5.0 + 8.0 * progress))
            air_temp = current_air_temp + 1.0 + 1.6 * progress
            air_humidity = max(45.0, current_air_humidity - (8.0 + 14.0 * progress))
        elif template_id == 3:
            soil_temp = current_soil_temp - (0.4 + 0.3 * progress)
            soil_humidity = min(94.0, current_soil_humidity + (4.5 + 6.0 * progress))
            ec_value = max(150.0, current_ec - (18.0 + 5.0 * progress))
            ph_value = current_ph
            n_value = current_n
            p_value = current_p
            k_value = current_k
            air_temp = max(21.0, current_air_temp - (2.2 + 1.2 * progress))
            air_humidity = min(99.99, max(95.5, current_air_humidity + (10.0 + 2.0 * progress)))
        else:
            soil_temp = current_soil_temp + 0.15
            soil_humidity = min(96.0, current_soil_humidity + (6.5 + 4.5 * progress))
            ec_value = current_ec + (95.0 + 70.0 * (1.0 - 0.5 * progress))
            ph_value = min(7.4, current_ph + (0.05 + 0.06 * progress))
            n_value = current_n + (18.0 + 12.0 * (1.0 - 0.2 * progress))
            p_value = current_p + (24.0 + 14.0 * (1.0 - 0.2 * progress))
            k_value = current_k + (18.0 + 12.0 * (1.0 - 0.2 * progress))
            air_temp = max(22.0, current_air_temp - (0.6 + 0.2 * progress))
            air_humidity = min(99.99, current_air_humidity + (6.0 + 3.0 * progress))

        npk_data["temp"] = round(soil_temp, 2)
        npk_data["hum"] = round(soil_humidity, 2)
        npk_data["ec"] = int(round(ec_value))
        npk_data["ph"] = round(ph_value, 1)
        npk_data["N"] = int(round(n_value))
        npk_data["P"] = int(round(p_value))
        npk_data["K"] = int(round(k_value))
        npk_data["sensor_alarm"] = False
        npk_data["npk_signal_present"] = True
        npk_data["npk_values_valid"] = True
        npk_data["read_ok"] = True
        npk_data["retry_count"] = 0
        npk_data["consecutive_fail_count"] = 0

        sht30_data["sht_temp_c"] = round(air_temp, 2)
        sht30_data["sht_hum_pct"] = round(min(99.99, max(35.0, air_humidity)), 2)
        sht30_data["sht_read_ok"] = True
        sht30_data["sht_retry_count"] = 0
        sht30_data["sht_invalid_streak"] = 0
        sht30_data["sht_sample_valid"] = True

    def _build_latest_meta_payload(
        self,
        *,
        latest_meta: dict[str, Any],
        latest_record: dict[str, Any],
        event_key: str,
        date_key: str,
    ) -> dict[str, Any]:
        previous_ts_server = int(latest_meta.get("ts_server") or latest_record["ts_server"])
        previous_ts_device = int(latest_meta.get("ts_device") or latest_record["ts_device"])
        delta_server_sec = int(latest_record["ts_server"]) - previous_ts_server
        delta_device_sec = int(latest_record["ts_device"]) - previous_ts_device
        primary_poll_after_sec = int(latest_meta.get("primary_poll_after_sec") or 900)
        tolerance = max(60, primary_poll_after_sec // 3)
        expected_min = max(0, primary_poll_after_sec - tolerance)
        expected_max = primary_poll_after_sec + tolerance
        return {
            "schema_version": 1,
            "node_id": self.settings.node_id,
            "latest_date_key": date_key,
            "latest_event_key": event_key,
            "latest_local_iso": latest_record.get("sample_time_local"),
            "latest_path": f"{self.settings.telemetry_root_path}/{date_key}/{event_key}",
            "previous_date_key": latest_meta.get("latest_date_key"),
            "previous_event_key": latest_meta.get("latest_event_key"),
            "previous_path": latest_meta.get("latest_path"),
            "previous_ts_device": previous_ts_device,
            "previous_ts_server": previous_ts_server,
            "delta_device_sec": delta_device_sec,
            "delta_server_sec": delta_server_sec,
            "expected_device_min_sec": expected_min,
            "expected_device_max_sec": expected_max,
            "expected_server_min_sec": expected_min,
            "expected_server_max_sec": expected_max,
            "device_in_expected_range": expected_min <= delta_device_sec <= expected_max,
            "server_in_expected_range": expected_min <= delta_server_sec <= expected_max,
            "primary_poll_after_sec": primary_poll_after_sec,
            "retry_after_no_change_sec": int(latest_meta.get("retry_after_no_change_sec") or 300),
            "record_sha256": f"demo_{event_key}_{TEMPLATE_ID_TO_NAME[int(latest_record['demo_template_id'])]}",
            "ts_device": int(latest_record["ts_device"]),
            "ts_server": int(latest_record["ts_server"]),
            "updated_at_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def _build_live_payload(
        self,
        *,
        live_root: dict[str, Any],
        latest_record: dict[str, Any],
        event_key: str,
    ) -> dict[str, Any]:
        payload = copy.deepcopy(live_root)
        payload["schema_version"] = 1
        sensors = payload.setdefault("sensors", {})
        sensors["npk"] = {
            **sensors.get("npk", {}),
            "n": latest_record["packet"]["npk_data"]["N"],
            "p": latest_record["packet"]["npk_data"]["P"],
            "k": latest_record["packet"]["npk_data"]["K"],
            "ec": latest_record["packet"]["npk_data"]["ec"],
            "ph": latest_record["packet"]["npk_data"]["ph"],
            "humidity_percent": latest_record["packet"]["npk_data"]["hum"],
            "temperature_c": latest_record["packet"]["npk_data"]["temp"],
            "sample_valid": True,
            "read_ok": True,
            "status": "ok",
            "ts_sample": int(latest_record["ts_device"]),
        }
        sensors["sht30"] = {
            **sensors.get("sht30", {}),
            "humidity_percent": latest_record["packet"]["sht30_data"]["sht_hum_pct"],
            "temperature_c": latest_record["packet"]["sht30_data"]["sht_temp_c"],
            "sample_valid": True,
            "read_ok": True,
            "status": "ok",
            "ts_sample": int(latest_record["ts_device"]),
        }
        payload.setdefault("meta", {})
        payload["meta"]["last_event_id"] = event_key
        payload["meta"]["last_seen_ts"] = int(latest_record["ts_device"])
        payload["meta"]["last_sync_ts"] = int(latest_record["ts_server"])
        payload.setdefault("health", {}).setdefault("overall", {})
        payload["health"]["overall"]["last_sync_ts"] = int(latest_record["ts_server"])
        payload["health"]["overall"]["online"] = True
        return payload

    def _local_datetime(self, inject_date_key: str, *, hour: int, minute: int) -> datetime:
        target_date = datetime.strptime(inject_date_key, "%Y-%m-%d").date()
        return datetime(
            year=target_date.year,
            month=target_date.month,
            day=target_date.day,
            hour=hour,
            minute=minute,
            tzinfo=self.settings.timezone,
        )

    def _resolve_server_ts_from_path(self, telemetry_path: str) -> int:
        try:
            return int(str(telemetry_path).rsplit("/", maxsplit=1)[-1])
        except (TypeError, ValueError):
            return 0
