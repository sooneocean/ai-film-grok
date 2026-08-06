"""Multi-heroine pack."""
from __future__ import annotations
from typing import Any
from edit_policy_shared import PolicyError
__all__ = ["_MULTI_HEROINE_PROMPT_MARKERS","_MALE_CAST_IDS","resolve_heroine_cast_mode","lint_multi_heroine"]
_MULTI_HEROINE_PROMPT_MARKERS: tuple[str, ...] = (
    "双女主",
    "雙女主",
    "多女主",
    "两个女",
    "兩個女",
    "两位女",
    "兩位女",
    "两女",
    "兩女",
    "三个女",
    "三女",
    "百合双",
    "双飞",
    "雙飛",
    "3p女",
    "3P女",
    "两位女主",
    "兩位女主",
    "dual heroine",
    "dual heroines",
    "two heroines",
    "two girls",
    "multi heroine",
    "multi-heroine",
    "multiple heroines",
    "threesome girls",
)
_MALE_CAST_IDS = frozenset(
    {
        "partner",
        "male",
        "hero_m",
        "him",
        "man",
        "boy",
        "guy",
        "男主",
        "男",
        "彼氏",
        "boyfriend",
    }
)


def resolve_heroine_cast_mode(
    *,
    multi_heroine: object | None = None,
    cast_mode: object | None = None,
    heroine_ids: list[str] | None = None,
    cast_ids: list[str] | None = None,
    cast_masters: dict[str, Any] | None = None,
    prompt_blob: str = "",
    female_ref_image_count: int | None = None,
) -> dict[str, Any]:
    """Decide single vs multi heroine elastically from prompt / images / explicit fields.

    Default is **single**. Multi only when evidence is clear (user said so, ≥2 heroine
    ids, ≥2 female cast masters, or ≥2 female ref images with multi cue).
    """
    reasons: list[str] = []
    heroines = [str(x).strip() for x in (heroine_ids or []) if str(x).strip()]
    cast = [str(x).strip() for x in (cast_ids or []) if str(x).strip()]
    masters = cast_masters if isinstance(cast_masters, dict) else {}
    master_ids = [str(k).strip() for k in masters if str(k).strip()]
    # Female master candidates = masters not clearly male-coded
    female_masters = [
        m for m in master_ids if m.lower() not in _MALE_CAST_IDS and "male" not in m.lower()
    ]
    blob = (prompt_blob or "").strip()
    blob_l = blob.lower()
    prompt_multi = any(m in blob for m in _MULTI_HEROINE_PROMPT_MARKERS) or any(
        m in blob_l for m in _MULTI_HEROINE_PROMPT_MARKERS if m.isascii()
    )
    if prompt_multi:
        reasons.append("prompt_markers")

    # Explicit cast_mode wins when single|multi
    mode_raw = str(cast_mode or "").strip().lower()
    if mode_raw in {"single", "1", "solo"}:
        return {
            "mode": "single",
            "active": False,
            "heroine_ids": heroines[:1] if heroines else (female_masters[:1] or cast[:1]),
            "reasons": ["explicit_cast_mode=single"],
            "prompt_multi": prompt_multi,
            "female_master_count": len(female_masters),
            "female_ref_image_count": female_ref_image_count,
        }
    if mode_raw in {"multi", "multiple", "dual"}:
        if len(heroines) < 2 and len(female_masters) >= 2:
            heroines = female_masters
        reasons.append("explicit_cast_mode=multi")
        return {
            "mode": "multi",
            "active": True,
            "heroine_ids": heroines if len(heroines) >= 2 else female_masters,
            "reasons": reasons,
            "prompt_multi": prompt_multi,
            "female_master_count": len(female_masters),
            "female_ref_image_count": female_ref_image_count,
        }

    # Explicit multi_heroine bool
    if multi_heroine is False or str(multi_heroine).strip().lower() in {
        "0",
        "false",
        "no",
        "off",
        "single",
    }:
        return {
            "mode": "single",
            "active": False,
            "heroine_ids": heroines[:1] if heroines else (female_masters[:1] or []),
            "reasons": ["explicit_multi_heroine=false"],
            "prompt_multi": prompt_multi,
            "female_master_count": len(female_masters),
            "female_ref_image_count": female_ref_image_count,
        }
    if multi_heroine is True or str(multi_heroine).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        if len(heroines) < 2 and len(female_masters) >= 2:
            heroines = list(female_masters)
        reasons.append("explicit_multi_heroine=true")
        return {
            "mode": "multi",
            "active": True,
            "heroine_ids": heroines,
            "reasons": reasons,
            "prompt_multi": prompt_multi,
            "female_master_count": len(female_masters),
            "female_ref_image_count": female_ref_image_count,
        }

    # Evidence-based auto
    if len(heroines) >= 2:
        reasons.append("heroine_ids>=2")
    if len(female_masters) >= 2:
        reasons.append("cast_masters_female>=2")
    ref_n = int(female_ref_image_count or 0)
    if ref_n >= 2 and prompt_multi:
        reasons.append("female_ref_images>=2+prompt")
    elif ref_n >= 2 and len(female_masters) >= 2:
        reasons.append("female_ref_images>=2+masters")

    # Weak: two female-looking cast ids only when prompt also multi
    if not reasons and prompt_multi and len(cast) >= 2:
        cand = [c for c in cast if c.lower() not in _MALE_CAST_IDS]
        if len(cand) >= 2:
            heroines = cand
            reasons.append("prompt_multi+cast_ids")

    if reasons and (
        len(heroines) >= 2 or len(female_masters) >= 2 or (prompt_multi and ref_n >= 2)
    ):
        if len(heroines) < 2 and len(female_masters) >= 2:
            heroines = list(female_masters)
        return {
            "mode": "multi",
            "active": True,
            "heroine_ids": heroines,
            "reasons": reasons,
            "prompt_multi": prompt_multi,
            "female_master_count": len(female_masters),
            "female_ref_image_count": female_ref_image_count,
        }

    # Default single — one primary heroine
    single_id = (
        (heroines[0] if heroines else None)
        or (female_masters[0] if female_masters else None)
        or (cast[0] if cast else "hero")
    )
    return {
        "mode": "single",
        "active": False,
        "heroine_ids": [single_id] if single_id else [],
        "reasons": ["default_single"],
        "prompt_multi": prompt_multi,
        "female_master_count": len(female_masters),
        "female_ref_image_count": female_ref_image_count,
        "note": (
            "Single-heroine default. Multi only if prompt/images/cast evidence "
            "or cast_mode/multi_heroine/heroine_ids say so."
        ),
    }

def lint_multi_heroine(
    shots: list[dict[str, Any]],
    *,
    cast_ids: list[str] | None = None,
    heroine_ids: list[str] | None = None,
    active: bool | None = None,
    cast_mode: str | None = None,
) -> dict[str, Any]:
    """Soft lint for multi-heroine only when mode is multi / active.

    Single-heroine films: no dual/focal-gap warnings (elastic default).
    """
    issues: list[dict[str, Any]] = []
    codes: list[str] = []
    heroines = [str(x).strip() for x in (heroine_ids or []) if str(x).strip()]
    cast = [str(x).strip() for x in (cast_ids or []) if str(x).strip()]
    mode = (cast_mode or "").strip().lower()
    is_multi = bool(active) if active is not None else (mode == "multi" or len(heroines) >= 2)

    if not is_multi:
        return {
            "ok": True,
            "codes": [],
            "warning_count": 0,
            "issues": [],
            "heroine_ids": heroines[:1] if heroines else [],
            "cast_ids": cast,
            "focal_set": [],
            "mode": "single",
            "active": False,
            "note": "cast_mode=single — multi-heroine lint skipped (elastic default)",
        }

    focals: set[str] = set()
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        fc = str(dsl.get("focal_character") or shot.get("focal_character") or "").strip()
        if fc:
            focals.add(fc)

    if len(heroines) >= 2:
        missing_focus = [h for h in heroines if h not in focals]
        if missing_focus:
            codes.append("MULTI_HEROINE_FOCAL_GAP")
            issues.append(
                {
                    "code": "MULTI_HEROINE_FOCAL_GAP",
                    "severity": "warning",
                    "message": (
                        f"multi-heroine cast {heroines} but no shot focal_character for "
                        f"{missing_focus} — give each heroine ≥1 POV/stance beat"
                    ),
                }
            )
        # dual/pair beats recommended
        has_dual = False
        for shot in shots:
            if not isinstance(shot, dict):
                continue
            dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
            vp = str(dsl.get("viewpoint") or "").lower()
            if vp == "dual" or str(shot.get("heat_phase") or "") == "climax":
                # weak dual signal
                if vp == "dual":
                    has_dual = True
        if not has_dual and len(heroines) >= 2:
            codes.append("MULTI_HEROINE_NO_DUAL")
            issues.append(
                {
                    "code": "MULTI_HEROINE_NO_DUAL",
                    "severity": "warning",
                    "message": (
                        "≥2 heroines but no viewpoint=dual shot — "
                        "add at least one two-shot / 同框 for relationship peak"
                    ),
                }
            )

    if len(cast) >= 3 and len(focals) < 2:
        codes.append("MULTI_CAST_FLAT_FOCAL")
        issues.append(
            {
                "code": "MULTI_CAST_FLAT_FOCAL",
                "severity": "warning",
                "message": (
                    f"cast has {len(cast)} ids but focal variety only {sorted(focals)} — "
                    "rotate focal_character across heroines/partner"
                ),
            }
        )

    return {
        "ok": len(issues) == 0,
        "codes": sorted(set(codes)),
        "warning_count": len(issues),
        "issues": issues,
        "heroine_ids": heroines,
        "cast_ids": cast,
        "focal_set": sorted(focals),
        "mode": "multi",
        "active": True,
        "note": "Multi-heroine active — see references/ecchi-story.md §女主弹性 · character-stance.md",
    }

