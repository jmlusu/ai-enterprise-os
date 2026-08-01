"""CLI and runtime telemetry.

- :mod:`ai_company.telemetry.cli` — baseline CLI invocation telemetry
  (every ``ai-company ...`` invocation is appended to a JSONL log under
  the runtime data directory).
"""

from ai_company.telemetry.cli import record_cli_invocation

__all__ = ["record_cli_invocation"]
