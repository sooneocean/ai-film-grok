"""C5.6 — no production hardcodes of user home or brew tool paths."""

from __future__ import annotations

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

FORBIDDEN_USER = ("/Users/dex",)
FORBIDDEN_TOOL_LITERALS = (
    "/opt/homebrew/bin/ffmpeg",
    "/opt/homebrew/bin/ffprobe",
    "/home/linuxbrew/.linuxbrew/bin/ffmpeg",
    "/home/linuxbrew/.linuxbrew/bin/ffprobe",
)


def test_no_users_dex_in_production_scripts() -> None:
    offenders: list[str] = []
    for path in sorted(SCRIPTS.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(SCRIPTS).as_posix()
        text = path.read_text(encoding="utf-8")
        for needle in FORBIDDEN_USER:
            if needle not in text:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if needle not in line:
                    continue
                # util.paths module docstring may mention historical hardcodes in backticks
                if rel == "util/paths.py" and ("previously" in line or "``" in line):
                    continue
                offenders.append(f"{rel}:{i}:{line.strip()[:80]}")
    assert not offenders, "/Users/dex still present:\n" + "\n".join(offenders)


def test_no_hardcoded_brew_tool_binaries_outside_util_paths() -> None:
    offenders: list[str] = []
    for path in sorted(SCRIPTS.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(SCRIPTS).as_posix()
        if rel == "util/paths.py":
            continue
        text = path.read_text(encoding="utf-8")
        for needle in FORBIDDEN_TOOL_LITERALS:
            if needle in text:
                for i, line in enumerate(text.splitlines(), 1):
                    if needle in line:
                        offenders.append(f"{rel}:{i}")
    assert not offenders, "hardcoded brew tool paths:\n" + "\n".join(offenders)


def test_resolve_tool_exported() -> None:
    from util.paths import resolve_tool

    got = resolve_tool("ffprobe")
    assert got is None or got.is_file()
