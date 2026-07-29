import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from ai_company.registry.engine import registry

class GeneratorEngine:
    def __init__(self, template_dir: str = "templates", output_dir: str = "generated"):
        self.template_dir = Path(template_dir)
        self.output_dir = Path(output_dir)
        
        if not self.template_dir.exists():
            self.template_dir.mkdir(parents=True, exist_ok=True)
            
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=False
        )

    def render_template(self, template_name: str, output_path: Path):
        """Renders a single Jinja2 template using the Registry context."""
        try:
            template = self.env.get_template(template_name)
        except TemplateNotFound:
            print(f"Warning: Template {template_name} not found.")
            return

        # Inject the loaded company config into the template context
        context = {"company": registry.config.model_dump()}
        rendered_content = template.render(**context)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered_content, encoding="utf-8")
        print(f"Generated: {output_path}")

    def render_all(self):
        """Renders all .j2 templates in the template directory."""
        if not registry.config:
            raise RuntimeError("Registry must be loaded before generating.")
            
        for template_file in self.template_dir.rglob("*.j2"):
            relative_path = template_file.relative_to(self.template_dir)
            # Remove .j2 extension for the final output
            out_name = relative_path.with_suffix("") 
            output_path = self.output_dir / out_name
            self.render_template(str(relative_path), output_path)

# Singleton instance
generator = GeneratorEngine()