# AI Enterprise OS Constitution

## Core Directives for OpenCode Sessions
1. **Read State First:** Every session MUST read `.ai-company/state/current_sprint.yaml` before writing code.
2. **Always use Pydantic v2** for all data validation and schemas.
3. **Never use pseudo-code or placeholders** in production files.
4. **Strict Typing:** All Python modules must use standard `typing`.
5. **Update State Last:** Every session must update the sprint state upon completion.