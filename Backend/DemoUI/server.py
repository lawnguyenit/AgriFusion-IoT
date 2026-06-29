from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import Template
from typing import Any

from . import pipeline_audits


ROOT_DIR = Path(__file__).resolve().parents[2]
DEMOUI_DIR = ROOT_DIR / "Backend" / "DemoUI"
REGISTRY_PATH = DEMOUI_DIR / "command_registry.json"
LAST_RUNS_PATH = DEMOUI_DIR / "last_runs.json"

BACKEND_MAIN = ROOT_DIR / "Backend" / "main.py"
BENCHMARK_DATASET_MAIN = ROOT_DIR / "Backend" / "Benchmark" / "benchmark_dataset" / "main.py"
REAL_LABELING_MAIN = ROOT_DIR / "Backend" / "Benchmark" / "benchmark_dataset" / "real_labeling" / "main.py"
SINGLE_WINDOW_MAIN = ROOT_DIR / "Backend" / "Benchmark" / "benchmark_dataset" / "single_window_features" / "main.py"
TABULAR_PREPARE = ROOT_DIR / "Backend" / "Benchmark" / "tabular_benchmark" / "prepare.py"
TABULAR_TRAIN = ROOT_DIR / "Backend" / "Benchmark" / "tabular_benchmark" / "train.py"
TABULAR_REPORT = ROOT_DIR / "Backend" / "Benchmark" / "tabular_benchmark" / "report.py"
FRONTEND_INDEX = ROOT_DIR / "Frontend" / "public" / "index.html"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
COMMAND_TIMEOUT_SECONDS = 60 * 60
POLL_INTERVAL_MS = 1000
MAX_LOG_LINES = 4000
DEFAULT_DATE_KEY = "2026-05-20"
DEFAULT_PACKET_GAP_MINUTES = 64
DEFAULT_LABEL_MODE = "binary"
DEFAULT_MODEL_TARGET = "xgboost"
DEFAULT_RESULT_RUNTIME_EXPERIMENT = "auto"
DEFAULT_FEATURE_VERSION = "v2"

MODEL_TARGET_OPTIONS = {
    "xgboost": "XGBoost",
    "tabnet_classifier": "TabNet Classifier",
    "ft_transformer_classifier": "FT-Transformer Classifier",
    "all": "All benchmark models",
}

LABEL_MODE_OPTIONS = ("binary", "tri_class", "four_class")
RESULT_RUNTIME_OPTIONS = ("auto", "v0", "v1")
FEATURE_VERSION_OPTIONS = ("v0", "v1", "v2", "all")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local AgriFusion pipeline dashboard.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port. Default: 8787")
    parser.add_argument("--open-browser", action="store_true", help="Open browser after server starts.")
    return parser.parse_args()


def load_registry() -> dict[str, Any]:
    payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    stages = payload.get("stages", [])
    actions = payload.get("actions", [])
    return {
        "stages": stages,
        "actions": actions,
        "quick_ui": payload.get("quick_ui", {}),
        "stage_by_id": {stage["id"]: stage for stage in stages},
        "action_by_id": {action["id"]: action for action in actions},
    }


REGISTRY = load_registry()


@dataclass
class CommandState:
    action_id: str = ""
    stage_id: str = ""
    command: list[str] = field(default_factory=list)
    command_display: str = ""
    dry_run: bool = False
    is_running: bool = False
    status: str = "idle"
    progress_pct: float = 0.0
    progress_label: str = "Idle"
    started_at: float | None = None
    ended_at: float | None = None
    returncode: int | None = None
    error: str | None = None
    pid: int | None = None
    line_count: int = 0
    log_lines: list[str] = field(default_factory=list)
    expected_output_status: dict[str, bool] = field(default_factory=dict)

    def append_log(self, line: str) -> None:
        self.log_lines.append(line)
        if len(self.log_lines) > MAX_LOG_LINES:
            overflow = len(self.log_lines) - MAX_LOG_LINES
            self.log_lines = self.log_lines[overflow:]
        self.line_count += 1

    def duration_seconds(self) -> float | None:
        if self.started_at is None:
            return None
        end_ts = time.time() if self.is_running else (self.ended_at or time.time())
        return round(end_ts - self.started_at, 2)


class BusyError(RuntimeError):
    pass


class CommandRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = CommandState()
        self._process: subprocess.Popen[str] | None = None

    def start(self, action: dict[str, Any], command: list[str], *, dry_run: bool) -> dict[str, Any]:
        worker: threading.Thread | None = None
        with self._lock:
            if self._state.is_running:
                raise BusyError("Another command is still running.")
            self._state = CommandState(
                action_id=str(action["id"]),
                stage_id=str(action["stage_id"]),
                command=command,
                command_display=_join_command(command),
                dry_run=dry_run,
                is_running=not dry_run,
                status="running" if not dry_run else "completed",
                progress_pct=4.0,
                progress_label="Dry run" if dry_run else "Khoi dong command...",
                started_at=time.time(),
            )
            self._append_line_locked("system", f"Action: {action['title']}")
            self._append_line_locked("system", f"Command: {self._state.command_display}")
            if dry_run:
                self._state.ended_at = time.time()
                self._state.returncode = 0
                self._state.progress_pct = 100.0
                self._state.expected_output_status = _check_expected_outputs(action)
                _persist_last_run(self._state, action)
            else:
                worker = threading.Thread(
                    target=self._run_process,
                    args=(action, command),
                    daemon=True,
                )
        if worker is not None:
            worker.start()
        return self.snapshot()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            process = self._process
            if process is None or not self._state.is_running:
                process = None
            else:
                self._append_line_locked("system", "Stop requested from dashboard. Dang terminate process...")
                self._state.progress_label = "Dang dung command..."
        if process is None:
            return self.snapshot()
        process.terminate()
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            state = self._state
            if state.is_running:
                elapsed = state.duration_seconds() or 0.0
                progress_pct = round(max(state.progress_pct, min(92.0, 6.0 + elapsed / 8.0)), 1)
            else:
                progress_pct = round(state.progress_pct, 1)
            return {
                "action_id": state.action_id,
                "stage_id": state.stage_id,
                "command": state.command,
                "command_display": state.command_display,
                "dry_run": state.dry_run,
                "is_running": state.is_running,
                "status": state.status,
                "progress_pct": progress_pct,
                "progress_label": state.progress_label,
                "started_at": state.started_at,
                "ended_at": state.ended_at,
                "duration_seconds": state.duration_seconds(),
                "returncode": state.returncode,
                "error": state.error,
                "pid": state.pid,
                "line_count": state.line_count,
                "expected_output_status": state.expected_output_status,
                "log_text": "\n".join(state.log_lines) if state.log_lines else "Nhan mot nut de chay command.",
            }

    def _run_process(self, action: dict[str, Any], command: list[str]) -> None:
        process: subprocess.Popen[str] | None = None
        stdout_thread: threading.Thread | None = None
        stderr_thread: threading.Thread | None = None
        timed_out = False

        try:
            process = subprocess.Popen(
                command,
                cwd=str(ROOT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            with self._lock:
                self._process = process
                self._state.pid = process.pid
                self._state.progress_label = "Process dang chay..."
                self._append_line_locked("system", f"Spawned PID {process.pid}")

            stdout_thread = threading.Thread(target=self._drain_stream, args=(process.stdout, "stdout"), daemon=True)
            stderr_thread = threading.Thread(target=self._drain_stream, args=(process.stderr, "stderr"), daemon=True)
            stdout_thread.start()
            stderr_thread.start()

            try:
                returncode = process.wait(timeout=COMMAND_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                returncode = -1
                with self._lock:
                    self._append_line_locked("stderr", f"Command timed out after {COMMAND_TIMEOUT_SECONDS} seconds.")

            if stdout_thread is not None:
                stdout_thread.join(timeout=2)
            if stderr_thread is not None:
                stderr_thread.join(timeout=2)

            with self._lock:
                self._process = None
                self._state.is_running = False
                self._state.ended_at = time.time()
                self._state.returncode = returncode
                self._state.expected_output_status = _check_expected_outputs(action)
                if timed_out:
                    self._state.status = "timeout"
                    self._state.error = "Command timed out."
                    self._state.progress_pct = max(self._state.progress_pct, 96.0)
                    self._state.progress_label = "Timeout"
                elif returncode == 0:
                    self._state.status = "completed"
                    self._state.error = None
                    self._state.progress_pct = 100.0
                    self._state.progress_label = "Hoan tat"
                else:
                    self._state.status = "failed"
                    self._state.error = f"Command failed with return code {returncode}."
                    self._state.progress_pct = max(self._state.progress_pct, 96.0)
                    self._state.progress_label = "That bai"
                _persist_last_run(self._state, action)
        except Exception as exc:
            with self._lock:
                self._process = None
                self._state.is_running = False
                self._state.ended_at = time.time()
                self._state.returncode = -1
                self._state.status = "failed"
                self._state.error = str(exc)
                self._state.progress_pct = 96.0
                self._state.progress_label = "That bai"
                self._append_line_locked("stderr", f"Runner error: {exc}")
                _persist_last_run(self._state, action)
        finally:
            if process is not None:
                try:
                    if process.stdout is not None:
                        process.stdout.close()
                    if process.stderr is not None:
                        process.stderr.close()
                except Exception:
                    pass

    def _drain_stream(self, stream: Any, stream_name: str) -> None:
        if stream is None:
            return
        for raw_line in iter(stream.readline, ""):
            line = raw_line.rstrip("\r\n")
            with self._lock:
                self._append_line_locked(stream_name, line)
                self._update_progress(line)

    def _append_line_locked(self, stream_name: str, line: str) -> None:
        prefix = ""
        if stream_name == "stderr":
            prefix = "[stderr] "
        elif stream_name == "system":
            prefix = "[system] "
        self._state.append_log(f"{prefix}{line}" if line else "")

    def _update_progress(self, line: str) -> None:
        text = line.strip()
        if not text:
            return
        if "Layer1 da nap" in text:
            self._state.progress_pct = max(self._state.progress_pct, 12.0)
            self._state.progress_label = "Da nap source records"
        elif "Layer1 dang chay" in text:
            self._state.progress_pct = max(self._state.progress_pct, 26.0)
            self._state.progress_label = text.replace("--- ", "").replace(" ---", "")
        elif "da quet" in text and "source record" in text:
            self._state.progress_pct = max(self._state.progress_pct, min(88.0, self._state.progress_pct + 2.0))
            self._state.progress_label = text
        elif "Best experiment/model:" in text:
            self._state.progress_pct = max(self._state.progress_pct, 88.0)
            self._state.progress_label = "Da co ket qua benchmark"
        elif "Build report:" in text or "Markdown summary:" in text:
            self._state.progress_pct = max(self._state.progress_pct, 94.0)
            self._state.progress_label = "Da tao report"
        elif "Result publisher hoan tat" in text:
            self._state.progress_pct = max(self._state.progress_pct, 95.0)
            self._state.progress_label = "Da publish result"


def _join_command(command: list[str]) -> str:
    return " ".join(command)


def _read_last_runs() -> dict[str, Any]:
    if not LAST_RUNS_PATH.exists():
        return {}
    try:
        return json.loads(LAST_RUNS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _persist_last_run(state: CommandState, action: dict[str, Any]) -> None:
    payload = _read_last_runs()
    stage_id = str(action["stage_id"])
    payload[stage_id] = {
        "action_id": state.action_id,
        "action_title": action["title"],
        "status": state.status,
        "started_at": state.started_at,
        "ended_at": state.ended_at,
        "duration_seconds": state.duration_seconds(),
        "returncode": state.returncode,
        "dry_run": state.dry_run,
        "expected_output_status": state.expected_output_status,
    }
    LAST_RUNS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _check_expected_outputs(action: dict[str, Any]) -> dict[str, bool]:
    outputs = action.get("expected_outputs", [])
    result: dict[str, bool] = {}
    for item in outputs:
        path = ROOT_DIR / str(item)
        result[str(item)] = path.exists()
    return result


def _bool_payload(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _csv_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).replace("\n", ",")
    return [part.strip() for part in text.split(",") if part.strip()]


def build_command(action_id: str, payload: dict[str, Any]) -> list[str]:
    label_mode = str(payload.get("label_mode") or DEFAULT_LABEL_MODE)
    model_target = str(payload.get("model_target") or DEFAULT_MODEL_TARGET)
    result_runtime_experiment = str(payload.get("result_runtime_experiment") or DEFAULT_RESULT_RUNTIME_EXPERIMENT)
    feature_version = str(payload.get("feature_version") or DEFAULT_FEATURE_VERSION).strip().lower()
    date_key = str(payload.get("date_key") or DEFAULT_DATE_KEY)
    single_date = str(payload.get("single_date") or date_key).strip()
    from_date = str(payload.get("from_date") or "").strip()
    to_date = str(payload.get("to_date") or "").strip()
    template_id = str(payload.get("template_id") or "0")
    packet_gap_minutes = str(payload.get("packet_gap_minutes") or DEFAULT_PACKET_GAP_MINUTES)
    experiments = _csv_list(payload.get("experiments"))
    smoke_test = _bool_payload(payload.get("smoke_test"))
    skip_super_table = _bool_payload(payload.get("skip_super_table"))
    if not experiments and feature_version and feature_version != "all":
        experiments = [feature_version]

    if action_id == "sync_latest_layer0":
        return [sys.executable, str(BACKEND_MAIN), "--only-layer0", "--latest-only"]
    if action_id == "sync_full_layer0":
        return [sys.executable, str(BACKEND_MAIN), "--only-layer0", "--full-history"]
    if action_id == "sync_day_layer0":
        if not single_date:
            raise ValueError("single_date is required for sync_day_layer0.")
        return [
            sys.executable,
            str(BACKEND_MAIN),
            "--only-layer0",
            "--full-history",
            "--start-date",
            single_date,
            "--end-date",
            single_date,
        ]
    if action_id == "sync_range_layer0":
        if not from_date or not to_date:
            raise ValueError("from_date and to_date are required for sync_range_layer0.")
        return [
            sys.executable,
            str(BACKEND_MAIN),
            "--only-layer0",
            "--full-history",
            "--start-date",
            from_date,
            "--end-date",
            to_date,
        ]
    if action_id == "check_raw_record_count":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "raw-count"]
    if action_id == "open_layer0_folder":
        return ["explorer.exe", str(ROOT_DIR / "Backend" / "Output_data" / "Layer0")]

    if action_id == "build_layer1":
        return [sys.executable, str(BACKEND_MAIN), "--only-layer1"]
    if action_id == "validate_layer1":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "validate-layer1"]
    if action_id == "sensor_quality_summary":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "sensor-quality"]
    if action_id == "open_layer1_folder":
        return ["explorer.exe", str(ROOT_DIR / "Backend" / "Output_data" / "Layer1")]

    if action_id == "build_aligned_benchmark_table":
        return [
            sys.executable,
            str(BENCHMARK_DATASET_MAIN),
            "--skip-real-labeling",
            "--skip-single-window-features",
            "--skip-multi-window-features",
        ]
    if action_id == "check_telemetry_gaps":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "telemetry-gaps"]
    if action_id == "preview_aligned_data":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "preview-aligned"]
    if action_id == "export_alignment_summary":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "alignment-summary"]

    if action_id == "run_weak_labeling":
        return [
            sys.executable,
            str(REAL_LABELING_MAIN),
            "--input-csv",
            str(ROOT_DIR / "Backend" / "Benchmark" / "benchmark_dataset" / "dataset" / "benchmark_input_aligned.csv"),
            "--output-csv",
            str(ROOT_DIR / "Backend" / "Benchmark" / "benchmark_dataset" / "dataset" / "benchmark_input_labeled.csv"),
        ]
    if action_id == "show_big_label_distribution":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "label-distribution"]
    if action_id == "show_label_mapping":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "label-mapping"]
    if action_id == "export_label_audit_report":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "label-audit-report"]
    if action_id == "preview_labeled_rows":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "preview-labeled"]

    if action_id in {"build_v0_features", "build_v1_features"}:
        version = "v0" if action_id == "build_v0_features" else "v1"
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "feature-summary", "--version", version]
    if action_id == "build_v2_window_features":
        return [sys.executable, str(SINGLE_WINDOW_MAIN), "--experiment", "exp2"]
    if action_id == "build_all_feature_sets":
        return [sys.executable, str(BENCHMARK_DATASET_MAIN)]
    if action_id == "compare_feature_sets":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "feature-compare"]
    if action_id == "check_nan_missing_features":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "feature-nan-check"]

    if action_id in {"prepare_binary_datasets", "prepare_tri_class_datasets", "prepare_four_class_datasets"}:
        lane = {
            "prepare_binary_datasets": "binary",
            "prepare_tri_class_datasets": "tri_class",
            "prepare_four_class_datasets": "four_class",
        }[action_id]
        return [sys.executable, str(TABULAR_PREPARE), "--label-mode", lane]
    if action_id == "prepare_all_benchmark_configs":
        return [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                f"& {sys.executable} '{TABULAR_PREPARE}' --label-mode binary; "
                f"& {sys.executable} '{TABULAR_PREPARE}' --label-mode tri_class; "
                f"& {sys.executable} '{TABULAR_PREPARE}' --label-mode four_class"
            ),
        ]
    if action_id == "show_split_summary":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "split-summary", "--label-mode", label_mode]
    if action_id == "check_rare_class_coverage":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "rare-class-coverage", "--label-mode", label_mode]
    if action_id == "check_purge_gap":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "purge-gap", "--label-mode", label_mode]

    if action_id in {"train_selected_config", "train_all_benchmark_configs", "train_xgboost_only"}:
        command = [sys.executable, str(TABULAR_TRAIN), "--label-mode", label_mode]
        if experiments:
            command.extend(["--experiments", *experiments])
        if action_id == "train_selected_config":
            if model_target != "all":
                command.extend(["--model-names", model_target])
        elif action_id == "train_xgboost_only":
            command.extend(["--model-names", "xgboost"])
        if smoke_test:
            command.append("--smoke-test")
        return command
    if action_id == "open_training_log":
        latest_dir = pipeline_audits._find_latest_run(pipeline_audits.RunPointer(pipeline_audits.default_training_output_root(label_mode), "training_report.json"))
        return ["explorer.exe", str(latest_dir or pipeline_audits.default_training_output_root(label_mode))]

    if action_id in {
        "aggregate_metrics",
        "generate_macro_f1_charts",
        "generate_confusion_matrices",
        "generate_model_evaluation_report",
    }:
        return [sys.executable, str(TABULAR_REPORT), "--label-mode", label_mode]
    if action_id == "publish_report_to_web":
        return [
            sys.executable,
            str(BACKEND_MAIN),
            "--only-result",
            "--publish-result",
            "--result-mode",
            "snapshot",
            "--result-payload-scope",
            "full",
            "--result-runtime-experiment",
            result_runtime_experiment,
        ]
    if action_id == "open_report_folder":
        latest_dir = pipeline_audits._find_latest_run(pipeline_audits.RunPointer(pipeline_audits.default_report_output_root(label_mode), "report_manifest.json"))
        return ["explorer.exe", str(latest_dir or pipeline_audits.default_report_output_root(label_mode))]
    if action_id == "open_web_dashboard":
        return ["explorer.exe", str(FRONTEND_INDEX)]

    if action_id == "export_audit_report":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "export-defense-audit"]
    if action_id == "show_training_feature_columns":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "training-feature-columns", "--label-mode", label_mode]
    if action_id == "show_excluded_label_columns":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "excluded-label-columns"]
    if action_id == "show_leakage_checklist":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "leakage-checklist"]
    if action_id == "show_limitations_summary":
        return [sys.executable, "-m", "Backend.DemoUI.pipeline_audits", "limitations-summary"]

    if action_id == "bootstrap_day":
        command = [sys.executable, str(BACKEND_MAIN), "--demo-bootstrap-day", "--inject-date-key", date_key]
        if skip_super_table:
            command.append("--server-cycle-skip-super-table")
        return command
    if action_id == "inject_template":
        return [
            sys.executable,
            str(BACKEND_MAIN),
            "--inject-telemetry-template",
            template_id,
            "--inject-date-key",
            date_key,
            "--inject-packet-gap-minutes",
            packet_gap_minutes,
        ]
    if action_id == "server_cycle_demo":
        command = [
            sys.executable,
            str(BACKEND_MAIN),
            "--server-cycle-demo",
            "--inject-telemetry-template",
            template_id,
            "--inject-date-key",
            date_key,
            "--inject-packet-gap-minutes",
            packet_gap_minutes,
        ]
        if skip_super_table:
            command.append("--server-cycle-skip-super-table")
        return command
    if action_id == "reset_demo":
        return [
            sys.executable,
            str(BACKEND_MAIN),
            "--prune-output-after-local-date",
            date_key,
        ]

    raise ValueError(f"Unsupported action: {action_id}")


HTML_TEMPLATE = Template(
    """<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgriFusion Pipeline Control</title>
  <style>
    :root {
      --bg: #efe8dc;
      --panel: #fffdf8;
      --panel-alt: #f7f1e8;
      --line: #d8cfbf;
      --ink: #18211b;
      --muted: #657064;
      --accent: #285c46;
      --accent-soft: #dce8e1;
      --danger: #a04235;
      --warn: #8a6320;
      --shadow: 0 14px 34px rgba(22, 24, 20, 0.08);
      --terminal: #121714;
      --terminal-head: #1c241f;
      --terminal-ink: #e8f0ea;
      --terminal-muted: #90a593;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      overflow: hidden;
      font-family: "Segoe UI", Bahnschrift, sans-serif;
      background: radial-gradient(circle at top left, rgba(40,92,70,0.08), transparent 32%), var(--bg);
      color: var(--ink);
    }
    .app-shell {
      height: 100vh;
      padding: 14px;
    }
    .workspace {
      height: 100%;
      display: grid;
      grid-template-columns: minmax(420px, 44%) minmax(0, 56%);
      gap: 14px;
    }
    .panel {
      min-height: 0;
      border: 1px solid var(--line);
      border-radius: 22px;
      background: var(--panel);
      box-shadow: var(--shadow);
    }
    .control-panel {
      display: grid;
      grid-template-rows: auto auto auto 1fr auto;
      gap: 12px;
      padding: 16px;
      overflow: hidden;
    }
    .panel-kicker {
      margin: 0 0 4px;
      font-size: 11px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .panel-title {
      margin: 0;
      font-size: 27px;
      line-height: 1.05;
    }
    .panel-subtitle {
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
      max-width: 52ch;
    }
    .stage-selector {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 8px;
    }
    .stage-tab {
      appearance: none;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: var(--panel-alt);
      color: var(--ink);
      cursor: pointer;
      min-height: 52px;
      font: inherit;
      font-weight: 700;
      display: grid;
      place-items: center;
      transition: border-color 120ms ease, background 120ms ease, transform 120ms ease;
    }
    .stage-tab:hover {
      border-color: var(--accent);
      transform: translateY(-1px);
    }
    .stage-tab.active {
      background: var(--accent);
      border-color: var(--accent);
      color: #f7fbf8;
    }
    .stage-card {
      border: 1px solid var(--line);
      border-radius: 18px;
      background: var(--panel-alt);
      padding: 14px 16px;
      display: grid;
      gap: 8px;
    }
    .stage-index {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      border-radius: 10px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
    }
    .stage-name {
      margin: 0;
      font-size: 21px;
    }
    .stage-desc {
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
    }
    .form-panel {
      border: 1px solid var(--line);
      border-radius: 18px;
      background: var(--panel-alt);
      padding: 14px;
      display: grid;
      gap: 10px;
      align-content: start;
      overflow: auto;
    }
    .section-label {
      margin: 0;
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .field-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .field {
      display: grid;
      gap: 6px;
    }
    .field.span-2 { grid-column: span 2; }
    .field label {
      font-size: 12px;
      color: var(--muted);
    }
    .field small {
      color: var(--muted);
      font-size: 11px;
      line-height: 1.4;
    }
    input, select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #fffefb;
      color: var(--ink);
      padding: 10px 11px;
      font: inherit;
    }
    textarea {
      min-height: 84px;
      resize: vertical;
    }
    .checkbox-row {
      display: flex;
      align-items: center;
      gap: 10px;
      min-height: 44px;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 0 12px;
      background: #fffefb;
      font-size: 13px;
    }
    .checkbox-row input {
      width: auto;
      margin: 0;
    }
    .action-zone {
      min-height: 0;
      display: grid;
      grid-template-rows: auto 1fr auto;
      gap: 10px;
      overflow: hidden;
    }
    .action-grid {
      min-height: 0;
      overflow: auto;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      align-content: start;
      padding-right: 2px;
    }
    .action-btn {
      appearance: none;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: #fffefb;
      text-align: left;
      color: var(--ink);
      cursor: pointer;
      padding: 13px;
      display: grid;
      gap: 6px;
      transition: border-color 120ms ease, background 120ms ease, transform 120ms ease;
    }
    .action-btn:hover:enabled {
      border-color: var(--accent);
      background: #f1f7f3;
      transform: translateY(-1px);
    }
    .action-btn:disabled {
      opacity: 0.6;
      cursor: wait;
    }
    .action-btn.active {
      border-color: var(--accent);
      background: #eef6f1;
    }
    .action-title {
      font-size: 14px;
      font-weight: 700;
      line-height: 1.35;
    }
    .action-desc {
      font-size: 12px;
      color: var(--muted);
      line-height: 1.45;
    }
    .badge-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 4px 8px;
      border: 1px solid var(--line);
      background: var(--panel-alt);
      color: var(--muted);
      font-size: 11px;
    }
    .action-preview {
      border: 1px solid var(--line);
      border-radius: 16px;
      background: var(--panel-alt);
      padding: 12px 14px;
      display: grid;
      gap: 6px;
    }
    .action-preview strong {
      font-size: 14px;
    }
    .action-preview code {
      display: block;
      padding: 10px 11px;
      border-radius: 12px;
      background: #fffefb;
      border: 1px solid var(--line);
      font-family: Consolas, "Cascadia Mono", monospace;
      font-size: 12px;
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .terminal-panel {
      display: grid;
      grid-template-rows: auto auto auto 1fr;
      min-height: 0;
      overflow: hidden;
      background: var(--terminal);
      border-color: rgba(255,255,255,0.08);
    }
    .terminal-head {
      padding: 14px 16px 10px;
      background: var(--terminal-head);
      border-bottom: 1px solid rgba(255,255,255,0.08);
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
      flex-wrap: wrap;
    }
    .terminal-title {
      margin: 0;
      color: var(--terminal-ink);
      font-size: 22px;
      line-height: 1.05;
    }
    .terminal-note {
      margin: 7px 0 0;
      color: var(--terminal-muted);
      font-size: 12px;
      line-height: 1.45;
    }
    .toolbar {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }
    .toolbar button {
      appearance: none;
      border: 1px solid rgba(255,255,255,0.14);
      border-radius: 12px;
      background: rgba(255,255,255,0.06);
      color: var(--terminal-ink);
      cursor: pointer;
      padding: 9px 12px;
      font: inherit;
    }
    .toolbar button:disabled {
      opacity: 0.55;
      cursor: not-allowed;
    }
    .toolbar .danger {
      border-color: rgba(196, 91, 74, 0.42);
      color: #ffd4cc;
    }
    .status-strip {
      padding: 12px 16px;
      display: grid;
      gap: 10px;
      border-bottom: 1px solid rgba(255,255,255,0.08);
    }
    .status-row {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 8px 11px;
      border: 1px solid rgba(255,255,255,0.1);
      background: rgba(255,255,255,0.04);
      color: var(--terminal-ink);
      font-size: 12px;
    }
    .status-pill.error {
      color: #ffccbf;
      border-color: rgba(196, 91, 74, 0.42);
    }
    .status-pill.warn {
      color: #f6d8a0;
      border-color: rgba(138, 99, 32, 0.44);
    }
    .progress-track {
      height: 10px;
      border-radius: 999px;
      overflow: hidden;
      background: rgba(255,255,255,0.08);
    }
    .progress-fill {
      height: 100%;
      width: 0%;
      border-radius: 999px;
      background: linear-gradient(90deg, #2a6c50 0%, #56916e 55%, #b78533 100%);
      transition: width 160ms ease;
    }
    .command-strip {
      padding: 12px 16px;
      border-bottom: 1px solid rgba(255,255,255,0.08);
      color: var(--terminal-muted);
      font-size: 12px;
      line-height: 1.5;
      font-family: Consolas, "Cascadia Mono", monospace;
      word-break: break-word;
    }
    .command-strip strong {
      color: var(--terminal-ink);
      display: block;
      margin-bottom: 6px;
      font-family: "Segoe UI", Bahnschrift, sans-serif;
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }
    pre {
      margin: 0;
      min-height: 0;
      padding: 16px;
      overflow: auto;
      color: var(--terminal-ink);
      font-family: Consolas, "Cascadia Mono", monospace;
      font-size: 13px;
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-word;
      background: linear-gradient(180deg, #101612, #141d17);
    }
    .empty-note {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    @media (max-width: 1200px) {
      body { overflow: auto; }
      .app-shell { height: auto; min-height: 100vh; }
      .workspace {
        height: auto;
        grid-template-columns: 1fr;
      }
      .control-panel, .terminal-panel { min-height: 560px; }
    }
    @media (max-width: 760px) {
      .field-grid, .action-grid { grid-template-columns: 1fr; }
      .stage-selector { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <main class="app-shell">
    <section class="workspace">
      <aside class="panel control-panel">
        <header>
          <p class="panel-kicker">AgriFusion Quick Control</p>
          <h1 class="panel-title">Bang dieu khien thao tac theo giai doan</h1>
          <p class="panel-subtitle">Chon stage bang so, bam nut chuc nang o cot trai, va xem phan hoi server tai terminal o cot phai.</p>
        </header>

        <div id="stage_selector" class="stage-selector"></div>

        <section class="stage-card">
          <span id="stage_index" class="stage-index">01</span>
          <h2 id="stage_title" class="stage-name">Keo du lieu</h2>
          <p id="stage_description" class="stage-desc"></p>
        </section>

        <section class="form-panel">
          <p class="section-label">Tham so giai doan</p>
          <div id="field_grid" class="field-grid"></div>
          <div id="field_empty" class="empty-note">Giai doan nay khong can tham so bo sung.</div>
        </section>

        <section class="action-zone">
          <p class="section-label">Nut chuc nang</p>
          <div id="action_grid" class="action-grid"></div>
          <div class="action-preview">
            <p class="section-label">Action vua chon</p>
            <strong id="selected_action_title">Chua chon action</strong>
            <div id="selected_action_desc" class="empty-note">Nhan mot nut o tren de chay command.</div>
            <code id="selected_action_command">-</code>
          </div>
        </section>
      </aside>

      <section class="panel terminal-panel">
        <div class="terminal-head">
          <div>
            <h2 class="terminal-title">Command / Terminal</h2>
            <p class="terminal-note">Khu nay chi hien phan hoi cua server: command dang chay, stdout/stderr, thoi gian, return code va trang thai.</p>
          </div>
          <div class="toolbar">
            <button id="stop_btn" class="danger" type="button" disabled>Stop current command</button>
            <button id="clear_btn" type="button">Clear terminal</button>
            <button id="copy_btn" type="button">Copy log</button>
          </div>
        </div>

        <div class="status-strip">
          <div class="status-row">
            <span id="status_text" class="status-pill">idle</span>
            <span id="status_hint" class="status-pill">Idle</span>
            <span id="duration_text" class="status-pill">Duration: -</span>
            <span id="returncode_text" class="status-pill">Return code: -</span>
            <span id="pid_text" class="status-pill">PID: -</span>
          </div>
          <div class="progress-track">
            <div id="progress_fill" class="progress-fill"></div>
          </div>
        </div>

        <div class="command-strip">
          <strong>Current command</strong>
          <div id="command_text">-</div>
        </div>

        <pre id="terminal">Nhan mot nut chuc nang de chay command.</pre>
      </section>
    </section>
  </main>

  <script>
    const QUICK_UI = $QUICK_UI_JSON;
    const ACTIONS = $ACTION_MAP_JSON;
    const POLL_INTERVAL_MS = $POLL_INTERVAL_MS;
    const stageSelectorEl = document.getElementById("stage_selector");
    const stageIndexEl = document.getElementById("stage_index");
    const stageTitleEl = document.getElementById("stage_title");
    const stageDescriptionEl = document.getElementById("stage_description");
    const fieldGridEl = document.getElementById("field_grid");
    const fieldEmptyEl = document.getElementById("field_empty");
    const actionGridEl = document.getElementById("action_grid");
    const selectedActionTitleEl = document.getElementById("selected_action_title");
    const selectedActionDescEl = document.getElementById("selected_action_desc");
    const selectedActionCommandEl = document.getElementById("selected_action_command");
    const terminalEl = document.getElementById("terminal");
    const statusTextEl = document.getElementById("status_text");
    const statusHintEl = document.getElementById("status_hint");
    const durationTextEl = document.getElementById("duration_text");
    const returncodeTextEl = document.getElementById("returncode_text");
    const pidTextEl = document.getElementById("pid_text");
    const progressFillEl = document.getElementById("progress_fill");
    const commandTextEl = document.getElementById("command_text");
    const stopButton = document.getElementById("stop_btn");
    const clearButton = document.getElementById("clear_btn");
    const copyButton = document.getElementById("copy_btn");

    let selectedStageId = QUICK_UI.stages[0].id;
    let selectedActionId = "";
    let clearedLocally = false;
    const fieldValues = {};

    Object.entries(QUICK_UI.fields || {}).forEach(function(entry) {
      fieldValues[entry[0]] = entry[1].default;
    });

    function getStage(stageId) {
      return QUICK_UI.stages.find(function(item) { return item.id === stageId; }) || QUICK_UI.stages[0];
    }

    function getAction(actionId) {
      return ACTIONS[actionId];
    }

    function saveVisibleFieldValues() {
      const nodes = fieldGridEl.querySelectorAll("[data-field-id]");
      nodes.forEach(function(node) {
        const fieldId = node.getAttribute("data-field-id");
        if (!fieldId) return;
        fieldValues[fieldId] = node.type === "checkbox" ? node.checked : node.value;
      });
    }

    function createField(fieldId) {
      const fieldDef = QUICK_UI.fields[fieldId];
      if (!fieldDef) {
        return null;
      }
      const wrap = document.createElement("div");
      wrap.className = "field";
      if (fieldDef.type === "text" || fieldDef.type === "textarea") {
        wrap.classList.add("span-2");
      }

      if (fieldDef.type === "checkbox") {
        const row = document.createElement("label");
        row.className = "checkbox-row";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.checked = Boolean(fieldValues[fieldId]);
        input.setAttribute("data-field-id", fieldId);
        input.addEventListener("change", saveVisibleFieldValues);
        const text = document.createElement("span");
        text.textContent = fieldDef.label;
        row.appendChild(input);
        row.appendChild(text);
        wrap.appendChild(row);
        return wrap;
      }

      const label = document.createElement("label");
      label.textContent = fieldDef.label;
      wrap.appendChild(label);

      let input;
      if (fieldDef.type === "select") {
        input = document.createElement("select");
        (fieldDef.options || []).forEach(function(optionDef) {
          const option = document.createElement("option");
          option.value = optionDef.value;
          option.textContent = optionDef.label;
          if (String(fieldValues[fieldId]) === String(optionDef.value)) {
            option.selected = true;
          }
          input.appendChild(option);
        });
      } else if (fieldDef.type === "textarea") {
        input = document.createElement("textarea");
        input.value = fieldValues[fieldId] ?? "";
      } else {
        input = document.createElement("input");
        input.type = fieldDef.type || "text";
        input.value = fieldValues[fieldId] ?? "";
      }
      input.setAttribute("data-field-id", fieldId);
      if (fieldDef.placeholder) {
        input.placeholder = fieldDef.placeholder;
      }
      input.addEventListener("input", saveVisibleFieldValues);
      input.addEventListener("change", saveVisibleFieldValues);
      wrap.appendChild(input);

      if (fieldDef.help) {
        const help = document.createElement("small");
        help.textContent = fieldDef.help;
        wrap.appendChild(help);
      }
      return wrap;
    }

    function renderStageSelector() {
      stageSelectorEl.innerHTML = "";
      QUICK_UI.stages.forEach(function(stage) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "stage-tab" + (stage.id === selectedStageId ? " active" : "");
        button.textContent = String(stage.number);
        button.title = stage.title;
        button.addEventListener("click", function() {
          saveVisibleFieldValues();
          selectedStageId = stage.id;
          renderStage();
        });
        stageSelectorEl.appendChild(button);
      });
    }

    function renderStageFields(stage) {
      fieldGridEl.innerHTML = "";
      const fieldIds = stage.fields || [];
      fieldEmptyEl.style.display = fieldIds.length ? "none" : "block";
      fieldIds.forEach(function(fieldId) {
        const node = createField(fieldId);
        if (node) {
          fieldGridEl.appendChild(node);
        }
      });
    }

    function renderActionPreview(action) {
      if (!action) {
        selectedActionTitleEl.textContent = "Chua chon action";
        selectedActionDescEl.textContent = "Nhan mot nut o tren de chay command.";
        selectedActionCommandEl.textContent = "-";
        return;
      }
      selectedActionTitleEl.textContent = action.title;
      selectedActionDescEl.textContent = action.description || "";
      selectedActionCommandEl.textContent = action.command_preview || "-";
    }

    function renderStageActions(stage) {
      actionGridEl.innerHTML = "";
      (stage.action_ids || []).forEach(function(actionId) {
        const action = getAction(actionId);
        if (!action) {
          return;
        }
        const button = document.createElement("button");
        button.type = "button";
        button.className = "action-btn" + (selectedActionId === actionId ? " active" : "");
        button.innerHTML =
          '<span class="action-title">' + action.title + '</span>' +
          '<span class="action-desc">' + (action.description || "") + '</span>' +
          '<div class="badge-row">' +
            '<span class="badge">danger: ' + action.danger_level + '</span>' +
            '<span class="badge">dry-run: ' + (action.allow_dry_run ? "yes" : "no") + '</span>' +
          '</div>';
        button.addEventListener("mouseenter", function() {
          renderActionPreview(action);
        });
        button.addEventListener("click", async function() {
          selectedActionId = actionId;
          renderStageActions(stage);
          renderActionPreview(action);
          try {
            await runAction(actionId);
          } catch (error) {
            renderClientError(String(error));
          }
        });
        actionGridEl.appendChild(button);
      });
    }

    function renderStage() {
      const stage = getStage(selectedStageId);
      stageIndexEl.textContent = String(stage.number).padStart(2, "0");
      stageTitleEl.textContent = stage.title;
      stageDescriptionEl.textContent = stage.description || "";
      renderStageSelector();
      renderStageFields(stage);
      renderStageActions(stage);
      renderActionPreview(getAction(selectedActionId));
    }

    function buildPayload(actionId) {
      saveVisibleFieldValues();
      const payload = { action: actionId };
      Object.keys(QUICK_UI.fields || {}).forEach(function(fieldId) {
        payload[fieldId] = fieldValues[fieldId];
      });
      return payload;
    }

    function setStatusClasses(status) {
      statusTextEl.classList.remove("error", "warn");
      statusHintEl.classList.remove("error", "warn");
      if (status === "failed" || status === "timeout") {
        statusTextEl.classList.add("error");
        statusHintEl.classList.add("error");
      } else if (status === "running") {
        statusTextEl.classList.add("warn");
        statusHintEl.classList.add("warn");
      }
    }

    function renderState(state) {
      setStatusClasses(state.status);
      statusTextEl.textContent = state.is_running ? "running" : (state.status || "idle");
      statusHintEl.textContent = state.progress_label || "Idle";
      durationTextEl.textContent = "Duration: " + (state.duration_seconds === null ? "-" : String(state.duration_seconds) + " s");
      returncodeTextEl.textContent = "Return code: " + (state.returncode === null ? "-" : String(state.returncode));
      pidTextEl.textContent = "PID: " + (state.pid === null ? "-" : String(state.pid));
      progressFillEl.style.width = String(state.progress_pct || 0) + "%";
      commandTextEl.textContent = state.command_display || "-";
      if (!clearedLocally || state.is_running) {
        const nearBottom = terminalEl.scrollTop + terminalEl.clientHeight >= terminalEl.scrollHeight - 50;
        terminalEl.textContent = state.log_text || "Nhan mot nut chuc nang de chay command.";
        if (nearBottom || state.is_running) {
          terminalEl.scrollTop = terminalEl.scrollHeight;
        }
      }
      const running = Boolean(state.is_running);
      stopButton.disabled = !running;
      actionGridEl.querySelectorAll(".action-btn").forEach(function(button) {
        button.disabled = running;
      });
    }

    function renderClientError(message) {
      setStatusClasses("failed");
      statusTextEl.textContent = "failed";
      statusHintEl.textContent = message;
      terminalEl.textContent = message;
    }

    async function pollState() {
      const response = await fetch("/api/state");
      const state = await response.json();
      renderState(state);
    }

    async function runAction(actionId) {
      const action = getAction(actionId);
      const payload = buildPayload(actionId);
      clearedLocally = false;
      if (payload.dry_run !== true && action.danger_level === "high") {
        const confirmed = window.confirm("Action nay co danger level HIGH.\n\n" + action.title + "\n\nBan co chac muon chay command that?");
        if (!confirmed) {
          return;
        }
      }
      const response = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || "Command start failed.");
      }
      renderState(result);
    }

    async function stopCurrentCommand() {
      const response = await fetch("/api/stop", { method: "POST" });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || "Stop failed.");
      }
      renderState(result);
    }

    stopButton.addEventListener("click", async function() {
      try {
        await stopCurrentCommand();
      } catch (error) {
        renderClientError(String(error));
      }
    });

    clearButton.addEventListener("click", function() {
      clearedLocally = true;
      terminalEl.textContent = "Terminal view da duoc clear trong UI. Trang thai server van duoc giu nguyen.";
    });

    copyButton.addEventListener("click", async function() {
      try {
        await navigator.clipboard.writeText(terminalEl.textContent || "");
        statusHintEl.textContent = "Da copy log";
      } catch (error) {
        renderClientError("Khong copy duoc log: " + String(error));
      }
    });

    async function bootstrap() {
      renderStage();
      try {
        await pollState();
      } catch (error) {
        renderClientError(String(error));
      }
      window.setInterval(async function() {
        try {
          await pollState();
        } catch (error) {
          renderClientError(String(error));
        }
      }, POLL_INTERVAL_MS);
    }

    bootstrap();
  </script>
</body>
</html>
"""
)


def render_html() -> str:
    return HTML_TEMPLATE.substitute(
        QUICK_UI_JSON=json.dumps(REGISTRY.get("quick_ui", {}), ensure_ascii=True),
        ACTION_MAP_JSON=json.dumps(REGISTRY["action_by_id"], ensure_ascii=True),
        POLL_INTERVAL_MS=str(POLL_INTERVAL_MS),
    )


class ControlPanelHandler(BaseHTTPRequestHandler):
    runner = CommandRunner()

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/index.html"}:
            body = render_html().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/api/state":
            self._send_json(self.runner.snapshot())
            return

        if self.path == "/api/overview":
            self._send_json(
                {
                    "overview": pipeline_audits.collect_pipeline_overview(),
                    "last_runs": _read_last_runs(),
                }
            )
            return

        if self.path == "/healthz":
            self._send_json({"status": "ok"})
            return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/run":
            payload = self._read_json_body()
            if payload is None:
                return
            action_id = str(payload.get("action", "")).strip()
            action = REGISTRY["action_by_id"].get(action_id)
            if action is None:
                self._send_json({"error": f"Unknown action: {action_id}"}, status=HTTPStatus.BAD_REQUEST)
                return
            try:
                command = build_command(action_id, payload)
                dry_run = _bool_payload(payload.get("dry_run")) and bool(action.get("allow_dry_run", False))
                state = self.runner.start(action, command, dry_run=dry_run)
            except BusyError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.CONFLICT)
                return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json(state, status=HTTPStatus.ACCEPTED)
            return

        if self.path == "/api/stop":
            self._send_json(self.runner.stop(), status=HTTPStatus.ACCEPTED)
            return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_json_body(self) -> dict[str, Any] | None:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            self._send_json({"error": "Missing Content-Length header."}, status=HTTPStatus.BAD_REQUEST)
            return None
        try:
            payload_length = int(content_length)
        except ValueError:
            self._send_json({"error": "Invalid Content-Length header."}, status=HTTPStatus.BAD_REQUEST)
            return None
        raw_payload = self.rfile.read(payload_length)
        try:
            return json.loads(raw_payload.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON payload."}, status=HTTPStatus.BAD_REQUEST)
            return None

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ControlPanelHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"AgriFusion Telemetry Pipeline Dashboard listening at {url}")
    print("Press Ctrl+C to stop the server.")
    if args.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
