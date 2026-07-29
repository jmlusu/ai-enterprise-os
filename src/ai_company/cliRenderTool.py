import os
from pathlib import Path
import typer
import yaml
from jinja2 import Template
from pydantic import BaseModel, ValidationError

app = typer.Typer(help="Template Generation and Rendering Tool")

class VisionConfig(BaseModel):
    name: str
    description: str | None = None
    company_name: str | None = None

class CompanyConfig(BaseModel):
    vision: VisionConfig | None = None

@app.command()
def generate(
    config_path: Path = typer.Option(..., "--file", "-f", help="Path to company.yaml"),
    output_dir: Path = typer.Option(Path(".ai-company/templates"), "--output", "-o", help="Output directory")
):
    """Generate template files based on company.yaml configuration."""
    if not config_path.exists():
        typer.secho(f"Error: Configuration file {config_path} not found.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
        
        config = CompanyConfig(**raw_data)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        if config.vision:
            vision_dir = output_dir / "vision"
            vision_dir.mkdir(exist_ok=True)
            
            html_template = """<html>
<head>
    <title>Vision Summary: {{ name }}</title>
</head>
<body>
    <h1>{{ name }} Summary Report</h1>
    <p>{{ description }}</p>
    <p>Company: {{ company_name }}</p>
</body>
</html>"""
            
            template = Template(html_template)
            rendered = template.render(
                name=config.vision.name,
                description=config.vision.description or "No description provided.",
                company_name=config.vision.company_name or "Unknown Company"
            )
            
            output_file = vision_dir / "vision_summary.html"
            output_file.write_text(rendered, encoding="utf-8")
            typer.secho(f"Successfully generated: {output_file}", fg=typer.colors.GREEN)
        else:
            typer.secho("Warning: No 'vision' section found in configuration.", fg=typer.colors.YELLOW)

    except ValidationError as e:
        typer.secho("Validation Error against schema:", fg=typer.colors.RED)
        typer.echo(e)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"An unexpected error occurred: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()