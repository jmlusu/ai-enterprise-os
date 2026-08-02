"""Streaming OpenCode generate dispatcher (Phase 2 Wave 2b).

Implements the "generate" half of the generate -> review -> validate -> approve
loop behind the dashboard. It mirrors the frozen CLI contract exactly
(``ai-company generate <target>`` in ``cli/main.py``): resolve the target
through the command map, render the mapped prompt file, and dispatch to the
local ``opencode`` binary with the same flags.

Unlike the CLI, this runner:

- streams stdout/stderr of the child process into a per-run log file
  (``runtime/generate_logs/<run_id>.log``) so the dashboard can tail it live
  over the existing WebSocket bridge;
- tracks run lifecycle (queued -> running -> succeeded/failed/cancelled) in
  memory and persists a history record to ``runtime/generate_runs.jsonl``
  (append-only, fail-open, same pattern as CLI telemetry);
- surfaces an ``output_dir`` per run (artifacts land in ``generated/``) so the
  review step can point at concrete output.

Cancellation terminates the child process; the run is recorded as cancelled.
Runs still queued/running when the server restarts are replayed from history
as failed with ``interrupted by restart`` — the truthful state, since the
worker thread is gone.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_company.cli.command_map import load_command_map

logger = logging.getLogger(__name__)

GENERATE_RUNS_RELATIVE_PATH = Path("runtime") / "generate_runs.jsonl"
GENERATE_LOGS_RELATIVE_DIR = Path("runtime") / "generate_logs"
GENERATE_OUTPUT_DIR = "generated"
_INTERRUPTED_STATUS = "failed"


@dataclass(frozen=True)
class GenerateTarget:
    """A dispatcher target from the command map (mirrors CommandEntry)."""

    name: str
    description: str
    prompt_file: str
    agent: str
    model: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "description": self.description,
            "prompt_file": self.prompt_file,
            "agent": self.agent,
            "model": self.model,
        }


@dataclass
class GenerateRun:
    """Lifecycle record for one generate dispatch."""

    run_id: str
    target: str
    status: str
    started_at: str | None
    finished_at: str | None
    exit_code: int | None
    error: str
    log_path: str
    output_dir: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "target": self.target,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "error": self.error,
            "log_path": self.log_path,
            "output_dir": self.output_dir,
        }


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _utc_now_seconds() -> int:
    return int(datetime.now(UTC).timestamp())


class GenerateRunner:
    """Streaming OpenCode dispatcher with persisted run history.

    Thread-safe: ``start`` spawns one daemon worker per run; ``cancel``
    terminates the child process; reads never mutate state.
    """

    def __init__(
        self,
        *,
        root: str | Path = ".",
        history_path: str | Path | None = None,
        poll_interval: float = 0.5,
    ) -> None:
        self._root = Path(root)
        self._history_path = (
            Path(history_path)
            if history_path is not None
            else self._root / GENERATE_RUNS_RELATIVE_PATH
        )
        self._logs_dir = self._root / GENERATE_LOGS_RELATIVE_DIR
        self._poll_interval = poll_interval
        self._lock = threading.RLock()
        self._runs: dict[str, GenerateRun] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._procs: dict[str, subprocess.Popen[str]] = {}
        self._load_history()

    # ------------------------------------------------------------------ #
    # Targets
    # ------------------------------------------------------------------ #
    def list_targets(self) -> list[GenerateTarget]:
        """Return all dispatcher targets from the command map (sorted)."""
        targets: list[GenerateTarget] = []
        for name, entry in load_command_map().items():
            targets.append(
                GenerateTarget(
                    name=name,
                    description=entry.description,
                    prompt_file=entry.prompt_file,
                    agent=entry.agent,
                    model=entry.model,
                )
            )
        return sorted(targets, key=lambda t: t.name)

    def target(self, name: str) -> GenerateTarget:
        """Look up a single target by name; raises ValueError if unknown."""
        for target in self.list_targets():
            if target.name == name:
                return target
        available = ", ".join(t.name for t in self.list_targets())
        raise ValueError(f"Unknown target '{name}'. Available: {available}")

    # ------------------------------------------------------------------ #
    # Run lifecycle
    # ------------------------------------------------------------------ #
    def start(self, target: str, reason: str = "") -> GenerateRun:
        """Queue a generate run for ``target`` and return its record.

        The worker is spawned immediately. If the ``opencode`` binary is not
        on PATH, the run fails fast (no thread) with a descriptive error.
        ``reason`` is retained for audit alignment (write endpoints record it
        in the audit log; the runner echoes it in the run record's error field
        when the dispatch is invalid).
        """
        del reason  # audit reason is recorded by the API layer, not the runner
        resolved = self.target(target)
        prompt_path = self._root / resolved.prompt_file
        if not prompt_path.is_file():
            raise ValueError(
                f"Prompt file for target '{target}' not found: {resolved.prompt_file}"
            )

        opencode_path = shutil.which("opencode")
        if opencode_path is None:
            raise ValueError(
                "Could not find 'opencode' on PATH. Is it installed and available in this shell?"
            )

        run_id = f"g{_utc_now_seconds()}-{len(self._runs) + 1}"
        run = GenerateRun(
            run_id=run_id,
            target=target,
            status="queued",
            started_at=None,
            finished_at=None,
            exit_code=None,
            error="",
            log_path=str((self._logs_dir / f"{run_id}.log").relative_to(self._root)),
            output_dir=GENERATE_OUTPUT_DIR,
        )
        with self._lock:
            self._runs[run_id] = run
            self._append_history(run)

        thread = threading.Thread(
            target=self._execute,
            args=(run, resolved, opencode_path),
            name=f"generate-{run_id}",
            daemon=True,
        )
        with self._lock:
            self._threads[run_id] = thread
        thread.start()
        return run

    def cancel(self, run_id: str) -> GenerateRun | None:
        """Terminate a running run (no-op if already finished)."""
        with self._lock:
            run = self._runs.get(run_id)
            proc = self._procs.get(run_id)
        if run is None:
            return None
        if run.status not in ("queued", "running"):
            return run
        with self._lock:
            run.status = "cancelled"
            run.finished_at = _now_iso()
            run.error = "cancelled by operator"
            self._append_history(run)
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                logger.debug("Failed to terminate process for run %s", run_id)
        return run

    def get(self, run_id: str) -> GenerateRun | None:
        """Return a run record (from memory; history is merged at boot)."""
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self, limit: int = 50) -> list[GenerateRun]:
        """Return the most recent ``limit`` runs (newest first)."""
        with self._lock:
            runs = sorted(self._runs.values(), key=lambda r: r.run_id, reverse=True)
        return runs[:limit]

    def log_tail(self, run_id: str, max_lines: int = 400) -> list[str]:
        """Return the last ``max_lines`` lines of a run's streamed log."""
        log_path = self._root / self._logs_dir / f"{run_id}.log"
        if not log_path.is_file():
            return []
        try:
            with log_path.open("r", encoding="utf-8", errors="replace") as handle:
                lines = handle.read().splitlines()
        except OSError as exc:
            logger.debug("Log read failed for run %s: %s", run_id, exc)
            return []
        return lines[-max_lines:]

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _execute(
        self,
        run: GenerateRun,
        target: GenerateTarget,
        opencode_path: str,
    ) -> None:
        rendered = self._render_prompt(target)
        cmd = [
            opencode_path,
            "run",
            "--file",
            str(rendered),
            "--agent",
            target.agent,
            "--model",
            target.model,
            "Execute the attached prompt against the current company registry.",
        ]

        with self._lock:
            if run.status == "cancelled":
                return
            run.status = "running"
            run.started_at = _now_iso()
            self._append_history(run)

        log_path = self._root / self._logs_dir / f"{run.run_id}.log"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(self._root),
                shell=False,
            )
        except OSError as exc:
            with self._lock:
                if run.status == "cancelled":
                    return
                run.status = _INTERRUPTED_STATUS
                run.finished_at = _now_iso()
                run.error = f"failed to start opencode: {exc}"
                run.exit_code = None
                self._append_history(run)
            return

        with self._lock:
            self._procs[run.run_id] = proc

        try:
            with log_path.open("w", encoding="utf-8", errors="replace") as handle:
                if proc.stdout is not None:
                    for line in proc.stdout:
                        handle.write(line)
                        handle.flush()
            exit_code = proc.wait()
        finally:
            with self._lock:
                self._procs.pop(run.run_id, None)

        with self._lock:
            if run.status == "cancelled":
                return
            run.exit_code = exit_code
            run.finished_at = _now_iso()
            if exit_code == 0:
                run.status = "succeeded"
                run.error = ""
            else:
                run.status = _INTERRUPTED_STATUS
                run.error = f"opencode exited with code {exit_code}"
            self._append_history(run)

    def _render_prompt(self, target: GenerateTarget) -> Path:
        """Render the target prompt file (mirrors ``cli.render.render_prompt``).

        Falls back to the raw prompt text when the company manifest is
        unavailable (e.g. a bare test workspace) — the dispatch still works,
        only without registry context interpolation.
        """
        from ai_company.cli.render import TMP_PROMPT, render_prompt

        try:
            return render_prompt(target.prompt_file)
        except Exception as exc:
            logger.debug(
                "Prompt rendering for '%s' fell back to raw text: %s",
                target.name,
                exc,
            )
            source = self._root / target.prompt_file
            raw = source.read_text(encoding="utf-8")
            TMP_PROMPT.parent.mkdir(parents=True, exist_ok=True)
            TMP_PROMPT.write_text(raw, encoding="utf-8")
            return TMP_PROMPT

    def _load_history(self) -> None:
        """Reconstruct run records from persisted history at boot."""
        if not self._history_path.is_file():
            return
        try:
            with self._history_path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        logger.debug("Skipping corrupt generate history line")
                        continue
                    run = GenerateRun(
                        run_id=data.get("run_id", ""),
                        target=data.get("target", ""),
                        status=data.get("status", _INTERRUPTED_STATUS),
                        started_at=data.get("started_at"),
                        finished_at=data.get("finished_at"),
                        exit_code=data.get("exit_code"),
                        error=data.get("error", ""),
                        log_path=data.get("log_path", ""),
                        output_dir=data.get("output_dir", GENERATE_OUTPUT_DIR),
                    )
                    if run.status in ("queued", "running"):
                        run.status = _INTERRUPTED_STATUS
                        run.error = "interrupted by restart"
                        run.finished_at = _now_iso()
                    if run.run_id:
                        self._runs[run.run_id] = run
        except OSError as exc:
            logger.debug("Generate history read failed: %s", exc)

    def _append_history(self, run: GenerateRun) -> None:
        """Append a run record to the history log (fail-open)."""
        try:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            with self._history_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(run.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.debug("Generate history write failed: %s", exc)


__all__ = [
    "GENERATE_LOGS_RELATIVE_DIR",
    "GENERATE_OUTPUT_DIR",
    "GENERATE_RUNS_RELATIVE_PATH",
    "GenerateRun",
    "GenerateRunner",
    "GenerateTarget",
]
