#!/usr/bin/env python3
"""Lightweight secret scan for CI (no gitea-publish dependency).

Scans tracked text files for high-signal credential patterns.
Exit 0 if clean; 1 if findings. Designed for honesty: local pre-push may skip
when gitea-publish is absent — CI must still run this.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# High-signal only — avoid noisy false positives on docs/examples.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_pat", re.compile(r"\bghp_[A-Za-z0-9]{36,}\b")),
    ("github_oauth", re.compile(r"\bgho_[A-Za-z0-9]{36,}\b")),
    ("github_user", re.compile(r"\bghu_[A-Za-z0-9]{36,}\b")),
    ("github_server", re.compile(r"\bghs_[A-Za-z0-9]{36,}\b")),
    ("github_refresh", re.compile(r"\bghr_[A-Za-z0-9]{36,}\b")),
    ("xai_sk_style", re.compile(r"\bxai-[A-Za-z0-9_]{20,}\b")),
    ("openai_sk", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("generic_api_key_assign", re.compile(r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{24,}['\"]")),
]

SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".mp4",
    ".mov",
    ".wav",
    ".mp3",
    ".onnx",
    ".pyc",
    ".so",
    ".dylib",
    ".zip",
    ".gz",
    ".whl",
}
SKIP_DIR_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    ".venv",
    "venv",
    "artifacts",
    "bgm-library",
    "video-library",
    "tts-evaluations",
    "piper-voices",
}


def _tracked_files() -> list[Path]:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(ROOT), "ls-files", "-z"],
            text=False,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"[secret_scan] git ls-files failed: {exc}", file=sys.stderr)
        sys.exit(2)
    paths: list[Path] = []
    for raw in out.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="replace")
        path = ROOT / rel
        if any(part in SKIP_DIR_PARTS for part in Path(rel).parts):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if not path.is_file():
            continue
        paths.append(path)
    return paths


def main() -> int:
    findings: list[str] = []
    for path in _tracked_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Skip this file's own pattern source and config examples with placeholders.
        rel = path.relative_to(ROOT).as_posix()
        if rel.endswith("secret_scan.py"):
            continue
        if rel.endswith("config.env.example"):
            continue
        for name, pattern in PATTERNS:
            for match in pattern.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                findings.append(f"{rel}:{line_no}: {name}")
    if findings:
        print("[secret_scan] FAIL — possible secrets:", file=sys.stderr)
        for row in findings[:50]:
            print(f"  {row}", file=sys.stderr)
        if len(findings) > 50:
            print(f"  … and {len(findings) - 50} more", file=sys.stderr)
        return 1
    print("[secret_scan] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
