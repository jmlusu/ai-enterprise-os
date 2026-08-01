"""Shared services layer (ADR 0003).

Single source of truth for business logic. The CLI, the dashboard API, and
OpenCode prompt execution are thin adapters over these services; new features
are implemented here first, then exposed per surface.

Phase 1 (wave 1) ships the two services every surface needs to answer "is the
system healthy?": the runtime facade and the dashboard event bridge.
"""

from ai_company.services.dashboard_events import DashboardEventBridge
from ai_company.services.runtime_facade import RuntimeFacade

__all__ = ["DashboardEventBridge", "RuntimeFacade"]
