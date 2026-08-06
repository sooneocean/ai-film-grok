#!/usr/bin/env python3
"""Programmatic continuity join checks (MVP · v2.40).

Four machine-readable rules (not full NLP nine-item checklist):
1. longform requires continuity_chain.md with join markers
2. continue pairs must not declare dissolve/freeze/reverse joins
3. optional first/last frame byte match when paths exist
4. no non-continue insert wedged between declared continue pair (heuristic)
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json
from util.errors import FilmError

_FORBIDDEN_JOIN = re.compile(r"\b(dissolve|freeze|reverse|xfade)\b", re.I)
_JOIN_LINE = re.compile(r"(?:join|continue|match.?cut)", re.I)


class ContinuityProgrammaticError(FilmError):
    pass


def _sha256_file(path: Path) -> str | None:
    if not path.is_file() or path.is_symlink():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _flatten_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sc in spec.get("scenes") or []:
        if not isinstance(sc, dict):
            continue
        for sh in sc.get("shots") or []:
            if isinstance(sh, dict) and sh.get("id"):
                out.append(sh)
    if not out:
        for sh in spec.get("shots") or []:
            if isinstance(sh, dict) and sh.get("id"):
                out.append(sh)
    return out


def _chain_mode(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    return str(
        shot.get("chain_mode") or dsl.get("chain_mode") or shot.get("join") or ""
    ).strip().lower()


def check_continuity_programmatic(
    root: Path | str,
    *,
    write: bool = True,
    require_longform_doc: bool = True,
) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    issues: list[dict[str, Any]] = []
    spec = read_json(root_p / "film-spec.json") or {}
    production_mode = str(spec.get("production_mode") or "shortform").lower()
    longform = production_mode == "longform" or bool(spec.get("long_form")) or bool(
        spec.get("require_continuity_chain")
    )
    chain_path = root_p / "continuity_chain.md"
    chain_text = ""
    if chain_path.is_file():
        try:
            chain_text = chain_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            issues.append({"code": "CHAIN_READ_FAIL", "message": str(exc)})
    elif longform and require_longform_doc:
        issues.append(
            {
                "code": "CHAIN_DOC_MISSING",
                "message": "longform requires continuity_chain.md",
            }
        )

    if chain_text and longform:
        if not _JOIN_LINE.search(chain_text) and "join" not in chain_text.lower():
            issues.append(
                {
                    "code": "CHAIN_JOIN_SPARSE",
                    "message": "continuity_chain.md has no join/continue markers",
                }
            )
        if _FORBIDDEN_JOIN.search(chain_text) and "continue" in chain_text.lower():
            # Soft signal: forbidden words near continue docs often mean dissolve cover-up
            if re.search(r"continue.{0,80}(dissolve|freeze|reverse)", chain_text, re.I | re.S):
                issues.append(
                    {
                        "code": "CHAIN_FORBIDDEN_JOIN_WORDING",
                        "message": "continue join must not use dissolve/freeze/reverse cover-up",
                    }
                )

    shots = _flatten_shots(spec)
    continue_ids: list[str] = []
    for i, sh in enumerate(shots):
        mode = _chain_mode(sh)
        sid = str(sh.get("id"))
        if mode in {"continue", "match_cut", "match-cut", "hard_continue"}:
            continue_ids.append(sid)
            # Forbidden transition on the shot itself
            trans = str(
                sh.get("transition")
                or sh.get("transition_style")
                or (sh.get("dsl") or {}).get("transition")
                or ""
            ).lower()
            if _FORBIDDEN_JOIN.search(trans):
                issues.append(
                    {
                        "code": "CONTINUE_FORBIDDEN_TRANSITION",
                        "message": f"{sid} chain_mode=continue but transition={trans!r}",
                        "shot_id": sid,
                    }
                )
            # Byte match: prev last frame vs this first keyframe when present
            if i > 0:
                prev = shots[i - 1]
                prev_id = str(prev.get("id"))
                last_candidates = [
                    root_p / "keyframes" / f"{prev_id}_last.jpg",
                    root_p / "keyframes" / f"{prev_id}_last.png",
                    root_p / "receipts" / "frames" / f"{prev_id}_last.jpg",
                ]
                first_candidates = [
                    root_p / "keyframes" / f"{sid}.jpg",
                    root_p / "keyframes" / f"{sid}.png",
                    root_p / "keyframes" / f"{sid}_first.jpg",
                ]
                last_p = next((p for p in last_candidates if p.is_file()), None)
                first_p = next((p for p in first_candidates if p.is_file()), None)
                if last_p and first_p:
                    ha, hb = _sha256_file(last_p), _sha256_file(first_p)
                    if ha and hb and ha != hb:
                        issues.append(
                            {
                                "code": "CONTINUE_FRAME_HASH_MISMATCH",
                                "message": (
                                    f"{prev_id}→{sid} continue seam: last/first frame hash differ"
                                ),
                                "shot_id": sid,
                                "prev_id": prev_id,
                            }
                        )

    # Heuristic: insert between two continues with same beat is suspicious only if
    # middle is chain_mode empty and dramatic_function insert — soft code
    for i in range(1, len(shots) - 1):
        prev_m, mid_m, next_m = (
            _chain_mode(shots[i - 1]),
            _chain_mode(shots[i]),
            _chain_mode(shots[i + 1]),
        )
        mid = shots[i]
        df = str(mid.get("dramatic_function") or "").lower()
        if (
            prev_m in {"continue", "match_cut", "match-cut"}
            and next_m in {"continue", "match_cut", "match-cut"}
            and not mid_m
            and ("insert" in df or str(mid.get("shot_size") or "").lower() == "insert")
        ):
            issues.append(
                {
                    "code": "CONTINUE_INSERT_WEDGE",
                    "message": (
                        f"{mid.get('id')} insert wedged between continue shots "
                        f"{shots[i - 1].get('id')}→{shots[i + 1].get('id')}"
                    ),
                    "shot_id": str(mid.get("id")),
                }
            )

    ok = not issues
    out: dict[str, Any] = {
        "schema_version": 1,
        "kind": "continuity-programmatic",
        "at": utc_now(),
        "root": str(root_p),
        "ok": ok,
        "longform": longform,
        "continue_shot_count": len(continue_ids),
        "issues": issues,
        "next_cmd": (
            None
            if ok
            else f'aifilm continuity-chain check --root "{root_p}"  # fix join / frame chain'
        ),
    }
    if write:
        rec = root_p / "receipts" / "continuity-programmatic.json"
        rec.parent.mkdir(parents=True, exist_ok=True)
        write_json(rec, out)
    return out


def assert_continuity_programmatic(root: Path | str, *, hard: bool = True) -> dict[str, Any]:
    if os.environ.get("AIFILM_SKIP_CONTINUITY_PROG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return {"ok": True, "skipped": True, "escape": "AIFILM_SKIP_CONTINUITY_PROG=1"}
    report = check_continuity_programmatic(root, write=True)
    if hard and not report.get("ok"):
        codes = ",".join(i.get("code", "?") for i in report.get("issues") or [])
        raise ContinuityProgrammaticError(
            f"continuity programmatic hard fail: {codes}. "
            f"See receipts/continuity-programmatic.json"
        )
    return report
