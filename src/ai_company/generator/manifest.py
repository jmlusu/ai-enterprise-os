"""Manifest generation module for AI Enterprise OS Generator Engine.

This module provides functionality for generating, validating, and exporting
manifests for AI companies. Manifests describe the structure, dependencies,
and configuration of generated artifacts.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ManifestEntry:
    """Represents a single entry in the manifest."""

    id: str
    type: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    dependencies: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    checksum: str | None = None
    status: str = "pending"
    created_at: str | None = None
    updated_at: str | None = None
    generated_by: str | None = None
    output_path: str | None = None

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ManifestEntry):
            return NotImplemented
        return self.id == other.id


@dataclass
class GeneratorManifest:
    """Complete manifest for a generation process.

    Contains metadata, entries, configuration, and status information
    for the complete generation process.

    Args:
        plan_id: Unique identifier for the generation plan
        version: Manifest version
        manifest_type: Type of manifest (e.g., "company", "registry", "generation")
        entries: List of manifest entries
        metadata: Additional metadata for the manifest
    """

    plan_id: str
    version: str = "1.0.0"
    manifest_type: str = "generation"
    entries: list[ManifestEntry] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    manifest_checksum: str | None = None
    _created_at: str | None = None
    _updated_at: str | None = None

    @property
    def created_at(self) -> str:
        if self._created_at is None:
            self._created_at = datetime.now().isoformat()
        return self._created_at

    @created_at.setter
    def created_at(self, value: str) -> None:
        self._created_at = value

    @property
    def updated_at(self) -> str:
        self._updated_at = datetime.now().isoformat()
        return self._updated_at

    def add_entry(self, entry: ManifestEntry) -> None:
        """Add an entry to the manifest."""
        if entry.id in {e.id for e in self.entries}:
            # Update existing entry
            for i, e in enumerate(self.entries):
                if e.id == entry.id:
                    self.entries[i] = entry
                    break
        else:
            self.entries.append(entry)

    def get_entry(self, entry_id: str) -> ManifestEntry | None:
        """Get an entry by ID."""
        for entry in self.entries:
            if entry.id == entry_id:
                return entry
        return None

    def remove_entry(self, entry_id: str) -> bool:
        """Remove an entry by ID."""
        for i, entry in enumerate(self.entries):
            if entry.id == entry_id:
                del self.entries[i]
                return True
        return False

    def get_entries_by_type(self, entry_type: str) -> list[ManifestEntry]:
        """Get all entries of a given type."""
        return [e for e in self.entries if e.type == entry_type]

    def get_entries_by_status(self, status: str) -> list[ManifestEntry]:
        """Get all entries with a given status."""
        return [e for e in self.entries if e.status == status]

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest to dictionary."""
        return {
            "plan_id": self.plan_id,
            "version": self.version,
            "manifest_type": self.manifest_type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "entries_count": len(self.entries),
            "entries": [self._entry_to_dict(e) for e in self.entries],
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert manifest to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_yaml(self) -> str:
        """Convert manifest to YAML string."""
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    def validate(self) -> list[str]:
        """Validate the manifest and return errors.

        Returns:
            List of validation error messages. Empty if valid.
        """
        errors: list[str] = []

        if not self.plan_id:
            errors.append("Plan ID is required")

        if not self.entries:
            errors.append("Manifest must have at least one entry")

        # Check for duplicate entry IDs
        entry_ids = [e.id for e in self.entries]
        if len(entry_ids) != len(set(entry_ids)):
            errors.append("Duplicate entry IDs found")

        # Check for circular dependencies
        self._validate_dependencies(errors)

        # Validate entry attributes
        for entry in self.entries:
            if not entry.id:
                errors.append("Entry ID is required")
            if not entry.type:
                errors.append("Entry type is required")
            if not entry.name:
                errors.append("Entry name is required")

        return errors

    def export_to_file(
        self,
        output_path: Path,
        format: str = "json",
    ) -> Path:
        """Export manifest to a file.

        Args:
            output_path: Path to write the manifest file
            format: Export format ("json" or "yaml")

        Returns:
            Path to the exported file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            content = self.to_json()
        elif format == "yaml":
            content = self.to_yaml()
        else:
            raise ValueError(f"Unsupported format: {format}")

        output_path.write_text(content, encoding="utf-8")
        logger.debug(f"Exported manifest to {output_path}")

        return output_path.resolve()

    @staticmethod
    def load_from_file(file_path: Path) -> GeneratorManifest:
        """Load a manifest from a file.

        Args:
            file_path: Path to the manifest file

        Returns:
            Loaded GeneratorManifest

        Raises:
            ValueError: If manifest format is not recognized
        """
        content = file_path.read_text(encoding="utf-8")

        if file_path.suffix in (".yaml", ".yml"):
            data = yaml.safe_load(content)
        elif file_path.suffix == ".json":
            data = json.loads(content)
        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")

        manifest = GeneratorManifest(
            plan_id=data["plan_id"],
            version=data.get("version", "1.0.0"),
            manifest_type=data.get("manifest_type", "generation"),
            metadata=data.get("metadata", {}),
        )
        manifest._created_at = data.get("created_at")
        manifest._updated_at = data.get("updated_at")

        for entry_data in data.get("entries", []):
            entry = ManifestEntry(
                id=entry_data["id"],
                type=entry_data["type"],
                name=entry_data["name"],
                description=entry_data.get("description", ""),
                version=entry_data.get("version", "1.0.0"),
                dependencies=entry_data.get("dependencies", []),
                tags=entry_data.get("tags", []),
                metadata=entry_data.get("metadata", {}),
                checksum=entry_data.get("checksum"),
                status=entry_data.get("status", "pending"),
                created_at=entry_data.get("created_at"),
                updated_at=entry_data.get("updated_at"),
                generated_by=entry_data.get("generated_by"),
                output_path=entry_data.get("output_path"),
            )
            manifest.add_entry(entry)

        return manifest

    @staticmethod
    def from_registry(
        registry: Any,
        plan_id: str,
        manifest_type: str = "registry",
    ) -> GeneratorManifest:
        """Create a manifest from a CompanyRegistry.

        Args:
            registry: CompanyRegistry instance
            plan_id: Plan identifier
            manifest_type: Type of manifest

        Returns:
            Created GeneratorManifest
        """
        manifest = GeneratorManifest(
            plan_id=plan_id,
            manifest_type=manifest_type,
        )

        # Add entries from registry
        if hasattr(registry, "executives"):
            for exec_ in registry.executives or []:
                if exec_.name:
                    entry = ManifestEntry(
                        id=f"executive:{exec_.name.lower().replace(' ', '_')}",
                        type="executive",
                        name=exec_.name,
                        description=exec_.bio or "",
                        metadata={"title": exec_.title, "department": exec_.department},
                    )
                    manifest.add_entry(entry)

        if hasattr(registry, "specialists"):
            for spec in registry.specialists or []:
                if spec.name:
                    entry = ManifestEntry(
                        id=f"specialist:{spec.name.lower().replace(' ', '_')}",
                        type="specialist",
                        name=spec.name,
                        description=spec.expertise or "",
                        metadata={"expertise": spec.expertise},
                    )
                    manifest.add_entry(entry)

        if hasattr(registry, "departments"):
            for dept_name, dept_data in (registry.departments or {}).items():
                entry = ManifestEntry(
                    id=f"department:{dept_name.lower().replace(' ', '_')}",
                    type="department",
                    name=dept_name,
                    description=getattr(dept_data, "description", "") or "",
                    metadata={"roles": len(getattr(dept_data, "roles", []))},
                )
                manifest.add_entry(entry)

        return manifest

    def _entry_to_dict(self, entry: ManifestEntry) -> dict[str, Any]:
        """Convert a single ManifestEntry to a dictionary."""
        return {
            "id": entry.id,
            "type": entry.type,
            "name": entry.name,
            "description": entry.description,
            "version": entry.version,
            "dependencies": entry.dependencies,
            "tags": entry.tags,
            "metadata": entry.metadata,
            "checksum": entry.checksum,
            "status": entry.status,
            "created_at": entry.created_at or datetime.now().isoformat(),
            "updated_at": entry.updated_at or datetime.now().isoformat(),
            "generated_by": entry.generated_by,
            "output_path": entry.output_path,
        }

    def _validate_dependencies(self, errors: list[str]) -> None:
        """Validate dependency references in entries."""
        entry_ids = {e.id for e in self.entries}

        for entry in self.entries:
            for dep_id in entry.dependencies:
                if dep_id not in entry_ids:
                    errors.append(
                        f"Entry '{entry.id}' depends on missing entry '{dep_id}'"
                    )


class ManifestBuilder:
    """Builder for constructing manifests programmatically.

    Provides a fluent interface for building manifests step by step.
    """

    def __init__(self) -> None:
        self.entries: list[ManifestEntry] = []

    def add_entry(
        self,
        entry_id: str,
        entry_type: str,
        name: str,
        description: str = "",
        version: str = "1.0.0",
        dependencies: list[str] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        generated_by: str | None = None,
        output_path: str | None = None,
    ) -> ManifestBuilder:
        """Add an entry to the manifest."""
        entry = ManifestEntry(
            id=entry_id,
            type=entry_type,
            name=name,
            description=description,
            version=version,
            dependencies=dependencies or [],
            tags=tags or [],
            metadata=metadata or {},
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            generated_by=generated_by,
            output_path=output_path,
        )
        self.entries.append(entry)
        return self

    def build(self, plan_id: str, manifest_type: str = "custom") -> GeneratorManifest:
        """Build the manifest with accumulated entries.

        Args:
            plan_id: Plan identifier
            manifest_type: Type of manifest

        Returns:
            Constructed GeneratorManifest
        """
        manifest = GeneratorManifest(
            plan_id=plan_id,
            manifest_type=manifest_type,
            entries=self.entries,
        )
        return manifest


class ManifestError(Exception):
    """Exception raised for manifest-related errors."""

    def __init__(self, message: str, manifest_id: str | None = None) -> None:
        super().__init__(message)
        self.manifest_id = manifest_id
