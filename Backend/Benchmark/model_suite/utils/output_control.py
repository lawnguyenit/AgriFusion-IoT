from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
from pathlib import Path
import re
import warnings

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


@contextmanager
def capture_python_output(log_path: Path):
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            yield
    log_path.parent.mkdir(parents=True, exist_ok=True)
    warning_text = "".join(
        warnings.formatwarning(
            message=item.message,
            category=item.category,
            filename=item.filename,
            lineno=item.lineno,
            line=item.line,
        )
        for item in caught_warnings
    )
    stdout_text = _strip_ansi(stdout_buffer.getvalue())
    stderr_text = _strip_ansi(stderr_buffer.getvalue())
    sections = [
        "# Captured warnings",
        warning_text.strip() or "(none)",
        "",
        "# Captured stdout",
        stdout_text.strip() or "(none)",
        "",
        "# Captured stderr",
        stderr_text.strip() or "(none)",
        "",
    ]
    log_path.write_text("\n".join(sections), encoding="utf-8")


def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)
