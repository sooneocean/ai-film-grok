#!/usr/bin/env python3
"""Style + identity lock from user reference images (input-first).

Problem: photoreal multi-shot I2V drifts faces; manhua/anime stays stable because
the medium itself is a hard constraint. This module makes that constraint
explicit and machine-checkable:

  1) Infer / force medium (anime | manhua | semi_real | photoreal)
  2) Build style fingerprint + signature_block from medium + palette/lighting
  3) Build cast_locks tokens (face/hair/never) for prompt_injector
  4) Emit agent still/I2V prefixes that must lead every generation call
  5) Validate bible before lock-style / before bulk

No image model calls here — pure planning + JSON receipts. Agent still uses
image_edit(cast|face-lock) for pixels; this locks the *language* and gates.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from util import sha256_file as _sha256
from util import utc_now

# ---------------------------------------------------------------------------
# Medium presets — the biggest lever for identity stability
# ---------------------------------------------------------------------------

MEDIUM_PRESETS: dict[str, dict[str, Any]] = {
    "anime": {
        "label": "anime",
        "medium": "high-quality anime illustration",
        "rendering": (
            "clean anime linework, soft cel shading, stable character sheets, "
            "consistent eye shape and hair clumps across shots"
        ),
        "stability": "high",
        "signature_extra": (
            "same character design sheet language every shot; "
            "do not switch to photoreal or 3D; flat cel color blocks"
        ),
        "negative": (
            "photoreal skin pores, live-action photo, 3D CGI, western cartoon, "
            "oil painting, inconsistent eye size, random hair recolor"
        ),
        "still_hint": ("anime still, cel shaded, clean lineart, character design consistency"),
        "i2v_hint": (
            "animate as anime frame, keep cel shading and lineart, face and hair silhouette locked"
        ),
    },
    "manhua": {
        "label": "manhua",
        "medium": "vertical manhua / 漫剧 illustration",
        "rendering": (
            "Chinese manhua vertical-drama look, clean ink line, soft gradient "
            "skin, stable face chart, cinematic 9:16 panel language"
        ),
        "stability": "high",
        "signature_extra": (
            "漫剧统一画风；同一角色设定表；禁止跳回写实摄影；线稿与上色公式全片一致"
        ),
        "negative": (
            "photoreal DSLR photo, live-action, 3D render, western comic ink, "
            "inconsistent face proportions, random makeup restyle"
        ),
        "still_hint": ("manhua vertical drama still, clean line, soft color, face-chart stable"),
        "i2v_hint": ("animate as manhua panel motion, keep line and face chart, no photoreal"),
    },
    "semi_real": {
        "label": "semi_real",
        "medium": "semi-realistic cinematic illustration",
        "rendering": (
            "semi-real illustrated faces, soft painterly skin, simplified pores, "
            "stable bone structure, film lighting"
        ),
        "stability": "medium",
        "signature_extra": (
            "semi-real not pure photo; illustrated face lock; "
            "prefer consistency over photographic detail"
        ),
        "negative": (
            "hyper-detailed skin pores, raw phone selfie, 3D Unreal Engine look, "
            "anime chibi, oil-painting style drift"
        ),
        "still_hint": ("semi-realistic illustrated portrait, film light, face structure locked"),
        "i2v_hint": ("semi-real motion, keep illustrated face structure, no photoreal morph"),
    },
    "photoreal": {
        "label": "photoreal",
        "medium": "photoreal cinematic short",
        "rendering": (
            "photoreal, detailed skin/fabric, natural pores, contemporary digital cinema"
        ),
        "stability": "low",
        "signature_extra": (
            "STRICT same person identity; reference-first only; "
            "never pure text-to-image for faces; accept higher pilot reject rate"
        ),
        "negative": (
            "anime, manhua, cartoon, 3D CGI character, face morph mid-shot, "
            "identity swap, different person"
        ),
        "still_hint": ("photoreal cinematic still, same person as cast master, natural skin"),
        "i2v_hint": ("photoreal motion, keep exact face identity from frame-1, no face morph"),
        "agent_warning": (
            "photoreal = lowest face stability under multi-shot I2V; "
            "require face-lock crops + cast master + pilot 3-shot pass; "
            "prefer manhua/anime if user wants 漫剧质感"
        ),
    },
}

_ANIME_KEYS = (
    "anime",
    "二次元",
    "动画",
    "赛璐",
    "cel",
    "番剧",
)
_MANHUA_KEYS = (
    "漫剧",
    "漫画",
    "manhua",
    "manhwa",
    "竖屏漫",
    "条漫",
    "插画",
    "绘本",
)
_SEMI_KEYS = (
    "半写实",
    "semi",
    "illustrated",
    "插画写实",
)
_PHOTO_KEYS = (
    "写实",
    "真人",
    "photoreal",
    "photo",
    "live action",
    "电影感",
    "实拍",
)


def _blob(*parts: str) -> str:
    return " ".join(p for p in parts if p).lower()


def infer_medium(
    *,
    theme: str = "",
    title: str = "",
    user_hint: str = "",
    explicit: str | None = None,
) -> str:
    """Return medium key. explicit wins; else keyword score; default photoreal."""
    if explicit:
        key = str(explicit).strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "manga": "manhua",
            "comic": "manhua",
            "realistic": "photoreal",
            "real": "photoreal",
            "photo": "photoreal",
            "2d": "anime",
            "cel": "anime",
        }
        key = aliases.get(key, key)
        if key in MEDIUM_PRESETS:
            return key
        raise ValueError(f"unknown medium {explicit!r}; choose {sorted(MEDIUM_PRESETS)}")

    blob = _blob(theme, title, user_hint)
    scores = {
        "manhua": sum(1 for k in _MANHUA_KEYS if k in blob),
        "anime": sum(1 for k in _ANIME_KEYS if k in blob),
        "semi_real": sum(1 for k in _SEMI_KEYS if k in blob),
        "photoreal": sum(1 for k in _PHOTO_KEYS if k in blob),
    }
    # Character sheet + urban romance without 漫剧 → still often photoreal by default
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return "photoreal"
    return best


def build_style_fingerprint(
    medium: str,
    *,
    palette: str = "",
    lighting: str = "",
    lens: str = "",
    extra: str = "",
) -> dict[str, Any]:
    preset = MEDIUM_PRESETS[medium]
    return {
        "medium_key": medium,
        "medium": preset["medium"],
        "rendering": preset["rendering"],
        "stability": preset["stability"],
        "palette": palette or "to be filled from ref / theme",
        "lighting": lighting or "motivated practicals, coherent grade across shots",
        "lens": lens or "contemporary digital / illustration panel, modest DOF",
        "signature_extra": preset["signature_extra"],
        "negative": preset["negative"],
        "still_hint": preset["still_hint"],
        "i2v_hint": preset["i2v_hint"],
        "agent_warning": preset.get("agent_warning") or "",
        "extra": extra,
        "schema_version": 1,
    }


def build_signature_block(
    title: str,
    fingerprint: dict[str, Any],
    *,
    locale_note: str = "",
) -> str:
    parts = [
        f"Style lock for '{title}': {fingerprint['medium']}.",
        fingerprint["rendering"],
        fingerprint["signature_extra"],
    ]
    if fingerprint.get("palette") and "to be filled" not in str(fingerprint["palette"]):
        parts.append(f"Palette: {fingerprint['palette']}.")
    if fingerprint.get("lighting"):
        parts.append(f"Lighting: {fingerprint['lighting']}.")
    if locale_note:
        parts.append(locale_note)
    parts.append("NEVER switch medium mid-film. Same face chart / cast master every shot.")
    text = " ".join(p.strip() for p in parts if p and str(p).strip())
    if len(text) < 40:
        text += " Consistent character design, locked identity, stable wardrobe colors."
    return text


def build_cast_lock(
    char_id: str,
    *,
    display_name: str = "",
    face_notes: str = "",
    hair_lock: str = "",
    never_tokens: str = "",
    makeup_lock: str = "",
    default_wardrobe: str = "",
) -> dict[str, Any]:
    """Structured cast lock consumed by prompt_injector (cast_locks.<id>)."""
    name = display_name or char_id
    face = face_notes.strip() or (
        f"adult {name}: face STRICT match to cast master + face-lock crops; "
        "same bone structure eyes brows nose lips jaw"
    )
    hair = hair_lock.strip() or "hair match cast master; NEVER random recolor"
    never = never_tokens.strip() or (
        "NEVER different person, NEVER face morph, NEVER pure text-to-image face, "
        "NEVER change eye spacing or jaw"
    )
    tokens = f"{face}; Hair: {hair}; image_edit ONLY from cast master / face-lock / approved still"
    return {
        "char_id": char_id,
        "display_name": name,
        "identity_lock_tokens": tokens,
        "hair_lock": hair,
        "makeup_lock": makeup_lock,
        "never_tokens": never,
        "default_wardrobe": default_wardrobe,
        "face_notes": face,
    }


def build_agent_still_prompt_prefix(
    fingerprint: dict[str, Any],
    cast_locks: dict[str, dict[str, Any]],
    *,
    cast_ids: list[str] | None = None,
) -> str:
    """Leading block every still generation prompt should start with."""
    ids = cast_ids or list(cast_locks.keys())
    lines = [
        f"MEDIUM LOCK: {fingerprint['medium']} — NEVER switch medium.",
        f"Style: {fingerprint['still_hint']}. {fingerprint.get('signature_extra', '')}",
    ]
    for cid in ids:
        cl = cast_locks.get(cid) or {}
        if cl.get("identity_lock_tokens"):
            lines.append(f"IDENTITY {cid}: {cl['identity_lock_tokens']}")
        if cl.get("hair_lock"):
            lines.append(f"Hair lock {cid}: {cl['hair_lock']}")
        if cl.get("never_tokens"):
            lines.append(f"Never {cid}: {cl['never_tokens']}")
    lines.append(
        "Refs: image_edit(cast master and/or face-lock crops and/or approved still) ONLY for faces. "
        "No text, no watermark, no labels."
    )
    if fingerprint.get("negative"):
        lines.append(f"--no {fingerprint['negative']}")
    return "\n".join(lines)


def build_agent_i2v_prompt_prefix(
    fingerprint: dict[str, Any],
    *,
    motion: str = "",
) -> str:
    lines = [
        f"MEDIUM LOCK: {fingerprint['medium']} — keep frame-1 identity.",
        fingerprint["i2v_hint"],
        "Full head and both shoulders framed unless shot is pure env.",
    ]
    if motion:
        lines.append(f"Motion: {motion}")
    return " ".join(lines)


def validate_style_lock_bible(bible: dict[str, Any]) -> dict[str, Any]:
    """Return {ok, hard[], soft[], medium_key, stability}."""
    hard: list[str] = []
    soft: list[str] = []
    fp = bible.get("style_fingerprint") if isinstance(bible.get("style_fingerprint"), dict) else {}
    medium_key = str(fp.get("medium_key") or "").strip()
    if not medium_key:
        # fallback from medium string
        med = str(bible.get("medium") or "").lower()
        if "manhua" in med or "漫" in med:
            medium_key = "manhua"
        elif "anime" in med:
            medium_key = "anime"
        elif "semi" in med:
            medium_key = "semi_real"
        elif "photo" in med or "real" in med:
            medium_key = "photoreal"
        else:
            hard.append("STYLE_FINGERPRINT_MISSING: run aifilm style-lock plan|apply")
    sig = str(bible.get("signature_block") or "").strip()
    if len(sig) < 40:
        hard.append("SIGNATURE_TOO_SHORT")
    if "to be filled" in str(bible.get("palette") or "").lower():
        hard.append("PALETTE_PLACEHOLDER")
    if "to be filled" in str(bible.get("identity_lock") or "").lower():
        hard.append("IDENTITY_PLACEHOLDER")
    cast_masters = bible.get("cast_masters") if isinstance(bible.get("cast_masters"), dict) else {}
    if not cast_masters:
        hard.append("CAST_MASTER_MISSING")
    cast_locks = bible.get("cast_locks") if isinstance(bible.get("cast_locks"), dict) else {}
    if cast_masters and not cast_locks:
        soft.append("CAST_LOCKS_EMPTY: structured face/hair tokens missing — photoreal will drift")
    for cid, path in cast_masters.items():
        if cid in {"hero"} and len(cast_masters) > 1:
            continue
        if not cast_locks.get(cid):
            soft.append(f"CAST_LOCK_MISSING:{cid}")
    if medium_key == "photoreal":
        soft.append(
            "PHOTOREAL_LOW_STABILITY: multi-shot I2V face drift risk; "
            "prefer manhua/anime for 漫剧质感 or tighten pilot rejects"
        )
    if not bible.get("canonical_style_path"):
        soft.append("STYLE_MASTER_PATH_MISSING")
    stability = (MEDIUM_PRESETS.get(medium_key) or {}).get("stability", "unknown")
    return {
        "ok": not hard,
        "hard": hard,
        "soft": soft,
        "medium_key": medium_key or None,
        "stability": stability,
        "cast_master_count": len(cast_masters),
        "cast_lock_count": len(cast_locks),
    }


def crop_face_regions_from_sheet(
    sheet_path: Path,
    out_dir: Path,
    *,
    char_id: str = "hero",
) -> dict[str, str]:
    """Heuristic crops for standard character sheets (left FRONT head + mid close-up).

    Returns map of crop_name -> path. Requires Pillow. Best-effort; agent should
    verify crops visually.
    """
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("Pillow required for face crop") from exc

    sheet_path = Path(sheet_path).expanduser().resolve()
    if not sheet_path.is_file():
        raise FileNotFoundError(sheet_path)
    out_dir = Path(out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    img = Image.open(sheet_path).convert("RGB")
    w, h = img.size
    # Layout-agnostic relative boxes (character sheets often left=FRONT, bottom=close-up)
    boxes = {
        "front_head": (int(w * 0.05), int(h * 0.04), int(w * 0.22), int(h * 0.30)),
        "emotion_face": (int(w * 0.28), int(h * 0.68), int(w * 0.48), int(h * 0.96)),
        "expr_grid": (int(w * 0.58), int(h * 0.10), int(w * 0.72), int(h * 0.28)),
    }
    paths: dict[str, str] = {}
    for name, box in boxes.items():
        crop = img.crop(box)
        # upscale small faces for better edit refs
        if crop.width < 400:
            crop = crop.resize((crop.width * 3, crop.height * 3), Image.Resampling.LANCZOS)
        dest = out_dir / f"{char_id}-face-lock-{name}.png"
        crop.save(dest)
        paths[name] = str(dest)
    return paths


def plan_from_ref(
    *,
    root: Path,
    ref_path: Path,
    char_id: str = "hero",
    display_name: str = "",
    medium: str | None = None,
    theme: str = "",
    title: str = "",
    user_hint: str = "",
    face_notes: str = "",
    hair_lock: str = "",
    never_tokens: str = "",
    default_wardrobe: str = "",
    palette: str = "",
    lighting: str = "",
    crop_faces: bool = True,
) -> dict[str, Any]:
    """Build a style-lock plan JSON (does not write bible until apply)."""
    root = Path(root).expanduser().resolve()
    ref_path = Path(ref_path).expanduser().resolve()
    if not ref_path.is_file():
        raise FileNotFoundError(f"ref missing: {ref_path}")

    medium_key = infer_medium(theme=theme, title=title, user_hint=user_hint, explicit=medium)
    fp = build_style_fingerprint(medium_key, palette=palette, lighting=lighting)
    title_s = title or root.name
    signature = build_signature_block(title_s, fp)
    cast = build_cast_lock(
        char_id,
        display_name=display_name or char_id,
        face_notes=face_notes,
        hair_lock=hair_lock,
        never_tokens=never_tokens,
        default_wardrobe=default_wardrobe,
    )
    crops: dict[str, str] = {}
    if crop_faces:
        try:
            crops = crop_face_regions_from_sheet(
                ref_path, root / "canonical" / "cast", char_id=char_id
            )
        except Exception as exc:  # noqa: BLE001 — best-effort crop
            crops = {"error": str(exc)}

    # Stage assets under source/
    source_dir = root / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    staged = source_dir / f"style-ref-{char_id}{ref_path.suffix.lower() or '.png'}"
    if ref_path.resolve() != staged.resolve():
        shutil.copy2(ref_path, staged)

    still_prefix = build_agent_still_prompt_prefix(fp, {char_id: cast}, cast_ids=[char_id])
    i2v_prefix = build_agent_i2v_prompt_prefix(fp)

    plan = {
        "schema_version": 1,
        "kind": "style-lock-plan",
        "at": utc_now(),
        "root": str(root),
        "ref_path": str(ref_path),
        "ref_staged": str(staged),
        "ref_sha256": _sha256(ref_path),
        "medium_key": medium_key,
        "stability": fp["stability"],
        "style_fingerprint": fp,
        "signature_block": signature,
        "identity_lock": cast["identity_lock_tokens"],
        "cast_locks": {char_id: cast},
        "cast_id": char_id,
        "face_crops": crops,
        "agent_still_prompt_prefix": still_prefix,
        "agent_i2v_prompt_prefix": i2v_prefix,
        "agent_do": _agent_checklist(medium_key, char_id, crops),
        "warnings": [],
    }
    if medium_key == "photoreal":
        plan["warnings"].append(MEDIUM_PRESETS["photoreal"]["agent_warning"])
    return plan


def apply_plan_to_bible(bible: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    """Merge plan into style-bible dict (mutates and returns)."""
    fp = plan.get("style_fingerprint") or {}
    bible["style_fingerprint"] = fp
    bible["medium"] = fp.get("medium") or bible.get("medium")
    bible["rendering"] = fp.get("rendering") or bible.get("rendering")
    if fp.get("palette") and "to be filled" not in str(fp.get("palette")):
        bible["palette"] = fp["palette"]
    elif not bible.get("palette") or "to be filled" in str(bible.get("palette") or "").lower():
        # force a concrete medium-derived palette stub so lock-style can pass
        bible["palette"] = (
            f"locked-{plan.get('medium_key', 'style')}: "
            "keep grade coherent across shots; match style master"
        )
    if fp.get("lighting"):
        bible["lighting"] = fp["lighting"]
    if fp.get("lens"):
        bible["lens"] = fp["lens"]
    bible["signature_block"] = plan.get("signature_block") or bible.get("signature_block")
    bible["identity_lock"] = plan.get("identity_lock") or bible.get("identity_lock")
    neg = str(bible.get("negative_hints") or "")
    extra_neg = str(fp.get("negative") or "")
    if extra_neg and extra_neg not in neg:
        bible["negative_hints"] = (neg + "; " + extra_neg).strip("; ")
    locks = bible.get("cast_locks") if isinstance(bible.get("cast_locks"), dict) else {}
    for cid, cl in (plan.get("cast_locks") or {}).items():
        locks[cid] = cl
        # mirror into characters
        chars = bible.get("characters") if isinstance(bible.get("characters"), dict) else {}
        entry = chars.get(cid) if isinstance(chars.get(cid), dict) else {}
        entry = dict(entry)
        entry["identity"] = cl.get("identity_lock_tokens") or entry.get("identity")
        if cl.get("default_wardrobe"):
            entry["default_wardrobe"] = cl["default_wardrobe"]
        entry["cast_master"] = entry.get("cast_master") or (f"canonical/cast/{cid}-master.png")
        chars[cid] = entry
        bible["characters"] = chars
        # wardrobe variants default
        wv = (
            bible.get("wardrobe_variants")
            if isinstance(bible.get("wardrobe_variants"), dict)
            else {}
        )
        if cid not in wv and cl.get("default_wardrobe"):
            wv[cid] = {
                "full": cl["default_wardrobe"],
                "default": cl["default_wardrobe"],
            }
            bible["wardrobe_variants"] = wv
    bible["cast_locks"] = locks
    bible["style_lock_plan_at"] = plan.get("at")
    bible["style_lock_ref_sha256"] = plan.get("ref_sha256")
    # prompt prefixes for agent
    bible["agent_still_prompt_prefix"] = plan.get("agent_still_prompt_prefix")
    bible["agent_i2v_prompt_prefix"] = plan.get("agent_i2v_prompt_prefix")
    return bible


def write_plan(root: Path, plan: dict[str, Any]) -> Path:
    root = Path(root).expanduser().resolve()
    out = root / "receipts" / "style-lock-plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def read_plan(root: Path) -> dict[str, Any] | None:
    path = Path(root).expanduser().resolve() / "receipts" / "style-lock-plan.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _agent_checklist(medium_key: str, char_id: str, crops: dict[str, str]) -> list[str]:
    steps = [
        f"medium={medium_key} stability={MEDIUM_PRESETS[medium_key]['stability']}",
        f"Verify face crops under canonical/cast/{char_id}-face-lock-*.png (re-crop if labels/wrong region)",
        f"image_edit(face-lock + sheet) → canonical/cast/{char_id}-master.png 9:16",
        "Optional style-v1: env still in same medium OR first approved lookbook frame",
        "aifilm style-lock apply --root … then lock-style --canonical … --cast-master …",
        "Every still: start prompt with agent_still_prompt_prefix; faces only via image_edit(cast)",
        "I2V only from verified keyframes; serial; re-reject face morph",
    ]
    if medium_key == "photoreal":
        steps.insert(
            1,
            "WARNING photoreal: consider switching medium to manhua/anime for 漫剧-like stability",
        )
    if crops.get("error"):
        steps.insert(1, f"Face auto-crop failed: {crops['error']} — crop manually")
    return steps


def recommend_medium_for_user_goal(goal: str) -> dict[str, Any]:
    """Human-facing recommendation when user complains about stability."""
    g = (goal or "").lower()
    if any(k in g for k in ("稳", "漫剧", "稳定", "一致", "质感好")):
        return {
            "recommended": "manhua",
            "why": "符号化画风约束强，多镜 I2V 脸漂更少；更接近漫剧成片质感",
            "fallback": "anime",
            "avoid": "photoreal for multi-shot bulk without heavy pilot rejects",
        }
    if any(k in g for k in ("写实", "真人", "电影")):
        return {
            "recommended": "photoreal",
            "why": "用户要真人电影感；须 face-lock + cast master + 严 pilot",
            "fallback": "semi_real",
            "avoid": "pure image_gen faces; long I2V without re-keyframe",
        }
    return {
        "recommended": "semi_real",
        "why": "折中：保留电影光影，脸比纯写实稳",
        "fallback": "manhua",
        "avoid": None,
    }
