Build the Registry Engine.

The Registry Engine loads all company YAML files.

Validate every object.

Resolve references.

Create an in-memory company graph.

Detect duplicate IDs.

Detect broken relationships.

Produce a canonical registry object used by every subsystem.

Include complete unit tests.

Generate documentation.

Generate Mermaid diagrams.

ESTABLISHED VALIDATION PATTERN — FOLLOW THIS:

src/ai_company/cli/command_map.py already validates YAML-derived data
using a Pydantic BaseModel (CommandEntry) with explicit typed fields,
a default value where appropriate (description: str = ""), and a
loader function that:
  1. Reads the raw YAML into a plain dict
  2. Attempts to construct the Pydantic model per entry
  3. Collects every validation error before failing (not just the first)
  4. Reports all errors together with the offending key, then exits
     cleanly rather than raising an unhandled traceback

Every YAML-derived object in the Registry Engine (companies, departments,
executives, specialists, policies, workflows) must be validated the same
way: one Pydantic model per YAML object type, a loader that accumulates
and reports all errors together, and a clean failure path instead of a
raw stack trace reaching the user.

Do not invent a different validation approach (e.g. jsonschema, manual
dict checks, or silent defaults for missing required fields). Consistency
with the existing CommandEntry pattern matters more than any marginal
improvement a different approach might offer.
