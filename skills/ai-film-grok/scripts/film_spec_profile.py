"""I2V / H3 / FRW profile resolve helpers (R3 peel from film_spec).

Public symbols remain re-exported by ``film_spec`` for hard-compat.
Iron: no silent i2v_provider / h3 profile default changes — move-only peel.
"""

from __future__ import annotations

# Motion provider profiles. Adult meat stays local H3; LTX is opt-in audio lane.
# ``seedance_first`` and ``grok_primary`` remain readable compatibility inputs.
I2V_PROVIDERS = frozenset({"frw", "frw-ltx23", "grok", "comfy-h3", "auto"})
# h3_primary: local 5090 MiniMax H3 is the film-wide motion primary (unlimited compute).
# hybrid_h3: dual-lane (Grok bulk soft + H3 restricted/meat).
# ltx23_adult: safe dialogue + soft → FRW LTX 2.3 native audio; restricted/meat → H3 hard.
# ltx23_primary: legacy full-film LTX (deprecated for new adult max films).
I2V_PROFILES = frozenset(
    {
        "ltx23_primary",
        "ltx23_adult",
        "seedance_first",
        "grok_primary",
        "hybrid_h3",
        "h3_primary",
    }
)
# Explicit legacy FRW lifeboat; it is not part of the automatic action chain.
FRW_I2V_FRW_ONLY_LIFEBOAT = "legacy-img2video"

# H3 ships stereo diegetic audio; prefer keeping it when usable.
# strip_native_use_tts_bgm remains available when VO-only plates are wanted.
H3_AUDIO_POLICIES = frozenset(
    {
        "prefer_native",  # default: keep if usable, else strip for TTS/BGM
        "keep_native",  # always keep H3 native track
        "strip_native_use_tts_bgm",
        "mute_native",
    }
)

DEFAULT_H3_CONFIG: dict[str, object] = {
    "enabled": False,
    "stage": "pilot",
    "max_duration_sec": 8,
    "megapixels_draft": 0.2,
    "megapixels_select": 0.6,
    "audio_policy": "prefer_native",
    "allow_bulk": False,
}


def resolve_i2v_profile() -> str:
    """Operating profile for hero motion bulk.

    ``seedance_first`` is retained for backwards-compatible parsing but now
    normalizes to the supported Grok-first action chain.
    ``h3_primary`` = local 5090 MiniMax H3 is the film-wide primary (T2V/I2V/R2V/FLF).
    """
    from config_loader import get_config

    cfg = get_config()
    raw = cfg.i2v_profile.strip().lower()
    if raw == "seedance_first":
        return "grok_primary"
    return raw if raw in I2V_PROFILES else "grok_primary"


def default_i2v_provider() -> str:
    profile = resolve_i2v_profile()
    if profile == "h3_primary":
        # Unlimited local compute primary; Grok only via opt-in cloud escape.
        return "comfy-h3"
    if profile in {"grok_primary", "hybrid_h3"}:
        # hybrid_h3 keeps Grok as the bulk auto lock; restricted shots route to
        # comfy-h3 via production_router / shot intent, not a film-wide lock.
        return "grok"
    if profile in {"ltx23_primary", "ltx23_adult"}:
        # Film-wide auto label is FRW LTX; restricted meat still soft-locks to H3.
        return "frw-ltx23"
    return "frw"


def resolve_h3_config(spec: dict | None = None) -> dict[str, object]:
    """Merge film-spec h3 block with profile defaults.

    - ``h3_primary`` / ``hybrid_h3`` → H3 lane enabled
    - Adult / heat max films auto-enable dual-lane H3 (Grok bulk + local meat)
      unless ``h3.enabled`` is explicitly false or heat is soft
    """
    profile = resolve_i2v_profile()
    raw = (spec or {}).get("h3") if isinstance(spec, dict) else None
    merged = dict(DEFAULT_H3_CONFIG)
    if profile in {"hybrid_h3", "h3_primary", "ltx23_adult"}:
        # ltx23_adult still needs H3 for restricted/bare meat (never silent cloud meat).
        merged["enabled"] = True
    # Adult-max default dual-lane without requiring env hybrid_h3.
    # ltx23_primary is legacy pure-cloud; do not auto-force H3 unless film opts in.
    if isinstance(spec, dict) and profile != "ltx23_primary":
        genre = str(spec.get("genre") or "").strip().lower()
        heat = str(spec.get("heat_scale") or "").strip().lower()
        adult_max = spec.get("adult_max_iron")
        soft = heat in {"soft", "medium"} or adult_max is False
        adultish = genre == "adult" or heat in {"max", "hot", "extreme"}
        explicit_enabled = raw.get("enabled") if isinstance(raw, dict) else None
        if (
            not soft
            and adultish
            and explicit_enabled is not False
            and (explicit_enabled is True or not isinstance(raw, dict) or "enabled" not in raw)
        ):
            merged["enabled"] = True
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in DEFAULT_H3_CONFIG or key in {"notes"}:
                merged[key] = value
        if raw.get("enabled") is False:
            merged["enabled"] = False
    # clamp duration hard top for GPU safety
    try:
        max_dur = float(merged.get("max_duration_sec") or 8)
    except (TypeError, ValueError):
        max_dur = 8.0
    merged["max_duration_sec"] = max(3.0, min(max_dur, 15.0))
    try:
        mp = float(merged.get("megapixels_draft") or 0.2)
    except (TypeError, ValueError):
        mp = 0.2
    merged["megapixels_draft"] = max(0.1, min(mp, 1.0))
    audio = str(merged.get("audio_policy") or "prefer_native").strip()
    if audio not in H3_AUDIO_POLICIES:
        audio = "prefer_native"
    merged["audio_policy"] = audio
    return merged


def default_frw_video_model() -> str:
    return FRW_I2V_FRW_ONLY_LIFEBOAT


def frw_i2v_fallback_chain() -> tuple[str, ...]:
    return (
        "frw:img2video-api",
        "grok:video-1.5",
    )
