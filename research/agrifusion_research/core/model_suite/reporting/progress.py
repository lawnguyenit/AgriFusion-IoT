from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
import sys

try:
    from rich.console import Console
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
except Exception:  # pragma: no cover - optional dependency fallback
    Console = None
    Progress = None


@dataclass(frozen=True)
class SmokeJobProgress:
    index: int
    total: int
    stage_id: str
    model_key: str
    feature_view_id: str
    fold_id: str
    run_scope: str


class SmokeSuiteProgressReporter:
    def __init__(self, *, enabled: bool = True, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._enabled = enabled
        self._console = None
        self._progress = None
        self._task_id = None
        self._current_job_description = ""
        if self._enabled and Console is not None and Progress is not None and _supports_unicode_output(self._stream):
            self._console = Console(file=self._stream, force_terminal=True, soft_wrap=True)
            self._progress = Progress(
                TextColumn("run"),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=None),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=self._console,
                transient=False,
            )

    def __enter__(self) -> SmokeSuiteProgressReporter:
        if self._progress is not None:
            self._progress.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._progress is not None:
            self._progress.stop()

    def start_run(self, *, run_id: str, output_dir: Path, total_jobs: int, profile_name: str) -> None:
        if not self._enabled:
            return
        if self._console is not None:
            self._console.print(
                f"[bold]model_suite[/bold] run `[cyan]{run_id}[/cyan]` | "
                f"profile=`{profile_name}` | jobs={total_jobs}"
            )
            self._console.print(f"artifact dir: {output_dir}")
        else:
            self._stream.write(
                f"model_suite run {run_id} | profile={profile_name} | jobs={total_jobs}\n"
                f"artifact dir: {output_dir}\n"
            )
            self._stream.flush()
        if self._progress is not None:
            self._task_id = self._progress.add_task("waiting for first job", total=total_jobs)

    def enter_stage(self, *, stage_id: str, stage_job_count: int) -> None:
        if not self._enabled:
            return
        message = f"stage {stage_id} | scheduled jobs={stage_job_count}"
        if self._console is not None:
            self._console.print(f"[bold blue]{message}[/bold blue]")
        else:
            self._stream.write(f"{message}\n")
            self._stream.flush()

    def start_job(self, job: SmokeJobProgress) -> None:
        if not self._enabled:
            return
        self._current_job_description = (
            f"{job.index}/{job.total} | {job.stage_id} | {job.model_key} | "
            f"{job.feature_view_id} | {job.fold_id} | {job.run_scope}"
        )
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, description=self._current_job_description)
        else:
            self._stream.write(f"START {self._current_job_description}\n")
            self._stream.flush()

    def complete_job(self, *, status: str, note: str | None = None) -> None:
        if not self._enabled:
            return
        clean_note = (note or "").strip()
        suffix = f" | {clean_note}" if clean_note else ""
        if self._progress is not None and self._task_id is not None:
            self._progress.advance(self._task_id, 1)
            self._progress.console.print(f"[green]{status}[/green]{suffix}")
        else:
            self._stream.write(f"PROGRESS {_ascii_bar(self._task_id, status, suffix, self._current_job_description)}\n")
            self._stream.flush()

    def fail_job(self, *, status: str, note: str) -> None:
        if not self._enabled:
            return
        clean_note = note.strip()
        if self._progress is not None and self._task_id is not None:
            self._progress.advance(self._task_id, 1)
            self._progress.console.print(f"[red]{status}[/red] | {clean_note}")
        else:
            self._stream.write(f"FAIL {status} | {self._current_job_description} | {clean_note}\n")
            self._stream.flush()

    def finish(self, *, trained_jobs: int, total_jobs: int, output_dir: Path) -> None:
        if not self._enabled:
            return
        message = f"completed trained_jobs={trained_jobs}/{total_jobs} | artifacts={output_dir}"
        if self._console is not None:
            self._console.print(f"[bold green]{message}[/bold green]")
        else:
            self._stream.write(f"{message}\n")
            self._stream.flush()


def _supports_unicode_output(stream: TextIO) -> bool:
    encoding = getattr(stream, "encoding", None)
    if encoding is None:
        return False
    return str(encoding).lower().startswith("utf")


def _ascii_bar(task_id: int | None, status: str, suffix: str, description: str) -> str:
    _ = task_id
    parts = description.split(" | ", maxsplit=1)
    progress = parts[0] if parts else "?"
    current = parts[1] if len(parts) > 1 else description
    completed_str, total_str = progress.split("/", maxsplit=1)
    completed = int(completed_str)
    total = int(total_str)
    width = 20
    filled = width if total <= 0 else int(width * completed / total)
    bar = f"[{'#' * filled}{'-' * (width - filled)}]"
    return f"{bar} {completed}/{total} | {status} | {current}{suffix}"
