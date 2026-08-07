"""Tests for util.paths (P3-2: externalize hardcoded macOS paths).

Portable: asserts behavior on any platform without assuming homebrew exists.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import util.paths as P


def test_system_bindirs_always_present():
    path = P.build_subprocess_path()
    for d in ("/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"):
        assert d in path


def test_homebrew_only_injected_when_present():
    path = P.build_subprocess_path()
    hb_present = Path("/opt/homebrew/bin").is_dir()
    linuxbrew_present = Path("/home/linuxbrew/.linuxbrew/bin").is_dir()
    if hb_present or linuxbrew_present:
        assert ("/opt/homebrew/bin" in path) or (
            "/home/linuxbrew/.linuxbrew/bin" in path
        )
    else:
        assert "/opt/homebrew/bin" not in path
        assert "/home/linuxbrew/.linuxbrew/bin" not in path


def test_plugin_root_is_this_checkout():
    root = P.plugin_root()
    assert root.name == "ai-film-grok"
    assert (root / "plugin.json").is_file()


def test_first_existing_file_picks_real_then_none():
    d = tempfile.mkdtemp()
    real = Path(d) / "exists.txt"
    real.write_text("ok")
    # returns the resolved (symlink-normalized) existing path
    assert P.first_existing_file(Path("/nope/missing"), real) == real.resolve()
    assert P.first_existing_file(Path("/nope/a"), Path("/nope/b")) is None


def test_resolve_tool_finds_shutil_which(monkeypatch, tmp_path: Path):
    import shutil
    import util.paths as P

    fake = tmp_path / "ffprobe"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setattr(shutil, "which", lambda name: str(fake) if name == "ffprobe" else None)
    got = P.resolve_tool("ffprobe")
    assert got is not None
    assert got.resolve() == fake.resolve()


def test_resolve_tool_rejects_path_injection():
    import util.paths as P

    assert P.resolve_tool("../ffprobe") is None
    assert P.resolve_tool("") is None
    assert P.resolve_tool("ffprobe/../x") is None
