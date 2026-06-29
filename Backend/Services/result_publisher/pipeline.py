from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

try:
    from Config.runtime import BackendSettings
    from Services.result_publisher.report_charts import render_report_chart_bundle
except ModuleNotFoundError:
    from ...Config.runtime import BackendSettings
    from .report_charts import render_report_chart_bundle


METRIC_LIMITS: dict[str, tuple[float | None, float | None]] = {
    "temperature_c": (None, None),
    "humidity_pct": (0.0, 100.0),
    "ph": (0.0, 14.0),
    "ec_us_cm": (0.0, None),
    "n_ppm": (0.0, None),
    "p_ppm": (0.0, None),
    "k_ppm": (0.0, None),
    "rain_mm": (0.0, None),
    "cloud_cover_pct": (0.0, 100.0),
    "et0_mm": (0.0, None),
}

GROUP_FIELD_MAP: dict[str, dict[str, str]] = {
    "air": {
        "temp_air_c": "temperature_c",
        "humidity_air_pct": "humidity_pct",
    },
    "soil": {
        "soil_temp_c": "temperature_c",
        "soil_humidity_pct": "humidity_pct",
        "soil_ph": "ph",
        "soil_ec_us_cm": "ec_us_cm",
    },
    "npk": {
        "n_ppm": "n_ppm",
        "p_ppm": "p_ppm",
        "k_ppm": "k_ppm",
    },
    "weather": {
        "temp_air_c": "temperature_c",
        "humidity_air_pct": "humidity_pct",
        "rain_mm": "rain_mm",
        "precipitation_mm": "precipitation_mm",
        "dew_point_c": "dew_point_c",
        "cloud_cover_pct": "cloud_cover_pct",
        "soil_temp_0_7cm_c": "soil_temperature_0_7cm_c",
        "et0_mm": "et0_mm",
    },
}

FEATURE_COLUMNS = [
    "soil_temp",
    "soil_humidity",
    "air_temp",
    "air_humidity",
    "EC",
    "air_temp_delta_1step",
    "soil_temp_delta_1step",
    "soil_humidity_delta_1step",
    "EC_delta_1step",
    "air_temp_slope_3h",
    "air_temp_range_3h",
    "air_temp_mean_3h",
    "soil_temp_slope_3h",
    "soil_humidity_slope_3h",
    "soil_humidity_range_3h",
    "EC_slope_3h",
    "EC_range_3h",
]

STATE_LIVE_SYNCING = "live_syncing"
STATE_AWAITING_ANALYSIS = "awaiting_server_analysis"
STATE_HISTORICAL_VIEW = "historical_view"
STATE_OFFLINE_ERROR = "offline_error"
PAYLOAD_SCOPE_FULL = "full"
PAYLOAD_SCOPE_DIAGNOSIS_ONLY = "diagnosis-only"
DEFAULT_RUNTIME_EXPERIMENTS = ("v0", "v1", "v2")
DISPLAY_LABELS = {
    "normal_context": "Binh thuong",
    "packet_loss_outage": "Packet loss outage",
    "water_deficit": "Thieu nuoc",
    "rain_or_fertigation_context": "Mua-am hoac tuoi-bon",
    "moisture_or_intervention_context": "Mua-am hoac tuoi-bon",
}


@dataclass(frozen=True)
class ResultPublishPaths:
    output_root: Path
    state_path: Path
    payload_path: Path
    manifest_path: Path
    chart_root: Path
    chart_manifest_path: Path
    benchmark_root: Path

    @classmethod
    def from_settings(cls, settings: BackendSettings) -> "ResultPublishPaths":
        output_root = settings.output_data_root / "Result_publish"
        return cls(
            output_root=output_root,
            state_path=output_root / "result_sync_state.json",
            payload_path=output_root / "latest_result_payload.json",
            manifest_path=output_root / "latest_publish_manifest.json",
            chart_root=output_root / "report_charts",
            chart_manifest_path=output_root / "report_charts" / "chart_manifest.json",
            benchmark_root=settings.server_dir / "Benchmark",
        )


@dataclass(frozen=True)
class BenchmarkModelArtifact:
    report_path: Path
    experiment_dir: Path
    experiment_name: str
    source_kind: str
    model_name: str
    label_mode: str
    artifact_path: Path
    feature_schema_path: Path
    direct_dataset_path: Path
    scaler_path: Path
    imputer_path: Path
    label_policy_path: Path
    validation_accuracy: float
    validation_macro_f1: float


@dataclass(frozen=True)
class ResultPublishRunResult:
    status: str
    requested_mode: str
    effective_mode: str
    dry_run: bool
    payload_scope: str
    result_path: str
    last_published_ts: int | None
    history_counts: dict[str, int]
    history_last_ts: dict[str, int | None]
    diagnosis_label: str | None
    diagnosis_probability: float | None
    runtime_model_family: str | None
    runtime_experiment: str | None
    state_path: Path
    payload_path: Path
    manifest_path: Path


def _resolve_existing_runtime_artifact_path(path: Path) -> Path:
    if path.exists():
        return path

    path_text = str(path)
    legacy_marker = f"{Path('Benchmark')}{os.sep}direct_benchmark{os.sep}"
    current_marker = f"{Path('Benchmark')}{os.sep}tabular_benchmark{os.sep}"
    if legacy_marker in path_text:
        remapped = Path(path_text.replace(legacy_marker, current_marker, 1))
        if remapped.exists():
            return remapped

    if "direct_benchmark" in path.parts:
        parts = list(path.parts)
        remapped_parts = ["tabular_benchmark" if part == "direct_benchmark" else part for part in parts]
        remapped = Path(*remapped_parts)
        if remapped.exists():
            return remapped

    if "direct_benchmark" in path_text:
        remapped = Path(path_text.replace("direct_benchmark", "tabular_benchmark", 1))
        if remapped.exists():
            return remapped

    return path


class RuntimeDiagnosisModel:
    def __init__(self, artifact: BenchmarkModelArtifact):
        self.artifact = artifact
        self.model = joblib.load(artifact.artifact_path)
        self.label_policy = _load_json(artifact.label_policy_path)
        feature_schema = _load_json(artifact.feature_schema_path)
        self.feature_columns = feature_schema.get("feature_columns", FEATURE_COLUMNS)
        self.class_names = self.label_policy.get("class_names", ["normal", "abnormal"])
        self.use_raw_inference = artifact.model_name == "xgboost"
        self.imputer, self.scaler = (None, None) if self.use_raw_inference else self._build_runtime_transformers()

    def _build_runtime_transformers(self) -> tuple[SimpleImputer, StandardScaler]:
        dataset = pd.read_csv(self.artifact.direct_dataset_path)
        split_column = "direct_split" if "direct_split" in dataset.columns else "split"
        if split_column in dataset.columns:
            train_frame = dataset.loc[dataset[split_column] == "train", self.feature_columns].copy()
        else:
            train_frame = dataset[self.feature_columns].copy()
        train_matrix = train_frame.to_numpy(dtype=np.float32)
        imputer = SimpleImputer(strategy="median")
        imputed = imputer.fit_transform(train_matrix)
        scaler = StandardScaler()
        scaler.fit(imputed)
        return imputer, scaler

    def predict(self, feature_row: dict[str, float | None]) -> dict[str, Any]:
        ordered_row = [[feature_row.get(column) for column in self.feature_columns]]
        if self.use_raw_inference:
            inference_frame = pd.DataFrame(ordered_row, columns=self.feature_columns)
            class_ids = self.model.predict(inference_frame)
            probabilities = self.model.predict_proba(inference_frame)[0].tolist()
        else:
            matrix = np.asarray(ordered_row, dtype=np.float32)
            imputed = self.imputer.transform(matrix)
            scaled = self.scaler.transform(imputed)
            class_ids = self.model.predict(scaled)
            probabilities = self.model.predict_proba(scaled)[0].tolist()
        predicted_id = int(class_ids[0])
        predicted_label = self.class_names[predicted_id]
        probability_map = {
            class_name: float(probabilities[index])
            for index, class_name in enumerate(self.class_names)
        }
        abnormal_probability = self._resolve_abnormal_probability(probability_map)
        return {
            "label": predicted_label,
            "labelId": predicted_id,
            "probabilities": probability_map,
            "abnormalProbability": abnormal_probability,
            "featureColumns": list(self.feature_columns),
        }

    def _resolve_abnormal_probability(self, probability_map: dict[str, float]) -> float | None:
        if "abnormal" in probability_map:
            return float(probability_map.get("abnormal", 0.0))
        if "normal_context" in probability_map:
            return float(1.0 - probability_map.get("normal_context", 0.0))
        if "normal" in probability_map:
            return float(1.0 - probability_map.get("normal", 0.0))
        return None


class ResultPublisherPipeline:
    def __init__(self, *, settings: BackendSettings, firebase_service: Any, result_path: str = "result"):
        self.settings = settings
        self.firebase_service = firebase_service
        self.result_path = result_path.strip("/") or "result"
        self.paths = ResultPublishPaths.from_settings(settings)

    def run(
        self,
        *,
        mode: str = "snapshot",
        dry_run: bool = False,
        payload_scope: str = PAYLOAD_SCOPE_FULL,
        runtime_experiment: str = "auto",
    ) -> ResultPublishRunResult:
        requested_mode = mode.strip().lower()
        if requested_mode not in {"snapshot", "append"}:
            raise ValueError(f"Unsupported result publish mode: {mode}")
        normalized_payload_scope = str(payload_scope).strip().lower()
        if normalized_payload_scope not in {PAYLOAD_SCOPE_FULL, PAYLOAD_SCOPE_DIAGNOSIS_ONLY}:
            raise ValueError(f"Unsupported result payload scope: {payload_scope}")
        normalized_runtime_experiment = str(runtime_experiment).strip().lower()
        if normalized_runtime_experiment not in {"auto", *DEFAULT_RUNTIME_EXPERIMENTS}:
            raise ValueError(f"Unsupported result runtime experiment: {runtime_experiment}")

        self.paths.output_root.mkdir(parents=True, exist_ok=True)
        bundle = self._load_layer1_bundle()
        diagnosis_payload, model_artifact = self._build_diagnosis(
            bundle,
            runtime_experiment=normalized_runtime_experiment,
        )
        rule_signals = self._build_rule_signals(bundle)
        anomalies = self._build_anomalies_from_rule_signals(rule_signals)
        recommendations = self._build_recommendations(bundle=bundle, diagnosis_payload=diagnosis_payload)
        forecast = self._build_forecast(bundle)

        effective_mode = requested_mode
        previous_state = self._load_state()

        pipeline_payload = self._build_pipeline_state(
            effective_mode=effective_mode,
            has_new_records=self._has_new_records(bundle, previous_state),
            diagnosis_payload=diagnosis_payload,
            dry_run=dry_run,
        )
        payload = self._build_result_payload(
            bundle=bundle,
            payload_scope=normalized_payload_scope,
            pipeline_payload=pipeline_payload,
            diagnosis_payload=diagnosis_payload,
            model_artifact=model_artifact,
            forecast=forecast,
            rule_signals=rule_signals,
            anomalies=anomalies,
            recommendations=recommendations,
        )
        _write_json(self.paths.payload_path, payload)
        chart_manifest = self._build_report_charts(
            payload=payload,
            payload_scope=normalized_payload_scope,
        )
        _write_json(self.paths.chart_manifest_path, chart_manifest)

        published = True
        if not dry_run:
            if self.firebase_service is None:
                raise ValueError("firebase_service is required when dry_run=False")
            if effective_mode == "snapshot":
                published = self.firebase_service.set_data(self.result_path, payload)
            else:
                published = self._publish_append(payload=payload, previous_state=previous_state)

        history_counts = {
            group: len(records)
            for group, records in payload["history"].items()
        }
        history_last_ts = {
            group: max(records) if records else None
            for group, records in bundle["histories"].items()
        }
        current_state = {
            "resultPath": self.result_path,
            "lastPublishedTs": payload["meta"]["lastPublishedTs"],
            "mode": effective_mode,
            "payloadScope": normalized_payload_scope,
            "historyLastTs": history_last_ts,
            "diagnosisTs": diagnosis_payload.get("ts") if diagnosis_payload else None,
            "updatedAtLocal": _now_local_iso(self.settings),
        }
        _write_json(self.paths.state_path, current_state)

        manifest = {
            "status": "dry_run" if dry_run else ("published" if published else "publish_failed"),
            "requestedMode": requested_mode,
            "effectiveMode": effective_mode,
            "dryRun": dry_run,
            "payloadScope": normalized_payload_scope,
            "runtimeExperimentPolicy": normalized_runtime_experiment,
            "localStateAvailable": previous_state is not None,
            "resultPath": self.result_path,
            "historyCounts": history_counts,
            "localHistoryCounts": {
                group: len(records) for group, records in bundle["histories"].items()
            },
            "historyLastTs": history_last_ts,
            "latestTsByGroup": {
                group: latest_payload.get("ts")
                for group, latest_payload in payload["latest"].items()
            },
            "diagnosis": diagnosis_payload,
            "modelArtifact": None
            if model_artifact is None
            else {
                "reportPath": str(model_artifact.report_path),
                "artifactPath": str(model_artifact.artifact_path),
                "experimentName": model_artifact.experiment_name,
                "sourceKind": model_artifact.source_kind,
                "validationMacroF1": model_artifact.validation_macro_f1,
            },
            "diagnosisModel": None if diagnosis_payload is None else diagnosis_payload.get("model"),
            "payloadPath": str(self.paths.payload_path),
            "statePath": str(self.paths.state_path),
            "reportChartManifestPath": str(self.paths.chart_manifest_path),
            "reportCharts": chart_manifest,
            "updatedAtLocal": _now_local_iso(self.settings),
        }
        _write_json(self.paths.manifest_path, manifest)

        return ResultPublishRunResult(
            status=manifest["status"],
            requested_mode=requested_mode,
            effective_mode=effective_mode,
            dry_run=dry_run,
            payload_scope=normalized_payload_scope,
            result_path=self.result_path,
            last_published_ts=payload["meta"]["lastPublishedTs"],
            history_counts=history_counts,
            history_last_ts=history_last_ts,
            diagnosis_label=None if diagnosis_payload is None else diagnosis_payload.get("label"),
            diagnosis_probability=None
            if diagnosis_payload is None
            else diagnosis_payload.get("abnormalProbability"),
            runtime_model_family=None
            if diagnosis_payload is None
            else _runtime_model_family_from_payload(diagnosis_payload),
            runtime_experiment=None
            if diagnosis_payload is None
            else _runtime_experiment_from_payload(diagnosis_payload),
            state_path=self.paths.state_path,
            payload_path=self.paths.payload_path,
            manifest_path=self.paths.manifest_path,
        )

    def _build_report_charts(self, *, payload: dict[str, Any], payload_scope: str) -> dict[str, Any]:
        history_payload = payload.get("history", {})
        if payload_scope != PAYLOAD_SCOPE_FULL or not any(history_payload.get(group_name) for group_name in history_payload):
            return {
                "status": "skipped",
                "outputRoot": str(self.paths.chart_root),
                "updatedAtLocal": _now_local_iso(self.settings),
                "reason": "history_not_requested",
                "chartCount": 0,
                "charts": [],
            }
        try:
            return render_report_chart_bundle(
                payload=payload,
                output_root=self.paths.chart_root,
                timezone_name=self.settings.timezone_name,
                updated_at_local=_now_local_iso(self.settings),
            )
        except Exception as exc:
            return {
                "status": "chart_render_failed",
                "outputRoot": str(self.paths.chart_root),
                "updatedAtLocal": _now_local_iso(self.settings),
                "error": repr(exc),
                "chartCount": 0,
                "charts": [],
            }

    def _load_layer1_bundle(self) -> dict[str, Any]:
        layer1_root = self.settings.layer1_root
        raw_latest = {
            "sht30": _load_json_or_default(layer1_root / "sht30" / "latest.json", default={}),
            "npk": _load_json_or_default(layer1_root / "npk" / "latest.json", default={}),
            "meteo": _load_json_or_default(layer1_root / "meteo" / "latest.json", default={}),
        }
        histories = {
            "air": self._load_history_group(layer1_root / "sht30" / "history.jsonl", group_name="air"),
            "soil": self._load_history_group(layer1_root / "npk" / "history.jsonl", group_name="soil"),
            "npk": self._load_history_group(layer1_root / "npk" / "history.jsonl", group_name="npk"),
            "weather": self._load_history_group(layer1_root / "meteo" / "history.jsonl", group_name="weather"),
        }
        latest = {
            "air": self._record_to_group_point(raw_latest["sht30"], group_name="air"),
            "soil": self._record_to_group_point(raw_latest["npk"], group_name="soil"),
            "npk": self._record_to_group_point(raw_latest["npk"], group_name="npk"),
            "weather": self._record_to_group_point(raw_latest["meteo"], group_name="weather"),
        }
        feature_rows = self._build_feature_rows(histories["air"], histories["soil"], histories["npk"])
        latest_feature_row = feature_rows[-1] if feature_rows else None
        return {
            "histories": histories,
            "latest": latest,
            "rawLatest": raw_latest,
            "featureRows": feature_rows,
            "latestFeatureRow": latest_feature_row,
        }

    def _build_diagnosis(
        self,
        bundle: dict[str, Any],
        *,
        runtime_experiment: str,
    ) -> tuple[dict[str, Any] | None, BenchmarkModelArtifact | None]:
        latest_feature_row = bundle["latestFeatureRow"]
        if latest_feature_row is None:
            return None, None
        allowed_experiments = _resolve_runtime_experiment_filter(runtime_experiment)
        model_artifact = self._discover_best_runtime_tabular_artifact(
            label_mode="four_class",
            allowed_experiments=allowed_experiments,
        )
        if model_artifact is None:
            model_artifact = self._discover_best_runtime_tabular_artifact(
                label_mode="binary",
                allowed_experiments=allowed_experiments,
            )
        if model_artifact is None:
            return (
                {
                    "status": "model_unavailable",
                    "label": "unknown",
                    "labelId": -1,
                    "displayLabel": "Khong co mo hinh san sang",
                    "abnormalProbability": None,
                    "ts": latest_feature_row["timestamp"],
                    "requestedExperiment": runtime_experiment,
                },
                None,
            )
        try:
            model = RuntimeDiagnosisModel(model_artifact)
            prediction = model.predict(latest_feature_row)
        except Exception as exc:
            return (
                {
                    "status": "model_error",
                    "label": "unknown",
                    "labelId": -1,
                    "displayLabel": "Loi mo hinh XGBoost",
                    "abnormalProbability": None,
                    "ts": latest_feature_row["timestamp"],
                    "error": repr(exc),
                },
                model_artifact,
            )

        predicted_label = str(prediction["label"])
        abnormal_probability = prediction["abnormalProbability"]
        severity = _severity_from_probability(abnormal_probability)
        return (
            {
                "status": "ready",
                "label": predicted_label,
                "displayLabel": display_label_for_runtime_label(predicted_label),
                "labelId": prediction["labelId"],
                "abnormalProbability": abnormal_probability,
                "probabilities": prediction["probabilities"],
                "severity": severity,
                "ts": latest_feature_row["timestamp"],
                "model": {
                    "family": model_artifact.model_name,
                    "labelScheme": model_artifact.label_mode,
                    "artifactPath": str(model_artifact.artifact_path),
                    "experimentName": model_artifact.experiment_name,
                    "sourceKind": model_artifact.source_kind,
                    "validationAccuracy": model_artifact.validation_accuracy,
                    "validationMacroF1": model_artifact.validation_macro_f1,
                    "requestedExperiment": runtime_experiment,
                },
            },
            model_artifact,
        )

    def _build_pipeline_state(
        self,
        *,
        effective_mode: str,
        has_new_records: bool,
        diagnosis_payload: dict[str, Any] | None,
        dry_run: bool,
    ) -> dict[str, Any]:
        if dry_run:
            state = STATE_HISTORICAL_VIEW
            detail = "Dry-run: da dong goi payload tu local artifact, chua ghi len Firebase."
        elif effective_mode == "snapshot":
            state = STATE_HISTORICAL_VIEW
            detail = "Da bootstrap lich su tu local artifact len nhanh result."
        elif diagnosis_payload is None or diagnosis_payload.get("status") != "ready":
            state = STATE_AWAITING_ANALYSIS
            detail = "Da thu thap du lieu moi, dang cho phan tich hoac model chua san sang."
        elif has_new_records:
            state = STATE_LIVE_SYNCING
            detail = "Dang dong bo ban ghi moi va cap nhat ket qua phan tich len result."
        else:
            state = STATE_HISTORICAL_VIEW
            detail = "Khong co ban ghi moi, dang hien thi lich su da dong bo."
        return {
            "state": state,
            "detail": detail,
            "lastSyncTs": _max_ts_from_payloads(self._load_latest_group_points()),
            "lastAnalysisTs": None if diagnosis_payload is None else diagnosis_payload.get("ts"),
            "updatedAtLocal": _now_local_iso(self.settings),
        }

    def _build_result_payload(
        self,
        *,
        bundle: dict[str, Any],
        payload_scope: str,
        pipeline_payload: dict[str, Any],
        diagnosis_payload: dict[str, Any] | None,
        model_artifact: BenchmarkModelArtifact | None,
        forecast: dict[str, dict[str, Any]],
        rule_signals: dict[str, Any],
        anomalies: dict[str, Any],
        recommendations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        last_published_ts = _max_ts_from_payloads(bundle["latest"])
        history_payload = self._resolve_history_payload(bundle=bundle, payload_scope=payload_scope)
        history_range = {
            group: {
                "startTs": None if not records else min(records),
                "endTs": None if not records else max(records),
                "count": len(records),
            }
            for group, records in history_payload.items()
        }
        analysis_status = "ready"
        if diagnosis_payload is None:
            analysis_status = "pending_features"
        elif diagnosis_payload.get("status") != "ready":
            analysis_status = diagnosis_payload.get("status", "model_unavailable")

        return {
            "meta": {
                "snapshotVersion": _now_local_iso(self.settings),
                "lastPublishedTs": last_published_ts,
                "source": "server",
                "payloadScope": payload_scope,
                "historyRange": history_range,
            },
            "pipeline": pipeline_payload,
            "latest": bundle["latest"],
            "history": {
                group: {str(ts): payload for ts, payload in records.items()}
                for group, records in history_payload.items()
            },
            "analysis": {
                "status": analysis_status,
                "priority": _analysis_priority(diagnosis_payload, anomalies),
                "modelName": _analysis_model_name(diagnosis_payload, model_artifact),
                "source": "server",
                "lastAnalysisTs": None if diagnosis_payload is None else diagnosis_payload.get("ts"),
                "diagnosis": diagnosis_payload,
                "ruleSignals": rule_signals,
                "forecast": forecast,
                "anomalies": anomalies,
                "recommendations": recommendations,
            },
        }

    def _build_forecast(self, bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
        raw_latest = bundle["rawLatest"]
        return {
            "air": self._forecast_group(raw_latest["sht30"], group_name="air"),
            "soil": self._forecast_group(raw_latest["npk"], group_name="soil"),
            "npk": self._forecast_group(raw_latest["npk"], group_name="npk"),
            "weather": self._forecast_group(raw_latest["meteo"], group_name="weather"),
        }

    def _resolve_history_payload(
        self,
        *,
        bundle: dict[str, Any],
        payload_scope: str,
    ) -> dict[str, dict[int, dict[str, Any]]]:
        if payload_scope == PAYLOAD_SCOPE_FULL:
            return bundle["histories"]
        return {
            group_name: {}
            for group_name in bundle["histories"]
        }

    def _forecast_group(self, raw_record: dict[str, Any], *, group_name: str) -> dict[str, Any]:
        latest_point = self._record_to_group_point(raw_record, group_name=group_name)
        ts = latest_point.get("ts")
        if ts is None:
            return {}
        windows = raw_record.get("memory", {}).get("windows", {})
        preferred_window = windows.get("3h") or windows.get("6h") or {}
        forecast: dict[str, Any] = {}
        for horizon_hours in (1, 2, 3, 4, 5, 6):
            future_ts = int(ts) + horizon_hours * 3600
            point: dict[str, Any] = {"ts": future_ts}
            for raw_key, output_key in GROUP_FIELD_MAP[group_name].items():
                current_value = latest_point.get(output_key)
                if current_value is None:
                    continue
                metric_window = preferred_window.get(raw_key, {})
                slope = metric_window.get("trend_per_hour")
                metric_range = None
                metric_min = metric_window.get("min")
                metric_max = metric_window.get("max")
                if metric_min is not None and metric_max is not None:
                    metric_range = float(metric_max) - float(metric_min)
                predicted = float(current_value)
                if slope is not None:
                    predicted += float(slope) * horizon_hours
                predicted = _clamp_metric(output_key, predicted)
                uncertainty = max(
                    0.05,
                    abs(float(metric_range or 0.0)) * 0.12,
                    abs(float(slope or 0.0)) * horizon_hours * 0.18,
                )
                point[output_key] = round(predicted, 4)
                point[f"{output_key}_lower"] = round(_clamp_metric(output_key, predicted - uncertainty), 4)
                point[f"{output_key}_upper"] = round(_clamp_metric(output_key, predicted + uncertainty), 4)
            forecast[str(future_ts)] = point
        return forecast

    def _build_rule_signals(self, bundle: dict[str, Any]) -> dict[str, Any]:
        rule_signals: dict[str, Any] = {}
        for source_name, raw_record in bundle["rawLatest"].items():
            fuzzy_signals = raw_record.get("fuzzy_signals", {}).get("signals", {})
            ts = _safe_int(raw_record.get("timestamps", {}).get("ts_server"))
            for signal_name, signal_payload in fuzzy_signals.items():
                level = str(signal_payload.get("level", "normal")).lower()
                if level not in {"watch", "warning", "critical"}:
                    continue
                groups, metrics = _map_signal_to_scope(signal_name)
                signal_id = f"{source_name}_{signal_name}_{ts}"
                rule_signals[signal_id] = {
                    "ts": ts,
                    "label": _signal_label(signal_name, signal_payload),
                    "severity": level,
                    "groups": groups,
                    "metrics": metrics,
                    "score": _safe_float(signal_payload.get("risk_score")),
                    "source": "layer1_fuzzy",
                }
        return rule_signals

    def _build_anomalies_from_rule_signals(
        self,
        rule_signals: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        anomalies: dict[str, dict[str, Any]] = {}
        for signal_id, signal_payload in rule_signals.items():
            groups = signal_payload.get("groups", [])
            metrics = signal_payload.get("metrics", [])
            anomalies[signal_id] = {
                "ts": signal_payload.get("ts"),
                "label": signal_payload.get("label"),
                "severity": signal_payload.get("severity"),
                "groupIds": groups,
                "groups": groups,
                "metricIds": metrics,
                "metrics": metrics,
                "value": signal_payload.get("score"),
                "source": signal_payload.get("source"),
            }
        return anomalies

    def _publish_append(self, *, payload: dict[str, Any], previous_state: dict[str, Any] | None) -> bool:
        result_ok = True
        history_last_ts = {} if previous_state is None else previous_state.get("historyLastTs", {})
        history_payload = payload["history"]
        for group_name, group_records in history_payload.items():
            last_ts = _safe_int(history_last_ts.get(group_name))
            for ts_text, record_payload in group_records.items():
                ts_value = _safe_int(ts_text)
                if last_ts is not None and ts_value is not None and ts_value <= last_ts:
                    continue
                path = f"{self.result_path}/history/{group_name}/{ts_text}"
                result_ok = self.firebase_service.set_data(path, record_payload) and result_ok

        result_ok = self.firebase_service.set_data(f"{self.result_path}/meta", payload["meta"]) and result_ok
        result_ok = self.firebase_service.set_data(f"{self.result_path}/pipeline", payload["pipeline"]) and result_ok
        result_ok = self.firebase_service.set_data(f"{self.result_path}/latest", payload["latest"]) and result_ok
        result_ok = self.firebase_service.set_data(f"{self.result_path}/analysis", payload["analysis"]) and result_ok
        return result_ok

    def _has_new_records(self, bundle: dict[str, Any], previous_state: dict[str, Any] | None) -> bool:
        if previous_state is None:
            return True
        history_last_ts = previous_state.get("historyLastTs", {})
        for group_name, group_records in bundle["histories"].items():
            if not group_records:
                continue
            current_last_ts = max(group_records)
            previous_last_ts = _safe_int(history_last_ts.get(group_name))
            if previous_last_ts is None or current_last_ts > previous_last_ts:
                return True
        return False

    def _discover_best_runtime_tabular_artifact(
        self,
        *,
        label_mode: str,
        allowed_experiments: tuple[str, ...],
    ) -> BenchmarkModelArtifact | None:
        candidate_roots = [
            self.paths.benchmark_root / "tabular_benchmark" / "artifacts" / label_mode / "training",
        ]
        best_candidate: BenchmarkModelArtifact | None = None
        for direct_root in candidate_roots:
            if not direct_root.exists():
                continue
            for report_path in direct_root.rglob("training_report.json"):
                report = _load_json(report_path)
                if "models" not in report or "experiment_name" not in report:
                    continue
                if str(report.get("label_mode", "")).strip() != label_mode:
                    continue
                experiment_name = str(report.get("experiment_name", report_path.parent.name)).strip()
                if experiment_name not in allowed_experiments:
                    continue
                for model_payload in report.get("models", []):
                    if model_payload.get("model_name") != "xgboost":
                        continue
                    if not model_payload.get("available", False):
                        continue
                    validation_accuracy = float(model_payload.get("validation_accuracy", -1.0))
                    validation_macro_f1 = float(model_payload.get("validation_macro_f1", -1.0))
                    experiment_dir = report_path.parent
                    artifact_path = _resolve_existing_runtime_artifact_path(Path(model_payload["artifact_path"]))
                    candidate = BenchmarkModelArtifact(
                        report_path=report_path,
                        experiment_dir=experiment_dir,
                        experiment_name=experiment_name,
                        source_kind=str(report.get("source_kind", experiment_name)),
                        model_name=str(model_payload.get("model_name", "xgboost")),
                        label_mode=label_mode,
                        artifact_path=artifact_path,
                        feature_schema_path=experiment_dir / "feature_schema.json",
                        direct_dataset_path=experiment_dir / "direct_dataset.csv",
                        scaler_path=experiment_dir / "scaler.pkl",
                        imputer_path=experiment_dir / "imputer.pkl",
                        label_policy_path=experiment_dir / "label_policy.json",
                        validation_accuracy=validation_accuracy,
                        validation_macro_f1=validation_macro_f1,
                    )
                    if not (
                        candidate.artifact_path.exists()
                        and candidate.feature_schema_path.exists()
                        and candidate.direct_dataset_path.exists()
                        and candidate.label_policy_path.exists()
                    ):
                        continue
                    if best_candidate is None or (
                        candidate.validation_macro_f1,
                        candidate.validation_accuracy,
                    ) > (
                        best_candidate.validation_macro_f1,
                        best_candidate.validation_accuracy,
                    ):
                        best_candidate = candidate
        return best_candidate

    def _build_recommendations(
        self,
        *,
        bundle: dict[str, Any],
        diagnosis_payload: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        if diagnosis_payload is None or diagnosis_payload.get("status") != "ready":
            return []

        abnormal_probability = diagnosis_payload.get("abnormalProbability")
        label = str(diagnosis_payload.get("label", "unknown"))
        display_label = str(diagnosis_payload.get("displayLabel", label))
        probability_suffix = ""
        if isinstance(abnormal_probability, (int, float)) and not math.isnan(float(abnormal_probability)):
            probability_suffix = f" Xac suat bat thuong ~ {round(float(abnormal_probability) * 100.0, 1)}%."

        latest = bundle.get("latest", {})
        air_latest = latest.get("air", {}) if isinstance(latest, dict) else {}
        soil_latest = latest.get("soil", {}) if isinstance(latest, dict) else {}
        npk_latest = latest.get("npk", {}) if isinstance(latest, dict) else {}

        mapping = {
            "normal_context": {
                "level": "info",
                "groups": ["air", "soil", "npk"],
                "text": f"FT-Transformer phan loai hien tai la '{display_label}'. He thong dang o trang thai on dinh, tiep tuc theo doi chu ky tiep theo.{probability_suffix}",
            },
            "packet_loss_outage": {
                "level": "warning",
                "groups": ["air", "soil"],
                "text": f"Phat hien '{display_label}'. Kiem tra khoang gap tai telemetry, nguon dien/solar va tinh lien tuc upload truoc khi ket luan loi cam bien.{probability_suffix}",
            },
            "water_deficit": {
                "level": "warning",
                "groups": ["soil", "air"],
                "text": (
                    f"FT-Transformer nghi ngo '{display_label}'. Do am dat hien tai o muc {format_metric_value(soil_latest.get('humidity_pct'), '%')} "
                    f"va nhiet do khong khi {format_metric_value(air_latest.get('temperature_c'), 'C')}; can uu tien kiem tra ke hoach tuoi som.{probability_suffix}"
                ),
            },
            "rain_or_fertigation_context": {
                "level": "info",
                "groups": ["air", "soil", "npk"],
                "text": (
                    f"FT-Transformer phat hien '{display_label}'. Quan sat them do am khong khi {format_metric_value(air_latest.get('humidity_pct'), '%')}, "
                    f"do am dat {format_metric_value(soil_latest.get('humidity_pct'), '%')} va NPK N={format_metric_value(npk_latest.get('n_ppm'), 'ppm')} "
                    f"de xac dinh day la mua/ngu canh am hay can thiep tuoi-bon.{probability_suffix}"
                ),
            },
            "moisture_or_intervention_context": {
                "level": "info",
                "groups": ["air", "soil", "npk"],
                "text": (
                    f"FT-Transformer phat hien '{display_label}'. Quan sat them do am khong khi {format_metric_value(air_latest.get('humidity_pct'), '%')}, "
                    f"do am dat {format_metric_value(soil_latest.get('humidity_pct'), '%')} va NPK N={format_metric_value(npk_latest.get('n_ppm'), 'ppm')} "
                    f"de xac dinh day la mua/ngu canh am hay can thiep tuoi-bon.{probability_suffix}"
                ),
            },
        }
        payload = mapping.get(
            label,
            {
                "level": "info",
                "groups": ["air", "soil", "npk"],
                "text": f"Server da tra ve nhan '{display_label}'.{probability_suffix}",
            },
        )
        return [payload]

    def _build_feature_rows(
        self,
        air_history: dict[int, dict[str, Any]],
        soil_history: dict[int, dict[str, Any]],
        npk_history: dict[int, dict[str, Any]],
    ) -> list[dict[str, float | int | None]]:
        common_timestamps = sorted(set(air_history).intersection(soil_history).intersection(npk_history))
        base_rows: list[dict[str, float | int | None]] = []
        feature_rows: list[dict[str, float | int | None]] = []

        for timestamp in common_timestamps:
            air_point = air_history[timestamp]
            soil_point = soil_history[timestamp]
            npk_point = npk_history[timestamp]
            base_row = {
                "timestamp": timestamp,
                "soil_temp": _safe_float(soil_point.get("temperature_c")),
                "soil_humidity": _safe_float(soil_point.get("humidity_pct")),
                "air_temp": _safe_float(air_point.get("temperature_c")),
                "air_humidity": _safe_float(air_point.get("humidity_pct")),
                "EC": _safe_float(soil_point.get("ec_us_cm")),
                "pH": _safe_float(soil_point.get("ph")),
                "N": _safe_float(npk_point.get("n_ppm")),
                "P": _safe_float(npk_point.get("p_ppm")),
                "K": _safe_float(npk_point.get("k_ppm")),
            }
            previous_row = base_rows[-1] if base_rows else None
            feature_row = dict(base_row)

            feature_row["air_temp_delta_1step"] = _delta(base_row["air_temp"], None if previous_row is None else previous_row["air_temp"])
            feature_row["soil_temp_delta_1step"] = _delta(base_row["soil_temp"], None if previous_row is None else previous_row["soil_temp"])
            feature_row["soil_humidity_delta_1step"] = _delta(
                base_row["soil_humidity"],
                None if previous_row is None else previous_row["soil_humidity"],
            )
            feature_row["EC_delta_1step"] = _delta(base_row["EC"], None if previous_row is None else previous_row["EC"])

            window_rows = [row for row in [*base_rows, base_row] if timestamp - int(row["timestamp"]) <= 3 * 3600]
            feature_row["air_temp_slope_3h"] = _window_slope(window_rows, "air_temp")
            feature_row["air_temp_range_3h"] = _window_range(window_rows, "air_temp")
            feature_row["air_temp_mean_3h"] = _window_mean(window_rows, "air_temp")
            feature_row["soil_temp_slope_3h"] = _window_slope(window_rows, "soil_temp")
            feature_row["soil_humidity_slope_3h"] = _window_slope(window_rows, "soil_humidity")
            feature_row["soil_humidity_range_3h"] = _window_range(window_rows, "soil_humidity")
            feature_row["EC_slope_3h"] = _window_slope(window_rows, "EC")
            feature_row["EC_range_3h"] = _window_range(window_rows, "EC")

            base_rows.append(base_row)
            feature_rows.append(feature_row)

        return feature_rows

    def _load_history_group(self, history_path: Path, *, group_name: str) -> dict[int, dict[str, Any]]:
        records: dict[int, dict[str, Any]] = {}
        if not history_path.exists():
            return records
        with history_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                raw_record = json.loads(line)
                point = self._record_to_group_point(raw_record, group_name=group_name)
                ts = point.get("ts")
                if ts is None:
                    continue
                records[int(ts)] = point
        return dict(sorted(records.items(), key=lambda item: item[0]))

    def _record_to_group_point(self, raw_record: dict[str, Any], *, group_name: str) -> dict[str, Any]:
        timestamps = raw_record.get("timestamps", {})
        ts_server = _safe_int(timestamps.get("ts_server"))
        point: dict[str, Any] = {
            "ts": ts_server,
            "observed_at_local": timestamps.get("observed_at_local"),
        }
        perception = raw_record.get("perception", {})
        for raw_key, output_key in GROUP_FIELD_MAP[group_name].items():
            value = _safe_float(perception.get(raw_key))
            if value is not None:
                point[output_key] = value
        return point

    def _load_state(self) -> dict[str, Any] | None:
        if not self.paths.state_path.exists():
            return None
        return _load_json(self.paths.state_path)

    def _load_latest_group_points(self) -> dict[str, dict[str, Any]]:
        layer1_root = self.settings.layer1_root
        return {
            "air": self._record_to_group_point(
                _load_json_or_default(layer1_root / "sht30" / "latest.json", default={}),
                group_name="air",
            ),
            "soil": self._record_to_group_point(
                _load_json_or_default(layer1_root / "npk" / "latest.json", default={}),
                group_name="soil",
            ),
            "npk": self._record_to_group_point(
                _load_json_or_default(layer1_root / "npk" / "latest.json", default={}),
                group_name="npk",
            ),
            "weather": self._record_to_group_point(
                _load_json_or_default(layer1_root / "meteo" / "latest.json", default={}),
                group_name="weather",
            ),
        }


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_json_or_default(path: Path, *, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    return _load_json(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, bool):
            return float(int(value))
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _delta(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return float(current) - float(previous)


def _window_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    values = [_safe_float(row.get(key)) for row in rows]
    return [value for value in values if value is not None]


def _window_mean(rows: list[dict[str, Any]], key: str) -> float | None:
    values = _window_values(rows, key)
    if not values:
        return None
    return float(sum(values) / len(values))


def _window_range(rows: list[dict[str, Any]], key: str) -> float | None:
    values = _window_values(rows, key)
    if len(values) < 2:
        return None
    return float(max(values) - min(values))


def _window_slope(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [(int(row["timestamp"]), _safe_float(row.get(key))) for row in rows]
    usable = [(ts, value) for ts, value in values if value is not None]
    if len(usable) < 3:
        return None
    start_ts, start_value = usable[0]
    end_ts, end_value = usable[-1]
    hours = (end_ts - start_ts) / 3600.0
    if hours <= 0:
        return None
    return float((end_value - start_value) / hours)


def _clamp_metric(metric_name: str, value: float) -> float:
    minimum, maximum = METRIC_LIMITS.get(metric_name, (None, None))
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _signal_label(signal_name: str, signal_payload: dict[str, Any]) -> str:
    level = str(signal_payload.get("level", "normal")).lower()
    human_name = signal_name.replace("_", " ")
    return f"{human_name.capitalize()} ({level})"


def _map_signal_to_scope(signal_name: str) -> tuple[list[str], list[str]]:
    signal = signal_name.lower()
    if "air_temperature" in signal or "condensation" in signal or "air_humidity" in signal:
        return ["air"], ["air_temperature", "air_humidity"]
    if "nitrogen" in signal:
        return ["npk"], ["npk_n"]
    if "phosphorus" in signal:
        return ["npk"], ["npk_p"]
    if "potassium" in signal:
        return ["npk"], ["npk_k"]
    if "soil_moisture" in signal:
        return ["soil"], ["soil_humidity"]
    if "soil_ph" in signal:
        return ["soil"], ["soil_ph"]
    if "salinity" in signal:
        return ["soil"], ["soil_ec"]
    if "meteo" in signal or "dew_point" in signal or "cloud_cover" in signal or "rain" in signal:
        return ["weather"], []
    return ["air", "soil"], ["air_temperature", "soil_humidity"]


def _severity_from_probability(probability: float | None) -> str:
    if probability is None:
        return "normal"
    if probability >= 0.85:
        return "critical"
    if probability >= 0.65:
        return "warning"
    if probability >= 0.5:
        return "watch"
    return "normal"


def _analysis_priority(diagnosis_payload: dict[str, Any] | None, anomalies: dict[str, Any]) -> str:
    severities = [payload.get("severity", "normal") for payload in anomalies.values()]
    if diagnosis_payload is not None:
        severities.append(diagnosis_payload.get("severity", "normal"))
    if "critical" in severities:
        return "critical"
    if "warning" in severities:
        return "warning"
    if "watch" in severities:
        return "watch"
    return "normal"


def _max_ts_from_payloads(payloads: dict[str, dict[str, Any]]) -> int | None:
    timestamps = [_safe_int(payload.get("ts")) for payload in payloads.values()]
    usable = [timestamp for timestamp in timestamps if timestamp is not None]
    return max(usable) if usable else None


def _now_local_iso(settings: BackendSettings) -> str:
    return datetime.now(settings.timezone).isoformat(timespec="seconds")


def _analysis_model_name(
    diagnosis_payload: dict[str, Any] | None,
    model_artifact: BenchmarkModelArtifact | None,
) -> str | None:
    if diagnosis_payload is not None:
        model_payload = diagnosis_payload.get("model")
        if isinstance(model_payload, dict):
            family = str(model_payload.get("family", "")).strip()
            experiment_name = str(model_payload.get("experimentName", "")).strip()
            label_scheme = str(model_payload.get("labelScheme", "")).strip()
            if family == "ft_transformer":
                suffix = f" / {label_scheme}" if label_scheme else ""
                experiment = f" / {experiment_name}" if experiment_name else ""
                return f"FT-Transformer{suffix}{experiment}"
            if family == "xgboost":
                return "XGBoost"
    if model_artifact is not None:
        return "XGBoost"
    return None


def display_label_for_context(label: str) -> str:
    normalized = "rain_or_fertigation_context" if label == "moisture_or_intervention_context" else label
    return DISPLAY_LABELS.get(normalized, normalized.replace("_", " "))


def display_label_for_runtime_label(label: str) -> str:
    normalized = str(label).strip().lower()
    if normalized == "normal":
        return "Binh thuong"
    if normalized == "abnormal":
        return "Bat thuong can kiem tra"
    return display_label_for_context(normalized)


def _resolve_runtime_experiment_filter(runtime_experiment: str) -> tuple[str, ...]:
    normalized = str(runtime_experiment).strip().lower()
    if normalized == "auto":
        return DEFAULT_RUNTIME_EXPERIMENTS
    if normalized in DEFAULT_RUNTIME_EXPERIMENTS:
        return (normalized,)
    return DEFAULT_RUNTIME_EXPERIMENTS


def _runtime_model_family_from_payload(diagnosis_payload: dict[str, Any]) -> str | None:
    model_payload = diagnosis_payload.get("model")
    if not isinstance(model_payload, dict):
        return None
    family = str(model_payload.get("family", "")).strip()
    return family or None


def _runtime_experiment_from_payload(diagnosis_payload: dict[str, Any]) -> str | None:
    model_payload = diagnosis_payload.get("model")
    if not isinstance(model_payload, dict):
        return None
    experiment_name = str(model_payload.get("experimentName", "")).strip()
    return experiment_name or None


def format_metric_value(value: Any, unit: str) -> str:
    number = _safe_float(value)
    if number is None:
        return "--"
    if abs(number) >= 100:
        formatted = f"{number:.0f}"
    elif abs(number) >= 10:
        formatted = f"{number:.1f}"
    else:
        formatted = f"{number:.2f}"
    return f"{formatted} {unit}".strip()
