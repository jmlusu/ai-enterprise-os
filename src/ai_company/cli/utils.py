"""Shared utilities for CLI command groups."""

from pathlib import Path

import typer

from ai_company.models.company import CompanyManifest, CompanyRegistry
from ai_company.registry.registry import RegistryEngine
from ai_company.utils.console import console_print


def load_registry_and_manifest(
    company_dir: str | Path = Path("company"),
    config_dir: str | Path = Path("config/company"),
    manifest_path: str | Path = Path("config/company/company.yaml"),
) -> tuple[CompanyRegistry, CompanyManifest]:
    """Load registry and manifest, exiting on failure.

    Returns:
        Tuple of (CompanyRegistry, CompanyManifest).
    """
    engine = RegistryEngine()

    # Load manifest
    manifest_path = Path(manifest_path)
    manifest: CompanyManifest | None = None
    if manifest_path.exists():
        try:
            manifest = CompanyManifest.load(manifest_path)
        except (FileNotFoundError, ValueError) as e:
            console_print(f"[red]Failed to load manifest:[/red] {e}")
            raise typer.Exit(1) from e

    # Load registry
    result = engine.load(
        Path(company_dir),
        manifest=manifest,
        config_dir=Path(config_dir),
    )

    if not result.success or result.registry is None:
        for err in result.errors:
            console_print(f"  [red]✗[/red] {err}")
        raise typer.Exit(1)

    if result.warnings:
        for w in result.warnings:
            console_print(f"  [yellow]![/yellow] {w}")

    return result.registry, result.manifest or manifest  # type: ignore[return-value]
