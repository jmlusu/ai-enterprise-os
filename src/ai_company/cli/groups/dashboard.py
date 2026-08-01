"""Dashboard API CLI group: write-token management (ADR 0010).

Provides the ``ai-company dashboard`` command tree:

- ``dashboard token create`` — create or rotate the write token; the plaintext
  value is printed **only** on first-time creation (rotations never echo it).
- ``dashboard token revoke`` — delete the token file; existing sessions are
  invalidated immediately.
- ``dashboard token list``   — show token metadata (never the value).
- ``dashboard token info``   — alias of ``list`` (metadata only).

The token is the bearer credential for every Phase 2 write endpoint
(ADR 0010 §1): opaque ``secrets.token_urlsafe(32)`` (256-bit), stored in
``runtime/.write_token`` either plaintext or as a SHA-256 digest
(``--hash-at-rest``), with ``AI_ENTERPRISE_WRITE_TOKEN`` as the environment
override. The token file lives relative to the working directory, matching the
rest of the CLI tree (frozen per ADR 0006 — this group is purely additive).
"""

from __future__ import annotations

import typer

from ai_company.api.auth import TOKEN_ENV_VAR, WriteTokenService
from ai_company.utils.console import console_print

app = typer.Typer(help="Dashboard API operations (write-token management)")
token_app = typer.Typer(help="Write-token management (ADR 0010)")
app.add_typer(token_app, name="token")


def _service(hash_at_rest: bool, token_file: str) -> WriteTokenService:
    return WriteTokenService(token_file=token_file, hash_at_rest=hash_at_rest)


@token_app.command("create")
def token_create(
    hash_at_rest: bool = typer.Option(
        False,
        "--hash-at-rest",
        help="Store a SHA-256 digest instead of the plaintext token (ADR 0010 section 1)",
    ),
    token_file: str = typer.Option(
        "runtime/.write_token",
        "--token-file",
        help="Token file path (relative to the working directory)",
    ),
) -> None:
    """Create or rotate the write token (value printed only on first creation)."""
    service = _service(hash_at_rest, token_file)
    try:
        created = service.create()
    except ValueError as exc:
        console_print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    if created is not None:
        console_print("[green]✓[/green] Write token created (store it safely):")
        console_print(f"  [bold cyan]{created}[/bold cyan]")
        console_print(
            "[dim]The value is not shown again. Revoke with "
            "`ai-company dashboard token revoke`.[/dim]"
        )
    else:
        console_print(
            "[yellow]Token rotated.[/yellow] The new value is not shown "
            "(ADR 0010 section 1: rotated tokens are never printed)."
        )
    console_print(_format_info(service))


@token_app.command("revoke")
def token_revoke(
    token_file: str = typer.Option(
        "runtime/.write_token",
        "--token-file",
        help="Token file path (relative to the working directory)",
    ),
) -> None:
    """Delete the write token file (invalidates all existing sessions)."""
    service = _service(hash_at_rest=False, token_file=token_file)
    if service.managed_by_env:
        console_print(
            f"[red]Token is managed by {TOKEN_ENV_VAR}; "
            "revoke it through the environment.[/red]"
        )
        raise typer.Exit(1)
    service.revoke()
    console_print("[green]✓[/green] Write token revoked.")
    console_print("[dim]All open dashboard sessions are now invalidated.[/dim]")


@token_app.command("list")
def token_list(
    token_file: str = typer.Option(
        "runtime/.write_token",
        "--token-file",
        help="Token file path (relative to the working directory)",
    ),
) -> None:
    """Show write-token metadata (never the value)."""
    service = _service(hash_at_rest=False, token_file=token_file)
    console_print(_format_info(service))


@token_app.command("info")
def token_info(
    token_file: str = typer.Option(
        "runtime/.write_token",
        "--token-file",
        help="Token file path (relative to the working directory)",
    ),
) -> None:
    """Alias of ``list``: show write-token metadata."""
    token_list(token_file=token_file)


def _format_info(service: WriteTokenService) -> str:
    info = service.info()
    status = "[green]present[/green]" if service.has_token() else "[dim]absent[/dim]"
    return (
        "Write token:\n"
        f"  Status: {status}\n"
        f"  Path: {info['path']}\n"
        f"  Managed by env ({TOKEN_ENV_VAR}): {'yes' if info['managed_by_env'] else 'no'}\n"
        f"  Hash at rest: {'yes' if info['hash_at_rest'] else 'no'}\n"
        f"  Created at: {info['created_at'] or '-'}"
    )


__all__ = ["app"]
