"""Dashboard API package (ADR 0002 / ADR 0009).

Read-only contract v1: FastAPI REST + WebSocket live event feed served by
``ai-company serve``.
"""

from ai_company.api.app import create_app

__all__ = ["create_app"]
