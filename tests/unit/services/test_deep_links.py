"""Unit tests for the OpenCode desktop deep-link builders (Sprint 5.5 P3).

Covers the ``opencode://new-session`` URL construction, the Pydantic v2 input
validation (Core Directive 2), the per-surface prompt builders, and the
additive ``deep_link`` enrichment used by the facade.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ai_company.services.deep_links import (
    NEW_SESSION_ACTION,
    OPENCODE_SCHEME,
    NewSessionDeepLink,
    build_new_session_link,
    enrich_plan,
    enrich_run,
    enrich_target,
    plan_continue_prompt,
    project_directory,
    review_link,
    run_continue_prompt,
    target_continue_prompt,
)

_DIRECTORY = r"C:\Users\example\ai-enterprise-os"


def test_new_session_url_scheme_and_action() -> None:
    url = build_new_session_link(_DIRECTORY, "continue the work")
    assert url.startswith(f"{OPENCODE_SCHEME}://{NEW_SESSION_ACTION}?")
    assert "directory=" in url
    assert "prompt=" in url


def test_directory_normalizes_backslashes_and_encodes() -> None:
    url = build_new_session_link(_DIRECTORY, "continue the work")
    assert "%5C" not in url
    assert "%2F" in url
    assert "directory=" in url


def test_query_values_are_percent_encoded() -> None:
    prompt = 'tune the "model" & ship? (v2)'
    url = build_new_session_link(_DIRECTORY, prompt)
    assert '"' not in url.split("prompt=", 1)[1]
    assert "&prompt=" in url
    assert "&ship" not in url  # the literal ampersand must be encoded
    assert "%22" in url and "%26" in url and "%3F" in url


def test_roundtrip_query_values_restore_input() -> None:
    from urllib.parse import parse_qs, urlparse

    prompt = "tune the 'model' & ship? (v2)"
    url = build_new_session_link(_DIRECTORY, prompt)
    query = parse_qs(urlparse(url).query)
    assert query["directory"] == [_DIRECTORY.replace("\\", "/")]
    assert query["prompt"] == [prompt]


def test_blank_prompt_rejected() -> None:
    with pytest.raises(ValidationError):
        NewSessionDeepLink(directory=_DIRECTORY, prompt="   ")


def test_blank_directory_rejected() -> None:
    with pytest.raises(ValidationError):
        NewSessionDeepLink(directory="", prompt="continue")


def test_overlong_prompt_rejected() -> None:
    with pytest.raises(ValidationError):
        NewSessionDeepLink(directory=_DIRECTORY, prompt="x" * 2001)


def test_run_continue_prompt_carries_context() -> None:
    run: dict[str, Any] = {
        "run_id": "g123-1",
        "target": "registry",
        "status": "failed",
        "output_dir": "generated",
        "log_path": "runtime/generate_logs/g123-1.log",
    }
    prompt = run_continue_prompt(run)
    assert "g123-1" in prompt
    assert "'registry'" in prompt
    assert "generated" in prompt
    assert "g123-1.log" in prompt


def test_target_continue_prompt_carries_context() -> None:
    target: dict[str, Any] = {
        "key": "registry",
        "description": "Regenerate the company registry.",
        "prompt_file": "prompts/opencode/registry.md",
        "agent": "ai-company",
    }
    prompt = target_continue_prompt(target)
    assert "'registry'" in prompt
    assert "Regenerate the company registry." in prompt
    assert "prompts/opencode/registry.md" in prompt


def test_target_continue_prompt_accepts_name_key() -> None:
    prompt = target_continue_prompt({"name": "reports", "description": ""})
    assert "'reports'" in prompt


def test_plan_continue_prompt_carries_context() -> None:
    prompt = plan_continue_prompt({"plan_id": "plan-7", "status": "running"})
    assert "'plan-7'" in prompt
    assert "running" in prompt


def test_enrich_run_adds_deep_link_without_mutating_input() -> None:
    run: dict[str, Any] = {"run_id": "g123-1", "target": "registry"}
    original = dict(run)
    enriched = enrich_run(run, _DIRECTORY)
    assert run == original
    assert enriched["deep_link"].startswith(
        f"{OPENCODE_SCHEME}://{NEW_SESSION_ACTION}?"
    )
    assert enriched["run_id"] == "g123-1"


def test_enrich_target_adds_deep_link() -> None:
    enriched = enrich_target({"key": "registry"}, _DIRECTORY)
    assert enriched["deep_link"].startswith(
        f"{OPENCODE_SCHEME}://{NEW_SESSION_ACTION}?"
    )
    assert enriched["key"] == "registry"


def test_enrich_plan_adds_deep_link() -> None:
    enriched = enrich_plan({"plan_id": "plan-7"}, _DIRECTORY)
    assert enriched["deep_link"].startswith(
        f"{OPENCODE_SCHEME}://{NEW_SESSION_ACTION}?"
    )
    assert enriched["plan_id"] == "plan-7"


def test_project_directory_from_default_config(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    assert project_directory(str(config_dir)) == str(tmp_path)


def test_project_directory_explicit_value(tmp_path: Path) -> None:
    target = tmp_path / "workspace"
    assert project_directory(str(target)) == str(target)


def test_review_link_builds_url_with_base() -> None:
    url = review_link("decision_1", "http://127.0.0.1:8000")
    assert url == "http://127.0.0.1:8000/decisions?focus=decision_1"


def test_review_link_defaults_to_loopback() -> None:
    url = review_link("decision_2")
    assert url == "http://127.0.0.1:8000/decisions?focus=decision_2"


def test_review_link_encodes_id() -> None:
    url = review_link("decision a/b")
    assert "decision%20a%2Fb" in url
