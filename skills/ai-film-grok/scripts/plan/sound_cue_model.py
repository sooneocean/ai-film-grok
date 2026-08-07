"""SoundCue production objects — sound-first awareness (Film Production OS W7).

Types: dialogue | adr | foley | ambience | sfx | music | silence | transition
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

SOUND_CUE_TYPES = frozenset(
    {
        "dialogue",
        "adr",
        "foley",
        "ambience",
        "sfx",
        "music",
        "silence",
        "transition",
    }
)

CODE_SOUND_TYPE = "SOUND_CUE_TYPE_INVALID"
CODE_SOUND_MISSING = "SOUND_CUE_MISSING_FIELDS"


def _text(value: object) -> str:
    return str(value or "").strip()


def normalize_sound_cue(raw: object, *, default_id: str = "SOUND_001") -> dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    ctype = _text(src.get("type") or src.get("kind") or "ambience").lower()
    if ctype not in SOUND_CUE_TYPES:
        ctype = "sfx"
    cont = src.get("continuity") if isinstance(src.get("continuity"), dict) else {}
    continues = cont.get("continues_into_next_shot")
    if continues is None:
        continues = src.get("continues_into_next_shot")
    return {
        "schema_version": 1,
        "kind": "sound-cue",
        "id": _text(src.get("id")) or default_id,
        "type": ctype,
        "source": _text(src.get("source") or src.get("name") or src.get("label")) or None,
        "scene_id": _text(src.get("scene_id")) or None,
        "shot_id": _text(src.get("shot_id")) or None,
        "start": float(src.get("start") or 0.0)
        if isinstance(src.get("start"), (int, float, str)) and str(src.get("start")).strip() != ""
        else 0.0,
        "continuity": {
            "continues_into_next_shot": bool(continues)
            if continues is not None
            else (ctype == "ambience"),
        },
        "notes": _text(src.get("notes")) or None,
    }


def lint_sound_cue(cue: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    n = normalize_sound_cue(cue)
    if n["type"] not in SOUND_CUE_TYPES:
        issues.append(
            {
                "code": CODE_SOUND_TYPE,
                "severity": "error",
                "message": f"{n['id']}: invalid type {n['type']!r}",
            }
        )
    if not n.get("source") and n["type"] not in {"silence"}:
        issues.append(
            {
                "code": CODE_SOUND_MISSING,
                "severity": "warning",
                "message": f"{n['id']}: source label empty",
            }
        )
    errors = [i for i in issues if i.get("severity") == "error"]
    return {"ok": not errors, "cue": n, "issues": issues, "codes": sorted({i["code"] for i in issues})}


def collect_sound_cues_from_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Gather sound_cues / sound from scenes and shots into SoundCue objects."""
    out: list[dict[str, Any]] = []
    n = 0
    for si, scene in enumerate(spec.get("scenes") or []):
        if not isinstance(scene, dict):
            continue
        sc_id = _text(scene.get("id") or f"sc{si + 1:02d}")
        for raw in scene.get("sound_cues") or []:
            n += 1
            c = normalize_sound_cue(raw, default_id=f"SOUND_{n:03d}")
            c["scene_id"] = c.get("scene_id") or sc_id
            out.append(c)
        shots: list[dict[str, Any]] = []
        for sh in scene.get("shots") or []:
            if isinstance(sh, dict):
                shots.append(sh)
        for beat in scene.get("beats") or []:
            if not isinstance(beat, dict):
                continue
            for sh in beat.get("shots") or []:
                if isinstance(sh, dict):
                    shots.append(sh)
        for sh in shots:
            sid = _text(sh.get("id"))
            # structured sound_cues list
            for raw in sh.get("sound_cues") or []:
                n += 1
                c = normalize_sound_cue(raw, default_id=f"SOUND_{n:03d}")
                c["scene_id"] = c.get("scene_id") or sc_id
                c["shot_id"] = c.get("shot_id") or sid
                out.append(c)
            # freeform sound object → ambience + sfx lists
            sound = sh.get("sound") if isinstance(sh.get("sound"), dict) else {}
            for amb in sound.get("ambience") or []:
                n += 1
                out.append(
                    normalize_sound_cue(
                        {
                            "id": f"SOUND_{n:03d}",
                            "type": "ambience",
                            "source": amb,
                            "scene_id": sc_id,
                            "shot_id": sid,
                            "continues_into_next_shot": True,
                        }
                    )
                )
            for fx in sound.get("effects") or sound.get("sfx") or []:
                n += 1
                out.append(
                    normalize_sound_cue(
                        {
                            "id": f"SOUND_{n:03d}",
                            "type": "sfx",
                            "source": fx,
                            "scene_id": sc_id,
                            "shot_id": sid,
                        }
                    )
                )
            if sh.get("spoken_text") or sh.get("dialogue"):
                n += 1
                out.append(
                    normalize_sound_cue(
                        {
                            "id": f"SOUND_{n:03d}",
                            "type": "dialogue",
                            "source": "on_camera_or_ledger",
                            "scene_id": sc_id,
                            "shot_id": sid,
                            "continues_into_next_shot": False,
                        }
                    )
                )
    return out


def sound_cues_at_root(
    root: Path | str,
    *,
    write_receipt: bool = True,
) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    spec = read_json(root_p / "film-spec.json") or {}
    if not isinstance(spec, dict):
        return {"ok": False, "error": "film-spec missing"}
    cues = collect_sound_cues_from_spec(spec)
    issues: list[dict[str, Any]] = []
    for c in cues:
        r = lint_sound_cue(c)
        issues.extend(r.get("issues") or [])
    bridges = [
        c["id"]
        for c in cues
        if (c.get("continuity") or {}).get("continues_into_next_shot") is True
    ]
    report = {
        "ok": not any(i.get("severity") == "error" for i in issues),
        "kind": "sound-cues",
        "count": len(cues),
        "cues": cues,
        "bridge_cue_ids": bridges,
        "issues": issues,
        "codes": sorted({str(i["code"]) for i in issues}),
        "root": str(root_p),
        "at": utc_now(),
    }
    if write_receipt:
        path = root_p / "receipts" / "sound-cues.json"
        write_json(path, report)
        report["receipt"] = str(path)
    return report
