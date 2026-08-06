#!/usr/bin/env python3
"""Closeout narrative rebind — graph→spec projection must still be current.

P1 quality plan (2026-08-06): prevent shipping after silent graph edit without
re-project. Writes receipts/narrative-rebind.json.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

RECEIPT = "narrative-rebind.json"


class NarrativeRebindError(RuntimeError):
    pass


def _flatten_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sc in spec.get("scenes") or []:
        if isinstance(sc, dict):
            for sh in sc.get("shots") or []:
                if isinstance(sh, dict):
                    out.append(sh)
    if not out:
        for sh in spec.get("shots") or []:
            if isinstance(sh, dict):
                out.append(sh)
    return out


def check_narrative_rebind(root: Path | str, *, write: bool = True) -> dict[str, Any]:
    """Return ok + issues; hard when projection stale or graph missing on locked films."""
    base = Path(root).expanduser().resolve()
    issues: list[dict[str, Any]] = []
    graph_path = base / "drama-graph.json"
    spec_path = base / "film-spec.json"
    graph = read_json(graph_path) if graph_path.is_file() else None
    spec = read_json(spec_path) if spec_path.is_file() else None

    if not isinstance(spec, dict) or not spec:
        issues.append(
            {
                "code": "NARRATIVE_SPEC_MISSING",
                "severity": "hard",
                "message": "film-spec.json missing — cannot rebind narrative",
            }
        )
    if not isinstance(graph, dict) or not graph:
        # Legacy films without graph: soft only
        issues.append(
            {
                "code": "NARRATIVE_GRAPH_MISSING",
                "severity": "soft",
                "message": "drama-graph.json missing — skip hard rebind (legacy)",
            }
        )
    else:
        narrative = graph.get("narrative") if isinstance(graph.get("narrative"), dict) else {}
        projection = (
            narrative.get("projection") if isinstance(narrative.get("projection"), dict) else {}
        )
        bound = bool(projection.get("source_revision") or projection.get("actual_sha256"))
        if bound and projection.get("stale") is True:
            issues.append(
                {
                    "code": "NARRATIVE_PROJECTION_STALE",
                    "severity": "hard",
                    "message": (
                        "drama-graph projection is stale — re-run graph project / write-spec "
                        "before closeout"
                    ),
                }
            )
        if bound and projection.get("ok") is False:
            issues.append(
                {
                    "code": "NARRATIVE_PROJECTION_NOT_OK",
                    "severity": "hard",
                    "message": "narrative.projection.ok is false — fix graph project",
                }
            )
        # Shot count drift vs graph nodes (soft)
        try:
            from drama_graph import graph_status  # type: ignore

            st = graph_status(base, auto_derive=False)
            if isinstance(st, dict) and st.get("projection_stale"):
                issues.append(
                    {
                        "code": "NARRATIVE_GRAPH_STATUS_STALE",
                        "severity": "hard",
                        "message": "graph_status reports projection_stale",
                    }
                )
        except Exception:
            pass

    # Adult max: re-assert sex arc at closeout (receipt for evidence)
    sex_arc: dict[str, Any] = {}
    coitus: dict[str, Any] = {}
    if isinstance(spec, dict):
        heat = str(spec.get("heat_scale") or "").strip().lower()
        shots = _flatten_shots(spec)
        if heat == "max" and shots:
            try:
                from edit_policy_heat import lint_coitus_grammar, lint_sex_arc

                sex_arc = lint_sex_arc(shots, heat_scale=heat)
                coitus = lint_coitus_grammar(
                    shots,
                    heat_scale=heat,
                    audience_profile=str(spec.get("audience_profile") or "") or None,
                    coitus_grammar=spec.get("coitus_grammar")
                    if isinstance(spec.get("coitus_grammar"), dict)
                    else None,
                )
                # Promote missing core arc to hard on closeout when sex_arc_strict
                strict = spec.get("sex_arc_strict")
                if strict is None:
                    strict = True  # max default
                hard_codes = {
                    "SEX_ARC_FOREPLAY_MISSING",
                    "SEX_ARC_PENETRATION_MISSING",
                    "SEX_ARC_CLIMAX_RELEASE_MISSING",
                }
                for iss in sex_arc.get("issues") or []:
                    code = str(iss.get("code") or "")
                    if code in hard_codes and strict:
                        issues.append(
                            {
                                "code": code,
                                "severity": "hard",
                                "message": str(iss.get("message") or code),
                            }
                        )
                if coitus.get("enabled") and not coitus.get("ok", True):
                    for iss in coitus.get("issues") or []:
                        if str(iss.get("code")) == "COITUS_BEAT_MISSING":
                            issues.append(
                                {
                                    "code": "COITUS_BEAT_MISSING",
                                    "severity": "hard"
                                    if (spec.get("coitus_strict") is not False)
                                    else "soft",
                                    "message": str(iss.get("message") or "coitus beats missing"),
                                }
                            )
            except Exception as exc:  # noqa: BLE001
                issues.append(
                    {
                        "code": "ADULT_ARC_LINT_ERROR",
                        "severity": "soft",
                        "message": f"sex/coitus lint failed: {exc}"[:200],
                    }
                )

    hard = [i for i in issues if i.get("severity") == "hard"]
    soft = [i for i in issues if i.get("severity") != "hard"]
    ok = not hard
    out: dict[str, Any] = {
        "schema_version": 1,
        "kind": "narrative-rebind",
        "at": utc_now(),
        "root": str(base),
        "ok": ok,
        "issues": issues,
        "hard_count": len(hard),
        "soft_count": len(soft),
        "sex_arc": sex_arc,
        "coitus": coitus,
        "next_cmd": (
            None
            if ok
            else f'aifilm graph project --root "{base}"  # or write-spec; fix SEX_ARC_* then closeout'
        ),
    }
    if write:
        rec = base / "receipts" / RECEIPT
        rec.parent.mkdir(parents=True, exist_ok=True)
        write_json(rec, out)
    return out


def assert_narrative_rebind(root: Path | str, *, hard: bool = True) -> dict[str, Any]:
    if os.environ.get("AIFILM_SKIP_NARRATIVE_REBIND", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return {"ok": True, "skipped": True, "escape": "AIFILM_SKIP_NARRATIVE_REBIND=1"}
    rep = check_narrative_rebind(root, write=True)
    if hard and not rep.get("ok"):
        codes = ",".join(
            str(i.get("code")) for i in rep.get("issues") or [] if i.get("severity") == "hard"
        )
        raise NarrativeRebindError(
            f"narrative rebind hard fail: {codes}. See receipts/{RECEIPT}"
        )
    return rep
