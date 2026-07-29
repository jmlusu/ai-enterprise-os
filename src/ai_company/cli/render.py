from pathlib import Path
import yaml
from jinja2 import Template

COMPANY_YAML = Path("company/company.yaml")
TMP_PROMPT = Path(".ai-company/.tmp_rendered_prompt.md")


def render_prompt(prompt_file: str) -> Path:
    registry = yaml.safe_load(COMPANY_YAML.read_text())
    raw = Path(prompt_file).read_text()
    rendered = Template(raw).render(company=registry)
    TMP_PROMPT.parent.mkdir(parents=True, exist_ok=True)
    TMP_PROMPT.write_text(rendered)
    return TMP_PROMPT
