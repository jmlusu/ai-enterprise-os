from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


@dataclass
class TemplateInfo:
    content: str
    path: Path | None = None
    engine: str = "jinja"
    format: str = "jinja"
    variables: list[str] | None = None
    dependencies: list[str] | None = None
    last_modified: str | None = None

    def __post_init__(self) -> None:
        if self.path and self.path.exists():
            mtime = self.path.stat().st_mtime
            from datetime import datetime

            self.last_modified = datetime.fromtimestamp(mtime).isoformat()


class TemplateLoader:
    FORMAT_MAP: ClassVar[dict[str, str]] = {
        ".j2": "jinja",
        ".jinja": "jinja",
        ".jinja2": "jinja",
        ".py": "python",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".md": "markdown",
    }

    def __init__(self, search_path: Path | None = None) -> None:
        self.search_path = search_path

    def load(self, source: str | Path) -> tuple[str, str]:
        path: Path | None = None

        if isinstance(source, Path):
            path = source
        elif isinstance(source, str):
            p = Path(source)
            if p.exists():
                path = p
            elif self.search_path is not None:
                resolved = self.search_path / source
                if resolved.exists():
                    path = resolved

        if path is not None:
            content = path.read_text(encoding="utf-8")
            fmt = self.FORMAT_MAP.get(path.suffix, "jinja")
            return content, fmt

        return str(source), "jinja"

    def load_template(self, source: str | Path) -> str:
        content, _ = self.load(source)
        return content

    def detect_format(self, source: str | Path) -> str:
        if isinstance(source, Path):
            return self.FORMAT_MAP.get(source.suffix, "jinja")
        p = Path(source)
        if p.exists():
            return self.FORMAT_MAP.get(p.suffix, "jinja")
        return "jinja"

    def get_template(self, template_id: str) -> TemplateInfo:
        path: Path | None = None
        p = Path(template_id)
        if p.exists():
            path = p
        elif self.search_path is not None:
            resolved = self.search_path / template_id
            if resolved.exists():
                path = resolved
        content, fmt = self.load(template_id)
        return TemplateInfo(content=content, path=path, engine=fmt, format=fmt)

    def list_templates(self, engine: str | None = None) -> list[str]:
        if self.search_path is None or not self.search_path.exists():
            return []
        return [
            str(f.relative_to(self.search_path))
            for f in self.search_path.iterdir()
            if f.is_file()
            and (engine is None or self.FORMAT_MAP.get(f.suffix, "jinja") == engine)
        ]
