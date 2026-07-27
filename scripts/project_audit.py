#!/usr/bin/env python3
"""Read-only repository audit and generated baseline report.

The audit deliberately separates repository readiness from machine advisories.
It never invokes paid media providers and does not mutate project state unless
``--write-baseline`` is explicitly requested.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/ai-film-grok"
BASELINE = ROOT / "docs/reports/2026-07-24-baseline.md"


def command(*args: str, cwd: Path = ROOT) -> tuple[int, str]:
    """Run a local read-only command and return its exit code and output."""
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError as exc:
        return 127, str(exc)
    return proc.returncode, proc.stdout.strip()


def executable(name: str, *fallbacks: str) -> str:
    """Resolve a local executable without assuming an interactive shell PATH."""
    found = shutil.which(name)
    if found:
        return found
    for candidate in fallbacks:
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return name


def plugin_version() -> str:
    return str(
        json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))["version"]
    )


def git_value(*args: str) -> str:
    code, output = command("git", *args)
    return output if code == 0 else f"unavailable: {output}"


def current_head() -> str:
    return git_value("rev-parse", "HEAD")


def working_tree_is_clean() -> bool:
    return not git_value("status", "--porcelain")


def release_baseline_is_writable(working_tree: str) -> bool:
    return not working_tree


def source_fingerprint() -> str:
    """Hash repository files without including this generated report itself."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
    except OSError:
        return "unavailable"
    if proc.returncode != 0:
        return "unavailable"
    digest = hashlib.sha256()
    baseline_rel = BASELINE.relative_to(ROOT).as_posix()
    for raw_path in sorted(item for item in proc.stdout.split(b"\0") if item):
        relative = raw_path.decode("utf-8")
        if relative == baseline_rel:
            continue
        path = ROOT / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()


def parse_json_output(output: str) -> dict[str, Any] | None:
    try:
        value = json.loads(output)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def test_inventory() -> dict[str, int]:
    shipped_skills = [
        path for path in (ROOT / "skills").iterdir() if (path / "SKILL.md").is_file()
    ]
    tests = [
        path
        for test_root in [
            *(skill / "tests" for skill in shipped_skills),
            ROOT / "tests",
        ]
        if test_root.is_dir()
        for path in test_root.rglob("test_*.py")
    ]
    scripts = [
        path for skill in shipped_skills for path in (skill / "scripts").rglob("*.py")
    ]
    return {
        "test_files": len(tests),
        "script_files": len(scripts),
        "script_lines": sum(
            path.read_text(encoding="utf-8").count("\n") for path in scripts
        ),
    }


def doctor_snapshot() -> dict[str, Any]:
    code, output = command(str(SKILL / "scripts/aifilm"), "doctor")
    data = parse_json_output(output) or {}
    core = data.get("core_readiness") or {}
    return {
        "exit_code": code,
        "core_ok": bool(core.get("ok")),
        "strict_ok": bool(data.get("strict_ok")),
        "strict_status": data.get("strict_status", "unknown"),
        "strict_blocking": bool(data.get("strict_blocking")),
        "failed_checks": core.get("failed_checks", []),
        "environment_advisories": (data.get("environment_advisories") or {}).get(
            "warnings", []
        ),
        "provider_default": data.get("provider_default"),
    }


def coverage_snapshot() -> dict[str, Any]:
    path = SKILL / "coverage.json"
    if not path.is_file():
        return {"status": "not available; run make coverage"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        totals = data.get("totals") or {}
        files = data.get("files") or {}
        critical = {}
        for name in (
            "dispatch.py",
            "preflight.py",
            "production_gates.py",
            "render_final.py",
            "compose_render.py",
            "media_qa.py",
            "quality_evidence.py",
            "continuity.py",
        ):
            row = next(
                (
                    value
                    for key, value in files.items()
                    if key.endswith(f"scripts/{name}")
                ),
                None,
            )
            if row:
                critical[name] = row.get("summary", {}).get("percent_covered")
        return {
            "status": "available",
            "percent_covered": totals.get("percent_covered"),
            "covered_lines": totals.get("covered_lines"),
            "num_statements": totals.get("num_statements"),
            "critical_modules": critical,
        }
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "error": str(exc)}


def baseline_is_current(path: Path = BASELINE) -> bool:
    """Return whether a generated baseline matches the current source/version."""
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    head = re.search(r"^- HEAD: `([^`]+)`$", text, re.MULTILINE)
    version = re.search(r"^- Plugin version: `([^`]+)`$", text, re.MULTILINE)
    fingerprint = re.search(r"^- Source fingerprint: `([^`]+)`$", text, re.MULTILINE)
    working_tree = re.search(r"^- Working tree: `([^`]+)`$", text, re.MULTILINE)
    return bool(
        head
        and version
        and fingerprint
        and working_tree
        and version.group(1) == plugin_version()
        and fingerprint.group(1) == source_fingerprint()
        and working_tree.group(1) == "clean"
        and working_tree_is_clean()
    )


def build_snapshot(
    *, run_tests: bool = False, full_tests: bool = False
) -> dict[str, Any]:
    inventory = test_inventory()
    snapshot: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "head": current_head(),
        "source_fingerprint": source_fingerprint(),
        "branch": git_value("branch", "--show-current"),
        "remote": git_value(
            "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"
        ),
        "version": plugin_version(),
        "working_tree": git_value("status", "--porcelain"),
        "inventory": inventory,
        "checks": {},
        "doctor": doctor_snapshot(),
        "coverage": coverage_snapshot(),
        "gates": {
            "pilot": "requires film root and explicit user approval",
            "provider_canary": "not claimed by repository audit; inspect doctor/provider-canary",
            "delivery": "requires film-root delivery package and full screening evidence",
        },
    }
    checks: dict[str, Any] = snapshot["checks"]
    for name, args in {
        "plugin_validate": (
            executable("grok", "~/.grok/bin/grok"),
            "plugin",
            "validate",
            str(ROOT),
        ),
        "ruff_check": (
            executable("ruff", "~/.pyenv/shims/ruff"),
            "check",
            str(SKILL / "scripts"),
        ),
        "ruff_format": (
            executable("ruff", "~/.pyenv/shims/ruff"),
            "format",
            "--check",
            str(SKILL / "scripts"),
        ),
        "docs_current": (
            sys.executable,
            str(ROOT / "scripts/sync_project_docs.py"),
            "--check",
        ),
        "cli_help": (str(SKILL / "scripts/aifilm"), "--help"),
    }.items():
        code, output = command(*args)
        checks[name] = {"ok": code == 0, "exit_code": code, "output": output[-1200:]}
    checks["baseline_current"] = {
        "ok": baseline_is_current(),
        "status": "current" if baseline_is_current() else "stale or missing",
    }

    if run_tests:
        test_args = [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=line"]
        if not full_tests:
            test_args.extend(["-m", "not slow"])
        code, output = command(*test_args, cwd=SKILL)
        checks["tests_full" if full_tests else "tests_fast"] = {
            "ok": code == 0,
            "exit_code": code,
            "output": output[-2000:],
        }
    else:
        checks["tests_fast"] = {"ok": None, "status": "not run; use --run-tests"}

    # Some read-only probes update ignored local state. Capture identity only after
    # those probes so a freshly generated baseline can be current immediately.
    snapshot.update(
        head=current_head(),
        source_fingerprint=source_fingerprint(),
        version=plugin_version(),
        working_tree=git_value("status", "--porcelain"),
    )
    return snapshot


def markdown(snapshot: dict[str, Any]) -> str:
    checks = snapshot["checks"]
    doctor = snapshot["doctor"]
    inventory = snapshot["inventory"]

    def status(value: object) -> str:
        return "PASS" if value is True else "FAIL" if value is False else "NOT RUN"

    doctor_strict_status = (
        "ADVISORY"
        if not doctor["strict_ok"] and not doctor.get("strict_blocking")
        else status(doctor["strict_ok"])
    )

    lines = [
        "# ai-film-grok Baseline Report — generated",
        "",
        "> This file is generated by `scripts/project_audit.py`; do not edit the status values by hand.",
        "",
        "## Repository",
        "",
        f"- Generated at: `{snapshot['generated_at']}`",
        f"- HEAD: `{snapshot['head']}`",
        f"- Source fingerprint: `{snapshot['source_fingerprint']}`",
        f"- Branch: `{snapshot['branch']}`",
        f"- Upstream: `{snapshot['remote']}`",
        f"- Plugin version: `{snapshot['version']}`",
        f"- Working tree: `{'clean' if not snapshot['working_tree'] else 'dirty'}`",
        "",
        "## Verification",
        "",
        "| Check | Result |",
        "|---|---|",
    ]
    for name in (
        "plugin_validate",
        "ruff_check",
        "ruff_format",
        "docs_current",
        "cli_help",
        "baseline_current",
    ):
        lines.append(f"| `{name}` | {status(checks[name].get('ok'))} |")
    lines.extend(
        [
            f"| `doctor.core_readiness` | {status(doctor['core_ok'])} |",
            f"| `doctor.strict_ok` | {doctor_strict_status} (`{doctor.get('strict_status', 'unknown')}`) |",
            *[
                f"| `{name}` | {status(check.get('ok'))} |"
                for name, check in checks.items()
                if name in {"tests_fast", "tests_full"}
            ],
            "",
            "## Inventory",
            "",
            f"- Python scripts: `{inventory['script_files']}`",
            f"- Script lines: `{inventory['script_lines']}`",
            f"- Test files: `{inventory['test_files']}`",
            f"- Coverage: `{snapshot['coverage'].get('percent_covered', snapshot['coverage'].get('status'))}`",
            *[
                f"- Coverage `{name}`: `{percent}`"
                for name, percent in (
                    snapshot["coverage"].get("critical_modules") or {}
                ).items()
            ],
            "",
            "## Remaining production gates",
            "",
            f"- Pilot: {snapshot['gates']['pilot']}",
            f"- Provider canary: {snapshot['gates']['provider_canary']}",
            f"- Delivery: {snapshot['gates']['delivery']}",
            "",
            "## Environment advisories",
            "",
        ]
    )
    warnings = doctor.get("environment_advisories") or []
    lines.extend(f"- {warning}" for warning in warnings) if warnings else lines.append(
        "- None"
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    parser.add_argument(
        "--run-tests", action="store_true", help="run the fast pytest suite"
    )
    parser.add_argument(
        "--full-tests", action="store_true", help="run the full pytest suite"
    )
    parser.add_argument(
        "--write-baseline", action="store_true", help="write the generated baseline"
    )
    args = parser.parse_args(argv)
    snapshot = build_snapshot(
        run_tests=args.run_tests or args.full_tests, full_tests=args.full_tests
    )
    if args.write_baseline:
        if release_baseline_is_writable(str(snapshot["working_tree"])):
            snapshot["checks"]["baseline_current"] = {"ok": True, "status": "written"}
            BASELINE.parent.mkdir(parents=True, exist_ok=True)
            BASELINE.write_text(markdown(snapshot), encoding="utf-8")
        else:
            snapshot["checks"]["baseline_current"] = {
                "ok": False,
                "status": "not written: working tree is dirty",
            }
    if args.json:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    else:
        print(markdown(snapshot), end="")
    hard_check_names = [
        "plugin_validate",
        "ruff_check",
        "ruff_format",
        "docs_current",
        "cli_help",
        "baseline_current",
    ]
    if args.full_tests:
        hard_check_names.append("tests_full")
    elif args.run_tests:
        hard_check_names.append("tests_fast")
    hard_checks = (snapshot["checks"][name]["ok"] for name in hard_check_names)
    return 0 if all(hard_checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
