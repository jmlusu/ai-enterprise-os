"""Tests for ai_company.backup — create/restore round-trips and extraction safety.

The restore path is the Phase 0 disaster-recovery drill: a bundle created
by :func:`create_backup` must restore byte-for-byte into a fresh root, and
hostile archives must never escape the target directory.
"""

from __future__ import annotations

import io
import tarfile
import uuid
from pathlib import Path

import pytest

from ai_company.backup import create_backup, restore_backup
from ai_company.backup.backup import main


def _make_source(root: Path) -> Path:
    src = root / "runtime"
    (src / "events").mkdir(parents=True)
    (src / "events" / "a.json").write_text('{"n": 1}', encoding="utf-8")
    (src / "state.json").write_text('{"ok": true}', encoding="utf-8")
    (src / "memory").mkdir()
    return src


def test_create_and_restore_round_trip(temp_dir: Path) -> None:
    source = _make_source(temp_dir)
    archive = create_backup(
        dest_dir=str(temp_dir / "out"), source_dirs=["runtime"], root=temp_dir
    )
    assert archive.is_file()

    restored = restore_backup(archive, temp_dir / "restored")

    assert (restored / "runtime" / "state.json").read_text(
        encoding="utf-8"
    ) == '{"ok": true}'
    assert (restored / "runtime" / "events" / "a.json").read_text(
        encoding="utf-8"
    ) == '{"n": 1}'
    # Every source path is present in the restored tree.
    source_paths = {p.relative_to(source) for p in source.rglob("*") if p.is_file()}
    restored_paths = {
        p.relative_to(restored / "runtime")
        for p in (restored / "runtime").rglob("*")
        if p.is_file()
    }
    assert source_paths == restored_paths


def test_restore_byte_identical(temp_dir: Path) -> None:
    source = _make_source(temp_dir)
    archive = create_backup(
        dest_dir=str(temp_dir / "out"), source_dirs=["runtime"], root=temp_dir
    )
    restored = restore_backup(archive, temp_dir / "restored")

    for rel in [Path("state.json"), Path("events/a.json")]:
        original = (source / rel).read_bytes()
        restored_file = (restored / "runtime" / rel).read_bytes()
        assert restored_file == original


def test_restore_rejects_parent_traversal(temp_dir: Path) -> None:
    archive = temp_dir / "evil.tar.gz"
    victim = temp_dir.parent / f"evil-{uuid.uuid4().hex}.txt"
    with tarfile.open(archive, "w:gz") as handle:
        info = tarfile.TarInfo(f"../{victim.name}")
        payload = b"pwned"
        info.size = len(payload)
        handle.addfile(info, io.BytesIO(payload))

    with pytest.raises(ValueError, match="Unsafe archive member"):
        restore_backup(archive, temp_dir / "target")
    assert not victim.exists()


def test_restore_rejects_absolute_member(temp_dir: Path) -> None:
    archive = temp_dir / "evil-abs.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        info = tarfile.TarInfo("/abs/evil.txt")
        payload = b"pwned"
        info.size = len(payload)
        handle.addfile(info, io.BytesIO(payload))

    with pytest.raises(ValueError, match="Unsafe archive member"):
        restore_backup(archive, temp_dir / "target")


def test_restore_missing_archive_raises(temp_dir: Path) -> None:
    with pytest.raises(ValueError, match="Backup archive not found"):
        restore_backup(temp_dir / "nope.tar.gz", temp_dir / "target")


def test_main_restore_flag(temp_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _make_source(temp_dir)
    archive = create_backup(
        dest_dir=str(temp_dir / "out"), source_dirs=["runtime"], root=temp_dir
    )
    target = temp_dir / "restored"

    rc = main(["--restore", str(archive), "--dest", str(target)])

    assert rc == 0
    assert (target / "runtime" / "state.json").exists()
    captured = capsys.readouterr()
    assert "Restored" in captured.out


def test_main_create_no_sources_fails(
    monkeypatch: pytest.MonkeyPatch,
    temp_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    empty = temp_dir / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    rc = main(["--dest", str(temp_dir / "out")])
    assert rc == 1
    captured = capsys.readouterr()
    assert "No source directories found" in captured.err


def test_main_create_with_dirs(
    temp_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _make_source(temp_dir)
    rc = main(["--dest", str(temp_dir / "out"), "--dirs", "runtime"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Backup created" in captured.out
