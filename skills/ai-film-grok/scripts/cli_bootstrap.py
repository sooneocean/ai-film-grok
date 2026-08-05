"""Bootstrap / runtime lock CLI cluster — extracted from aifilm_grok (public cmd strings unchanged).

Commands: lock-runtime | resume-manifest
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from util import require_json as read_json
from util import sha256_file, write_json
from util.errors import FilmError
from runtime_policy import build_runtime_lock, verify_runtime_lock


def _emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))

def add_bootstrap_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    sub.add_parser(
        "lock-runtime", help="Fingerprint the current verified Python/FFmpeg/script runtime"
    )

    resume_manifest = sub.add_parser(
        "resume-manifest", help="Create only a missing manifest for a legacy film root"
    )
    resume_manifest.add_argument("--root", required=True)


def cmd_lock_runtime(_: argparse.Namespace) -> int:
    skill_dir = Path(__file__).resolve().parents[1]
    lock_path = skill_dir / "runtime-lock.json"
    write_json(lock_path, build_runtime_lock(skill_dir))
    result = verify_runtime_lock(skill_dir, lock_path)
    _emit({"ok": result["ok"], "runtime_lock": str(lock_path), "verification": result})
    return 0 if result["ok"] else 2



def cmd_resume_manifest(args: argparse.Namespace) -> int:
    """Create only the missing state manifest for a legacy film root."""
    import aifilm_grok as core

    raw_root = Path(args.root).expanduser()
    if raw_root.is_symlink():
        raise FilmError(f"Legacy root must not be a symlink: {raw_root}")
    root = raw_root.resolve()
    if not root.is_dir():
        raise FilmError(f"Legacy root must be a real directory: {root}")
    manifest_path = root / core.MANIFEST_NAME
    if manifest_path.exists() or manifest_path.is_symlink():
        raise FilmError(f"Manifest already exists at {manifest_path}; refusing to overwrite it")
    brief_path = root / "brief.json"
    if not brief_path.is_file():
        raise FilmError(f"Legacy root needs brief.json before manifest resume: {root}")
    brief = core.read_json(brief_path)
    title = str(brief.get("title") or "").strip()
    theme = str(brief.get("theme") or "").strip()
    aspect = str(brief.get("aspect_ratio") or "9:16").strip()
    if not title or not theme:
        raise FilmError("Legacy brief.json needs non-empty title and theme before manifest resume")
    manifest = core.empty_manifest(title=title, theme=theme, aspect=aspect)
    contract_path = root / "director-contract.json"
    graph_path = root / "drama-graph.json"
    truth = manifest["truth_contract"]
    truth["contract_sha256"] = core.sha256_file(contract_path) if contract_path.is_file() else ""
    truth["graph_sha256"] = core.sha256_file(graph_path) if graph_path.is_file() else ""
    truth["spec_sha256"] = (
        core.sha256_file(root / "film-spec.json") if (root / "film-spec.json").is_file() else ""
    )
    truth["timeline_sha256"] = (
        core.sha256_file(root / "timeline.json") if (root / "timeline.json").is_file() else ""
    )
    manifest["notes"].append(
        "Legacy resume created this manifest only; existing style, contract, still, and clip evidence remains unapproved until revalidated."
    )
    core.ensure_tree(root)
    core.save_manifest(root, manifest)
    core.emit(
        {
            "ok": True,
            "created": True,
            "root": str(root),
            "manifest": str(manifest_path),
            "preserved_existing_evidence": True,
            "next_step": "Revalidate and lock style plus native evidence before media generation.",
        }
    )
    return 0


