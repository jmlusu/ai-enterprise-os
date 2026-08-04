"""Shared write-auth guard for mutation endpoints (ADR 0010).

Both wave 2a (``write_endpoints.py``) and wave 2b (``operational_endpoints.py``)
implement the identical guard contract:

1. bearer token verification (mandatory on non-loopback hosts, opt-in on
   loopback via ``require_loopback_token``), plus the ``X-CSRF-Token``
   synchronizer check;
2. ``audit.write_rejected`` published (fail-open) on every rejection, without
   exposing the submitted token/CSRF values;
3. high-impact actions require a non-blank ``reason`` (HTTP 422) and publish
   ``audit.write_rejected`` with reason ``missing_reason``;
4. successful mutations publish ``audit.write`` via ``audited()``.

:class:`WriteGuard` centralizes that logic so wave 2b endpoints get exactly
the same guarantees as wave 2a with no duplicated code.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import HTTPException, Request

from ai_company.api.auth import (
    DEFAULT_AUDIT_FAILED_FILE,
    CsrfService,
    WriteTokenService,
    host_allowed,
    publish_write_audit,
    publish_write_rejected,
)
from ai_company.events import EventBus
from ai_company.telemetry.actions import record_action

__all__ = ["HIGH_IMPACT_ACTIONS", "WriteGuard"]

#: Actions that must carry a human-provided reason (ADR 0010 §5).
HIGH_IMPACT_ACTIONS: frozenset[str] = frozenset(
    {
        "runtime.stop",
        "runtime.restart",
        "runtime.recover",
        "runtime.unisolate",
        "orchestrate.rollback",
    }
)


class WriteGuard:
    """Stateless-ish guard factory: one instance per registered app."""

    def __init__(
        self,
        *,
        tokens: WriteTokenService,
        csrf: CsrfService,
        bus: EventBus | None,
        require_loopback_token: bool = False,
        audit_failed_file: Path = DEFAULT_AUDIT_FAILED_FILE,
    ) -> None:
        self._tokens = tokens
        self._csrf = csrf
        self._bus = bus
        self._require_loopback_token = require_loopback_token
        self._failed_path = audit_failed_file

    def reject(self, action: str, reason: str, detail: str | None = None) -> None:
        """Publish an ``audit.write_rejected`` event (fail-open)."""
        if self._bus is not None:
            publish_write_rejected(
                self._bus,
                action=action,
                reason=reason,
                detail=detail,
                failed_path=self._failed_path,
            )

    def guard(self, action: str) -> Callable[[Request], None]:
        """Build a FastAPI dependency enforcing token + CSRF for ``action``."""

        def _require_write_auth(request: Request) -> None:
            host = request.headers.get("host", "")
            loopback = host_allowed(host)
            token_required = (not loopback) or self._require_loopback_token
            auth_header = request.headers.get("authorization", "")
            token = (
                auth_header[7:].strip()
                if auth_header.lower().startswith("bearer ")
                else None
            )
            if token is not None:
                if not self._tokens.verify(token):
                    self.reject(action, "unauthorized", "invalid token")
                    raise HTTPException(status_code=401, detail="invalid write token")
            elif token_required:
                self.reject(action, "unauthorized", "missing token")
                raise HTTPException(status_code=401, detail="write token required")
            csrf_value = request.headers.get("x-csrf-token")
            if not self._csrf.verify(csrf_value):
                self.reject(action, "csrf_mismatch", "missing or invalid CSRF token")
                raise HTTPException(status_code=403, detail="invalid CSRF token")

        return _require_write_auth

    def require_reason(self, action: str, reason: str | None) -> None:
        """Enforce the ADR reason requirement for high-impact actions."""
        if action in HIGH_IMPACT_ACTIONS and (not reason or not reason.strip()):
            self.reject(
                action,
                "missing_reason",
                detail="reason is required for high-impact action",
            )
            raise HTTPException(
                status_code=422,
                detail=f"reason is required for high-impact action: {action}",
            )

    def audited(
        self,
        result: dict[str, object],
        action: str,
        reason: str | None = None,
        extra: dict[str, object] | None = None,
        source: str | None = "gui",
    ) -> dict[str, object]:
        """Publish an ``audit.write`` event (fail-open) and return ``result``.

        ``source`` feeds the D5 action telemetry (sprint 5.5 P5): ``"gui"``
        for dashboard operator writes, ``"desktop"`` for desktop-originated
        writes, and ``None`` to skip recording (telemetry plumbing such as
        ``telemetry.session.persist`` is not an operator action). Recording is
        fail-open and never affects the returned result.
        """
        if self._bus is not None:
            status = "ok" if result.get("success") else "failed"
            details: dict[str, object] = dict(extra or {})
            errors = result.get("errors")
            if errors:
                details["errors"] = errors
            publish_write_audit(
                self._bus,
                action=action,
                result=status,
                reason=reason,
                details=details or None,
                failed_path=self._failed_path,
            )
        if source is not None:
            record_action(source, action)
        return result
