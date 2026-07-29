from pathlib import Path

from ai_company.models.company import CompanyManifest
from ai_company.template_engine import Renderer

TMP_PROMPT = Path(".ai-company/.tmp_rendered_prompt.md")


def render_prompt(prompt_file: str) -> Path:
    manifest = CompanyManifest.load(Path("config/company/company.yaml"))
    context = {
        "company": {
            "name": manifest.name,
            "company_name": manifest.company_name or "",
            "description": manifest.description or "",
            "departments": [d.name for d in manifest.departments],
        }
    }
    raw = Path(prompt_file).read_text(encoding="utf-8")
    renderer = Renderer()
    rendered = renderer.render(raw, context, fmt="jinja")
    TMP_PROMPT.parent.mkdir(parents=True, exist_ok=True)
    TMP_PROMPT.write_text(rendered, encoding="utf-8")
    return TMP_PROMPT
