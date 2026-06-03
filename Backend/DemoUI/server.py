from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_MAIN = ROOT_DIR / "Backend" / "main.py"
FLB_DATASET_MAIN = ROOT_DIR / "Backend" / "Benchmark" / "fuzzy_logic_basic" / "main.py"
DEFAULT_DATE_KEY = "2026-05-20"
DEFAULT_PACKET_GAP_MINUTES = 64
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
COMMAND_TIMEOUT_SECONDS = 60 * 30

TEMPLATE_OPTIONS = {
    "0": "0 normal",
    "1": "1 packet-loss gap",
    "2": "2 water-deficit",
    "3": "3 rain-humid",
    "4": "4 fertigation-like",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a local web control panel for AgriFusion demo commands."
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port. Default: 8787")
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the control panel in the default browser after the server starts.",
    )
    return parser.parse_args()


@dataclass(frozen=True)
class ActionDefinition:
    action_id: str
    title: str
    description: str


ACTIONS = (
    ActionDefinition(
        action_id="bootstrap_day",
        title="Bootstrap 00:00 -> 12:00",
        description="Inject the deterministic normal baseline into Firebase and rebuild local Layer0/Layer1/Layer2.5 demo artifacts.",
    ),
    ActionDefinition(
        action_id="inject_template",
        title="Inject Template",
        description="Push one telemetry template into Firebase for the selected date without running the downstream sync cycle.",
    ),
    ActionDefinition(
        action_id="server_cycle_demo",
        title="Run Demo Cycle",
        description="Inject one post-12h telemetry episode, pull the synced range back to local output, then refresh Layer1/Layer2.5/result publish.",
    ),
    ActionDefinition(
        action_id="prepare_flb",
        title="Build FLB Dataset",
        description="Rebuild the current FLB benchmark dataset package: aligned Layer1 CSV, Layer2 exports, and Layer3 combo exports.",
    ),
)


class BusyError(RuntimeError):
    """Raised when a command is already running."""


class CommandRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._is_running = False

    def run(self, command: list[str]) -> dict[str, Any]:
        with self._lock:
            if self._is_running:
                raise BusyError("Another command is still running. Wait for it to finish first.")
            self._is_running = True

        started_at = time.time()
        try:
            completed = subprocess.run(
                command,
                cwd=str(ROOT_DIR),
                capture_output=True,
                text=True,
                timeout=COMMAND_TIMEOUT_SECONDS,
                check=False,
            )
            duration_seconds = round(time.time() - started_at, 2)
            return {
                "command": command,
                "returncode": completed.returncode,
                "duration_seconds": duration_seconds,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        except subprocess.TimeoutExpired as exc:
            duration_seconds = round(time.time() - started_at, 2)
            return {
                "command": command,
                "returncode": -1,
                "duration_seconds": duration_seconds,
                "stdout": exc.stdout or "",
                "stderr": (exc.stderr or "") + f"\nCommand timed out after {COMMAND_TIMEOUT_SECONDS} seconds.",
            }
        finally:
            with self._lock:
                self._is_running = False


def _validate_date_key(value: str) -> str:
    date.fromisoformat(value)
    return value


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def build_command(payload: dict[str, Any]) -> list[str]:
    action = str(payload.get("action", "")).strip()
    date_key = _validate_date_key(str(payload.get("date_key", DEFAULT_DATE_KEY)).strip() or DEFAULT_DATE_KEY)
    template_id = str(payload.get("template_id", "0")).strip()
    packet_gap_minutes = int(payload.get("packet_gap_minutes", DEFAULT_PACKET_GAP_MINUTES))
    skip_layer25 = _parse_bool(payload.get("skip_layer25", False))

    if template_id not in TEMPLATE_OPTIONS:
        raise ValueError(f"Unsupported template id: {template_id}")

    if action == "bootstrap_day":
        command = [
            sys.executable,
            str(BACKEND_MAIN),
            "--demo-bootstrap-day",
            "--inject-date-key",
            date_key,
        ]
        if skip_layer25:
            command.append("--server-cycle-skip-layer25")
        return command

    if action == "inject_template":
        return [
            sys.executable,
            str(BACKEND_MAIN),
            "--inject-telemetry-template",
            template_id,
            "--inject-date-key",
            date_key,
            "--inject-packet-gap-minutes",
            str(packet_gap_minutes),
        ]

    if action == "server_cycle_demo":
        command = [
            sys.executable,
            str(BACKEND_MAIN),
            "--server-cycle-demo",
            "--inject-telemetry-template",
            template_id,
            "--inject-date-key",
            date_key,
            "--inject-packet-gap-minutes",
            str(packet_gap_minutes),
        ]
        if skip_layer25:
            command.append("--server-cycle-skip-layer25")
        return command

    if action == "prepare_flb":
        return [sys.executable, str(FLB_DATASET_MAIN)]

    raise ValueError(f"Unsupported action: {action}")


def render_html() -> str:
    action_cards = "\n".join(
        f"""
        <button class="action-card" data-action="{item.action_id}">
          <span class="action-title">{item.title}</span>
          <span class="action-desc">{item.description}</span>
        </button>
        """
        for item in ACTIONS
    )
    template_options = "\n".join(
        f'<option value="{key}">{label}</option>' for key, label in TEMPLATE_OPTIONS.items()
    )
    return f"""<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AgriFusion Demo Control Panel</title>
  <style>
    :root {{
      --bg: #efe7d8;
      --panel: #fffaf0;
      --panel-2: #f4ecd8;
      --ink: #223127;
      --muted: #5f6d61;
      --accent: #1f6a4f;
      --accent-strong: #0f4f38;
      --border: #cdbf9f;
      --danger: #8b3d2f;
      --shadow: 0 18px 44px rgba(38, 42, 35, 0.12);
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      font-family: Bahnschrift, "Trebuchet MS", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top right, rgba(31, 106, 79, 0.18), transparent 28%),
        linear-gradient(180deg, #f7efe2 0%, var(--bg) 100%);
      color: var(--ink);
      min-height: 100vh;
    }}

    .shell {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px 20px 40px;
    }}

    .hero {{
      display: grid;
      gap: 10px;
      margin-bottom: 24px;
    }}

    .eyebrow {{
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-size: 12px;
      color: var(--muted);
    }}

    h1 {{
      margin: 0;
      font-size: clamp(30px, 6vw, 54px);
      line-height: 0.95;
      max-width: 760px;
    }}

    .subtitle {{
      max-width: 760px;
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }}

    .grid {{
      display: grid;
      grid-template-columns: minmax(280px, 360px) 1fr;
      gap: 20px;
    }}

    .panel {{
      background: rgba(255, 250, 240, 0.9);
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 20px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(8px);
    }}

    .panel h2 {{
      margin: 0 0 14px;
      font-size: 18px;
    }}

    .field-list {{
      display: grid;
      gap: 14px;
    }}

    label {{
      display: grid;
      gap: 6px;
      font-size: 14px;
      color: var(--muted);
    }}

    input, select {{
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 12px 14px;
      font: inherit;
      color: var(--ink);
      background: #fffdf7;
    }}

    .checkbox {{
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--ink);
    }}

    .checkbox input {{
      width: auto;
      transform: translateY(1px);
    }}

    .cards {{
      display: grid;
      gap: 12px;
    }}

    .action-card {{
      appearance: none;
      width: 100%;
      text-align: left;
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 16px;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.84), rgba(244,236,216,0.92));
      color: var(--ink);
      cursor: pointer;
      transition: transform 120ms ease, border-color 120ms ease, box-shadow 120ms ease;
      display: grid;
      gap: 6px;
    }}

    .action-card:hover:enabled {{
      transform: translateY(-2px);
      border-color: var(--accent);
      box-shadow: 0 10px 24px rgba(31, 106, 79, 0.14);
    }}

    .action-card:disabled {{
      cursor: wait;
      opacity: 0.72;
    }}

    .action-title {{
      font-size: 17px;
      font-weight: 700;
    }}

    .action-desc {{
      color: var(--muted);
      line-height: 1.45;
      font-size: 13px;
    }}

    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 14px;
    }}

    .status-pill {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 10px 14px;
      background: var(--panel-2);
      color: var(--accent-strong);
      font-size: 13px;
      border: 1px solid var(--border);
    }}

    .status-pill.error {{
      color: var(--danger);
    }}

    .meta {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }}

    .meta-card {{
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 12px 14px;
      background: #fffdf7;
    }}

    .meta-label {{
      display: block;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 6px;
    }}

    .meta-value {{
      font-size: 15px;
      word-break: break-word;
    }}

    pre {{
      margin: 0;
      padding: 16px;
      border-radius: 18px;
      background: #172018;
      color: #e7f3e6;
      font-family: Consolas, "Cascadia Mono", monospace;
      font-size: 13px;
      line-height: 1.5;
      min-height: 380px;
      overflow: auto;
      white-space: pre-wrap;
      border: 1px solid rgba(255,255,255,0.08);
    }}

    .note {{
      margin-top: 14px;
      font-size: 13px;
      color: var(--muted);
      line-height: 1.5;
    }}

    @media (max-width: 920px) {{
      .grid {{
        grid-template-columns: 1fr;
      }}

      h1 {{
        line-height: 1.02;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <span class="eyebrow">AgriFusion Local Demo</span>
      <h1>Control panel cho luong sinh demo, inject telemetry va build event.</h1>
      <p class="subtitle">
        Trang nay chay local tren may cua anh va goi truc tiep cac command da co trong repo.
        Date key la field mo de anh co the demo voi <code>2026-04-20</code> hoac giu moc duoc repo dang dung la <code>{DEFAULT_DATE_KEY}</code>.
      </p>
    </section>

    <section class="grid">
      <aside class="panel">
        <h2>Runtime Inputs</h2>
        <div class="field-list">
          <label>
            Date key
            <input id="date_key" type="date" value="{DEFAULT_DATE_KEY}">
          </label>

          <label>
            Template id
            <select id="template_id">
              {template_options}
            </select>
          </label>

          <label>
            Packet gap minutes
            <input id="packet_gap_minutes" type="number" min="1" step="1" value="{DEFAULT_PACKET_GAP_MINUTES}">
          </label>

          <label class="checkbox">
            <input id="skip_layer25" type="checkbox">
            Skip Layer2.5 khi command co ho tro
          </label>
        </div>

        <div class="note">
          <strong>Template map:</strong><br>
          0 normal, 1 packet-loss gap, 2 water-deficit, 3 rain-humid, 4 fertigation-like.
        </div>
      </aside>

      <section class="panel">
        <div class="toolbar">
          <h2>Actions</h2>
          <div id="status" class="status-pill">Idle</div>
        </div>

        <div class="cards">
          {action_cards}
        </div>

        <div class="toolbar" style="margin-top:20px;">
          <h2>Last Result</h2>
          <button id="clear_log" class="action-card" style="width:auto; padding:10px 14px;">
            <span class="action-title" style="font-size:14px;">Clear log</span>
          </button>
        </div>

        <div id="meta" class="meta">
          <div class="meta-card">
            <span class="meta-label">Command</span>
            <span id="meta_command" class="meta-value">Chua chay.</span>
          </div>
          <div class="meta-card">
            <span class="meta-label">Return Code</span>
            <span id="meta_returncode" class="meta-value">-</span>
          </div>
          <div class="meta-card">
            <span class="meta-label">Duration</span>
            <span id="meta_duration" class="meta-value">-</span>
          </div>
        </div>

        <pre id="log">Nhan mot action de chay command va hien log tai day.</pre>
      </section>
    </section>
  </main>

  <script>
    const statusEl = document.getElementById("status");
    const logEl = document.getElementById("log");
    const commandEl = document.getElementById("meta_command");
    const returnCodeEl = document.getElementById("meta_returncode");
    const durationEl = document.getElementById("meta_duration");
    const buttons = Array.from(document.querySelectorAll("[data-action]"));
    const clearButton = document.getElementById("clear_log");

    function setBusy(isBusy, message, isError = false) {{
      statusEl.textContent = message;
      statusEl.classList.toggle("error", isError);
      buttons.forEach((button) => {{
        button.disabled = isBusy;
      }});
    }}

    function buildPayload(action) {{
      return {{
        action,
        date_key: document.getElementById("date_key").value,
        template_id: document.getElementById("template_id").value,
        packet_gap_minutes: document.getElementById("packet_gap_minutes").value,
        skip_layer25: document.getElementById("skip_layer25").checked,
      }};
    }}

    function renderResult(result, action) {{
      commandEl.textContent = (result.command || []).join(" ");
      returnCodeEl.textContent = String(result.returncode);
      durationEl.textContent = `${{result.duration_seconds}} s`;

      const sections = [
        `ACTION: ${{action}}`,
        `RETURN CODE: ${{result.returncode}}`,
        `DURATION: ${{result.duration_seconds}} s`,
        "",
        "STDOUT",
        result.stdout || "(empty)",
        "",
        "STDERR",
        result.stderr || "(empty)",
      ];

      logEl.textContent = sections.join("\\n");
    }}

    async function runAction(action) {{
      setBusy(true, `Dang chay: ${{action}}`);
      logEl.textContent = "Dang thuc thi command...";
      try {{
        const response = await fetch("/api/run", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(buildPayload(action)),
        }});

        const result = await response.json();
        if (!response.ok) {{
          throw new Error(result.error || "Command failed.");
        }}

        renderResult(result, action);
        setBusy(false, "Hoan tat");
      }} catch (error) {{
        commandEl.textContent = "-";
        returnCodeEl.textContent = "error";
        durationEl.textContent = "-";
        logEl.textContent = String(error);
        setBusy(false, "That bai", true);
      }}
    }}

    buttons.forEach((button) => {{
      button.addEventListener("click", () => runAction(button.dataset.action));
    }});

    clearButton.addEventListener("click", () => {{
      commandEl.textContent = "Chua chay.";
      returnCodeEl.textContent = "-";
      durationEl.textContent = "-";
      logEl.textContent = "Nhan mot action de chay command va hien log tai day.";
      setBusy(false, "Idle");
    }});
  </script>
</body>
</html>
"""


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

        if self.path == "/healthz":
            self._send_json({"status": "ok"})
            return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/run":
            self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
            return

        payload = self._read_json_body()
        if payload is None:
            return

        try:
            command = build_command(payload)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            result = self.runner.run(command)
        except BusyError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.CONFLICT)
            return

        status = HTTPStatus.OK if result["returncode"] == 0 else HTTPStatus.INTERNAL_SERVER_ERROR
        self._send_json(result, status=status)

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
    print(f"AgriFusion Demo Control Panel listening at {url}")
    print("Press Ctrl+C to stop the server.")

    if args.open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down control panel...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
