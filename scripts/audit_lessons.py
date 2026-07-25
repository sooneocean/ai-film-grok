#!/usr/bin/env python3
"""Read-only audit for lessons and compatibility surfaces."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/ai-film-grok"
LESSONS = SKILL / "references"
REPORT_PATH = ROOT / "docs/reports/lessons-compatibility-audit.md"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _references_for(name: str) -> int:
    count = 0
    for root in (SKILL / "references", SKILL / "scripts", SKILL / "tests"):
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".md", ".py", ".json"}:
                try:
                    count += path.read_text(encoding="utf-8").count(name)
                except UnicodeDecodeError:
                    continue
    return count


def build_report() -> dict[str, Any]:
    files = sorted(LESSONS.glob("lessons-*.md"))
    by_hash: dict[str, list[str]] = defaultdict(list)
    entries: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    for path in files:
        text = path.read_text(encoding="utf-8")
        age_days = max(
            0, (now - datetime.fromtimestamp(path.stat().st_mtime, UTC)).days
        )
        refs = _references_for(path.name)
        classification = "active"
        if "deprecated:" in text.lower():
            classification = "deprecated"
        elif age_days > 30 and refs == 0:
            classification = "stale_candidate"
        digest = _sha256(path)
        by_hash[digest].append(path.name)
        entries.append(
            {
                "path": str(path.relative_to(ROOT)),
                "name": path.name,
                "age_days": age_days,
                "references": refs,
                "classification": classification,
                "sha256": digest,
            }
        )
    duplicates = [names for names in by_hash.values() if len(names) > 1]
    return {
        "generated_at": now.isoformat(),
        "lesson_count": len(entries),
        "stale_candidates": sum(
            item["classification"] == "stale_candidate" for item in entries
        ),
        "deprecated": sum(item["classification"] == "deprecated" for item in entries),
        "duplicates": duplicates,
        "entries": entries,
        "compatibility_surfaces": {
            "legacy_story_graph": "normalize_story_graph/export_legacy_story_plan",
            "legacy_provider_names": "film_spec fallback chains; explicit opt-in only",
            "legacy_receipts": "review-contract migration and receipt readers",
            "legacy_cli_imports": "aifilm_grok re-exports extracted command symbols",
            "legacy_config_keys": "config_loader compatibility aliases",
        },
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Lessons and Compatibility Audit",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Lessons: `{report['lesson_count']}`",
        f"- Stale candidates: `{report['stale_candidates']}`",
        f"- Deprecated: `{report['deprecated']}`",
        f"- Duplicate groups: `{len(report['duplicates'])}`",
        "",
        "## Classification",
        "",
        "| Lesson | Classification | References | Age (days) |",
        "|---|---|---:|---:|",
    ]
    lines.extend(
        f"| `{item['name']}` | `{item['classification']}` | {item['references']} | {item['age_days']} |"
        for item in report["entries"]
    )
    lines.extend(["", "## Compatibility surfaces", ""])
    lines.extend(
        f"- `{key}`: {value}" for key, value in report["compatibility_surfaces"].items()
    )
    if report["duplicates"]:
        lines.extend(["", "## Duplicate content groups", ""])
        lines.extend(
            f"- {', '.join(f'`{name}`' for name in group)}"
            for group in report["duplicates"]
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args(argv)
    report = build_report()
    output = (
        json.dumps(report, ensure_ascii=False, indent=2)
        if args.json
        else markdown(report)
    )
    if args.write_report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(markdown(report), encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
