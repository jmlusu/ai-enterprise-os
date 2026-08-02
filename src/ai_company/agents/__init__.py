"""Opencode persona agents — sync company personas into opencode agent files.

By default (``scope="both"``) personas are written to both the project's
``.opencode/agents`` and the user-global ``~/.config/opencode/agents`` so
they are available in every opencode session; use ``scope="project"`` to
keep them project-local.

Public API:
- :mod:`ai_company.agents.slug_map` — slug assignment and collision checks
- :mod:`ai_company.agents.template` — Jinja2 rendering of agent files
- :mod:`ai_company.agents.sync` — plan/run sync engine
- ``python -m ai_company.agents sync`` — command line entry point
"""

from ai_company.agents.slug_map import (
    BUILTIN_AGENT_SLUGS,
    EXECUTIVE_SLUGS,
    AgentSlugCollisionError,
    AgentSlugIndex,
    AgentSlugItem,
    slugify,
)
from ai_company.agents.sync import (
    PROJECT_AGENTS_DIR,
    AgentPlanEntry,
    AgentSyncConfig,
    AgentSyncEngine,
    AgentSyncPlan,
    AgentSyncResult,
    SyncScope,
    global_agents_dir,
    print_plan_summary,
    print_result_summary,
)
from ai_company.agents.template import (
    EXECUTIVE_TRIGGERS,
    GENERATED_MARKER,
    AgentRenderContext,
    build_trigger,
    render_agent_markdown,
)

__all__ = [
    "AgentPlanEntry",
    "AgentRenderContext",
    "AgentSlugCollisionError",
    "AgentSlugIndex",
    "AgentSlugItem",
    "AgentSyncConfig",
    "AgentSyncEngine",
    "AgentSyncPlan",
    "AgentSyncResult",
    "BUILTIN_AGENT_SLUGS",
    "EXECUTIVE_SLUGS",
    "EXECUTIVE_TRIGGERS",
    "GENERATED_MARKER",
    "PROJECT_AGENTS_DIR",
    "SyncScope",
    "build_trigger",
    "global_agents_dir",
    "print_plan_summary",
    "print_result_summary",
    "render_agent_markdown",
    "slugify",
]
