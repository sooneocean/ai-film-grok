#!/usr/bin/env python3
"""Export approved Grok I2V clips into HyperFrames / Remotion composition packages.

Does NOT replace Grok Imagine generation or the default FFmpeg final path.
This is the designed-post bridge: captions, title cards, overlays, preview Studio.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from edit_policy import (
    DEFAULT_TRANSITION_SEC,
    PolicyError,
    film_segment_timeline,
    normalize_transition_sec,
    suggest_join_intent,
)
from film_spec import FilmSpecError, validate_film_spec
from security_policy import (
    SecurityPolicyError,
    reject_symlinks,
    safe_existing_file,
    safe_output_path,
    safe_workspace_directory,
)

SCHEMA_VERSION = 1
ENGINES = ("hyperframes", "remotion", "both")
# Designed-post visual presets (titles/captions only — not I2V)
COMPOSE_PRESETS = ("auto", "ecchi-rnb", "minimal")
COMPOSE_PRESET_RESOLVED = ("ecchi-rnb", "minimal")


class ComposeExportError(RuntimeError):
    """User-facing composition export error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp = Path(handle.name)
    os.replace(temp, path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")
        temp = Path(handle.name)
    os.replace(temp, path)


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ComposeExportError(f"Missing JSON: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    shots: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if isinstance(shot, dict) and shot.get("id"):
                shots.append(shot)
    return shots


def narration_for_shot(shot: dict[str, Any]) -> str:
    for key in ("nar", "narration", "vo", "text"):
        val = shot.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def narration_en_for_shot(shot: dict[str, Any]) -> str:
    for key in ("nar_en", "narration_en", "vo_en", "text_en"):
        val = shot.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def format_caption_lines(
    zh: str,
    en: str = "",
    *,
    mode: str = "zh",
) -> dict[str, str]:
    """Split caption into primary/secondary lines for designed-post dual subs.

    Returns {text, zh, en, mode} where ``text`` is display (single or dual joined).
    """
    zh_s = (zh or "").strip()
    en_s = (en or "").strip()
    m = (mode or "zh").strip().lower()
    if m not in {"zh", "zh_en", "en"}:
        m = "zh"
    if m == "en":
        primary = en_s or zh_s
        return {"text": primary, "zh": zh_s, "en": en_s, "mode": m, "html_kind": "single"}
    if m == "zh_en" and en_s:
        return {
            "text": f"{zh_s}\n{en_s}",
            "zh": zh_s,
            "en": en_s,
            "mode": m,
            "html_kind": "dual",
        }
    return {"text": zh_s, "zh": zh_s, "en": en_s, "mode": "zh", "html_kind": "single"}


def parse_srt(path: Path) -> list[dict[str, Any]]:
    """Parse a simple SRT into {start, end, text} seconds."""
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return []

    def ts_to_sec(ts: str) -> float:
        ts = ts.strip().replace(",", ".")
        parts = ts.split(":")
        if len(parts) != 3:
            return 0.0
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)

    cues: list[dict[str, Any]] = []
    blocks = re.split(r"\n\s*\n", raw)
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        if len(lines) < 2:
            continue
        # skip index line if present
        if "-->" not in lines[0] and len(lines) >= 2:
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        left, _, right = lines[0].partition("-->")
        text = " ".join(ln.strip() for ln in lines[1:]).strip()
        if not text:
            continue
        cues.append(
            {
                "start": ts_to_sec(left),
                "end": ts_to_sec(right),
                "text": text,
            }
        )
    return cues


def remotion_captions(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map internal cues to @remotion/captions Caption shape.

    Dual zh_en cues use a single Caption text with newline (Remotion display
    preserves line breaks when whiteSpace is pre-line).
    """
    out: list[dict[str, Any]] = []
    for cue in cues:
        start_ms = int(round(float(cue["start"]) * 1000))
        end_ms = int(round(float(cue["end"]) * 1000))
        text = str(cue.get("text") or "")
        # Prefer explicit dual assembly
        if cue.get("html_kind") == "dual" and cue.get("zh") and cue.get("en"):
            text = f"{cue['zh']}\n{cue['en']}"
        out.append(
            {
                "text": text if text.startswith(" ") or not out else f" {text}",
                "startMs": start_ms,
                "endMs": end_ms,
                "timestampMs": start_ms,
                "confidence": None,
                "zh": cue.get("zh"),
                "en": cue.get("en"),
                "caption_mode": cue.get("mode") or cue.get("caption_mode"),
            }
        )
    return out


def build_timeline_package(
    root: Path,
    *,
    title_dur: float = 1.5,
    end_dur: float = 1.5,
) -> dict[str, Any]:
    """Build a portable composition package from film root (no FFmpeg required)."""
    try:
        reject_symlinks(root, field="film root")
    except SecurityPolicyError as exc:
        raise ComposeExportError(str(exc)) from exc

    manifest_path = root / "manifest.json"
    spec_path = root / "film-spec.json"
    if not manifest_path.is_file():
        raise ComposeExportError("manifest.json missing — run init + register clips first")
    if not spec_path.is_file():
        raise ComposeExportError("film-spec.json missing — run write-spec first")

    manifest = read_json(manifest_path)
    spec = read_json(spec_path)
    try:
        validate_film_spec(spec, assign_missing_ids=False)
    except FilmSpecError as exc:
        raise ComposeExportError(f"film-spec invalid: {exc}") from exc

    shots = flatten_shots(spec)
    if not shots:
        raise ComposeExportError("film-spec has no shots")

    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    width = int(manifest.get("width") or 720)
    height = int(manifest.get("height") or 1280)
    fps = int(manifest.get("fps") or 30)
    title = str(spec.get("title") or manifest.get("title") or "Untitled")

    try:
        transition_sec = normalize_transition_sec(spec.get("transition_sec", DEFAULT_TRANSITION_SEC))
    except PolicyError as exc:
        raise ComposeExportError(str(exc)) from exc

    story_intents: list[str] | None = None
    raw_intents = spec.get("transition_intents")
    if isinstance(raw_intents, list) and raw_intents:
        story_intents = [str(x) for x in raw_intents]
    else:
        beats = [str(s.get("dramatic_function") or "bridge") for s in shots]
        story_intents = [
            suggest_join_intent(beats[i], beats[i + 1]) for i in range(len(beats) - 1)
        ]

    packaged_shots: list[dict[str, Any]] = []
    shot_targets: list[float] = []
    for shot in shots:
        sid = str(shot["id"])
        rec = clips.get(sid)
        if not isinstance(rec, dict):
            raise ComposeExportError(f"Missing clip record for {sid} — register-clip first")
        if rec.get("status") != "approved":
            raise ComposeExportError(f"Clip {sid} is not approved (status={rec.get('status')!r})")
        rel = rec.get("path")
        if not isinstance(rel, str):
            raise ComposeExportError(f"Clip {sid} has no path")
        try:
            clip_path = safe_existing_file(root, rel, field=f"clip {sid}")
        except SecurityPolicyError as exc:
            raise ComposeExportError(str(exc)) from exc

        dur = rec.get("duration_sec")
        duration_sec: float | None = None
        if dur is not None:
            try:
                duration_sec = float(dur)
            except (TypeError, ValueError):
                duration_sec = None
        if duration_sec is None or duration_sec <= 0:
            # Fail-loud: probe real clip media instead of inventing 6.0
            try:
                from media_duration import MediaDurationError, probe_duration_sec

                duration_sec = probe_duration_sec(clip_path, label=f"export-compose:{sid}")
            except MediaDurationError as exc:
                raise ComposeExportError(str(exc)) from exc
            except Exception:
                # last resort: film-spec plan only if media probe path unavailable
                try:
                    duration_sec = float(shot.get("duration_sec") or 0)
                except (TypeError, ValueError):
                    duration_sec = 0.0
                if duration_sec <= 0:
                    raise ComposeExportError(
                        f"Clip {sid}: no usable duration_sec and media probe failed for {clip_path}"
                    )

        # Prefer relative path from film root for portable packages
        try:
            media_rel = str(clip_path.relative_to(root))
        except ValueError:
            media_rel = rel

        packaged_shots.append(
            {
                "id": sid,
                "dramatic_function": shot.get("dramatic_function"),
                "nar": narration_for_shot(shot),
                "nar_en": narration_en_for_shot(shot),
                "duration_sec": duration_sec,
                "media_rel": media_rel,
                "media_abs": str(clip_path),
                "motion": (shot.get("dsl") or {}).get("motion")
                if isinstance(shot.get("dsl"), dict)
                else None,
                "source_endpoint": rec.get("source_endpoint"),
            }
        )
        shot_targets.append(duration_sec)

    try:
        film_tl = film_segment_timeline(
            title_duration=float(title_dur),
            shot_targets=shot_targets,
            end_duration=float(end_dur),
            transition_sec=transition_sec,
            story_join_intents=story_intents,
        )
    except PolicyError as exc:
        raise ComposeExportError(str(exc)) from exc

    # Captions: prefer final.srt timing (zh); merge nar_en for dual zh_en designed-post
    caption_mode = str(spec.get("caption_mode") or "zh").strip().lower()
    if caption_mode not in {"zh", "zh_en", "en"}:
        caption_mode = "zh"
    srt_path = root / "out" / "final.srt"
    cues = parse_srt(srt_path)
    caption_source = "out/final.srt" if cues else "film-spec.nar"
    starts = film_tl.get("shot_starts") or []
    if not cues:
        for i, item in enumerate(packaged_shots):
            zh = str(item.get("nar") or "")
            en = str(item.get("nar_en") or "")
            if not zh and not en:
                continue
            t0 = float(starts[i]) if i < len(starts) else sum(shot_targets[:i])
            t1 = t0 + float(item["duration_sec"]) * 0.92
            lines = format_caption_lines(zh, en, mode=caption_mode)
            cues.append(
                {
                    "start": t0,
                    "end": t1,
                    "text": lines["text"],
                    "shot_id": item["id"],
                    "zh": lines["zh"],
                    "en": lines["en"],
                    "mode": lines["mode"],
                    "html_kind": lines["html_kind"],
                }
            )
    else:
        enriched: list[dict[str, Any]] = []
        for i, cue in enumerate(cues):
            zh = str(cue.get("text") or "").strip()
            en = ""
            sid = None
            if i < len(packaged_shots):
                sid = packaged_shots[i]["id"]
                en = str(packaged_shots[i].get("nar_en") or "")
            lines = format_caption_lines(zh, en, mode=caption_mode)
            enriched.append(
                {
                    "start": float(cue["start"]),
                    "end": float(cue["end"]),
                    "text": lines["text"],
                    "shot_id": sid,
                    "zh": lines["zh"],
                    "en": lines["en"],
                    "mode": lines["mode"],
                    "html_kind": lines["html_kind"],
                }
            )
        cues = enriched

    # Optional pre-mixed audio / final film as underlay references
    final_film = None
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    final_rec = outputs.get("final_film") if isinstance(outputs.get("final_film"), dict) else None
    if final_rec and isinstance(final_rec.get("path"), str):
        try:
            fp = safe_existing_file(root / "out", final_rec["path"], field="final film")
            final_film = {
                "path": str(fp.relative_to(root)) if fp.is_relative_to(root) else str(fp),
                "sha256": final_rec.get("sha256"),
                "duration_sec": final_rec.get("duration_sec"),
            }
        except (SecurityPolicyError, ValueError):
            final_film = None

    vo_candidates = [
        root / "out" / "voice.wav",
        root / "audio" / "voice.wav",
        root / "out" / "_final_work" / "voice_cat.wav",
    ]
    vo_path = next((p for p in vo_candidates if p.is_file()), None)
    bgm_candidates = [
        root / "out" / "music.wav",
        root / "audio" / "music.wav",
        root / "out" / "_final_work" / "music.wav",
    ]
    bgm_path = next((p for p in bgm_candidates if p.is_file()), None)

    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": utc_now(),
        "title": title,
        "root": str(root),
        "width": width,
        "height": height,
        "fps": fps,
        "transition_sec": transition_sec,
        "story_join_intents": story_intents,
        "film_timeline": {
            "shot_starts": film_tl.get("shot_starts"),
            "output_duration": film_tl.get("output_duration"),
            "use_ts": film_tl.get("use_ts"),
            "enabled": film_tl.get("enabled"),
            "join_intents": film_tl.get("full_join_intents") or film_tl.get("join_intents"),
            "title_duration": float(title_dur),
            "end_duration": float(end_dur),
        },
        "shots": packaged_shots,
        "captions": cues,
        "caption_source": caption_source,
        "caption_mode": caption_mode,
        "audio": {
            "vo_rel": str(vo_path.relative_to(root)) if vo_path else None,
            "bgm_rel": str(bgm_path.relative_to(root)) if bgm_path else None,
        },
        "final_film": final_film,
        "director_intent": spec.get("director_intent"),
        "sound_plan": spec.get("sound_plan"),
        "vo_mode": spec.get("vo_mode"),
        "notes": {
            "role": "designed-post bridge",
            "does_not_replace": [
                "Grok Imagine still/I2V generation",
                "default FFmpeg final (render_final.py)",
                "review-final seven-dimension scorecard",
            ],
            "use_for": [
                "designed captions / lower-thirds",
                "title + end card motion",
                "color grade / overlay graphics",
                "Studio preview before polish render",
                "perceptual continuity glue (captions/grade) — not match-cut dissolve",
            ],
        },
        # Fluency contract for HyperFrames / Remotion agents (2026-07-20)
        "fluency": _fluency_export_meta(spec, story_intents),
    }


def _fluency_export_meta(
    spec: dict[str, Any],
    story_intents: list[str] | None,
) -> dict[str, Any]:
    """Metadata so HF/Remotion agents respect match-cut + continue-chain policy."""
    intents = [str(x).lower() for x in (story_intents or [])]
    hard_n = sum(1 for x in intents if x == "hard")
    soft_n = sum(1 for x in intents if x in {"soft", "hold"})
    visual_fit = str(spec.get("visual_fit") or "slot").strip().lower()
    long_form = bool(spec.get("long_form") or spec.get("require_continuity_chain"))
    # Heuristic: mostly-hard joins + vo fit → continue-chain style plate
    continue_chain = long_form or (
        visual_fit == "vo" and hard_n >= max(1, soft_n)
    )
    video_join = "hard_match_cut" if hard_n >= soft_n else "mixed_soft"
    return {
        "visual_fit": visual_fit,
        "story_join_intents": intents,
        "video_join_policy": video_join,
        "continue_chain": continue_chain,
        "recommended_post_engine": "hyperframes",
        "recommended_layout": "underlay",
        "designed_post_may": [
            "captions",
            "bilingual_captions_zh_en",
            "title_end_cards",
            "consistent_grade_overlay",
            "studio_preview",
            "safe_area_chrome",
            "l_cut_j_cut_via_continuous_mix_audio",
            "caption_bridge_across_hard_cuts",
        ],
        "designed_post_must_not": [
            "ken_burns_stills_as_story",
            "dissolve_or_xfade_on_underlay_at_byte_identical_joins",
            "replace_i2v_or_continuity_chain",
            "burned_in_plus_designed_subs_double_burn",
            "ffmpeg_title_glyphs_plus_designed_title_double_burn",
            "soft_xfade_on_continue_byte_chain",
        ],
        "agent_skills": {
            "hyperframes": ["/hyperframes", "/hyperframes-core", "/hyperframes-animation"],
            "remotion": [
                "/remotion-best-practices",
                "/remotion-captions",
                "remotion-markup",
            ],
        },
        "docs": [
            "references/post-compose.md",
            "references/hf-remotion-capability-matrix.md",
            "references/lessons-2026-07-20-designed-post-fluency.md",
            "references/lessons-2026-07-20-title-double-burn.md",
            "references/lessons-2026-07-20-cut-silk-bilingual.md",
            "references/lessons-2026-07-20-action-fluency.md",
            "references/continuity_chain.md",
        ],
    }


def _rel_from_compose(film_root: Path, media_rel: str, compose_subdir: Path) -> str:
    """POSIX relative path from compose engine dir to media under film root."""
    target = (film_root / media_rel).resolve()
    base = compose_subdir.resolve()
    try:
        return Path(os.path.relpath(target, base)).as_posix()
    except ValueError:
        return target.as_posix()


def resolve_layout(package: dict[str, Any], layout: str) -> str:
    """auto → underlay when final_film exists, else multiclip."""
    layout = (layout or "auto").strip().lower()
    if layout not in {"auto", "multiclip", "underlay"}:
        raise ComposeExportError(f"layout must be auto|multiclip|underlay; got {layout!r}")
    if layout == "auto":
        if package.get("final_film") and package["final_film"].get("path"):
            return "underlay"
        return "multiclip"
    if layout == "underlay" and not (
        package.get("final_film") and package["final_film"].get("path")
    ):
        # graceful fallback
        return "multiclip"
    return layout


def resolve_compose_preset(package: dict[str, Any], preset: str = "auto") -> str:
    """Resolve designed-post visual preset.

    - explicit ``ecchi-rnb`` | ``minimal``
    - ``auto``: rnb/soul/sensual/色气 tone → ecchi-rnb, else minimal
    """
    raw = (preset or "auto").strip().lower().replace("_", "-")
    aliases = {
        "ecchi": "ecchi-rnb",
        "rnb": "ecchi-rnb",
        "soul": "ecchi-rnb",
        "sensual": "ecchi-rnb",
        "seductive": "ecchi-rnb",
        "clean": "minimal",
        "plain": "minimal",
    }
    raw = aliases.get(raw, raw)
    if raw in COMPOSE_PRESET_RESOLVED:
        return raw
    if raw not in {"auto", ""}:
        raise ComposeExportError(
            f"compose_preset must be auto|ecchi-rnb|minimal; got {preset!r}"
        )

    mood = ""
    sp = package.get("sound_plan")
    if isinstance(sp, dict):
        mood = str(sp.get("mood") or "").lower()
    tone = ""
    di = package.get("director_intent")
    if isinstance(di, dict):
        tone = str(di.get("tone") or "").lower()
    blob = f"{mood} {tone}"
    ecchi_tokens = (
        "rnb",
        "soul",
        "sensual",
        "seductive",
        "ecchi",
        "色气",
        "暧昧",
        "里番",
        "诱惑",
        "浪漫",
        "romantic",
    )
    if mood in {"rnb", "soul", "sensual", "seductive"} or any(t in blob for t in ecchi_tokens):
        return "ecchi-rnb"
    return "minimal"


def caption_clock_offset_for(
    *,
    layout: str,
    title_dur: float,
    caption_source: str = "",
) -> float:
    """Map package caption times onto the composition clock.

    - **underlay**: film_final (or SRT from final) shares absolute film clock → **0**.
      Never subtract title pad (would collapse early cues to t=0 and desync VO).
    - **multiclip**: I2V packed from t=0 without black title pad; package cues
      (final.srt / film_tl shot_starts) still include title pad → subtract title_dur.
    """
    if (layout or "").strip().lower() == "underlay":
        return 0.0
    # multiclip always authored against film_timeline with title pad
    _ = caption_source  # reserved for future SRT-without-title variants
    return max(0.0, float(title_dur))


def preset_hf_styles(preset: str, *, width: int) -> dict[str, str]:
    """CSS fragments + motion params for HyperFrames title/captions."""
    title_px = max(36, width // 14)
    end_px = max(28, width // 18)
    cap_px = max(22, width // 22)
    if preset == "ecchi-rnb":
        return {
            "body_bg": "#0a0608",
            "overlay_bg": (
                "linear-gradient(180deg, rgba(40,12,24,0.38), rgba(12,6,10,0.52))"
            ),
            "title_size": str(title_px),
            "end_size": str(end_px),
            "caption_size": str(max(cap_px, 24)),
            "caption_bg": "rgba(28, 10, 18, 0.62)",
            "caption_border": "1px solid rgba(255, 160, 190, 0.28)",
            "caption_shadow": "0 2px 16px rgba(180,40,80,0.35), 0 1px 8px rgba(0,0,0,0.65)",
            "caption_radius": "0.85em",
            "caption_bottom": "11%",
            "caption_pad": "0.55em 1.05em",
            "title_shadow": "0 2px 28px rgba(255,120,160,0.35), 0 2px 18px rgba(0,0,0,0.55)",
            "title_letter": "0.06em",
            "caption_letter": "0.03em",
            "title_y": "40",
            "title_dur_anim": "0.62",
            "cap_y": "16",
            "cap_anim": "0.32",
            "end_label": "完",
        }
    # minimal
    return {
        "body_bg": "#050508",
        "overlay_bg": "linear-gradient(180deg, rgba(0,0,0,0.30), rgba(0,0,0,0.48))",
        "title_size": str(title_px),
        "end_size": str(end_px),
        "caption_size": str(cap_px),
        "caption_bg": "rgba(0, 0, 0, 0.55)",
        "caption_border": "1px solid rgba(255,255,255,0.08)",
        "caption_shadow": "0 1px 10px rgba(0,0,0,0.7)",
        "caption_radius": "0.5em",
        "caption_bottom": "11%",
        "caption_pad": "0.45em 0.85em",
        "title_shadow": "0 2px 18px rgba(0,0,0,0.55)",
        "title_letter": "0.03em",
        "caption_letter": "0.02em",
        "title_y": "28",
        "title_dur_anim": "0.48",
        "cap_y": "12",
        "cap_anim": "0.26",
        "end_label": "完",
    }


def _stage_hf_media(
    hf_dir: Path,
    film_root: Path,
    media_rel: str,
    dest_name: str,
) -> str:
    """Copy media into compose/hyperframes/media/ (HF requires in-project root-relative paths)."""
    import shutil

    media_dir = hf_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    src = (film_root / media_rel).resolve()
    if not src.is_file():
        # fall back to absolute path already stored
        src = Path(media_rel).expanduser()
        if not src.is_file():
            raise ComposeExportError(f"HyperFrames media missing: {media_rel}")
    dest = media_dir / dest_name
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    return f"media/{dest_name}"


def write_hyperframes(
    compose_root: Path,
    package: dict[str, Any],
    film_root: Path,
    *,
    layout: str = "auto",
    compose_preset: str = "auto",
) -> dict[str, str]:
    hf_dir = compose_root / "hyperframes"
    hf_dir.mkdir(parents=True, exist_ok=True)

    width = int(package["width"])
    height = int(package["height"])
    title = str(package["title"])
    film_tl = package["film_timeline"]
    total = float(film_tl.get("output_duration") or 0)
    title_dur = float(film_tl.get("title_duration") or 1.5)
    end_dur = float(film_tl.get("end_duration") or 1.5)
    shots = package["shots"]
    captions = package["captions"]
    resolved_layout = resolve_layout(package, layout)
    resolved_preset = resolve_compose_preset(package, compose_preset)
    styles = preset_hf_styles(resolved_preset, width=width)
    caption_source = str(package.get("caption_source") or "")

    # Media MUST live under the composition project (HyperFrames missing_local_asset)
    video_tags: list[str] = []
    underlay = ""
    staged: list[dict[str, str]] = []
    # underlay: absolute film clock (offset 0); multiclip: subtract title pad
    caption_clock_offset = caption_clock_offset_for(
        layout=resolved_layout,
        title_dur=title_dur,
        caption_source=caption_source,
    )
    if resolved_layout == "underlay" and package.get("final_film") and package["final_film"].get("path"):
        fpath = str(package["final_film"]["path"])
        dest_name = f"underlay{Path(fpath).suffix or '.mp4'}"
        fsrc = _stage_hf_media(hf_dir, film_root, fpath, dest_name)
        staged.append({"from": fpath, "to": fsrc})
        fdur = package["final_film"].get("duration_sec")
        try:
            plate_dur = float(fdur) if fdur is not None else float(total)
        except (TypeError, ValueError):
            plate_dur = float(total)
        # Underlay composition clock MUST match plate duration (not title+shots inflated total).
        # Mismatch causes HF frame coverage failure (expected frames >> extracted frames).
        total = max(plate_dur, 0.1)
        # Plate carries mixed VO/BGM — mark data-has-audio so HF check accepts non-muted video
        # (lint: video_missing_muted). Do NOT also burn captions into plate (subs off).
        underlay = (
            f'    <video id="final-underlay" class="clip" src="{html.escape(fsrc)}" '
            f'playsinline data-has-audio="true" data-start="0" data-duration="{total:.3f}" '
            f'data-track-index="0" style="object-fit:cover;"></video>'
        )
    else:
        # Multiclip: pack I2V from t=0 (no black title pad) so formal motion QA continuity holds.
        # Use integer milliseconds so data-start/duration never float-overlap on same track
        # (HF check fails on 12.084 ending vs 12.083 start from .3f rounding).
        packed: list[tuple[float, float]] = []
        cursor_ms = 0
        for shot in shots:
            dur_ms = max(1, int(round(float(shot["duration_sec"]) * 1000.0)))
            t0 = cursor_ms / 1000.0
            dur = dur_ms / 1000.0
            packed.append((t0, dur))
            cursor_ms += dur_ms
        total = max(cursor_ms / 1000.0, 0.1)
        for i, shot in enumerate(shots):
            t0, dur = packed[i]
            sid = str(shot["id"])
            dest_name = f"{sid}{Path(shot['media_rel']).suffix or '.mp4'}"
            src = _stage_hf_media(hf_dir, film_root, shot["media_rel"], dest_name)
            staged.append({"from": str(shot["media_rel"]), "to": src})
            sid_e = html.escape(sid)
            video_tags.append(
                f'    <video id="clip-{sid_e}" class="clip" src="{html.escape(src)}" '
                f'muted playsinline data-start="{t0:.3f}" data-duration="{dur:.3f}" '
                f'data-track-index="1" style="object-fit:cover;"></video>'
            )

    audio_tags: list[str] = []
    audio = package.get("audio") or {}
    if resolved_layout == "multiclip":
        if audio.get("vo_rel"):
            asrc = _stage_hf_media(
                hf_dir, film_root, audio["vo_rel"], f"vo{Path(audio['vo_rel']).suffix or '.wav'}"
            )
            staged.append({"from": str(audio["vo_rel"]), "to": asrc})
            audio_tags.append(
                f'    <audio id="vo" class="clip" src="{html.escape(asrc)}" '
                f'data-start="0" data-duration="{total:.3f}" data-track-index="3"></audio>'
            )
        if audio.get("bgm_rel"):
            bsrc = _stage_hf_media(
                hf_dir, film_root, audio["bgm_rel"], f"bgm{Path(audio['bgm_rel']).suffix or '.wav'}"
            )
            staged.append({"from": str(audio["bgm_rel"]), "to": bsrc})
            audio_tags.append(
                f'    <audio id="bgm" class="clip" src="{html.escape(bsrc)}" '
                f'data-start="0" data-duration="{total:.3f}" data-track-index="4" '
                f'data-volume="0.45"></audio>'
            )

    # Title / end / captions as overlays ON TOP of motion
    overlay_parts: list[str] = []
    safe_title = html.escape(title)
    title_show = min(title_dur, max(0.4, total * 0.25))
    end_show = min(end_dur, max(0.4, total * 0.2))
    overlay_parts.append(
        f'    <section id="title-card" class="clip overlay" data-start="0" '
        f'data-duration="{title_show:.3f}" data-track-index="2" '
        f'data-preset="{html.escape(resolved_preset)}">'
        f'<div class="card"><h1 id="title-text">{safe_title}</h1></div></section>'
    )
    end_start = max(0.0, total - end_show)
    end_label = html.escape(styles["end_label"])
    overlay_parts.append(
        f'    <section id="end-card" class="clip overlay" data-start="{end_start:.3f}" '
        f'data-duration="{end_show:.3f}" data-track-index="6">'
        f'<div class="card"><p id="end-text">{end_label}</p></div></section>'
    )

    # Captions: own track each; underlay keeps absolute times (offset 0)
    # Dual zh_en → two-line caption stack (zh primary, en secondary)
    caption_cursor = 0.0
    placed_captions = 0
    for i, cue in enumerate(captions):
        cid = f"cap-{i:03d}"
        t0 = max(0.0, float(cue["start"]) - caption_clock_offset)
        t1 = max(t0 + 0.2, float(cue["end"]) - caption_clock_offset)
        if t0 >= total:
            continue
        # de-overlap only when necessary (multiclip offset collisions)
        if t0 < caption_cursor:
            t0 = caption_cursor
        t1 = min(max(t0 + 0.2, t1), total)
        if t0 >= total:
            continue
        dur = max(0.2, t1 - t0)
        caption_cursor = t0 + dur
        track = 10 + i
        kind = str(cue.get("html_kind") or "single")
        if kind == "dual" and cue.get("zh") and cue.get("en"):
            inner = (
                f'<span class="caption-text caption-dual">'
                f'<span class="cap-zh">{html.escape(str(cue["zh"]))}</span>'
                f'<span class="cap-en">{html.escape(str(cue["en"]))}</span>'
                f"</span>"
            )
        else:
            inner = f'<span class="caption-text">{html.escape(str(cue.get("text") or ""))}</span>'
        overlay_parts.append(
            f'    <div id="{cid}" class="clip caption" data-start="{t0:.3f}" '
            f'data-duration="{dur:.3f}" data-track-index="{track}">'
            f"{inner}</div>"
        )
        placed_captions += 1

    cap_y = styles["cap_y"]
    cap_anim = styles["cap_anim"]
    gsap_cap_block = f"""
      document.querySelectorAll(".caption").forEach((el) => {{
        const start = parseFloat(el.getAttribute("data-start") || "0");
        const span = el.querySelector(".caption-text");
        if (span) {{
          tl.from(span, {{ y: {cap_y}, opacity: 0, duration: {cap_anim}, ease: "power2.out" }}, start + 0.04);
        }}
      }});
"""

    index_html = f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={width}, height={height}" />
    <title>{safe_title} — ai-film-grok HyperFrames</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      /* system-ui only: avoids font_family_without_font_face (no @font-face needed) */
      /* preset: {resolved_preset} */
      body {{
        margin: 0;
        background: {styles["body_bg"]};
        color: #fff;
        font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      }}
      #root {{
        position: relative;
        width: {width}px;
        height: {height}px;
        overflow: hidden;
        background: #000;
      }}
      video.clip {{
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        object-fit: cover;
      }}
      .overlay {{
        position: absolute;
        inset: 0;
        display: grid;
        place-items: center;
        pointer-events: none;
        background: {styles["overlay_bg"]};
      }}
      .card h1, .card p {{
        margin: 0;
        font-weight: 700;
        letter-spacing: {styles["title_letter"]};
        text-align: center;
        text-shadow: {styles["title_shadow"]};
      }}
      .card h1 {{
        font-size: {styles["title_size"]}px;
        max-width: 92%;
        white-space: nowrap;
        line-height: 1.15;
      }}
      .card p {{ font-size: {styles["end_size"]}px; opacity: 0.92; }}
      .caption {{
        position: absolute;
        left: 0;
        right: 0;
        /* 9:16 safe zone: above home-indicator / UI chrome */
        bottom: {styles["caption_bottom"]};
        display: flex;
        justify-content: center;
        pointer-events: none;
        padding: 0 7%;
      }}
      .caption-text {{
        display: inline-block;
        max-width: 90%;
        padding: {styles["caption_pad"]};
        border-radius: {styles["caption_radius"]};
        border: {styles["caption_border"]};
        background: {styles["caption_bg"]};
        font-size: {styles["caption_size"]}px;
        line-height: 1.4;
        text-align: center;
        font-weight: 600;
        letter-spacing: {styles["caption_letter"]};
        text-shadow: {styles["caption_shadow"]};
        white-space: pre-line;
      }}
      .caption-dual {{
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 0.18em;
      }}
      .caption-dual .cap-zh {{
        font-size: 1em;
        font-weight: 600;
      }}
      .caption-dual .cap-en {{
        font-size: 0.72em;
        font-weight: 500;
        opacity: 0.88;
        letter-spacing: 0.02em;
      }}
    </style>
  </head>
  <body>
    <div
      id="root"
      data-composition-id="main"
      data-compose-preset="{html.escape(resolved_preset)}"
      data-compose-layout="{html.escape(resolved_layout)}"
      data-caption-clock-offset="{caption_clock_offset:.3f}"
      data-start="0"
      data-width="{width}"
      data-height="{height}"
      data-duration="{total:.3f}"
    >
{underlay}
{chr(10).join(video_tags)}
{chr(10).join(audio_tags)}
{chr(10).join(overlay_parts)}
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      tl.from("#title-text", {{ y: {styles["title_y"]}, opacity: 0, duration: {styles["title_dur_anim"]}, ease: "power3.out" }}, 0.12);
      tl.from("#end-text", {{ y: 24, opacity: 0, duration: 0.45, ease: "power2.out" }}, {end_start + 0.1:.3f});
{gsap_cap_block}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
"""
    # Patch root duration if underlay extended total
    index_html = index_html.replace(
        f'data-duration="{float(film_tl.get("output_duration") or 0):.3f}"',
        f'data-duration="{total:.3f}"',
        1,
    )
    write_text(hf_dir / "index.html", index_html)
    package_out = {
        **package,
        "layout": resolved_layout,
        "compose_preset": resolved_preset,
        "caption_clock_offset": caption_clock_offset,
        "staged_media": staged,
    }
    write_json(hf_dir / "composition-data.json", package_out)
    write_json(
        hf_dir / "media-stage-receipt.json",
        {
            "items": staged,
            "layout": resolved_layout,
            "compose_preset": resolved_preset,
            "caption_clock_offset": caption_clock_offset,
            "captions_placed": placed_captions,
        },
    )
    write_text(
        hf_dir / "README.md",
        f"""# HyperFrames compose package — {title}

Generated by `aifilm export-compose` from an ai-film-grok film root.
**layout:** `{resolved_layout}` · **preset:** `{resolved_preset}` · **caption_clock_offset:** `{caption_clock_offset}`

## Role

- **Shot footage**: already generated by Grok Imagine (I2V) and approved.
- **This package**: designed post — title card, captions, optional VO/BGM stems.
- **Media**: copied into `media/` (HyperFrames requires in-project root-relative paths).
- **One-command render:** `"$AIFILM" compose-render --root <root>` (check + render + audio mux + register final).

## Caption clock

- underlay → offset **0** (share film_final / final.srt absolute time; do not subtract title pad)
- multiclip → offset **title_dur** (I2V packed from t=0)

## Commands

```bash
cd "{hf_dir}"
npx hyperframes check
npx hyperframes preview
# or from film root:
"$AIFILM" compose-render --root "<film-root>" --engine hyperframes --compose-preset {resolved_preset}
"$AIFILM" review-final --root "<film-root>" --approve ...
```

## Load skills

- `/hyperframes` entry → `/hyperframes-core` before editing HTML
- `/hyperframes-animation` for richer motion
- `/media-use` for catalog BGM/SFX/grade (optional; does not replace aifilm VO policy)
""",
    )
    return {
        "dir": str(hf_dir),
        "index": str(hf_dir / "index.html"),
        "data": str(hf_dir / "composition-data.json"),
        "layout": resolved_layout,
        "compose_preset": resolved_preset,
        "caption_clock_offset": caption_clock_offset,
        "media_staged": len(staged),
    }


def write_remotion(compose_root: Path, package: dict[str, Any], film_root: Path) -> dict[str, str]:
    """Write a real Remotion package: media plan, Film.tsx, Root.tsx, package.json.

    Media is wired via media-copy-plan.json → public/clips/. Automated render
    requires npm install (node_modules); otherwise compose-render returns
    actionable bootstrap steps (not silent success).

    Timeline alignment with HyperFrames:
    - underlay: absolute film clock (caption offset 0)
    - multiclip: I2V packed from t=0; captions use caption_clock_offset_for
    """
    rem_dir = compose_root / "remotion"
    public_dir = rem_dir / "public"
    src_dir = rem_dir / "src"
    public_dir.mkdir(parents=True, exist_ok=True)
    src_dir.mkdir(parents=True, exist_ok=True)

    width = int(package["width"])
    height = int(package["height"])
    fps = int(package["fps"])
    title = str(package["title"])
    film_tl = package["film_timeline"]
    title_dur = float(film_tl.get("title_duration") or 1.5)
    end_dur = float(film_tl.get("end_duration") or 1.5)
    resolved_layout = str(package.get("layout") or "multiclip")
    resolved_preset = str(package.get("compose_preset") or "minimal")
    caption_clock_offset = float(
        package.get("caption_clock_offset")
        if package.get("caption_clock_offset") is not None
        else caption_clock_offset_for(
            layout=resolved_layout,
            title_dur=title_dur,
            caption_source=str(package.get("caption_source") or ""),
        )
    )

    # Manifest for agent / compose-render to copy clips into public/clips
    copy_plan: list[dict[str, str]] = []
    for shot in package["shots"]:
        dest = f"clips/{shot['id']}{Path(shot['media_rel']).suffix or '.mp4'}"
        copy_plan.append(
            {
                "shot_id": str(shot["id"]),
                "from_film_rel": str(shot["media_rel"]),
                "to_public": dest,
            }
        )

    # Optional underlay: final film as full-timeline plate
    underlay_public: str | None = None
    if (
        resolved_layout == "underlay"
        and package.get("final_film")
        and isinstance(package["final_film"], dict)
        and package["final_film"].get("path")
    ):
        fpath = str(package["final_film"]["path"])
        underlay_public = f"underlay/{Path(fpath).name}"
        copy_plan.append(
            {
                "shot_id": "_final_underlay",
                "from_film_rel": fpath,
                "to_public": underlay_public,
            }
        )

    # Shot packing: multiclip from t=0 (no black title pad) — matches HF
    shots_payload: list[dict[str, Any]] = []
    cursor_sec = 0.0
    for i, shot in enumerate(package["shots"]):
        dur = max(0.1, float(shot["duration_sec"]))
        if resolved_layout == "underlay":
            # underlay plate carries picture; shot sequences unused for video
            t0 = 0.0
        else:
            t0 = cursor_sec
            cursor_sec += dur
        shots_payload.append(
            {
                "id": shot["id"],
                "fromFrame": int(round(t0 * fps)),
                "durationInFrames": max(1, int(round(dur * fps))),
                "src": copy_plan[i]["to_public"],
                "nar": shot.get("nar") or "",
            }
        )

    if resolved_layout == "underlay":
        total = float(film_tl.get("output_duration") or 1.0)
        if package.get("final_film") and isinstance(package["final_film"], dict):
            fd = package["final_film"].get("duration_sec")
            if isinstance(fd, (int, float)) and float(fd) > 0:
                total = max(total, float(fd))
    else:
        # multiclip: packed I2V + translucent title/end overlays (no black pad)
        total = max(cursor_sec, end_dur + 0.5, 1.0)

    duration_in_frames = max(1, int(round(total * fps)))

    # Captions: apply same clock offset as HyperFrames
    raw_caps = package.get("captions") or []
    shifted: list[dict[str, Any]] = []
    for cue in raw_caps:
        if not isinstance(cue, dict):
            continue
        t0 = max(0.0, float(cue.get("start") or 0.0) - caption_clock_offset)
        t1 = max(t0 + 0.2, float(cue.get("end") or 0.0) - caption_clock_offset)
        shifted.append({"start": t0, "end": t1, "text": cue.get("text") or ""})
    captions = remotion_captions(shifted)
    write_json(public_dir / "captions.json", captions)

    # Preset → caption chrome (parity with HF ecchi-rnb / minimal)
    if resolved_preset == "ecchi-rnb":
        cap_bg = "rgba(28, 10, 18, 0.62)"
        cap_border = "1px solid rgba(255, 160, 190, 0.35)"
        overlay_bg = "linear-gradient(180deg, rgba(40,12,24,0.38), rgba(12,6,10,0.55))"
    else:
        cap_bg = "rgba(0,0,0,0.55)"
        cap_border = "1px solid rgba(255,255,255,0.12)"
        overlay_bg = "linear-gradient(180deg, rgba(0,0,0,0.35), rgba(0,0,0,0.55))"

    remotion_meta = {
        "fps": fps,
        "width": width,
        "height": height,
        "durationInFrames": duration_in_frames,
        "titleDurationSec": title_dur,
        "endDurationSec": end_dur,
        "layout": resolved_layout,
        "composePreset": resolved_preset,
        "captionClockOffset": caption_clock_offset,
        "underlaySrc": underlay_public,
        "shots": shots_payload,
        "mediaCopyPlan": copy_plan,
        "compositionId": "Film",
        "captionStyle": {"background": cap_bg, "border": cap_border},
        "overlayBackground": overlay_bg,
    }
    write_json(
        public_dir / "composition-data.json",
        {
            **{k: v for k, v in package.items() if k != "shots"},
            "shots": package["shots"],
            "remotion": remotion_meta,
        },
    )
    write_json(rem_dir / "media-copy-plan.json", {"items": copy_plan, "film_root": str(film_root)})
    write_json(rem_dir / "composition-data.json", package)

    # --- Real package.json (scaffold deps; install before automated render) ---
    npm_package = {
        "name": "ai-film-grok-remotion",
        "version": "1.0.0",
        "private": True,
        "description": "Designed-post Remotion package from ai-film-grok (titles/captions/overlays — not I2V)",
        "main": "src/index.ts",
        "scripts": {
            "studio": "remotion studio src/index.ts",
            "render": "remotion render src/index.ts Film out/film_remotion.mp4",
            "upgrade": "remotion upgrade",
        },
        "dependencies": {
            "@remotion/cli": "4.0.494",
            "@remotion/captions": "4.0.494",
            "react": "18.3.1",
            "react-dom": "18.3.1",
            "remotion": "4.0.494",
        },
        "devDependencies": {
            "@types/react": "18.3.12",
            "@types/react-dom": "18.3.1",
            "typescript": "5.6.3",
        },
        "ai_film_grok": {
            "kind": "remotion-designed-post",
            "composition_id": "Film",
            "entry": "src/index.ts",
            "layout": resolved_layout,
            "compose_preset": resolved_preset,
            "caption_clock_offset": caption_clock_offset,
            "does_not_replace": ["I2V", "ffmpeg-final", "review-final"],
        },
    }
    write_json(rem_dir / "package.json", npm_package)

    write_json(
        rem_dir / "tsconfig.json",
        {
            "compilerOptions": {
                "target": "ES2022",
                "module": "ES2022",
                "moduleResolution": "bundler",
                "jsx": "react-jsx",
                "strict": True,
                "esModuleInterop": True,
                "skipLibCheck": True,
                "resolveJsonModule": True,
                "noEmit": True,
            },
            "include": ["src"],
        },
    )

    write_text(
        rem_dir / "remotion.config.ts",
        """import { Config } from "@remotion/cli/config";

Config.setEntryPoint("./src/index.ts");
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
""",
    )

    title_js = json.dumps(title)
    composition_tsx = f"""/**
 * ai-film-grok → Remotion designed-post composition
 * Footage = approved Grok I2V (copied into public/ via media-copy-plan).
 * This file only adds title/end cards + captions — not a motion source.
 */
import React from "react";
import {{ AbsoluteFill, OffthreadVideo, Sequence, staticFile, useVideoConfig }} from "remotion";
import type {{ Caption }} from "@remotion/captions";
import compositionData from "../public/composition-data.json";
import captions from "../public/captions.json";

type Shot = {{
  id: string;
  fromFrame: number;
  durationInFrames: number;
  src: string;
  nar: string;
}};

type RemotionMeta = {{
  shots: Shot[];
  underlaySrc?: string | null;
  layout?: string;
}};

const rem = (compositionData as {{ remotion: RemotionMeta }}).remotion;
const shots = rem.shots;
const underlaySrc = rem.underlaySrc || null;
const captionList = captions as Caption[];
const captionBg = {json.dumps(cap_bg)};
const captionBorder = {json.dumps(cap_border)};
const overlayBg = {json.dumps(overlay_bg)};

export const Film: React.FC = () => {{
  const {{ fps, width, height }} = useVideoConfig();
  const titleFrames = Math.max(1, Math.round({title_dur} * fps));
  const endFrames = Math.max(1, Math.round({end_dur} * fps));
  const total = {duration_in_frames};

  return (
    <AbsoluteFill style={{{{ backgroundColor: "#000", fontFamily: "system-ui, sans-serif" }}}}>
      {{underlaySrc ? (
        <AbsoluteFill>
          <OffthreadVideo
            src={{staticFile(underlaySrc)}}
            style={{{{ width, height, objectFit: "cover" }}}}
          />
        </AbsoluteFill>
      ) : (
        shots.map((shot) => (
          <Sequence key={{shot.id}} from={{shot.fromFrame}} durationInFrames={{shot.durationInFrames}}>
            <AbsoluteFill>
              <OffthreadVideo
                src={{staticFile(shot.src)}}
                style={{{{ width, height, objectFit: "cover" }}}}
              />
            </AbsoluteFill>
          </Sequence>
        ))
      )}}

      <Sequence from={{0}} durationInFrames={{titleFrames}}>
        <AbsoluteFill
          style={{{{
            justifyContent: "center",
            alignItems: "center",
            background: overlayBg,
          }}}}
        >
          <h1
            style={{{{
              color: "white",
              fontSize: Math.max(36, width / 14),
              textAlign: "center",
              padding: 24,
            }}}}
          >
            {{{title_js}}}
          </h1>
        </AbsoluteFill>
      </Sequence>

      <Sequence from={{Math.max(0, total - endFrames)}} durationInFrames={{endFrames}}>
        <AbsoluteFill style={{{{ justifyContent: "center", alignItems: "center" }}}}>
          <p style={{{{ color: "white", fontSize: Math.max(28, width / 18) }}}}>完</p>
        </AbsoluteFill>
      </Sequence>

      {{captionList.map((c, i) => {{
        // startMs already clock-shifted at export (caption_clock_offset applied)
        const from = Math.round((c.startMs / 1000) * fps);
        const dur = Math.max(1, Math.round(((c.endMs - c.startMs) / 1000) * fps));
        return (
          <Sequence key={{i}} from={{from}} durationInFrames={{dur}}>
            <AbsoluteFill
              style={{{{
                justifyContent: "flex-end",
                alignItems: "center",
                paddingBottom: "8%",
              }}}}
            >
              <div
                style={{{{
                  maxWidth: "92%",
                  padding: "0.45em 0.85em",
                  borderRadius: 12,
                  background: captionBg,
                  border: captionBorder,
                  color: "white",
                  fontSize: Math.max(22, width / 22),
                  fontWeight: 600,
                  textAlign: "center",
                  whiteSpace: "pre-line",
                  lineHeight: 1.35,
                }}}}
              >
                {{c.text.trim()}}
              </div>
            </AbsoluteFill>
          </Sequence>
        );
      }})}}
    </AbsoluteFill>
  );
}};

export const filmMeta = {{
  id: "Film",
  component: Film,
  durationInFrames: {duration_in_frames},
  fps: {fps},
  width: {width},
  height: {height},
}};
"""
    write_text(src_dir / "Film.tsx", composition_tsx)

    write_text(
        src_dir / "Root.tsx",
        """import React from "react";
import { Composition } from "remotion";
import { Film, filmMeta } from "./Film";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id={filmMeta.id}
      component={Film}
      durationInFrames={filmMeta.durationInFrames}
      fps={filmMeta.fps}
      width={filmMeta.width}
      height={filmMeta.height}
    />
  );
};
""",
    )

    write_text(
        src_dir / "index.ts",
        """import { registerRoot } from "remotion";
import { RemotionRoot } from "./Root";

registerRoot(RemotionRoot);
""",
    )

    film_root_s = json.dumps(str(film_root))
    rem_dir_s = json.dumps(str(rem_dir))
    write_text(
        rem_dir / "README.md",
        f"""# Remotion compose package — {title}

Generated by `aifilm export-compose` from an ai-film-grok film root.

## Role (hard boundary)

- **Shot footage**: Grok Imagine I2V (already approved) — this package does **not** replace I2V.
- **This package**: React timeline + captions + title/end cards (designed post only).
- **Default formal delivery**: `"$AIFILM" final` (FFmpeg). Prefer HyperFrames for one-command designed post.
- **Formal gate**: `review-final` still required; export-compose ≠ delivery.

## One-shot path (preferred for designed post)

```bash
"$AIFILM" final --root {film_root_s} --post-engine hyperframes --tts-backend edge --music-mood rnb
```

## Remotion path (this folder)

```bash
# 1) From film root — copy clips into public/
"$AIFILM" compose-render --root {film_root_s} --engine remotion
#    → if node_modules missing: returns rendered:false + exact next steps (not silent ok)

# 2) Bootstrap deps (once, needs network)
cd {rem_dir_s}
npm install

# 3) Media copy (if step 1 only scaffolded)
"$AIFILM" compose-render --root {film_root_s} --engine remotion
#    → when node_modules present: auto remotion render + register-final (post_engine=remotion)

# 4) Manual render + register (if auto-render unavailable)
npx remotion render Film out/film_remotion.mp4
"$AIFILM" register-final --root {film_root_s} --source out/film_remotion.mp4 --post-engine remotion

# 5) Always
"$AIFILM" review-final --root {film_root_s} --approve ...
```

## Skills to load (agent)

| Task | Skill |
|---|---|
| Project structure / markup | `/remotion-best-practices` → remotion-markup |
| Captions | `/remotion-captions` |
| Render CLI | remotion-render under remotion-best-practices |
| New app bootstrap | remotion-create |
| HyperFrames alternative | `/hyperframes` → `/hyperframes-core` |

## Files

- `src/Film.tsx` — composition (title + I2V sequences + captions)
- `src/Root.tsx` — registers Composition id `Film`
- `src/index.ts` — registerRoot
- `public/captions.json` — @remotion/captions shape
- `public/composition-data.json` — timeline + shot wiring
- `media-copy-plan.json` — film root → public/ copy map
- `package.json` — remotion deps (run `npm install` before auto-render)
""",
    )
    return {
        "dir": str(rem_dir),
        "film_tsx": str(src_dir / "Film.tsx"),
        "root_tsx": str(src_dir / "Root.tsx"),
        "package_json": str(rem_dir / "package.json"),
        "captions": str(public_dir / "captions.json"),
        "copy_plan": str(rem_dir / "media-copy-plan.json"),
        "composition_id": "Film",
        "duration_in_frames": duration_in_frames,
        "layout": resolved_layout,
    }


def export_composition(
    root: Path,
    *,
    engine: str = "both",
    title_dur: float = 1.5,
    end_dur: float = 1.5,
    force: bool = False,
    layout: str = "auto",
    compose_preset: str = "auto",
) -> dict[str, Any]:
    engine = (engine or "both").strip().lower()
    if engine not in ENGINES:
        raise ComposeExportError(f"engine must be one of {ENGINES}; got {engine!r}")

    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ComposeExportError(f"Film root missing: {root}")

    package = build_timeline_package(root, title_dur=title_dur, end_dur=end_dur)
    resolved_layout = resolve_layout(package, layout)
    resolved_preset = resolve_compose_preset(package, compose_preset)
    package["layout"] = resolved_layout
    package["compose_preset"] = resolved_preset
    package["caption_clock_offset"] = caption_clock_offset_for(
        layout=resolved_layout,
        title_dur=title_dur,
        caption_source=str(package.get("caption_source") or ""),
    )

    try:
        compose_root = safe_workspace_directory(root, "compose", field="compose directory")
    except SecurityPolicyError as exc:
        raise ComposeExportError(str(exc)) from exc

    if compose_root.exists() and any(compose_root.iterdir()) and not force:
        # allow overwrite of known children only when force
        raise ComposeExportError(
            f"compose/ already has content: {compose_root} (pass --force to overwrite)"
        )
    compose_root.mkdir(parents=True, exist_ok=True)

    engines_written: dict[str, Any] = {}
    if engine in ("hyperframes", "both"):
        engines_written["hyperframes"] = write_hyperframes(
            compose_root,
            package,
            root,
            layout=resolved_layout,
            compose_preset=resolved_preset,
        )
    if engine in ("remotion", "both"):
        engines_written["remotion"] = write_remotion(compose_root, package, root)

    package_path = compose_root / "package.json"
    # not npm package — composition export manifest (name intentional for discoverability)
    export_manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "ai-film-grok-compose-export",
        "exported_at": package["exported_at"],
        "title": package["title"],
        "engine": engine,
        "engines": engines_written,
        "film_timeline": package["film_timeline"],
        "shot_count": len(package["shots"]),
        "caption_count": len(package["captions"]),
        "caption_source": package["caption_source"],
        "layout": resolved_layout,
        "compose_preset": resolved_preset,
        "post_policy": {
            "default_final": "ffmpeg render_final.py via aifilm final",
            "designed_final": "compose-render (HyperFrames check+render+audio+register)",
            "hyperframes": "designed captions/title/grade/preview — one-command final --post-engine hyperframes",
            "compose_presets": list(COMPOSE_PRESET_RESOLVED),
            "remotion": (
                "React timeline + Root.tsx + package.json; compose-render auto-renders "
                "when node_modules ready, else rendered:false + exact next_steps"
            ),
            "does_not_replace": ["I2V", "pilot gates", "review-final"],
            "formal_gate": "review-final still required for export-desktop",
            "skill_load": {
                "hyperframes": ["/hyperframes", "/hyperframes-core", "/hyperframes-animation"],
                "remotion": [
                    "/remotion-best-practices",
                    "/remotion-captions",
                    "remotion-markup",
                    "remotion-render",
                ],
            },
        },
    }
    write_json(package_path, export_manifest)
    write_json(compose_root / "composition-package.json", package)

    # Record on film manifest (non-gating)
    try:
        manifest = read_json(root / "manifest.json")
        outputs = manifest.setdefault("outputs", {})
        outputs["compose_export"] = {
            "path": "compose/package.json",
            "exported_at": package["exported_at"],
            "engine": engine,
            "layout": resolved_layout,
            "shot_count": len(package["shots"]),
        }
        write_json(root / "manifest.json", manifest)
    except ComposeExportError:
        pass

    return {
        "ok": True,
        "root": str(root),
        "compose_dir": str(compose_root),
        "export_manifest": str(package_path),
        "engine": engine,
        "layout": resolved_layout,
        "compose_preset": resolved_preset,
        "engines": engines_written,
        "shot_count": len(package["shots"]),
        "caption_count": len(package["captions"]),
        "caption_source": package["caption_source"],
        "duration_sec": package["film_timeline"].get("output_duration"),
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Export film root to HyperFrames/Remotion compose packages")
    p.add_argument("--root", required=True)
    p.add_argument("--engine", default="both", choices=list(ENGINES))
    p.add_argument(
        "--layout",
        default="auto",
        choices=["auto", "multiclip", "underlay"],
        help="auto: underlay if film_final exists",
    )
    p.add_argument(
        "--compose-preset",
        default="auto",
        choices=list(COMPOSE_PRESETS),
        help="Visual preset for titles/captions: auto|ecchi-rnb|minimal",
    )
    p.add_argument("--title-dur", type=float, default=1.5)
    p.add_argument("--end-dur", type=float, default=1.5)
    p.add_argument("--force", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = export_composition(
            Path(args.root),
            engine=args.engine,
            title_dur=args.title_dur,
            end_dur=args.end_dur,
            force=args.force,
            layout=args.layout,
            compose_preset=str(getattr(args, "compose_preset", "auto") or "auto"),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ComposeExportError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
