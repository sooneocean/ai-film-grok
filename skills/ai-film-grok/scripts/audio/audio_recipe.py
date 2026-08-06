#!/usr/bin/env python3
"""Scene-adaptive audio recipes for ai-film-grok.

Film-level ``audio_policy`` + per-shot ``audio_recipe`` so BGM/VO/lipsync/sung
are routed by dramatic_function (and capability gates), not hand-tuned every final.

Recipes (primary voice + bed thickness):
  narrate_bed      — storyteller VO + full bed (default)
  narrate_thin     — VO + thin bed (dense info / reaction)
  bed_focus        — bed/sfx lead; VO minimal or none
  dialogue_lipsync — character VO + near lipsync (opt-in)
  sung_beat        — sung line = dialogue (opt-in musical_hybrid only)

Hard rules:
  - Never auto-enable sung unless audio_policy.allow_sung + mode musical_hybrid
  - Never auto-enable lipsync unless allow_lipsync + near shot
  - Missing capability → degrade and record reasons (always have a playable path)
"""

from __future__ import annotations

from typing import Any

AUDIO_RECIPES = frozenset(
    {
        "narrate_bed",
        "narrate_thin",
        "bed_focus",
        "dialogue_lipsync",
        "sung_beat",
    }
)
AUDIO_POLICY_MODES = frozenset({"auto", "storyteller_only", "musical_hybrid"})
BED_SOURCES = frozenset({"auto", "library_only", "approved_library", "procedural_only"})

# Near-ish sizes that may justify lipsync / sung (mouth readable)
_NEAR_SIZES = frozenset(
    {
        "ecu",
        "cu",
        "close",
        "closeup",
        "close-up",
        "close_up",
        "mcu",
        "medium_close",
        "medium-close",
        "near",
        "portrait",
        "face",
        "head",
        "特写",
        "大特写",
        "近景",
    }
)


class AudioRecipeError(ValueError):
    pass


def _shot_size(shot: dict[str, Any]) -> str:
    cam = shot.get("camera") if isinstance(shot.get("camera"), dict) else {}
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    framing = dsl.get("framing") if isinstance(dsl.get("framing"), dict) else {}
    raw = cam.get("shot_size") or framing.get("shot_size") or shot.get("shot_size") or ""
    return str(raw).strip().lower().replace(" ", "_")


def is_near_shot(shot: dict[str, Any]) -> bool:
    if shot.get("screen_mode") == "on_camera" and shot.get("lipsync") is True:
        return True
    size = _shot_size(shot)
    if not size:
        return False
    if size in _NEAR_SIZES:
        return True
    # fuzzy: contains cu / close
    return any(k in size for k in ("cu", "close", "特写", "近景"))


def nar_char_count(shot: dict[str, Any]) -> int:
    nar = str(shot.get("nar") or "").strip()
    if nar:
        return len(nar)
    for cue in shot.get("audio_cues") or []:
        if isinstance(cue, dict) and cue.get("kind") == "voice":
            return len(str(cue.get("spoken_text") or "").strip())
    return len(str(shot.get("dialogue") or "").strip())


def default_audio_policy(
    *,
    vo_mode: str = "storyteller",
    author: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Conservative defaults: auto/storyteller never auto-sings."""
    author = author if isinstance(author, dict) else {}
    mode = str(author.get("mode") or "auto").strip().lower()
    if mode not in AUDIO_POLICY_MODES:
        raise AudioRecipeError(
            f"audio_policy.mode must be one of {sorted(AUDIO_POLICY_MODES)}; got {mode!r}"
        )
    bed_src = str(author.get("bed_source") or "auto").strip().lower()
    if bed_src not in BED_SOURCES:
        raise AudioRecipeError(
            f"audio_policy.bed_source must be one of {sorted(BED_SOURCES)}; got {bed_src!r}"
        )
    # sung only in musical_hybrid; default allow_sung=true there unless author says false
    if mode == "musical_hybrid":
        allow_sung = True if "allow_sung" not in author else bool(author.get("allow_sung"))
    else:
        allow_sung = False
    allow_lipsync = bool(author.get("allow_lipsync", False))
    try:
        max_sung = max(
            0, int(author.get("max_sung_shots") if author.get("max_sung_shots") is not None else 1)
        )
    except (TypeError, ValueError) as exc:
        raise AudioRecipeError("audio_policy.max_sung_shots must be int") from exc
    out: dict[str, Any] = {
        "mode": mode,
        "allow_sung": allow_sung,
        "allow_lipsync": allow_lipsync,
        "bed_source": bed_src,
        "max_sung_shots": max_sung,
    }
    if author.get("music_seed") is not None:
        try:
            out["music_seed"] = int(author["music_seed"])
        except (TypeError, ValueError) as exc:
            raise AudioRecipeError("audio_policy.music_seed must be int") from exc
    # vo_mode is informational only here; routing also checks vo_mode
    out["_vo_mode"] = str(vo_mode or "storyteller")
    return out


def validate_audio_policy(raw: object, *, vo_mode: str = "storyteller") -> dict[str, Any]:
    if raw is None:
        return default_audio_policy(vo_mode=vo_mode)
    if not isinstance(raw, dict):
        raise AudioRecipeError("audio_policy must be an object")
    return default_audio_policy(vo_mode=vo_mode, author=raw)


def _recipe_payload(
    recipe: str,
    *,
    reasons: list[str],
    source: str = "auto",
    degraded_from: str | None = None,
) -> dict[str, Any]:
    recipe = str(recipe).strip().lower()
    if recipe not in AUDIO_RECIPES:
        raise AudioRecipeError(
            f"audio_recipe must be one of {sorted(AUDIO_RECIPES)}; got {recipe!r}"
        )
    # Defaults per recipe
    table: dict[str, dict[str, Any]] = {
        "narrate_bed": {
            "primary_voice": "narration",
            "bed": "full",
            "bed_gain": 1.0,
            "lipsync": False,
            "sfx_level": "normal",
        },
        "narrate_thin": {
            "primary_voice": "narration",
            "bed": "thin",
            "bed_gain": 0.55,
            "lipsync": False,
            "sfx_level": "minimal",
        },
        "bed_focus": {
            "primary_voice": "none",
            "bed": "focus",
            "bed_gain": 1.15,
            "lipsync": False,
            "sfx_level": "rich",
        },
        "dialogue_lipsync": {
            "primary_voice": "dialogue",
            "bed": "thin",
            "bed_gain": 0.45,
            "lipsync": True,
            "sfx_level": "minimal",
        },
        "sung_beat": {
            "primary_voice": "sung",
            "bed": "thin",
            "bed_gain": 0.35,
            "lipsync": True,
            "sfx_level": "minimal",
        },
    }
    body = dict(table[recipe])
    body["recipe"] = recipe
    body["source"] = source
    body["reasons"] = list(reasons)
    if degraded_from:
        body["degraded_from"] = degraded_from
    return body


def parse_author_recipe(raw: object) -> str | None:
    """Author may set shot.audio_recipe as string or {recipe: ...}."""
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    if isinstance(raw, dict) and raw.get("recipe"):
        return str(raw["recipe"]).strip().lower()
    return None


def _capability(
    *,
    lipsync_ready: bool = False,
    music_library: bool = False,
    sung_provider_ready: bool = False,
) -> dict[str, bool]:
    return {
        "lipsync_ready": bool(lipsync_ready),
        "music_library": bool(music_library),
        "sung_provider_ready": bool(sung_provider_ready),
    }


def degrade_recipe(
    recipe: str,
    *,
    policy: dict[str, Any],
    shot: dict[str, Any],
    caps: dict[str, bool],
    reasons: list[str],
) -> tuple[str, list[str], str | None]:
    """Apply capability + policy gates; return (recipe, reasons, degraded_from)."""
    original = recipe
    degraded_from: str | None = None
    rsn = list(reasons)

    if recipe == "sung_beat":
        if not policy.get("allow_sung") or policy.get("mode") != "musical_hybrid":
            recipe = "narrate_bed"
            degraded_from = original
            rsn.append("sung blocked: need musical_hybrid + allow_sung")
        elif not caps.get("sung_provider_ready"):
            recipe = "narrate_bed"
            degraded_from = original
            rsn.append(
                "sung blocked: no sung provider available "
                "(set AIFILM_MUSIC_ARGV for HeartMuLa, or enable a local sung provider)"
            )
        elif not is_near_shot(shot):
            recipe = "narrate_bed"
            degraded_from = original
            rsn.append("sung blocked: need near shot_size for lipsync")

    if recipe == "dialogue_lipsync":
        if str(policy.get("mode")) == "storyteller_only" and not shot.get("lipsync"):
            recipe = "narrate_thin"
            degraded_from = degraded_from or original
            rsn.append("dialogue_lipsync→narrate_thin: storyteller_only")
        elif not policy.get("allow_lipsync") and not shot.get("lipsync"):
            recipe = "narrate_thin"
            degraded_from = degraded_from or original
            rsn.append("dialogue_lipsync→narrate_thin: allow_lipsync=false")
        elif not is_near_shot(shot):
            recipe = "narrate_thin"
            degraded_from = degraded_from or original
            rsn.append("dialogue_lipsync→narrate_thin: not near shot")
        elif not caps.get("lipsync_ready") and not shot.get("lipsync"):
            # author explicitly lipsync true still records desire; final may skip
            rsn.append("lipsync desired but backend not locked (final may skip)")

    return recipe, rsn, degraded_from


def suggest_recipe_for_shot(
    shot: dict[str, Any],
    *,
    policy: dict[str, Any],
    vo_mode: str,
    index: int,
    n_shots: int,
    sung_slots_left: int,
) -> tuple[str, list[str]]:
    """Pure routing from beat + policy (before capability degrade)."""
    beat = str(shot.get("dramatic_function") or "bridge").strip().lower()
    reasons: list[str] = [f"beat={beat}", f"policy.mode={policy.get('mode')}"]
    near = is_near_shot(shot)
    nlen = nar_char_count(shot)
    mode = str(policy.get("mode") or "auto")

    # Author explicit lipsync request on character/hybrid
    if (
        shot.get("lipsync") is True
        and vo_mode in {"character", "hybrid", "dialogue_drama"}
        and near
        and (policy.get("allow_lipsync") or mode == "musical_hybrid")
    ):
        return "dialogue_lipsync", reasons + ["author lipsync=true"]

    # musical_hybrid: at most N sung beats on climax-ish functions
    if (
        mode == "musical_hybrid"
        and policy.get("allow_sung")
        and sung_slots_left > 0
        and near
        and beat in {"action", "afterglow", "sensory"}
        and (index >= max(0, n_shots - 2) or beat == "action")
    ):
        return "sung_beat", reasons + ["musical climax candidate"]

    if beat == "sensory":
        if nlen <= 18:
            return "bed_focus", reasons + ["short nar → bed_focus"]
        return "narrate_thin", reasons + ["sensory thin bed"]
    if beat == "afterglow":
        if nlen <= 22:
            return "bed_focus", reasons + ["afterglow breath"]
        return "narrate_thin", reasons + ["afterglow thin"]
    if beat in {"bridge", "reaction"}:
        return "narrate_thin", reasons + [f"{beat} thin"]
    if beat in {"hook", "approach", "action"}:
        return "narrate_bed", reasons + [f"{beat} full bed"]
    return "narrate_bed", reasons + ["default"]


def resolve_shot_audio_recipe(
    shot: dict[str, Any],
    *,
    policy: dict[str, Any],
    vo_mode: str = "storyteller",
    index: int = 0,
    n_shots: int = 1,
    sung_slots_left: int = 0,
    caps: dict[str, bool] | None = None,
) -> dict[str, Any]:
    caps = caps or _capability()
    author_r = parse_author_recipe(shot.get("audio_recipe"))
    # If author already resolved full object with recipe+source=author and valid, re-validate
    if author_r:
        reasons = ["author audio_recipe"]
        recipe = author_r
        source = "author"
    else:
        recipe, reasons = suggest_recipe_for_shot(
            shot,
            policy=policy,
            vo_mode=vo_mode,
            index=index,
            n_shots=n_shots,
            sung_slots_left=sung_slots_left,
        )
        source = "auto"

    recipe, reasons, degraded_from = degrade_recipe(
        recipe,
        policy=policy,
        shot=shot,
        caps=caps,
        reasons=reasons,
    )
    payload = _recipe_payload(recipe, reasons=reasons, source=source, degraded_from=degraded_from)
    # Author lipsync true on dialogue/sung recipes sticks when near
    if payload["recipe"] in {"dialogue_lipsync", "sung_beat"} and is_near_shot(shot):
        if (
            shot.get("lipsync") is True
            or policy.get("allow_lipsync")
            or payload["recipe"] == "sung_beat"
        ):
            payload["lipsync"] = True
    # storyteller: force lipsync false on recipe unless character mode and allow
    if vo_mode == "storyteller" and payload["recipe"] not in {"sung_beat"}:
        payload["lipsync"] = False
        if "lipsync forced off (storyteller)" not in reasons and shot.get("lipsync"):
            payload["reasons"] = reasons + ["lipsync forced off (storyteller)"]
    return payload


def apply_audio_recipes_to_spec(
    spec: dict[str, Any],
    shots: list[dict[str, Any]],
    *,
    lipsync_ready: bool = False,
    music_library: bool = False,
    sung_provider_ready: bool = False,
) -> dict[str, Any]:
    """Mutate shots in place; set spec.audio_policy + spec._audio_routing. Returns routing summary."""
    vo_mode = str(spec.get("vo_mode") or "storyteller")
    policy = validate_audio_policy(spec.get("audio_policy"), vo_mode=vo_mode)
    caps = _capability(
        lipsync_ready=lipsync_ready,
        music_library=music_library,
        sung_provider_ready=sung_provider_ready,
    )
    n = len(shots)
    sung_left = int(policy.get("max_sung_shots") or 0) if policy.get("allow_sung") else 0
    # Prefer assigning sung to later climax: resolve in two passes
    # Pass 1: non-sung routing for all; collect candidates
    # Simpler: sequential with sung_left decremented when assigned
    counts: dict[str, int] = {r: 0 for r in AUDIO_RECIPES}
    applied: list[dict[str, Any]] = []
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        # Preserve explicit author recipe object fields if only string set later
        rec = resolve_shot_audio_recipe(
            shot,
            policy=policy,
            vo_mode=vo_mode,
            index=i,
            n_shots=n,
            sung_slots_left=sung_left,
            caps=caps,
        )
        if rec["recipe"] == "sung_beat":
            sung_left = max(0, sung_left - 1)
        shot["audio_recipe"] = rec
        # Align lipsync flag for downstream final (soft)
        if rec.get("lipsync") and vo_mode != "storyteller":
            if shot.get("lipsync") is not False:
                shot["lipsync"] = True
        elif vo_mode == "storyteller":
            shot["lipsync"] = False
        counts[rec["recipe"]] = counts.get(rec["recipe"], 0) + 1
        applied.append(
            {
                "shot_id": shot.get("id"),
                "recipe": rec["recipe"],
                "bed_gain": rec.get("bed_gain"),
                "primary_voice": rec.get("primary_voice"),
                "reasons": rec.get("reasons"),
                "degraded_from": rec.get("degraded_from"),
            }
        )

    # Film-level mean bed gain for mix hints
    gains = [
        float(s["audio_recipe"]["bed_gain"])
        for s in shots
        if isinstance(s.get("audio_recipe"), dict)
    ]
    mean_gain = sum(gains) / len(gains) if gains else 1.0

    # Annotate sound_plan with routing hint (non-breaking)
    sp = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else None
    if sp is not None:
        sp = dict(sp)
        sp["bed_gain_hint"] = round(mean_gain, 3)
        sp["bed_source_policy"] = policy.get("bed_source")
        notes = list(sp.get("_notes") or [])
        notes.append(f"audio_recipe: {', '.join(f'{k}={v}' for k, v in counts.items() if v)}")
        sp["_notes"] = notes
        spec["sound_plan"] = sp

    summary = {
        "ok": True,
        "policy": policy,
        "counts": counts,
        "mean_bed_gain": round(mean_gain, 3),
        "shots": applied,
        "caps": caps,
        "note": (
            "Per-shot audio_recipe set by write-spec. "
            "sung/lipsync never auto without audio_policy flags. "
            "See references/audio-recipe.md · voice-tracks.md (nar vs vocal_color)"
        ),
    }
    spec["audio_policy"] = policy
    spec["_audio_routing"] = summary
    # Multi-track voice: 娇喘语助 / tone_tags / sound_cues (independent gains at final)
    try:
        from voice_tracks import apply_voice_tracks_to_spec

        seed = 0
        try:
            seed = int((policy.get("music_seed") if isinstance(policy, dict) else None) or 0)
        except (TypeError, ValueError):
            seed = 0
        if not seed:
            try:
                seed = int((spec.get("audio_policy") or {}).get("music_seed") or 0)
            except (TypeError, ValueError):
                seed = 0
        if not seed:
            try:
                seed = int((spec.get("voice_tracks") or {}).get("seed") or 0)
            except (TypeError, ValueError):
                seed = 0
        vt = apply_voice_tracks_to_spec(
            spec, seed=seed or abs(hash(str(spec.get("title") or "film"))) % 997
        )
        summary["voice_tracks"] = vt
    except Exception as exc:  # noqa: BLE001 — never block write-spec on color layer
        summary["voice_tracks_error"] = str(exc)
    # Normalize authored per-line performance controls into the executable projection.
    try:
        from music_cue import compile_music_cue, summarize_music_timeline
        from performance_cue import normalize_performance_cue, summarize_bgm_response

        music_timeline = []
        for shot in shots:
            if not isinstance(shot, dict):
                continue
            shot["performance_cue"] = normalize_performance_cue(
                shot.get("performance_cue"), tone_tags=shot.get("tone_tags")
            )
            shot["music_cue"] = compile_music_cue(
                shot, default_mood=str(policy.get("mood") or "rnb")
            )
            music_timeline.append({"shot_id": shot.get("id"), **shot["music_cue"]})
        performance_bgm = summarize_bgm_response(shots)
        summary["performance_bgm"] = performance_bgm
        spec["_performance_bgm"] = performance_bgm
        summary["music_cue_routing"] = summarize_music_timeline(music_timeline)
        spec["_music_cue_routing"] = summary["music_cue_routing"]
    except Exception as exc:  # noqa: BLE001 — legacy specs without cues remain valid
        summary["performance_error"] = str(exc)
    return summary


def probe_caps_for_root(root: Any | None = None) -> dict[str, bool]:
    """Best-effort capability probe (optional root for music library)."""
    lipsync_ready = False
    music_library = False
    sung_provider_ready = False
    try:
        from lipsync_backend import probe as lipsync_probe  # type: ignore

        info = lipsync_probe()
        lipsync_ready = bool(info.get("ready"))
    except Exception:
        pass
    try:
        from pathlib import Path

        from sound_plan import resolve_music_template  # type: ignore

        if root is not None:
            hit = resolve_music_template(Path(root), mood="rnb", mode="auto", seed=0)
            music_library = hit is not None
    except Exception:
        pass
    # Sung provider readiness: external HeartMuLa (AIFILM_MUSIC_ARGV) OR a local
    # fallback (bundled local TTS adapter) — no longer blocked on the external dep.
    try:
        from sung_provider import sung_provider_ready as _sung_ready  # type: ignore

        sung_provider_ready = bool(_sung_ready())
    except Exception:
        import os

        sung_provider_ready = bool((os.environ.get("AIFILM_MUSIC_ARGV") or "").strip())
    return _capability(
        lipsync_ready=lipsync_ready,
        music_library=music_library,
        sung_provider_ready=sung_provider_ready,
    )
