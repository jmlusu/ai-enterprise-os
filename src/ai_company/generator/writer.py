"""File writing utility for AI Enterprise OS Generator Engine.

This module provides file writing functionality for the generation process,
including safe file writing, backup creation, and content validation.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FileWriteError(Exception):
    """Exception raised when file writing fails."""

    def __init__(
        self, message: str, file_path: str | None = None, error_code: str | None = None
    ) -> None:
        super().__init__(message)
        self.file_path = file_path
        self.error_code = error_code


class BackupInfo:
    """Contains information about a backup operation."""

    def __init__(
        self,
        original_path: str,
        backup_path: str,
        size: int,
        checksum: str | None = None,
        backup_time: datetime | None = None,
    ) -> None:
        self.original_path = original_path
        self.backup_path = backup_path
        self.size = size
        self.checksum = checksum
        self.backup_time = backup_time or datetime.now()


class FileValidationError(Exception):
    """Exception raised when file validation fails."""

    def __init__(
        self,
        message: str,
        file_path: str,
        validation_type: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.file_path = file_path
        self.validation_type = validation_type
        self.details = details or {}


class FileWriter:
    """Utility for writing files safely during generation.

    This class provides methods for:
    1. Writing content to files with proper directory creation
    2. Creating backups of existing files
    3. Validating file content before writing
    4. Generating and storing file checksums
    5. Implementing rollback capability
    6. Supporting dry-run mode

    Args:
        backup_enabled: Whether to create backups of existing files
        checksum_enabled: Whether to generate and store checksums
        validation_enabled: Whether to validate content before writing
        dry_run: Whether to simulate operations without writing
        output_dir: Base output directory
        custom_permissions: Custom file permissions (not implemented on all platforms)
    """

    def __init__(
        self,
        backup_enabled: bool = True,
        checksum_enabled: bool = True,
        validation_enabled: bool = True,
        dry_run: bool = False,
        output_dir: Path | None = None,
        custom_permissions: dict[str, int] | None = None,
    ) -> None:
        self.backup_enabled = backup_enabled
        self.checksum_enabled = checksum_enabled
        self.validation_enabled = validation_enabled
        self.dry_run = dry_run
        self.output_dir = output_dir or Path("generated")
        self.custom_permissions = custom_permissions or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        self.backups: dict[str, BackupInfo] = {}
        self.checksums: dict[str, str] = {}
        self.written_files: list[str] = []
        self.skipped_files: list[str] = []

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        content: str,
        destination: Path,
        backup: bool | None = None,
        validation_callbacks: list[Any] | None = None,
        file_metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Write content to a file.

        Args:
            content: Content to write
            destination: Destination path (relative to output_dir)
            backup: Whether to backup (uses instance default if None)
            validation_callbacks: List of validation functions to call
            file_metadata: Additional metadata about the file

        Returns:
            Absolute path to the written file

        Raises:
            FileWriteError: If writing fails
            FileValidationError: If validation fails
        """
        backup = backup if backup is not None else self.backup_enabled

        # Resolve absolute path
        absolute_destination = self.output_dir / destination
        absolute_destination = absolute_destination.resolve()

        # Create parent directories if needed
        absolute_destination.parent.mkdir(parents=True, exist_ok=True)

        # Validate content if enabled
        if self.validation_enabled and validation_callbacks:
            self._validate_content(absolute_destination, content, validation_callbacks)

        # Skip if file exists and has same content (incremental mode)
        if absolute_destination.exists():
            existing_checksum = self.checksums.get(str(absolute_destination))
            if existing_checksum:
                new_checksum = self._calculate_checksum(content)
                if existing_checksum == new_checksum:
                    self.logger.info(
                        f"File {absolute_destination} has not changed, skipping"
                    )
                    self.skipped_files.append(str(absolute_destination))
                    return absolute_destination

        # Create backup if enabled and file exists
        if backup and absolute_destination.exists():
            self._create_backup(absolute_destination)

        # Write file
        try:
            if not self.dry_run:
                # Write content
                absolute_destination.write_text(content, encoding="utf-8")

                # Generate checksum
                if self.checksum_enabled:
                    checksum = self._calculate_checksum(content)
                    self.checksums[str(absolute_destination)] = checksum

                self.written_files.append(str(absolute_destination))

                # Apply custom permissions if specified
                self._apply_custom_permissions(absolute_destination)

                self.logger.info(f"Written file: {absolute_destination}")
            else:
                self.logger.info(f"[DRY RUN] Would write file: {absolute_destination}")

            # Store file metadata
            if file_metadata:
                self._store_file_metadata(absolute_destination, file_metadata)

            return absolute_destination

        except Exception as e:
            error_message = f"Failed to write file {absolute_destination}: {e!s}"
            self.logger.error(error_message)
            raise FileWriteError(
                error_message, str(absolute_destination), "write_failed"
            ) from e

    def ensure_dir(self, path: Path) -> Path:
        """Ensure a directory exists.

        Args:
            path: Directory path to ensure exists

        Returns:
            Absolute path to the directory
        """
        absolute_path = self.output_dir / path
        absolute_path.mkdir(parents=True, exist_ok=True)
        return absolute_path.resolve()

    def get_checksum(self, file_path: Path) -> str | None:
        """Get checksum for a file.

        Args:
            file_path: Path to the file

        Returns:
            Checksum if available, None otherwise
        """
        absolute_path = self.output_dir / file_path
        return self.checksums.get(str(absolute_path.resolve()))

    def is_file_changed(self, file_path: Path) -> bool:
        """Check if a file has changed based on stored checksums.

        Args:
            file_path: Path to the file

        Returns:
            True if file has changed or checksum not available
        """
        absolute_path = self.output_dir / file_path
        if not absolute_path.exists():
            return True

        checksum = self.get_checksum(file_path)
        if checksum is None:
            return True

        try:
            current_content = absolute_path.read_text(encoding="utf-8")
            current_checksum = self._calculate_checksum(current_content)
            return checksum != current_checksum
        except Exception as e:
            self.logger.error(f"Failed to check file {file_path}: {e}")
            return True

    def can_write_file(
        self,
        file_path: Path,
        content: str | None = None,
    ) -> tuple[bool, list[str]]:
        """Check if a file can be written (permissions, validation, etc.).

        Args:
            file_path: Path to the file
            content: Optional content to validate

        Returns:
            Tuple of (can_write, list_of_issues)
        """
        issues: list[str] = []
        absolute_path = self.output_dir / file_path

        # Check if parent directory exists and is writable
        if not absolute_path.parent.exists():
            issues.append(f"Parent directory does not exist: {absolute_path.parent}")

        # Check if file exists and is writable
        if absolute_path.exists():
            if not absolute_path.is_file():
                issues.append(f"Path exists but is not a file: {absolute_path}")

            try:
                # Test write permission
                test_file = absolute_path.with_suffix(
                    f".{datetime.now().timestamp()}.test"
                )
                test_file.write_text("test", encoding="utf-8")
                test_file.unlink()
            except Exception as e:
                issues.append(f"File is not writable: {e!s}")

        # Validate content if provided
        if content and self.validation_enabled:
            try:
                if not isinstance(content, str):
                    issues.append(f"Content is not a string: {type(content)}")
            except Exception as e:
                issues.append(f"Content validation failed: {e!s}")

        return len(issues) == 0, issues

    def rollback_file(self, file_path: str) -> bool:
        """Rollback a file to its backup if available.

        Args:
            file_path: Absolute path to the file

        Returns:
            True if rollback was successful, False otherwise
        """
        if file_path not in self.backups:
            self.logger.warning(f"No backup available for file: {file_path}")
            return False

        backup_info = self.backups[file_path]

        try:
            # Read backup content
            with open(backup_info.backup_path, "r", encoding="utf-8") as f:
                backup_content = f.read()

            # Write backup content to original location
            original_path = Path(file_path)
            original_path.write_text(backup_content, encoding="utf-8")

            # Update checksums
            self.checksums[file_path] = (
                backup_info.checksum or self._calculate_checksum(backup_content)
            )

            self.logger.info(
                f"Rolled back file: {file_path} to {backup_info.backup_path}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Failed to rollback file {file_path}: {e!s}")
            return False

    def rollback_all(self) -> list[str]:
        """Rollback all files to their backup versions.

        Returns:
            List of successfully rolled back files
        """
        rolled_back = []
        for file_path in list(self.backups.keys()):
            if self.rollback_file(file_path):
                rolled_back.append(file_path)

        self.logger.info(f"Rolled back {len(rolled_back)} files")
        return rolled_back

    def get_write_stats(self) -> dict[str, Any]:
        """Get statistics about file writing operations."""
        return {
            "total_written": len(self.written_files),
            "total_skipped": len(self.skipped_files),
            "total_backups": len(self.backups),
            "checksums_generated": len(self.checksums),
            "written_files": self.written_files,
            "skipped_files": self.skipped_files,
            "backup_files": list(self.backups.keys()),
        }

    def _calculate_checksum(self, content: str) -> str:
        """Calculate checksum for content."""
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    def _create_backup(self, file_path: Path) -> None:
        """Create backup of existing file."""
        try:
            # Generate backup filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"{file_path.name}.{timestamp}.backup"
            backup_path = file_path.parent / backup_filename

            # Copy file content
            content = file_path.read_text(encoding="utf-8")
            backup_path.write_text(content, encoding="utf-8")

            # Calculate checksum
            checksum = self._calculate_checksum(content)

            # Store backup info
            backup_info = BackupInfo(
                original_path=str(file_path),
                backup_path=str(backup_path),
                size=file_path.stat().st_size,
                checksum=checksum,
                backup_time=datetime.now(),
            )

            self.backups[str(file_path)] = backup_info
            self.logger.info(f"Created backup: {backup_path}")

        except Exception as e:
            self.logger.error(f"Failed to create backup for {file_path}: {e}")

    def _apply_custom_permissions(self, file_path: Path) -> None:
        """Apply custom permissions to a file."""
        # Note: This is platform-dependent and may not work on all systems
        try:
            # For Windows, this is a no-op as file permissions are handled differently
            # For Unix-like systems, we could use os.chmod
            self.logger.debug(
                f"Applying permissions to {file_path} (platform may affect availability)"
            )
        except Exception as e:
            self.logger.warning(f"Could not apply permissions: {e}")

    def _validate_content(
        self,
        file_path: Path,
        content: str,
        validation_callbacks: list[Any],
    ) -> None:
        """Validate content using provided callbacks."""
        for callback in validation_callbacks:
            try:
                if callable(callback):
                    validation_result = callback(file_path, content)
                    if validation_result is False:
                        raise FileValidationError(
                            f"Content validation failed for {file_path}",
                            str(file_path),
                            "callback",
                        )
            except FileValidationError:
                raise
            except Exception as e:
                self.logger.warning(f"Validation callback failed for {file_path}: {e}")

    def _store_file_metadata(self, file_path: Path, metadata: dict[str, Any]) -> None:
        """Store metadata for a written file."""
        try:
            metadata_file = file_path.with_suffix(".metadata.json")
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Could not store metadata for {file_path}: {e}")
