"""I2V provider / profile / H3 / transition defaults for film_spec (W2 peel).

Structure-only. Does not retune default providers or H3 lanes — body moved
verbatim from validate_film_spec.
"""

from __future__ import annotations

from typing import Any

from edit_policy import (
    DEFAULT_TRANSITION_SEC,
    PolicyError,
    normalize_transition_intent,
    normalize_transition_sec,
    normalize_xfade_style,
)
from film_spec_profile import (
    I2V_PROVIDERS,
    default_frw_video_model,
    default_i2v_provider,
    frw_i2v_fallback_chain,
    resolve_h3_config,
    resolve_i2v_profile,
)
from plan.film_spec_lints import FilmSpecError

try:
    from plan.film_spec_constants import *  # noqa: F403
except ImportError:  # pragma: no cover
    from film_spec_constants import *  # type: ignore  # noqa: F403


def apply_provider_and_transition_defaults(spec: dict[str, Any]) -> None:
    """Mutate spec for i2v/still/H3/caption/transition defaults (pre-shot loop)."""
    # I2V profile is explicit so existing projects can keep their locked route.
    i2v_profile = resolve_i2v_profile()
    spec["_i2v_profile"] = i2v_profile
    chain = frw_i2v_fallback_chain()
    raw_i2v = spec.get("i2v_provider", "auto")
    spec["_i2v_provider_explicit"] = isinstance(raw_i2v, str) and raw_i2v.strip().lower() != "auto"
    raw_still = spec.get("still_provider", "auto")
    if not isinstance(raw_still, str) or raw_still.lower() not in {
        "auto",
        "comfy_lan",
        "grok",
    }:
        raise FilmSpecError("film-spec still_provider must be one of ['auto', 'comfy_lan', 'grok']")
    spec["still_provider"] = raw_still.lower()
    if not isinstance(raw_i2v, str) or raw_i2v.lower() not in I2V_PROVIDERS:
        raise FilmSpecError(f"film-spec i2v_provider must be one of {sorted(I2V_PROVIDERS)}")
    i2v_provider = raw_i2v.lower()
    if i2v_provider == "auto":
        i2v_provider = default_i2v_provider()
        i2v_notes = list(spec.get("_i2v_notes") or [])
        if i2v_profile == "ltx23_primary":
            i2v_notes.append(
                "auto→frw-ltx23 (LEGACY full-film LTX 2.3; prefer ltx23_adult for adult max; "
                "fresh approved canary + per-shot media review required)"
            )
        elif i2v_profile == "ltx23_adult":
            i2v_notes.append(
                "auto→frw-ltx23 label + ltx23_adult lanes: safe dialogue/soft → LTX 2.3 "
                "img2video-audio (prefer_native); restricted/bare/meat → comfy-h3 hard; "
                "still repair → FRW i2i still-challenge; canary required before bulk"
            )
        elif i2v_profile == "grok_primary":
            i2v_notes.append(
                "auto→grok (AIFILM_I2V_PROFILE=grok_primary / Seedance unavailable: "
                "bulk image_to_video; still=image_edit cast; register image_to_video)"
            )
        elif i2v_profile == "hybrid_h3":
            i2v_notes.append(
                "auto→grok bulk primary + hybrid_h3 lanes: restricted/meat → comfy-h3 pilot; "
                "env → FRW ltx-t2v; safe dialogue → FRW LTX 2.3 audio when lanes.dialogue=frw_ltx23; "
                "setup non-sensitive → Grok; H3 audio prefer_native"
            )
        elif i2v_profile == "h3_primary":
            i2v_notes.append(
                "auto→comfy-h3 film-wide primary (AIFILM_I2V_PROFILE=h3_primary): "
                "setup/meat/dialogue/continue → local MiniMax H3 (I2V/FLF/R2V by scene); "
                "env/bridge no-face → H3 T2V; Grok cloud only via AIFILM_ALLOW_CLOUD_RESTRICTED=1; "
                "H3 audio prefer_native"
            )
        else:
            i2v_notes.append("auto→frw-ltx23 (compatibility profile normalized to LTX primary)")
        spec["_i2v_notes"] = i2v_notes
    # Explicit legacy FRW remains readable for a deliberate recovery run.
    if i2v_profile in {"grok_primary", "hybrid_h3"} and i2v_provider == "frw":
        i2v_notes = list(spec.get("_i2v_notes") or [])
        i2v_notes.append(
            "NOTE explicit i2v_provider=frw — allowed only for a recorded technical fallback; "
            "auto always resolves to Grok primary"
        )
        spec["_i2v_notes"] = i2v_notes
    if i2v_profile == "h3_primary" and i2v_provider in {"grok", "frw", "frw-ltx23"}:
        i2v_notes = list(spec.get("_i2v_notes") or [])
        i2v_notes.append(
            f"NOTE explicit i2v_provider={i2v_provider} under h3_primary — cloud/FRW is "
            "opt-in only; per-shot soft-lock still prefers comfy-h3 unless provider is "
            "shot-explicit"
        )
        spec["_i2v_notes"] = i2v_notes
    spec["i2v_provider"] = i2v_provider
    # Dual-lane MiniMax H3: hybrid_h3 / h3_primary, explicit h3.enabled, or adult-max auto.
    h3_cfg = resolve_h3_config(spec)
    spec["h3"] = h3_cfg
    if h3_cfg.get("enabled") is True:
        # Do not demote an explicit h3_primary film to hybrid_h3.
        if str(spec.get("_i2v_profile") or "") == "grok_primary":
            spec["_i2v_profile"] = "hybrid_h3"
            notes = list(spec.get("_i2v_notes") or [])
            notes.append(
                "adult/heat dual-lane: film promoted to hybrid_h3 (Grok setup bulk + "
                "local MiniMax H3 restricted/meat); set h3.enabled=false to opt out, "
                "or AIFILM_I2V_PROFILE=h3_primary for full local primary"
            )
            spec["_i2v_notes"] = notes
        if not isinstance(spec.get("motion_lanes"), dict):
            profile_now = str(spec.get("_i2v_profile") or "")
            if profile_now == "h3_primary":
                spec["motion_lanes"] = {
                    "default": "comfy-h3",
                    "restricted_local": "comfy-h3",
                    "env": "comfy-h3",
                    "dialogue": "comfy-h3",
                    "dialogue_restricted_local": "comfy-h3",
                    "setup_non_sensitive": "comfy-h3",
                    "allow_cloud_soft": False,
                }
            elif profile_now == "ltx23_adult":
                # Option A: safe dialogue/soft → LTX audio; meat → H3; i2i repair separate.
                spec["motion_lanes"] = {
                    "default": "frw-ltx23",
                    "restricted_local": "comfy-h3",
                    "env": "frw_ltx_t2v",
                    "dialogue": "frw_ltx23",
                    "dialogue_safe_cloud": "cloud_ltx23_audio",
                    "dialogue_restricted_local": "local_dialogue_h3",
                    "setup_non_sensitive": "cloud_ltx23_audio",
                    "still_repair": "frw_img2image_still_challenge",
                    "allow_ltx_dialogue": True,
                    "allow_cloud_soft": True,
                }
            else:
                spec["motion_lanes"] = {
                    "default": "cloud",
                    "restricted_local": "comfy-h3",
                    "env": "frw_ltx_t2v",
                    "dialogue": "frw_ltx23",
                    "dialogue_safe_cloud": "cloud_ltx23_audio",
                    "dialogue_restricted_local": "local_dialogue_h3",
                    "setup_non_sensitive": "grok",
                    "still_repair": "frw_img2image_still_challenge",
                    "allow_ltx_dialogue": True,
                }
    elif str(spec.get("_i2v_profile") or "") == "h3_primary" and not isinstance(
        spec.get("motion_lanes"), dict
    ):
        # Profile alone still seeds local-primary lanes even if h3.enabled later false.
        spec["motion_lanes"] = {
            "default": "comfy-h3",
            "restricted_local": "comfy-h3",
            "env": "comfy-h3",
            "dialogue": "comfy-h3",
            "setup_non_sensitive": "comfy-h3",
            "allow_cloud_soft": False,
        }
    elif str(spec.get("_i2v_profile") or "") == "ltx23_adult" and not isinstance(
        spec.get("motion_lanes"), dict
    ):
        spec["motion_lanes"] = {
            "default": "frw-ltx23",
            "restricted_local": "comfy-h3",
            "env": "frw_ltx_t2v",
            "dialogue": "frw_ltx23",
            "dialogue_safe_cloud": "cloud_ltx23_audio",
            "dialogue_restricted_local": "local_dialogue_h3",
            "setup_non_sensitive": "cloud_ltx23_audio",
            "still_repair": "frw_img2image_still_challenge",
            "allow_ltx_dialogue": True,
            "allow_cloud_soft": True,
        }
    # FRW video model (Seedance/LTX path). auto → seedance id kept as aspirational label
    raw_fvm = spec.get("frw_video_model", default_frw_video_model())
    if not isinstance(raw_fvm, str) or raw_fvm.lower() not in FRW_VIDEO_MODELS:
        raise FilmSpecError(f"film-spec frw_video_model must be one of {sorted(FRW_VIDEO_MODELS)}")
    fvm = raw_fvm.lower()
    if i2v_provider == "frw-ltx23" and fvm == "legacy-img2video":
        fvm = "ltx-i2v"
    if fvm == "seedance-2-fast-i2v":
        raise FilmSpecError(
            "frw_video_model=seedance-2-fast-i2v is unavailable; use LTX 2.3 Audio or "
            "legacy-img2video only as the reviewed FRW fallback"
        )
    if fvm == "auto":
        fvm = default_frw_video_model()
        notes = list(spec.get("_frw_video_notes") or [])
        notes.append(
            f"auto→{fvm} (label for when FRW seedance returns; "
            f"L1 active provider={i2v_provider}; never legacy img2video default)"
        )
        spec["_frw_video_notes"] = notes
    if fvm == "legacy-img2video":
        notes = list(spec.get("_frw_video_notes") or [])
        notes.append(
            "FRW API img2video fallback: current film canary plus decoded, human-approved "
            "media are required; register frw_img2video with the actual returned model; "
            "prefer the LTX → FRW API I2V → Grok Video 1.5 chain"
        )
        spec["_frw_video_notes"] = notes
    if fvm.startswith("ltx-"):
        notes = list(spec.get("_frw_video_notes") or [])
        notes.append(
            "LTX: width/height/duration/fps must be strings; "
            "9:16 preserve native 704×1280; do not upscale or stretch; "
            "ltx-i2v/flf may 502 platform-side — fall back to grok"
        )
        spec["_frw_video_notes"] = notes
    spec["frw_video_model"] = fvm
    # Seedance defaults for agent CLI (aspect/resolution/duration)
    if "frw_aspect_ratio" not in spec or not spec.get("frw_aspect_ratio"):
        ar = str(spec.get("aspect_ratio") or DEFAULT_FRW_ASPECT)
        spec["frw_aspect_ratio"] = (
            "9:16"
            if ar in {"9:16", "9x16"}
            else ("16:9" if ar in {"16:9", "16x9"} else DEFAULT_FRW_ASPECT)
        )
    if "frw_resolution" not in spec or not spec.get("frw_resolution"):
        # FRW fallback may use a provider resolution label, but native LTX
        # pixels remain 704x1280 for vertical generation.
        spec["frw_resolution"] = DEFAULT_FRW_RESOLUTION
    if "frw_duration" not in spec or not spec.get("frw_duration"):
        spec["frw_duration"] = DEFAULT_FRW_DURATION
    # Always store as strings (LTX/API reject numbers)
    spec["frw_duration"] = str(spec.get("frw_duration") or DEFAULT_FRW_DURATION)
    if "frw_fps" not in spec or not spec.get("frw_fps"):
        if fvm.startswith("ltx-"):
            spec["frw_fps"] = DEFAULT_FRW_FPS
    else:
        spec["frw_fps"] = str(spec["frw_fps"])
    # LTX pixel size (seedance uses aspect+resolution labels instead)
    ar_frw = str(spec.get("frw_aspect_ratio") or DEFAULT_FRW_ASPECT)
    if fvm.startswith("ltx-"):
        if not spec.get("frw_width") or not spec.get("frw_height"):
            if ar_frw in {"9:16", "9x16"}:
                spec["frw_width"] = str(spec.get("frw_width") or DEFAULT_LTX_WIDTH)
                spec["frw_height"] = str(spec.get("frw_height") or DEFAULT_LTX_HEIGHT)
            elif ar_frw in {"16:9", "16x9"}:
                spec["frw_width"] = str(spec.get("frw_width") or "1280")
                spec["frw_height"] = str(spec.get("frw_height") or "720")
            else:
                spec["frw_width"] = str(spec.get("frw_width") or DEFAULT_LTX_WIDTH)
                spec["frw_height"] = str(spec.get("frw_height") or DEFAULT_LTX_HEIGHT)
        else:
            spec["frw_width"] = str(spec["frw_width"])
            spec["frw_height"] = str(spec["frw_height"])
    # Action fallback order is policy, while execution remains capability- and
    # receipt-gated in i2v_provider.generate_with_fallback.
    spec["_frw_fallback_chain"] = list(chain)
    # Env / synth layer model (LTX T2V beds — no face import)
    raw_env = spec.get("frw_env_model", DEFAULT_FRW_ENV_MODEL)
    if not isinstance(raw_env, str) or raw_env.lower() not in FRW_ENV_MODELS:
        raise FilmSpecError(f"film-spec frw_env_model must be one of {sorted(FRW_ENV_MODELS)}")
    env_m = raw_env.lower()
    if env_m == "auto":
        env_m = DEFAULT_FRW_ENV_MODEL
        notes = list(spec.get("_frw_env_notes") or [])
        notes.append(f"auto→{env_m} for env/bridge/insert beds (no cast import)")
        spec["_frw_env_notes"] = notes
    if env_m == "legacy-text2video":
        notes = list(spec.get("_frw_env_notes") or [])
        notes.append("WARN legacy-text2video: classic FRW T2V; prefer ltx-t2v")
        spec["_frw_env_notes"] = notes
    spec["frw_env_model"] = env_m
    if "_frw_t2v_fallback_chain" not in spec:
        spec["_frw_t2v_fallback_chain"] = list(FRW_T2V_FALLBACK_CHAIN)
    # Layer routing summary for agents (P1 hero vs P5 synth)
    hero_primary = (
        "frw_ltx23_img2video_audio"
        if i2v_provider == "frw-ltx23"
        else "grok_image_to_video"
        if i2v_provider == "grok"
        else f"frw:{fvm}"
    )
    spec["_layer_routing"] = {
        "i2v_profile": i2v_profile,
        "hero_still": "grok_image_edit_cast",
        "hero_motion_primary": hero_primary,
        "hero_i2v_provider": i2v_provider,
        "hero_motion_priority": list(ACTION_MOTION_PROVIDER_CHAIN),
        "hero_motion_fallback": list(chain),
        "hero_motion_frw_only_lifeboat": FRW_I2V_FRW_ONLY_LIFEBOAT,
        "env_synth_primary": "frw_ltx_t2v",
        "env_synth_fallback": [
            "grok:image_to_video_no_face",
            "local:verified-t2v",
        ],
        "env_plate_cli": "frw newvideo --model ltx-t2v; then Grok no-face I2V if unavailable",
        "env_register_endpoint": "frw_ltx_t2v",
        "key_canary": (
            "FRW LTX, FRW API I2V, and Grok Video 1.5 each need a film-scoped approved "
            "canary before fallback"
        ),
        "register_endpoint_hero": (
            "frw_ltx23_img2video_audio"
            if i2v_provider == "frw-ltx23"
            else "image_to_video"
            if i2v_provider == "grok"
            else "frw_seedance_i2v|frw_ltx_*|frw_img2video"
        ),
        "designed_post": "hyperframes|remotion",
        "note": (
            "action order is FRW LTX 2.3 → Grok I2V → verified FRW Wan → other verified "
            "local I2V; unready providers are skipped, while an attempted provider switches "
            "only after a classified technical failure"
        ),
    }
    # Caption language(s) for designed-post (HyperFrames/Remotion)
    raw_cap = spec.get("caption_mode", DEFAULT_CAPTION_MODE)
    if not isinstance(raw_cap, str) or raw_cap.lower() not in CAPTION_MODES:
        raise FilmSpecError(f"film-spec caption_mode must be one of {sorted(CAPTION_MODES)}")
    spec["caption_mode"] = raw_cap.lower()
    # Transition fluency (silk editorial glue vs punchy hard punctuation)
    raw_flu = spec.get("transition_fluency", DEFAULT_TRANSITION_FLUENCY)
    if not isinstance(raw_flu, str) or raw_flu.lower() not in TRANSITION_FLUENCIES:
        raise FilmSpecError(
            f"film-spec transition_fluency must be one of {sorted(TRANSITION_FLUENCIES)}"
        )
    flu = raw_flu.lower()
    if flu == "auto":
        # storyteller/色气 short: default silk on non-continue; horror punchy left to author
        tone_blob = " ".join(
            str(x)
            for x in (
                (spec.get("director_intent") or {}).get("tone")
                if isinstance(spec.get("director_intent"), dict)
                else "",
                spec.get("title") or "",
                spec.get("description") or "",
            )
        ).lower()
        if any(k in tone_blob for k in ("horror", "惊悚", "恐怖", "thriller", "dark")):
            flu = "punchy"
        else:
            flu = "silk"
        notes = list(spec.get("_transition_fluency_notes") or [])
        notes.append(f"auto→{flu} transition_fluency")
        spec["_transition_fluency_notes"] = notes
    spec["transition_fluency"] = flu
    allow_fallback = spec.get("tts_allow_network_fallback", False)
    if not isinstance(allow_fallback, bool):
        raise FilmSpecError("film-spec tts_allow_network_fallback must be boolean")
    native_volume = spec.get("native_audio_volume", 0.72)
    if not isinstance(native_volume, (int, float)) or isinstance(native_volume, bool):
        raise FilmSpecError("film-spec native_audio_volume must be a number between 0 and 1")
    if float(native_volume) < 0 or float(native_volume) > 1:
        raise FilmSpecError("film-spec native_audio_volume must be between 0 and 1")
    # Default silk dissolve when author omits transition_sec.  Keep this fact so
    # the voice-coupled strategy cannot turn an implicit global default into an
    # authored 0.40s hold just because one join is a mood_hold.
    transition_sec_authored = "transition_sec" in spec and spec.get("transition_sec") is not None
    if not transition_sec_authored:
        spec["transition_sec"] = DEFAULT_TRANSITION_SEC
    try:
        spec["transition_sec"] = normalize_transition_sec(spec.get("transition_sec"))
    except PolicyError as exc:
        raise FilmSpecError(str(exc)) from exc

    try:
        spec["transition_style"] = normalize_xfade_style(spec.get("transition_style"))
    except PolicyError as exc:
        raise FilmSpecError(str(exc)) from exc

    # Optional P2: per-join story transition intents (length n_shots-1 after shots known)
    # If omitted, auto-fill from dramatic_function sequence after shots validated.
    raw_intents = spec.get("transition_intents")
    if raw_intents is not None and not isinstance(raw_intents, list):
        raise FilmSpecError("transition_intents must be an array of hard|soft|hold")
    raw_styles = spec.get("transition_styles")
    if raw_styles is not None and not isinstance(raw_styles, list):
        raise FilmSpecError("transition_styles must be an array of xfade style names")

    default_intent = spec.get("transition_default", "soft")
    try:
        spec["transition_default"] = normalize_transition_intent(
            default_intent, field="transition_default"
        )
    except PolicyError as exc:
        raise FilmSpecError(str(exc)) from exc

