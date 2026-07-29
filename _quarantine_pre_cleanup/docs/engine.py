from pathlib import Path
from ai_company.registry.engine import registry

class DocsEngine:
    def __init__(self, output_dir: str = "docs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_architecture_doc(self):
        if not registry._config:
            raise RuntimeError("Registry must be loaded first.")
            
        content = f"""# AI Enterprise OS Architecture
**Company:** {registry.config.vision.company_name}
**Vision:** {registry.config.vision.name}

## Overview
{registry.config.vision.description}

## Core Subsystems
1. **Registry Engine:** Loads and validates company.yaml.
2. **Generator Engine:** Renders Jinja2 templates.
3. **CLI Dispatcher:** Typer-based command routing.
4. **Docs Engine:** Generates this documentation.
5. **Agents Engine:** Defines OpenCode agent personas.
6. **Dashboard Engine:** Renders state and health dashboards.
"""
        out_file = self.output_dir / "architecture.md"
        out_file.write_text(content, encoding="utf-8")
        print(f"Generated: {out_file}")

docs_engine = DocsEngine()