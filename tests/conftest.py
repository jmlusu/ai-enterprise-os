import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir() -> Iterator[Path]:
    d = Path(tempfile.mkdtemp())
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def temp_yaml_file(temp_dir: Path) -> Path:
    f = temp_dir / "test.yaml"
    f.write_text("name: test\nvalue: 42\n", encoding="utf-8")
    return f
