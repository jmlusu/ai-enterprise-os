"""Dashboard API package (ADR 0002 / ADR 0009 / ADR 0010).

Public surface served by ``ai-company serve``:

- Read contract (Phase 1, ADR 0009): FastAPI REST + WebSocket live event feed.
- Write contract (Phase 2 Wave 2a, ADR 0010): guarded mutation endpoints
  behind a bearer token + per-run CSRF + mandatory ``audit.write`` audit.

Key seams exported for programmatic use:

- :func:`create_app` — build the FastAPI application (read + guarded writes).
- :class:`WriteTokenService` — bearer-token lifecycle (create/rotate/revoke/
  verify; optional SHA-256 hash-at-rest; env override).
- :class:`CsrfService` — per-run synchronizer token checked on mutations.
- :func:`register_write_endpoints` — attach the write surface to an app.
"""

from ai_company.api.app import create_app
from ai_company.api.auth import CsrfService, WriteTokenService
from ai_company.api.write_endpoints import register_write_endpoints

__all__ = [
    "create_app",
    "CsrfService",
    "WriteTokenService",
    "register_write_endpoints",
]
