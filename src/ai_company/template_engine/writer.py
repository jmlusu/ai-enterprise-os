import sys
from pathlib import Path


class Writer:
    def write(self, content: str, destination: Path | None = None) -> str | Path:
        if destination is None:
            sys.stdout.write(content)
            sys.stdout.write("\n")
            return content
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        return destination
