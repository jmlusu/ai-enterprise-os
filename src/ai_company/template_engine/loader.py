from pathlib import Path
from typing import ClassVar


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
