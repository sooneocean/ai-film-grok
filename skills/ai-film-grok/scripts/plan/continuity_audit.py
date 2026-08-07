"""Continuity In → Action → Out → next In audit (Film Production OS W4/W5).

Rule engine + report — not a chat agent. Chains wardrobe/prop/physical keys
across ordered shots when continuity_in/out are authored.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

CODE_CONT_BREAK = "CONTINUITY_BREAK"
CODE_CONT_UNSTATED = "CONTINUITY_UNSTATED"
CODE_CONT_WARDROBE_REWIND = "CONTINUITY_WARDROBE_REWIND"


def _text(value: object) -> str:
    return str(value or "").strip()


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _flatten_shots(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    out: list[tuple[str, str, dict[str, Any]]] = []
    for si, scene in enumerate(spec.get("scenes") or []):
        if not isinstance(scene, dict):
            continue
        sc_id = _text(scene.get("id") or f"sc{si + 1:02d}")
        # scene-level continuity seeds first shot if present
        scene_in = _as_dict(scene.get("continuity_in"))
        scene_out = _as_dict(scene.get("continuity_out"))
        shots: list[dict[str, Any]] = []
        beats = scene.get("beats") if isinstance(scene.get("beats"), list) else None
        if beats:
            for bi, beat in enumerate(beats):
                if not isinstance(beat, dict):
                    continue
                bt = _text(beat.get("id") or f"bt{bi + 1}")
                for sh in beat.get("shots") or []:
                    if isinstance(sh, dict):
                        shots.append({**sh, "_beat_id": bt})
        else:
            for sh in scene.get("shots") or []:
                if isinstance(sh, dict):
                    shots.append(sh)
        for i, sh in enumerate(shots):
            # seed first/last from scene when shot lacks
            if i == 0 and scene_in and not _as_dict(sh.get("continuity_in")):
                sh = {**sh, "continuity_in": scene_in}
            if i == len(shots) - 1 and scene_out and not _as_dict(sh.get("continuity_out")):
                sh = {**sh, "continuity_out": scene_out}
            out.append((sc_id, _text(sh.get("_beat_id") or sh.get("beat_id")), sh))
    return out


def _state_blob(shot: dict[str, Any], key: str) -> dict[str, Any]:
    raw = shot.get(key)
    if isinstance(raw, dict):
        return dict(raw)
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    raw2 = dsl.get(key)
    return dict(raw2) if isinstance(raw2, dict) else {}


def audit_continuity_chain(spec: dict[str, Any], *, strict: bool = False) -> dict[str, Any]:
    triples = _flatten_shots(spec)
    issues: list[dict[str, Any]] = []
    unstated = 0
    for i, (sc_id, _bt, shot) in enumerate(triples):
        sid = _text(shot.get("id") or f"shot{i + 1}")
        cin = _state_blob(shot, "continuity_in")
        cout = _state_blob(shot, "continuity_out")
        if not cin and not cout:
            unstated += 1
            issues.append(
                {
                    "code": CODE_CONT_UNSTATED,
                    "severity": "warning",
                    "message": f"{sid}: no continuity_in/out authored",
                    "shot_ids": [sid],
                    "scene_id": sc_id,
                }
            )
            continue
        if i + 1 < len(triples):
            n_sc, _, nxt = triples[i + 1]
            if n_sc != sc_id:
                continue  # cross-scene: only soft
            nid = _text(nxt.get("id") or f"shot{i + 2}")
            nin = _state_blob(nxt, "continuity_in")
            if cout and nin:
                for key, out_val in cout.items():
                    if key not in nin:
                        continue
                    if _text(nin.get(key)) != _text(out_val):
                        # wardrobe rank rewind heuristic
                        msg = (
                            f"{sid}→{nid}: continuity break on {key!r}: "
                            f"out={out_val!r} in={nin.get(key)!r}"
                        )
                        code = CODE_CONT_BREAK
                        if key in {"wardrobe", "wardrobe_rank", "clothing", "jacket"}:
                            # if next looks more dressed than out, flag rewind
                            code = CODE_CONT_WARDROBE_REWIND
                        issues.append(
                            {
                                "code": code,
                                "severity": "error" if strict else "warning",
                                "message": msg,
                                "shot_ids": [sid, nid],
                                "scene_id": sc_id,
                                "key": key,
                            }
                        )
            elif cout and not nin:
                issues.append(
                    {
                        "code": CODE_CONT_UNSTATED,
                        "severity": "warning",
                        "message": f"{nid}: missing continuity_in after {sid} authored out",
                        "shot_ids": [nid],
                        "scene_id": sc_id,
                    }
                )

    errors = [i for i in issues if i.get("severity") == "error"]
    return {
        "ok": not errors,
        "kind": "continuity-audit",
        "strict": strict,
        "shot_count": len(triples),
        "unstated_count": unstated,
        "issues": issues,
        "codes": sorted({str(i["code"]) for i in issues}),
        "blocking": sorted({str(i["code"]) for i in errors}),
        "picture_lock_allowed": not errors,
    }


def continuity_audit_at_root(
    root: Path | str,
    *,
    strict: bool = False,
    write_receipt: bool = True,
) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    spec = read_json(root_p / "film-spec.json") or {}
    if not isinstance(spec, dict):
        return {"ok": False, "error": "film-spec missing"}
    report = audit_continuity_chain(spec, strict=strict)
    report["root"] = str(root_p)
    report["at"] = utc_now()
    if write_receipt:
        path = root_p / "receipts" / "continuity-audit.json"
        write_json(path, report)
        report["receipt"] = str(path)
    return report
