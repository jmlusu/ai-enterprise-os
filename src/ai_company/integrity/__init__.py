"""Repository integrity checks executed by CI (and locally).

- ``ai_company.integrity.check_command_map`` — verifies the
  command_map.yaml <-> prompts/opencode/ <-> opencode.json contract.
- ``ai_company.integrity.check_cli_surface`` — enforces the frozen CLI
  surface (ADR 0006): no removals/renames/changes; additive drift is
  accepted only via ``--update`` (R8).

Run the checks with::

    uv run python -m ai_company.integrity.check_command_map
    uv run python -m ai_company.integrity.check_cli_surface
"""
