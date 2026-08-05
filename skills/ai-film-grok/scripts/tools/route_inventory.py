#!/usr/bin/env python3
"""Inventory CLI / next_action / skill / policy routing surfaces (R0).

Read-only. Emits JSON coverage matrix + orphan lists for route-catalog work.

  python scripts/tools/route_inventory.py
  python scripts/tools/route_inventory.py --out /tmp/route-inventory.json
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parents[1]
SKILL_ROOT = SCRIPTS.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _dict_string_keys_from_assign(source: str, name: str) -> set[str]:
    """Parse top-level `name = { "k": ... }` string keys via AST."""
    tree = ast.parse(source)
    keys: set[str] = set()
    for node in tree.body:
        target_names: list[str] = []
        value = None
        if isinstance(node, ast.Assign):
            value = node.value
            for t in node.targets:
                if isinstance(t, ast.Name):
                    target_names.append(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_names = [node.target.id]
            value = node.value
        if name not in target_names or value is None:
            continue
        if not isinstance(value, ast.Dict):
            continue
        for k in value.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                keys.add(k.value)
    return keys


def hub_cli_cmds() -> dict[str, Any]:
    hub = SCRIPTS / "aifilm_grok.py"
    text = _read(hub)
    # Prefer live parser if import works; fall back to regex.
    cmds: set[str] = set()
    try:
        import aifilm_grok as hub_mod

        parser = hub_mod.build_parser()
        # argparse stores subparsers under _subparsers
        for action in parser._actions:  # noqa: SLF001
            if getattr(action, "choices", None) and isinstance(action.choices, dict):
                cmds.update(str(k) for k in action.choices)
                break
    except Exception as exc:  # noqa: BLE001 — inventory must stay offline-friendly
        cmds = set(re.findall(r'add_parser\(\s*["\']([a-z0-9][a-z0-9-]*)["\']', text))
        cmds |= set(re.findall(r'["\']([a-z0-9][a-z0-9-]*)["\']\s*:\s*cmd_', text))
        cmds |= set(re.findall(r'["\']([a-z0-9][a-z0-9-]*)["\']\s*:\s*cmd_workflow', text))
        fallback_note = str(exc)
    else:
        fallback_note = None

    simple = set(
        re.findall(
            r'^\s*["\']([a-z0-9][a-z0-9-]*)["\']\s*:\s*(?:cmd_|[A-Za-z_])',
            text,
            re.M,
        )
    )
    # _SIMPLE_DISPATCH block keys
    m = re.search(r"_SIMPLE_DISPATCH\s*=\s*\{(.*?)\n\s*\}", text, re.S)
    simple_dispatch: set[str] = set()
    if m:
        simple_dispatch = set(re.findall(r'["\']([a-z0-9][a-z0-9-]*)["\']\s*:', m.group(1)))

    if_ladder = set(re.findall(r'if args\.cmd == ["\']([a-z0-9][a-z0-9-]*)["\']', text))

    return {
        "path": str(hub.relative_to(SKILL_ROOT)),
        "cli_cmds": sorted(cmds),
        "cli_count": len(cmds),
        "simple_dispatch": sorted(simple_dispatch),
        "simple_dispatch_count": len(simple_dispatch),
        "if_ladder": sorted(if_ladder),
        "if_ladder_count": len(if_ladder),
        "parser_import_error": fallback_note,
        "regex_cmd_hints": sorted(simple)[:0],  # reserved
    }


def dispatch_tables() -> dict[str, Any]:
    path = SCRIPTS / "spine" / "dispatch.py"
    text = _read(path)
    return {
        "path": str(path.relative_to(SKILL_ROOT)),
        "action_skills": sorted(_dict_string_keys_from_assign(text, "_ACTION_SKILLS")),
        "skill_policies": sorted(_dict_string_keys_from_assign(text, "_SKILL_POLICIES")),
        "command_policies": sorted(_dict_string_keys_from_assign(text, "_COMMAND_POLICIES")),
        "stage_owners": sorted(_dict_string_keys_from_assign(text, "_STAGE_OWNERS")),
    }


def next_action_ids() -> dict[str, Any]:
    path = SCRIPTS / "spine" / "next_actions.py"
    text = _read(path)
    stage_map = _dict_string_keys_from_assign(text, "_ACTION_STAGE")
    adds = set(re.findall(r'add\(\s*["\']([a-z0-9_./-]+)["\']', text))
    return {
        "path": str(path.relative_to(SKILL_ROOT)),
        "action_stage_keys": sorted(stage_map),
        "add_ids": sorted(adds),
        "union": sorted(stage_map | adds),
    }


def advance_actions() -> dict[str, Any]:
    path = SCRIPTS / "spine" / "advance.py"
    text = _read(path)
    # ADVANCE_POLICIES or similar
    keys = _dict_string_keys_from_assign(text, "ADVANCE_POLICIES")
    if not keys:
        # try common name
        for name in ("_ADVANCE_POLICIES", "POLICIES", "LOCAL_ADVANCE"):
            keys = _dict_string_keys_from_assign(text, name)
            if keys:
                break
    # Fallback: string keys before AdvancePolicy(
    if not keys:
        keys = set(re.findall(r'["\']([a-z0-9_./-]+)["\']\s*:\s*AdvancePolicy\s*\(', text))
    return {
        "path": str(path.relative_to(SKILL_ROOT)),
        "advance_eligible": sorted(keys),
        "count": len(keys),
    }


def skill_surfaces() -> dict[str, Any]:
    reg_path = SKILL_ROOT / "registry" / "skills.json"
    reg = json.loads(_read(reg_path)) if reg_path.is_file() else {"skills": []}
    skill_ids = [
        str(s.get("id"))
        for s in (reg.get("skills") or [])
        if isinstance(s, dict) and s.get("id")
    ]
    runner_path = SCRIPTS / "skill_runner.py"
    runner_text = _read(runner_path)
    runners = _dict_string_keys_from_assign(runner_text, "RUNNERS")
    return {
        "registry_path": str(reg_path.relative_to(SKILL_ROOT)),
        "registry_skill_ids": sorted(skill_ids),
        "registry_count": len(skill_ids),
        "runner_path": str(runner_path.relative_to(SKILL_ROOT)),
        "runner_skill_ids": sorted(runners),
        "runner_count": len(runners),
        "in_registry_not_runner": sorted(set(skill_ids) - runners),
        "in_runner_not_registry": sorted(runners - set(skill_ids)),
    }


def build_report() -> dict[str, Any]:
    hub = hub_cli_cmds()
    disp = dispatch_tables()
    nxt = next_action_ids()
    adv = advance_actions()
    skills = skill_surfaces()

    cli = set(hub["cli_cmds"])
    actions = set(nxt["union"])
    action_skills = set(disp["action_skills"])
    cmd_pol = set(disp["command_policies"])
    advance = set(adv["advance_eligible"])

    # Orphans / gaps (informational)
    actions_not_in_action_skills = sorted(actions - action_skills)
    advance_not_in_actions = sorted(advance - actions)
    cmd_policy_not_in_cli = sorted(cmd_pol - cli)
    if_ladder_not_in_simple = sorted(set(hub["if_ladder"]) - set(hub["simple_dispatch"]))

    return {
        "schema_version": 1,
        "kind": "ai-film-route-inventory",
        "skill_root": str(SKILL_ROOT),
        "hub": hub,
        "dispatch": disp,
        "next_actions": nxt,
        "advance": adv,
        "skills": skills,
        "gaps": {
            "next_action_missing_action_skill_map": actions_not_in_action_skills,
            "advance_not_in_next_actions_union": advance_not_in_actions,
            "command_policy_not_in_cli": cmd_policy_not_in_cli,
            "if_ladder_outside_simple_dispatch": if_ladder_not_in_simple,
            "summary": {
                "cli_count": hub["cli_count"],
                "if_ladder_count": hub["if_ladder_count"],
                "next_action_count": len(actions),
                "action_skill_map_count": len(action_skills),
                "advance_count": adv["count"],
                "registry_skills": skills["registry_count"],
                "runner_skills": skills["runner_count"],
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Route surface inventory (R0)")
    parser.add_argument("--out", type=Path, default=None, help="Write JSON report path")
    parser.add_argument("--pretty", action="store_true", default=True)
    args = parser.parse_args()
    report = build_report()
    text = json.dumps(report, indent=2 if args.pretty else None, ensure_ascii=False) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    g = report["gaps"]["summary"]
    print(
        f"summary: cli={g['cli_count']} if_ladder={g['if_ladder_count']} "
        f"next_actions={g['next_action_count']} advance={g['advance_count']} "
        f"skills={g['registry_skills']}/{g['runner_skills']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
