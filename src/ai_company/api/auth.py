"""Write-auth infrastructure for the dashboard API (ADR 0010, Phase 2 wave 2a).

Delivers the security scheme ratified in ADR 0010:

- **Opaque bearer token** — ``secrets.token_urlsafe(32)`` (256-bit), stored in
  ``runtime/.write_token`` either plaintext or as a SHA-256 digest
  (``--hash-at-rest``), optionally overridden by the
  ``AI_ENTERPRISE_WRITE_TOKEN`` environment variable.
- **Synchronizer CSRF token** — per-run ``secrets.token_urlsafe(16)`` issued at
  boot; every mutation must echo it in the ``X-CSRF-Token`` header.
- **Mandatory write audit** — ``audit.write`` / ``audit.write_rejected`` events
  published to the EventBus on every write; publishing is fail-open to
  ``runtime/.audit.failed.jsonl`` and never blocks localhost writes.
- **Host allowlist** — loopback-only Host header defence (risk R9), shared by
  the security middleware and the write guard.

The write guard applies the ADR rules:
- non-loopback hosts are fail-closed (token mandatory) whenever reachable;
- loopback hosts may opt into a mandatory token via ``--require-loopback-token``;
- a provided token must always verify (invalid token -> 401);
- CSRF missing/mismatch -> 403.

Rejected writes publish ``audit.write_rejected`` without ever exposing the
submitted token or CSRF value.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ai_company.events import Event, EventMetadata, EventType

logger = logging.getLogger(__name__)

__all__ = [
    "ALLOWED_HOSTS",
    "CsrfService",
    "DEFAULT_AUDIT_FAILED_FILE",
    "DEFAULT_TOKEN_FILE",
    "TOKEN_ENV_VAR",
    "WriteTokenService",
    "host_allowed",
    "publish_write_audit",
    "publish_write_rejected",
]

#: Default on-disk token location (ADR 0010 §1).
DEFAULT_TOKEN_FILE = Path("runtime/.write_token")

#: Fail-open destination for audit events that could not be published.
DEFAULT_AUDIT_FAILED_FILE = Path("runtime/.audit.failed.jsonl")

#: Environment variable override for the write token (ADR 0010 §4).
TOKEN_ENV_VAR = "AI_ENTERPRISE_WRITE_TOKEN"

#: Loopback hosts only — DNS-rebinding defence (risk R9, ADR 0009/0010).
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


def host_allowed(host: str) -> bool:
    """Return True only for loopback Host headers (with or without port)."""
    host = (host or "").strip().lower()
    if not host:
        return False
    if host.startswith("["):  # IPv6 literal, e.g. "[::1]:8000"
        return host.split("]", 1)[0] + "]" in ALLOWED_HOSTS
    return host.split(":", 1)[0] in ALLOWED_HOSTS


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class WriteTokenService:
    """Opaque bearer-token store with optional hash-at-rest (ADR 0010).

    The token value is returned by :meth:`create` **only on first-time
    creation**; rotating an existing token never reveals the new value.
    Verification uses constant-time comparison.
    """

    def __init__(
        self,
        token_file: Path | str = DEFAULT_TOKEN_FILE,
        *,
        hash_at_rest: bool = False,
        env_token: str | None = None,
    ) -> None:
        self._token_file = Path(token_file)
        self._hash_at_rest = hash_at_rest
        self._env_token = env_token
        self._stored: str | None = None
        self._created_at: datetime | None = None
        self._load()

    # ── introspection ────────────────────────────────────────────────────

    @property
    def token_file(self) -> Path:
        return self._token_file

    @property
    def hash_at_rest(self) -> bool:
        return self._hash_at_rest

    @property
    def managed_by_env(self) -> bool:
        return self._env_token is not None

    @property
    def created_at(self) -> datetime | None:
        return self._created_at

    def has_token(self) -> bool:
        return self.managed_by_env or self._stored is not None

    def info(self) -> dict[str, Any]:
        """Metadata about the token — never the value itself."""
        return {
            "path": str(self._token_file),
            "managed_by_env": self.managed_by_env,
            "hash_at_rest": self._hash_at_rest,
            "created_at": self._created_at.isoformat() if self._created_at else None,
            "exists": self.managed_by_env or self._token_file.exists(),
        }

    # ── lifecycle ────────────────────────────────────────────────────────

    def create(self) -> str | None:
        """Create or rotate the token.

        Returns the plaintext value only when a token is created for the
        first time; returns ``None`` when an existing token was rotated
        (ADR 0010 §1: rotated tokens are not printed).
        """
        if self.managed_by_env:
            raise ValueError(
                f"Token is managed by {TOKEN_ENV_VAR}; "
                "create/rotate it through the environment"
            )
        was_absent = self._stored is None
        token = secrets.token_urlsafe(32)
        self._write_token(token)
        self._stored = token
        self._created_at = _utcnow()
        return token if was_absent else None

    def revoke(self) -> None:
        """Delete the token file; existing sessions are invalidated."""
        if self.managed_by_env:
            raise ValueError(
                f"Token is managed by {TOKEN_ENV_VAR}; revoke it through the environment"
            )
        try:
            self._token_file.unlink(missing_ok=True)
        except OSError:
            logger.debug("Token file already gone or not removable", exc_info=True)
        self._stored = None
        self._created_at = None

    def verify(self, token: str | None) -> bool:
        """Constant-time verification of a presented token."""
        if not token:
            return False
        expected = self._env_token if self._env_token is not None else self._stored
        if expected is None:
            return False
        if self._hash_at_rest and self._env_token is None:
            candidate = _sha256(token)
        else:
            candidate = token
        return hmac.compare_digest(candidate, expected)

    # ── internals ────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._env_token is not None:
            self._stored = None
            self._created_at = None
            return
        try:
            content = self._token_file.read_text(encoding="utf-8").strip()
        except OSError:
            content = ""
        if content:
            self._stored = content
            try:
                self._created_at = datetime.fromtimestamp(
                    self._token_file.stat().st_mtime, tz=UTC
                )
            except OSError:
                self._created_at = _utcnow()
        else:
            self._stored = None
            self._created_at = None

    def _write_token(self, token: str) -> None:
        self._token_file.parent.mkdir(parents=True, exist_ok=True)
        stored = _sha256(token) if self._hash_at_rest else token
        self._token_file.write_text(stored + "\n", encoding="utf-8")
        self._chmod_private(self._token_file)

    @staticmethod
    def _chmod_private(path: Path) -> None:
        if os.name != "posix":
            return  # Windows: file ACLs are out of scope (ADR 0010 §1)
        try:
            os.chmod(path, 0o600)
        except OSError:
            logger.debug("chmod 0600 failed for %s", path, exc_info=True)


class CsrfService:
    """Per-run synchronizer token checked on every mutation (ADR 0010 §2)."""

    def __init__(self, token: str | None = None) -> None:
        self._token = token or secrets.token_urlsafe(16)

    @property
    def token(self) -> str:
        return self._token

    def verify(self, value: str | None) -> bool:
        if not value:
            return False
        return hmac.compare_digest(value, self._token)


def _build_event(
    event_type: EventType, payload: dict[str, Any], actor: str = "dashboard"
) -> Event:
    return Event(
        metadata=EventMetadata(
            event_type=event_type,
            source="dashboard-api",
            user_id=actor,
        ),
        payload=payload,
    )


def _fail_open(
    bus: Any,
    event: Event,
    failed_path: Path,
) -> None:
    """Publish the audit event; on failure append to the fail-open JSONL file.

    Never raises: the audit must not block localhost writes (ADR 0010 §3).
    """
    try:
        bus.publish(event)
        return
    except Exception:
        logger.exception("Audit publish failed; appending to %s", failed_path)
    try:
        failed_path.parent.mkdir(parents=True, exist_ok=True)
        with failed_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(mode="json")) + "\n")
    except OSError:
        logger.exception("Audit fail-open write failed for %s", failed_path)


def publish_write_audit(
    bus: Any,
    *,
    action: str,
    result: str,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
    actor: str = "dashboard",
    failed_path: Path = DEFAULT_AUDIT_FAILED_FILE,
) -> None:
    """Publish an ``audit.write`` event for a completed write action."""
    payload: dict[str, Any] = {
        "action": action,
        "result": result,
        "actor": actor,
    }
    if reason is not None:
        payload["reason"] = reason
    if details:
        payload["details"] = details
    _fail_open(bus, _build_event(EventType.AUDIT_WRITE, payload, actor), failed_path)


def publish_write_rejected(
    bus: Any,
    *,
    action: str,
    reason: str,
    detail: str | None = None,
    actor: str = "dashboard",
    failed_path: Path = DEFAULT_AUDIT_FAILED_FILE,
) -> None:
    """Publish an ``audit.write_rejected`` event.

    The payload intentionally excludes the submitted token and CSRF value.
    """
    payload: dict[str, Any] = {
        "action": action,
        "reason": reason,
        "actor": actor,
    }
    if detail is not None:
        payload["detail"] = detail
    _fail_open(
        bus,
        _build_event(EventType.AUDIT_WRITE_REJECTED, payload, actor),
        failed_path,
    )
