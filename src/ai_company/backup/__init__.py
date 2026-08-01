"""Backup bundles for gitignored runtime state.

- :mod:`ai_company.backup.backup` — create timestamped tar.gz bundles of
  the runtime data directories (memory/, events/, generated/, runtime/,
  .ai-company/) that are gitignored and have no other off-box copy, and
  restore them back to disk safely.
- ``python -m ai_company.backup`` — command line entry point.
"""

from ai_company.backup.backup import (
    DEFAULT_SOURCE_DIRS,
    create_backup,
    restore_backup,
)

__all__ = ["DEFAULT_SOURCE_DIRS", "create_backup", "restore_backup"]
