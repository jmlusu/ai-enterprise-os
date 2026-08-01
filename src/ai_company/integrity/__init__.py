"""Repository integrity checks executed by CI (and locally).

- ``ai_company.integrity.check_command_map`` — verifies the
  command_map.yaml <-> prompts/opencode/ <-> opencode.json contract.

Run the checks with::

    uv run python -m ai_company.integrity.check_command_map
"""
