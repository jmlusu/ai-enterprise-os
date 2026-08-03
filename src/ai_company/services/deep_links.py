"""OpenCode desktop deep links (Sprint 5.5 P3) — "continue in OpenCode".

Phase 3 initiative goal: >=90% of generation targets runnable desktop-first.
The desktop app registers the ``opencode://`` URL scheme (installed at
``%LOCALAPPDATA%\\Programs\\@opencode-aidesktop\\OpenCode.exe``), so the
dashboard can hand a run/target/plan off to a desktop session with a single
click instead of re-typing the context into the CLI.

The desktop build supports project/session-launch deep links such as
``opencode://new-session?directory=<path>&prompt=<text>``; session-id resume
(``opencode://session/<id>``) is still an upstream feature request, so these
links always open a fresh session seeded with the selected context. This is a
desktop-URL-scheme surface, not a CLI surface (ADR 0006 — the command tree and
command map stay frozen), so there is no ``ai-company`` command counterpart and
the parity matrix records it as N/A.

All links are built through the shared :class:`NewSessionDeepLink` Pydantic
model (Core Directive 2 — Pydantic v2) so invalid input is rejected before it
ever reaches the registry handler.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, Field, field_validator

OPENCODE_SCHEME = "opencode"
NEW_SESSION_ACTION = "new-session"
MAX_PROMPT_LENGTH = 2000
MAX_DIRECTORY_LENGTH = 1024


class NewSessionDeepLink(BaseModel):
    """Validated ``opencode://new-session`` deep link.

    ``directory`` is the project folder the desktop app should open and
    ``prompt`` is the pre-filled instruction that seeds the new session.
    """

    directory: str = Field(min_length=1, max_length=MAX_DIRECTORY_LENGTH)
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)

    @field_validator("directory", "prompt")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @property
    def url(self) -> str:
        """Encoded deep-link URL (backslashes normalized for the desktop)."""
        directory = self.directory.replace("\\", "/")
        return (
            f"{OPENCODE_SCHEME}://{NEW_SESSION_ACTION}"
            f"?directory={quote(directory, safe='')}"
            f"&prompt={quote(self.prompt, safe='')}"
        )


def build_new_session_link(directory: str, prompt: str) -> str:
    """Build an ``opencode://new-session`` deep link from validated parts."""
    return NewSessionDeepLink(directory=directory, prompt=prompt).url


def run_continue_prompt(run: Mapping[str, Any]) -> str:
    """Session prompt that hands one generate run off to the desktop."""
    run_id = run.get("run_id") or ""
    target = run.get("target") or ""
    status = run.get("status") or ""
    output_dir = run.get("output_dir") or "generated"
    log_path = run.get("log_path") or ""
    return (
        f"Continue AI Enterprise OS generation run {run_id} for target "
        f"'{target}' (status: {status}). Review the artifacts under "
        f"{output_dir} and the log at {log_path}, then continue improving "
        "the generated output."
    )


def target_continue_prompt(target: Mapping[str, Any]) -> str:
    """Session prompt that hands one generation target off to the desktop."""
    key = target.get("key") or target.get("name") or ""
    description = target.get("description") or ""
    prompt_file = target.get("prompt_file") or ""
    agent = target.get("agent") or ""
    return (
        f"Continue AI Enterprise OS generate target '{key}'. {description} "
        f"Execute the mapped prompt file {prompt_file} (agent: {agent}) and "
        "iterate on the result."
    )


def plan_continue_prompt(record: Mapping[str, Any]) -> str:
    """Session prompt that hands one orchestration plan off to the desktop."""
    plan_id = record.get("plan_id") or record.get("id") or ""
    status = record.get("status") or ""
    return (
        f"Continue AI Enterprise OS orchestration plan '{plan_id}' "
        f"(status: {status}). Review progress and drive the plan to "
        "completion in this session."
    )


def enrich_run(run: Mapping[str, Any], directory: str) -> dict[str, Any]:
    """Return the run dict plus a ``deep_link`` to continue it in OpenCode."""
    enriched = dict(run)
    enriched["deep_link"] = build_new_session_link(
        directory, run_continue_prompt(enriched)
    )
    return enriched


def enrich_target(target: Mapping[str, Any], directory: str) -> dict[str, Any]:
    """Return the target dict plus a ``deep_link`` to run it in OpenCode."""
    enriched = dict(target)
    enriched["deep_link"] = build_new_session_link(
        directory, target_continue_prompt(enriched)
    )
    return enriched


def enrich_plan(record: Mapping[str, Any], directory: str) -> dict[str, Any]:
    """Return the orchestration record plus a ``deep_link`` to continue it."""
    enriched = dict(record)
    enriched["deep_link"] = build_new_session_link(
        directory, plan_continue_prompt(enriched)
    )
    return enriched


def project_directory(config_dir: str) -> str:
    """Resolve the project root a deep link should open from ``config_dir``.

    The default ``config`` directory lives directly under the project root, so
    the root is its parent. Any other value is treated as an explicit project
    directory.
    """
    path = Path(config_dir).resolve()
    if path.name == "config":
        return str(path.parent)
    return str(path)


__all__ = [
    "MAX_DIRECTORY_LENGTH",
    "MAX_PROMPT_LENGTH",
    "NEW_SESSION_ACTION",
    "OPENCODE_SCHEME",
    "NewSessionDeepLink",
    "build_new_session_link",
    "enrich_plan",
    "enrich_run",
    "enrich_target",
    "plan_continue_prompt",
    "project_directory",
    "run_continue_prompt",
    "target_continue_prompt",
]
