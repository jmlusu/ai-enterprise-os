"""Generate dispatch with a local/free-model fallback (R4, decision D9).

The primary provider is the local ``opencode`` binary (the frozen CLI
contract, ADR 0006). When OpenCode dispatch fails — binary missing from
PATH, startup failure, or non-zero exit (e.g. pinned-version break,
outage, doctor failure) — dispatch falls back to a local/free model via
the ``ollama`` CLI (decision D4 local default ``ollama/llama3.1:8b``),
so generation never hard-depends on OpenCode (no vendor lock-in).

The outcome reports *which* provider and model actually ran, keeping run
records and telemetry honest (R5). ``shutil.which`` and
``subprocess.Popen`` are read as module globals at call time so tests can
inject stub executables without touching production code.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_FALLBACK_MODEL = "ollama/llama3.1:8b"
_EXECUTE_ARG = "Execute the attached prompt against the current company registry."


@dataclass(frozen=True)
class FallbackConfig:
    """Local/free-model fallback settings (config/runtime/model_fallback.yaml)."""

    enabled: bool = True
    provider: str = "ollama"
    model: str = DEFAULT_FALLBACK_MODEL


@dataclass(frozen=True)
class DispatchAttempt:
    """One provider attempt: what ran and whether it succeeded."""

    provider: str
    model: str
    exit_code: int | None
    error: str


@dataclass(frozen=True)
class DispatchOutcome:
    """The full dispatch story: final result plus every attempt."""

    provider: str
    model: str
    exit_code: int | None
    attempts: tuple[DispatchAttempt, ...]

    @property
    def used_fallback(self) -> bool:
        """True when the local/free fallback produced the final result."""
        return self.provider != "opencode"


def load_fallback_config(config_dir: str | Path = "config") -> FallbackConfig:
    """Load fallback settings; sane defaults when the file is absent or broken.

    Accepts both a top-level ``enabled/provider/model`` layout and the
    namespaced ``fallback:`` block used by the shipped config file.
    """
    path = Path(config_dir) / "runtime" / "model_fallback.yaml"
    if not path.is_file():
        return FallbackConfig()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return FallbackConfig()
    if not isinstance(raw, dict):
        return FallbackConfig()
    block = raw.get("fallback") if isinstance(raw.get("fallback"), dict) else raw
    return FallbackConfig(
        enabled=bool(block.get("enabled", True)),
        provider=str(block.get("provider", "ollama")),
        model=str(block.get("model", DEFAULT_FALLBACK_MODEL)),
    )


def _run_process(
    cmd: list[str],
    *,
    cwd: Path,
    log_path: Path | None,
    stdin_path: Path | None = None,
    register_proc: Callable[[subprocess.Popen[str] | None], None] | None = None,
) -> int:
    """Run ``cmd``; stream merged output to ``log_path`` (or the terminal when
    ``log_path`` is None); return the exit code.

    ``register_proc`` (when given) receives the live child process right after
    spawn and ``None`` once it exits, so callers can terminate it mid-run
    (e.g. dashboard cancellation).
    """
    # The handle is consumed by ``with stdin_ctx as ...`` below, so this
    # ``open`` IS used as a context manager (ruff cannot trace it through
    # the ternary, hence the targeted noqa).
    stdin_ctx = (
        open(stdin_path, "r", encoding="utf-8")  # noqa: SIM115
        if stdin_path is not None
        else nullcontext(None)
    )
    proc: subprocess.Popen[str] | None = None
    with stdin_ctx as stdin_handle:
        try:
            common: dict = {"cwd": str(cwd), "shell": False}
            if log_path is not None:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                proc = subprocess.Popen(
                    cmd,
                    stdin=stdin_handle
                    if stdin_handle is not None
                    else subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    **common,
                )
                if register_proc is not None:
                    register_proc(proc)
                # Append: a fallback run keeps the failed primary's output in
                # the same log instead of truncating it away (honest history).
                with log_path.open("a", encoding="utf-8", errors="replace") as handle:
                    if proc.stdout is not None:
                        for line in proc.stdout:
                            handle.write(line)
                            handle.flush()
                return proc.wait()
            proc = subprocess.Popen(
                cmd,
                stdin=stdin_handle if stdin_handle is not None else subprocess.DEVNULL,
                **common,
            )
            if register_proc is not None:
                register_proc(proc)
            return proc.wait()
        finally:
            if register_proc is not None and proc is not None:
                register_proc(None)


def dispatch_generate(
    *,
    agent: str,
    model: str,
    prompt_path: Path,
    cwd: Path,
    log_path: Path | None,
    fallback_model: str = DEFAULT_FALLBACK_MODEL,
    fallback_enabled: bool = True,
    register_proc: Callable[[subprocess.Popen[str] | None], None] | None = None,
) -> DispatchOutcome:
    """Dispatch one generate run: primary ``opencode``, then local fallback.

    Returns an outcome whose ``exit_code`` is the code of the last provider
    that actually ran (0 = success) and whose ``provider``/``model`` name the
    provider behind that code — honest run records. When no provider ran
    (nothing on PATH) ``exit_code`` is None.

    ``register_proc`` (when given) receives each live child process so the
    caller can terminate it mid-run; it is unregistered after the child exits.
    """
    attempts: list[DispatchAttempt] = []

    # ── primary: opencode ──────────────────────────────────────────────── #
    opencode_path = shutil.which("opencode")
    if opencode_path is None:
        attempts.append(
            DispatchAttempt(
                provider="opencode",
                model=model,
                exit_code=None,
                error="opencode not found on PATH",
            )
        )
    else:
        cmd = [
            opencode_path,
            "run",
            "--file",
            str(prompt_path),
            "--agent",
            agent,
            "--model",
            model,
            _EXECUTE_ARG,
        ]
        try:
            rc = _run_process(
                cmd, cwd=cwd, log_path=log_path, register_proc=register_proc
            )
        except OSError as exc:
            attempts.append(
                DispatchAttempt(
                    provider="opencode",
                    model=model,
                    exit_code=None,
                    error=f"failed to start opencode: {exc}",
                )
            )
        else:
            attempts.append(
                DispatchAttempt(
                    provider="opencode",
                    model=model,
                    exit_code=rc,
                    error="" if rc == 0 else f"opencode exited with code {rc}",
                )
            )

    if attempts[-1].exit_code == 0:
        return _outcome(attempts)

    # ── fallback: local model via ollama (D9) ──────────────────────────── #
    if fallback_enabled:
        ollama_path = shutil.which("ollama")
        if ollama_path is None:
            attempts.append(
                DispatchAttempt(
                    provider="local",
                    model=fallback_model,
                    exit_code=None,
                    error="fallback unavailable: 'ollama' not found on PATH",
                )
            )
        else:
            local_model = (
                fallback_model.split("/", 1)[-1]
                if "/" in fallback_model
                else fallback_model
            )
            cmd = [ollama_path, "run", local_model]
            try:
                rc = _run_process(
                    cmd,
                    cwd=cwd,
                    log_path=log_path,
                    stdin_path=prompt_path,
                    register_proc=register_proc,
                )
            except OSError as exc:
                attempts.append(
                    DispatchAttempt(
                        provider="local",
                        model=fallback_model,
                        exit_code=None,
                        error=f"failed to start ollama: {exc}",
                    )
                )
            else:
                attempts.append(
                    DispatchAttempt(
                        provider="local",
                        model=fallback_model,
                        exit_code=rc,
                        error="" if rc == 0 else f"local model exited with code {rc}",
                    )
                )

    return _outcome(attempts)


def _outcome(attempts: list[DispatchAttempt]) -> DispatchOutcome:
    """Pick the outcome fields from the attempt list."""
    last = attempts[-1]
    if last.exit_code == 0:
        return DispatchOutcome(
            provider=last.provider,
            model=last.model,
            exit_code=0,
            attempts=tuple(attempts),
        )
    ran = [a for a in attempts if a.exit_code is not None]
    if ran:
        last_ran = ran[-1]
        return DispatchOutcome(
            provider=last_ran.provider,
            model=last_ran.model,
            exit_code=last_ran.exit_code,
            attempts=tuple(attempts),
        )
    return DispatchOutcome(
        provider=last.provider,
        model=last.model,
        exit_code=None,
        attempts=tuple(attempts),
    )


__all__ = [
    "DEFAULT_FALLBACK_MODEL",
    "DispatchAttempt",
    "DispatchOutcome",
    "FallbackConfig",
    "dispatch_generate",
    "load_fallback_config",
]
