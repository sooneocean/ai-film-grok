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
from platform_package import PlatformPackageError, load_platform_package
from security_policy import (
    SecurityPolicyError,
    reject_symlinks,
    safe_existing_file,
    safe_workspace_directory,
)
from show_package import ShowPackageError, resolve_show_package
from transition_ops import (
    TransitionOperationError,
    assert_hyperframes_safe_operations,
    bind_transition_operations_to_timeline,
)
from util import read_json as _util_read_json
from util import utc_now, write_json

SCHEMA_VERSION = 1
ENGINES = ("hyperframes", "remotion", "both")
# Designed-post visual presets (titles/captions only — not I2V)
COMPOSE_PRESETS = ("auto", "ecchi-rnb", "minimal")
COMPOSE_PRESET_RESOLVED = ("ecchi-rnb", "minimal")


class ComposeExportError(RuntimeError):
    """User-facing composition export error."""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        if not text.endswith("\n"):
            handle.write("\n")
        temp = Path(handle.name)
    os.replace(temp, path)


def read_json(path: Path) -> dict[str, Any]:
    """Strict read_json — raises ComposeExportError on missing (unlike util.read_json's None)."""
    data = _util_read_json(path)
    if data is None:
        raise ComposeExportError(f"Missing JSON: {path}")
    return data


def final_delivery_has_burned_subtitles(root: Path) -> bool:
    """Read the plate receipt before allowing a designed-caption underlay export."""
    path = root / "out" / "final-delivery.json"
    if not path.is_file():
        return False
    data = read_json(path)
    subtitles = data.get("subtitles") if isinstance(data.get("subtitles"), dict) else {}
    return subtitles.get("burned_in") is True


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


# HF designed captions: one short phrase per card (matches render_final.split_units)
HF_CAPTION_MAX_CHARS = 12


def expand_cues_phrase_split(
    cues: list[dict[str, Any]],
    *,
    max_chars: int = HF_CAPTION_MAX_CHARS,
    min_cue_sec: float = 0.55,
) -> list[dict[str, Any]]:
    """Re-split long SRT/nar cues into one-phrase cards for HyperFrames readability.

    Timing: char-weighted within each original cue window. Does not change
    total coverage of the parent cue's [start, end].
    """
    try:
        from render_final import split_units
    except Exception:  # pragma: no cover
        split_units = None  # type: ignore

    if not cues:
        return []
    out: list[dict[str, Any]] = []
    for cue in cues:
        start = float(cue.get("start") or 0.0)
        end = float(cue.get("end") or start)
        span = max(0.05, end - start)
        zh = str(cue.get("zh") or cue.get("text") or "").strip()
        en = str(cue.get("en") or "").strip()
        mode = str(cue.get("mode") or "zh")
        # Prefer zh for split; keep en only on first sub-cue when dual
        text_for_split = zh or str(cue.get("text") or "")
        if split_units is None:
            units = [text_for_split] if text_for_split else []
        else:
            units = split_units(text_for_split, max_len=max_chars)
        if not units:
            continue
        # One phrase fits the card: keep original window (no retime)
        # Allow +1 only for a trailing punct so 12+， still counts as one card
        _one = units[0]
        _one_ok = len(units) == 1 and (
            len(_one) <= max_chars
            or (len(_one) == max_chars + 1 and _one[-1] in "，。！？…、,.;!?——")
        )
        if _one_ok:
            lines = format_caption_lines(_one, en if mode == "zh_en" else "", mode=mode)
            out.append(
                {
                    **{k: v for k, v in cue.items() if k not in {"text", "zh", "en", "html_kind"}},
                    "start": start,
                    "end": end,
                    "text": lines["text"],
                    "zh": lines["zh"],
                    "en": lines["en"],
                    "mode": lines["mode"],
                    "html_kind": lines["html_kind"],
                }
            )
            continue
        # Drop units that would be shorter than min if we pack too many into short span
        weights = [max(1.0, float(len(u))) for u in units]
        total_w = sum(weights) or 1.0
        # If span too short for n cues, merge adjacent short units first
        # Never re-glue past max_chars (user: 一句一卡，長串拆開)
        n = len(units)
        if span < min_cue_sec * n and n > 1:
            merged: list[str] = []
            cur = ""
            for u in units:
                if not cur:
                    cur = u
                elif len(cur) + len(u) <= max_chars:
                    cur = cur + u
                else:
                    merged.append(cur)
                    cur = u
            if cur:
                merged.append(cur)
            units = merged or units
            weights = [max(1.0, float(len(u))) for u in units]
            total_w = sum(weights) or 1.0
        t = start
        gap = 0.04
        usable = max(0.2, span - gap * max(0, len(units) - 1))
        for i, (u, w) in enumerate(zip(units, weights, strict=False)):
            dur = usable * (w / total_w)
            dur = max(min_cue_sec * 0.7, dur)
            t1 = t + dur
            if i == len(units) - 1:
                t1 = end
            # en only on first phrase of dual block (avoid repeating EN n times)
            en_i = en if (i == 0 and mode == "zh_en") else ""
            lines = format_caption_lines(u, en_i, mode=mode if en_i else "zh")
            out.append(
                {
                    "start": round(t, 3),
                    "end": round(min(end, t1), 3),
                    "text": lines["text"],
                    "zh": lines["zh"],
                    "en": lines["en"],
                    "mode": lines["mode"],
                    "html_kind": lines["html_kind"],
                    "shot_id": cue.get("shot_id"),
                }
            )
            t = min(end, t1 + gap)
            if t >= end - 0.02:
                break
    return out


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
    try:
        platform_package = load_platform_package(root)
    except PlatformPackageError as exc:
        raise ComposeExportError(f"post-package invalid: {exc}") from exc
    try:
        show_package = resolve_show_package(root, spec)
    except ShowPackageError as exc:
        raise ComposeExportError(f"show-package invalid: {exc}") from exc

    shots = flatten_shots(spec)
    if not shots:
        raise ComposeExportError("film-spec has no shots")

    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    width = int(manifest.get("width") or 720)
    height = int(manifest.get("height") or 1280)
    fps = int(manifest.get("fps") or 30)
    title = str(spec.get("title") or manifest.get("title") or "Untitled")

    try:
        transition_sec = normalize_transition_sec(
            spec.get("transition_sec", DEFAULT_TRANSITION_SEC)
        )
    except PolicyError as exc:
        raise ComposeExportError(str(exc)) from exc

    story_intents: list[str] | None = None
    raw_intents = spec.get("transition_intents")
    if isinstance(raw_intents, list) and raw_intents:
        story_intents = [str(x) for x in raw_intents]
    else:
        beats = [str(s.get("dramatic_function") or "bridge") for s in shots]
        story_intents = [suggest_join_intent(beats[i], beats[i + 1]) for i in range(len(beats) - 1)]

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
    try:
        transition_ops = bind_transition_operations_to_timeline(
            list(spec.get("transition_ops") or []), film_timeline=film_tl
        )
    except TransitionOperationError as exc:
        raise ComposeExportError(f"transition operation timing: {exc}") from exc

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
            # one-phrase cards even when SRT missing (use nar window)
            base = {
                "start": t0,
                "end": t1,
                "text": zh,
                "shot_id": item["id"],
                "zh": zh,
                "en": en,
                "mode": caption_mode,
            }
            cues.extend(
                expand_cues_phrase_split(
                    [base], max_chars=int(platform_package["caption_policy"]["max_chars"])
                )
            )
    else:
        enriched: list[dict[str, Any]] = []
        for i, cue in enumerate(cues):
            zh = str(cue.get("text") or "").strip()
            en = ""
            sid = None
            # Map cue → shot by time overlap when cue count ≠ shot count
            mid = (float(cue["start"]) + float(cue["end"])) / 2.0
            for j, item in enumerate(packaged_shots):
                t0 = float(starts[j]) if j < len(starts) else sum(shot_targets[:j])
                t1 = t0 + float(item["duration_sec"])
                if t0 - 0.05 <= mid <= t1 + 0.05:
                    sid = item["id"]
                    en = str(item.get("nar_en") or "")
                    break
            if sid is None and i < len(packaged_shots):
                sid = packaged_shots[i]["id"]
                en = str(packaged_shots[i].get("nar_en") or "")
            enriched.append(
                {
                    "start": float(cue["start"]),
                    "end": float(cue["end"]),
                    "text": zh,
                    "shot_id": sid,
                    "zh": zh,
                    "en": en,
                    "mode": caption_mode,
                }
            )
        # Always phrase-split for HF: long SRT lines become 一句一卡
        cues = expand_cues_phrase_split(
            enriched, max_chars=int(platform_package["caption_policy"]["max_chars"])
        )
        caption_source = f"{caption_source}+phrase_split"

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
        "transition_ops": transition_ops,
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
        "platform_package": platform_package,
        "show_package": show_package,
        "audio": {
            "vo_rel": str(vo_path.relative_to(root)) if vo_path else None,
            "bgm_rel": str(bgm_path.relative_to(root)) if bgm_path else None,
        },
        "final_film": final_film,
        "director_intent": spec.get("director_intent"),
        "serial": spec.get("serial"),
        "episode_contract": spec.get("episode_contract")
        if isinstance(spec.get("episode_contract"), dict)
        else None,
        "sound_plan": spec.get("sound_plan"),
        "vo_mode": spec.get("vo_mode"),
        "title_sequence": spec.get("title_sequence")
        if isinstance(spec.get("title_sequence"), dict)
        else None,
        "end_roll": spec.get("end_roll") if isinstance(spec.get("end_roll"), dict) else None,
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
    continue_chain = long_form or (visual_fit == "vo" and hard_n >= max(1, soft_n))
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
        raise ComposeExportError(f"compose_preset must be auto|ecchi-rnb|minimal; got {preset!r}")

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
            "overlay_bg": ("linear-gradient(180deg, rgba(40,12,24,0.38), rgba(12,6,10,0.52))"),
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


def caption_theme_styles(theme: str) -> dict[str, str]:
    """Platform-owned caption identities; all values are static and seek-safe."""
    if theme == "platform-drama":
        return {
            "caption_bg": "rgba(7, 10, 18, 0.78)",
            "caption_border": "1px solid rgba(255,255,255,0.76)",
            "caption_shadow": "0 2px 14px rgba(0,0,0,0.82)",
            "caption_radius": "0.72em",
            "caption_pad": "0.50em 0.95em",
            "caption_letter": "0.025em",
        }
    return {}


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


def derive_credits_from_spec(
    spec: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Procedural credits from film-spec director_intent + scenes + manifest clips."""
    di = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
    cast_raw = di.get("cast") if isinstance(di.get("cast"), list) else []
    cast = []
    for c in cast_raw:
        if isinstance(c, dict):
            cast.append(
                {
                    "name": str(c.get("name") or c.get("id") or "Cast"),
                    "role": str(c.get("role") or ""),
                }
            )
        elif isinstance(c, str):
            cast.append({"name": c, "role": ""})
    if not cast:
        title = str(spec.get("title") or "")
        cast.append({"name": title, "role": "Director"})

    crew = [
        {"name": "AI Film Grok", "role": "Pipeline"},
        {"name": str(di.get("tone") or ""), "role": "Tone"},
    ]

    shots = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if isinstance(shot, dict) and shot.get("id"):
                shots.append(
                    {
                        "id": str(shot["id"]),
                        "title": str(shot.get("title") or shot.get("id")),
                    }
                )

    return {"cast": cast, "crew": crew, "shots": shots}


def build_title_sequence_html(
    package: dict[str, Any],
    title_sequence: dict[str, Any],
    preset: str,
    styles: dict[str, str],
    title_dur: float = 1.5,
) -> str | None:
    if not title_sequence:
        return None
    mode = str(title_sequence.get("mode") or "auto").strip().lower()
    if mode == "none":
        return None
    title = html.escape(str(package.get("title") or ""))
    subtitle = html.escape(str(title_sequence.get("subtitle") or ""))
    tagline = html.escape(str(title_sequence.get("tagline") or ""))
    show_motifs = bool(title_sequence.get("show_motifs", True))
    motif_tags = ""
    if show_motifs:
        motifs = []
        for key in (" motifs", "style", "tone"):
            val = str(key).strip()
            if val:
                motifs.append(val)
        if not motifs:
            motifs = ["film"]
        motif_tags = "".join(f'<span class="motif-tag">{html.escape(m)}</span>' for m in motifs[:6])
    parts = [f'<h1 class="ts-title">{title}</h1>']
    if subtitle:
        parts.append(f'<p class="ts-subtitle">{subtitle}</p>')
    if tagline:
        parts.append(f'<p class="ts-tagline">{tagline}</p>')
    if motif_tags:
        parts.append(f'<div class="motif-cloud">{motif_tags}</div>')
    content = "".join(parts)
    return f"""    <section id="title-sequence" class="clip overlay title-sequence" data-start="0" data-duration="{float(title_dur):.3f}" data-track-index="3">
      <div class="ts-backdrop"><div class="ts-content">{content}</div></div>
    </section>"""
    title = str(package.get("title") or "")
    safe_title = html.escape(title)
    subtitle = html.escape(str(title_sequence.get("subtitle") or ""))
    tagline = html.escape(str(title_sequence.get("tagline") or ""))
    show_motifs = bool(title_sequence.get("show_motifs", True))
    di = package.get("director_intent") if isinstance(package.get("director_intent"), dict) else {}
    motifs_raw = di.get("visual_motifs") or []
    motifs: list[str] = []
    if isinstance(motifs_raw, list) and show_motifs:
        for m in motifs_raw:
            s = str(m).strip()
            if s:
                motifs.append(s)

    motif_tags = ""
    if motifs:
        tags = "".join(f'<span class="motif-tag">{html.escape(t)}</span>' for t in motifs[:8])
        motif_tags = f'<div class="motif-cloud">{tags}</div>'

    subtitle_block = ""
    if subtitle:
        subtitle_block = f'<p class="ts-subtitle">{subtitle}</p>'
    if tagline:
        subtitle_block += f'<p class="ts-tagline">{tagline}</p>'

    inner = f"""<h1 class="ts-title">{safe_title}</h1>{subtitle_block}{motif_tags}"""
    return f"""    <section id="title-sequence" class="clip overlay title-sequence" data-start="0" data-duration="{float(title_dur):.3f}" data-track-index="2" data-preset="{html.escape(preset)}">
      <div class="ts-backdrop">
        <div class="ts-content">{inner}</div>
      </div>
    </section>"""


def build_end_roll_html(
    package: dict[str, Any],
    end_roll: dict[str, Any],
    preset: str,
    styles: dict[str, str],
    credits: dict[str, Any],
    *,
    output_duration: float | None = None,
) -> str | None:
    if not end_roll:
        return None
    mode = str(end_roll.get("mode") or "auto").strip().lower()
    if mode == "none":
        return None
    if mode == "cast_only":
        sections = [("Cast", credits.get("cast") or [])]
    elif mode == "full":
        sections = [
            (str(end_roll.get("cast_heading") or "Cast"), credits.get("cast") or []),
            (str(end_roll.get("crew_heading") or "Crew"), credits.get("crew") or []),
        ]
        if end_roll.get("show_shot_list") and credits.get("shots"):
            shot_lines = "".join(
                f'<div class="er-shot"><span class="er-shot-id">{html.escape(str(s.get("id") or ""))}</span>'
                f'<span class="er-shot-title">{html.escape(str(s.get("title") or ""))}</span></div>'
                for s in credits.get("shots") or []
            )
            sections.append(("Shots", [{"name": shot_lines, "role": ""}]))
    else:
        sections = [
            (str(end_roll.get("cast_heading") or "Cast"), credits.get("cast") or []),
            (str(end_roll.get("crew_heading") or "Crew"), credits.get("crew") or []),
        ]
        if end_roll.get("show_shot_list") and credits.get("shots"):
            shot_lines = "".join(
                f'<div class="er-shot"><span class="er-shot-id">{html.escape(str(s.get("id") or ""))}</span>'
                f'<span class="er-shot-title">{html.escape(str(s.get("title") or ""))}</span></div>'
                for s in credits.get("shots") or []
            )
            sections.append(("Shots", [{"name": shot_lines, "role": ""}]))

    scroll_dur = float(end_roll.get("scroll_duration_sec") or 5)
    scroll_dur = max(2.0, min(12.0, scroll_dur))
    available_duration = (
        float(output_duration)
        if output_duration is not None
        else float(package["film_timeline"].get("output_duration") or 0)
    )
    scroll_dur = min(scroll_dur, max(0.0, available_duration))
    if scroll_dur <= 0:
        return None

    section_blocks = []
    for heading, items in sections:
        if not items:
            continue
        lines = "".join(
            f'<div class="er-line"><span class="er-name">{html.escape(str(i.get("name") or ""))}</span>'
            f'<span class="er-role">{html.escape(str(i.get("role") or ""))}</span></div>'
            for i in items
        )
        section_blocks.append(
            f'<div class="er-section"><h3>{html.escape(heading)}</h3>{lines}</div>'
        )

    platform_copy = ""
    next_episode = str(end_roll.get("next_episode") or "").strip()
    cta = str(end_roll.get("cta") or "").strip()
    if next_episode:
        platform_copy += f'<p class="er-next">{html.escape(next_episode)}</p>'
    if cta:
        platform_copy += f'<p class="er-cta">{html.escape(cta)}</p>'
    inner = platform_copy + "".join(section_blocks)
    return f"""    <section id="end-roll" class="clip overlay end-roll" data-start="{max(0.0, available_duration - scroll_dur):.3f}" data-duration="{scroll_dur:.3f}" data-track-index="6">
      <div class="er-track"><div class="er-inner">{inner}</div></div>
    </section>"""


def build_platform_opening_html(
    package: dict[str, Any], show_package: dict[str, Any], *, title_dur: float
) -> str:
    """Build an escaped reusable show opening without changing source media."""
    opening = show_package.get("opening") if isinstance(show_package.get("opening"), dict) else {}
    brand = show_package.get("brand") if isinstance(show_package.get("brand"), dict) else {}
    duration = float(opening.get("duration_sec") or title_dur)
    title = str(opening.get("series_title") or package.get("title") or "")
    episode = str(opening.get("episode") or "")
    label = str(brand.get("label") or "")
    accent = str(brand.get("accent") or "")
    motion_preset = str(brand.get("motion_preset") or "drama-noir")
    return f'''    <section id="platform-opening" class="clip overlay platform-opening" data-start="0.000" data-duration="{duration:.3f}" data-track-index="2" data-show-package="{html.escape(str(show_package.get("id") or ""))}">
      <div class="platform-opening-card" data-show-motion="{html.escape(motion_preset)}" style="--platform-accent:{html.escape(accent)}">
        <p class="platform-brand">{html.escape(label)}</p><h1>{html.escape(title)}</h1><p>{html.escape(episode)}</p>
      </div>
    </section>'''


def build_platform_ending_html(
    package: dict[str, Any], show_package: dict[str, Any], *, end_dur: float
) -> str:
    """Build an escaped reusable show ending positioned against the timeline duration."""
    ending = show_package.get("ending") if isinstance(show_package.get("ending"), dict) else {}
    timeline = (
        package.get("film_timeline") if isinstance(package.get("film_timeline"), dict) else {}
    )
    duration = float(ending.get("duration_sec") or end_dur)
    output_duration = float(timeline.get("output_duration") or duration)
    start = max(0.0, output_duration - duration)
    cta = str(ending.get("cta") or "")
    serial = package.get("serial")
    contract = (
        package.get("episode_contract")
        if (
            (serial is True or (isinstance(serial, dict) and serial.get("enabled") is True))
            and isinstance(package.get("episode_contract"), dict)
        )
        else {}
    )
    hook = str(contract.get("ending_question") or ending.get("next_episode_hook") or "")
    brand = show_package.get("brand") if isinstance(show_package.get("brand"), dict) else {}
    motion_preset = str(brand.get("motion_preset") or "drama-noir")
    return f'''    <section id="platform-ending" class="clip overlay platform-ending" data-start="{start:.3f}" data-duration="{duration:.3f}" data-track-index="6" data-show-package="{html.escape(str(show_package.get("id") or ""))}">
      <div class="platform-ending-card" data-show-motion="{html.escape(motion_preset)}"><p>{html.escape(hook)}</p><p>{html.escape(cta)}</p></div>
    </section>'''


def show_motion_profile(show_package: dict[str, Any] | None) -> dict[str, str | float]:
    """Return one deterministic GSAP motion profile for a validated show package."""
    brand = show_package.get("brand") if isinstance(show_package, dict) else {}
    preset = str((brand or {}).get("motion_preset") or "drama-noir")
    return {
        "drama-noir": {"x": 0, "y": 28, "scale": 0.92, "ease": "power3.out"},
        "romance-glow": {"x": 0, "y": 14, "scale": 0.88, "ease": "back.out(1.25)"},
        "suspense-red": {"x": -22, "y": 0, "scale": 1.06, "ease": "power4.out"},
    }.get(preset, {"x": 0, "y": 28, "scale": 0.92, "ease": "power3.out"})


def build_title_sequence_tsx(
    package: dict[str, Any], title_sequence: dict[str, Any], preset: str
) -> str | None:
    """Remotion title sequence component source.

    Returns None for mode=none / empty (Film.tsx uses its own title card).
    Fancy TSX title sequences deferred — HyperFrames HTML path is primary.
    """
    if not title_sequence:
        return None
    mode = str(title_sequence.get("mode") or "none").strip().lower()
    if mode == "none":
        return None
    # Opt-in fancy title: fall back to Film.tsx simple card until brace-safe generator lands
    return None


def build_end_roll_tsx(end_roll: dict[str, Any], credits: dict[str, Any]) -> str | None:
    """Remotion end-roll component source. See build_title_sequence_tsx."""
    if not end_roll:
        return None
    mode = str(end_roll.get("mode") or "none").strip().lower()
    if mode == "none":
        return None
    return None


def escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def write_hyperframes(
    compose_root: Path,
    package: dict[str, Any],
    film_root: Path,
    *,
    layout: str = "auto",
    compose_preset: str = "auto",
) -> dict[str, str]:
    try:
        assert_hyperframes_safe_operations(package.get("transition_ops") or [])
    except TransitionOperationError as exc:
        raise ComposeExportError(f"HyperFrames transition safety: {exc}") from exc
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
    platform_package = (
        package.get("platform_package") if isinstance(package.get("platform_package"), dict) else {}
    )
    safe_area = (
        platform_package.get("safe_area")
        if isinstance(platform_package.get("safe_area"), dict)
        else {}
    )
    caption_theme = str((platform_package.get("caption_policy") or {}).get("theme") or "default")
    styles = {
        **styles,
        **caption_theme_styles(caption_theme),
        "caption_bottom": f"{int(height * float(safe_area.get('bottom_pct') or 16) / 100)}px",
    }
    caption_source = str(package.get("caption_source") or "")

    # Media MUST live under the composition project (HyperFrames missing_local_asset)
    video_tags: list[str] = []
    underlay = ""
    staged: list[dict[str, str]] = []
    composition_shot_starts: dict[str, float] = {}
    # underlay: absolute film clock (offset 0); multiclip: subtract title pad
    if (
        resolved_layout == "underlay"
        and package.get("final_film")
        and package["final_film"].get("path")
    ):
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
        for index, shot in enumerate(shots):
            starts = film_tl.get("shot_starts") or []
            if index < len(starts):
                composition_shot_starts[str(shot.get("id") or "")] = float(starts[index])
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
            composition_shot_starts[sid] = t0
            dest_name = f"{sid}{Path(shot['media_rel']).suffix or '.mp4'}"
            src = _stage_hf_media(hf_dir, film_root, shot["media_rel"], dest_name)
            staged.append({"from": str(shot["media_rel"]), "to": src})
            sid_e = html.escape(sid)
            video_tags.append(
                f'    <video id="clip-{sid_e}" class="clip" src="{html.escape(src)}" '
                f'muted playsinline data-start="{t0:.3f}" data-duration="{dur:.3f}" '
                f'data-track-index="1" style="object-fit:cover;"></video>'
            )

    # The actual media clock, not the draft timeline, owns all overlay bounds.
    title_show = min(title_dur, max(0.4, total * 0.25))
    end_show = min(end_dur, max(0.4, total * 0.2))
    caption_clock_offset = caption_clock_offset_for(
        layout=resolved_layout,
        title_dur=title_show,
        caption_source=caption_source,
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
    transition_gsap_lines: list[str] = []
    for op_index, operation in enumerate(package.get("transition_ops") or []):
        if not isinstance(operation, dict):
            continue
        picture = operation.get("picture")
        timeline = operation.get("timeline")
        if not isinstance(picture, dict) or not isinstance(timeline, dict):
            continue
        effect = str(picture.get("hyperframes_overlay") or "none")
        if effect == "none":
            continue
        try:
            # Underlay shares the final film clock. Multiclip is packed without
            # title pads or xfade overlaps, so use the actual incoming clip edge.
            target_shot = str(operation.get("to_shot") or "")
            start = composition_shot_starts.get(
                target_shot,
                float(timeline.get("at_sec") or 0.0) - caption_clock_offset,
            )
            duration = float(picture.get("duration_sec") or 0.0)
        except (TypeError, ValueError):
            continue
        start = max(0.0, start)
        duration = min(max(0.0, duration), max(0.0, total - start))
        if duration < 0.04:
            continue
        overlay_id = f"transition-op-{op_index:03d}"
        overlay_parts.append(
            f'    <div id="{overlay_id}" class="clip transition-overlay transition-{html.escape(effect)}" '
            f'data-transition-op="{html.escape(str(operation.get("join_id") or op_index))}" '
            f'data-start="{start:.3f}" data-duration="{duration:.3f}" '
            f'data-track-index="{200 + op_index}"><div class="transition-overlay-inner"></div></div>'
        )
        half = max(0.02, duration / 2)
        transition_gsap_lines.append(
            f'      tl.fromTo("#{overlay_id} .transition-overlay-inner", '
            f"{{ opacity: 0, xPercent: -12 }}, "
            f'{{ opacity: 0.46, xPercent: 12, duration: {half:.3f}, ease: "power2.out" }}, {start:.3f});\n'
            f'      tl.to("#{overlay_id} .transition-overlay-inner", '
            f'{{ opacity: 0, duration: {half:.3f}, ease: "power2.in" }}, {(start + half):.3f});'
        )
    safe_title = html.escape(title)
    credits = package.get("credits") or {}
    title_sequence = package.get("title_sequence") or {}
    end_roll = package.get("end_roll") or {}

    show_package = (
        package.get("show_package") if isinstance(package.get("show_package"), dict) else None
    )
    title_suppressed = str(title_sequence.get("mode") or "").strip().lower() == "none"
    end_suppressed = str(end_roll.get("mode") or "").strip().lower() == "none"
    if show_package and not title_suppressed:
        title_seq_html = build_platform_opening_html(package, show_package, title_dur=title_show)
    else:
        title_seq_html = build_title_sequence_html(
            package, title_sequence, resolved_preset, styles, title_dur=title_show
        )
    if show_package and not end_suppressed:
        end_roll_html = build_platform_ending_html(package, show_package, end_dur=end_show)
    else:
        end_roll_html = build_end_roll_html(
            package, end_roll, resolved_preset, styles, credits, output_duration=total
        )

    title_disabled = bool(show_package) or bool(package.get("_platform_title_disabled"))
    end_disabled = bool(show_package) or bool(package.get("_platform_end_disabled"))
    ending_config = (
        show_package.get("ending")
        if isinstance(show_package, dict) and isinstance(show_package.get("ending"), dict)
        else {}
    )
    platform_ending_duration = float(ending_config.get("duration_sec") or end_show)
    platform_ending_start = max(0.0, total - platform_ending_duration)
    show_motion = show_motion_profile(show_package)
    if title_seq_html:
        overlay_parts.append(title_seq_html)
    elif not title_disabled:
        overlay_parts.append(
            f'    <section id="title-card" class="clip overlay" data-start="0" '
            f'data-duration="{title_show:.3f}" data-track-index="2" '
            f'data-preset="{html.escape(resolved_preset)}">'
            f'<div class="card"><h1 id="title-text">{safe_title}</h1></div></section>'
        )
    end_start = max(0.0, total - end_show)
    if end_roll_html:
        overlay_parts.append(end_roll_html)
    elif not end_disabled:
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
      /* Generic family only: HyperFrames must not inject an unavailable system font. */
      /* preset: {resolved_preset} */
      body {{
        margin: 0;
        background: {styles["body_bg"]};
        color: #fff;
        font-family: sans-serif;
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
      .transition-overlay {{
        position: absolute;
        inset: 0;
        overflow: hidden;
        pointer-events: none;
        z-index: 40;
      }}
      .transition-overlay-inner {{
        position: absolute;
        inset: -12%;
        opacity: 0;
        filter: blur(14px);
      }}
      .transition-directional_blur .transition-overlay-inner {{
        background: linear-gradient(90deg, rgba(214, 229, 255, 0), rgba(214, 229, 255, 0.34), rgba(214, 229, 255, 0));
      }}
      .transition-light_leak .transition-overlay-inner {{
        background: radial-gradient(ellipse at 14% 50%, rgba(255, 202, 126, 0.68), rgba(255, 160, 98, 0.16) 32%, rgba(255, 160, 98, 0) 68%);
      }}
      .transition-color_wash .transition-overlay-inner {{
        background: linear-gradient(115deg, rgba(65, 30, 93, 0.0), rgba(152, 88, 120, 0.38), rgba(255, 215, 169, 0.0));
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
      .platform-opening, .platform-ending {{
        background:
          radial-gradient(circle at 20% 18%, color-mix(in srgb, var(--platform-accent, #f5c2d5) 30%, transparent), transparent 36%),
          linear-gradient(145deg, rgba(5, 8, 18, 0.96), rgba(17, 10, 24, 0.90));
      }}
      .platform-opening-card, .platform-ending-card {{
        box-sizing: border-box;
        width: min(84%, 620px);
        padding: 9% 7%;
        border: 1px solid color-mix(in srgb, var(--platform-accent, #f5c2d5) 68%, white);
        border-radius: 28px;
        background: rgba(8, 10, 20, 0.42);
        box-shadow: 0 22px 70px rgba(0, 0, 0, 0.48);
        text-align: center;
      }}
      .platform-brand {{
        margin: 0 0 0.8em;
        color: var(--platform-accent, #f5c2d5);
        font-size: {max(15, int(width) // 32)}px;
        font-weight: 700;
        letter-spacing: 0.18em;
      }}
      .platform-opening-card h1 {{
        margin: 0;
        font-size: {max(36, int(width) // 11)}px;
        line-height: 1.12;
        letter-spacing: 0.04em;
        text-shadow: 0 3px 20px rgba(0, 0, 0, 0.72);
      }}
      .platform-opening-card > p:last-child {{
        margin: 1.0em 0 0;
        font-size: {max(17, int(width) // 25)}px;
        opacity: 0.82;
      }}
      .platform-ending-card {{
        --platform-accent: {html.escape(str((show_package.get("brand") or {}).get("accent") or "#f5c2d5")) if isinstance(show_package, dict) else "#f5c2d5"};
      }}
      .platform-ending-card p {{
        margin: 0;
        font-size: {max(20, int(width) // 21)}px;
        font-weight: 650;
        line-height: 1.35;
      }}
      .platform-ending-card p + p {{
        margin-top: 0.8em;
        color: var(--platform-accent, #f5c2d5);
        font-size: {max(16, int(width) // 28)}px;
        font-weight: 600;
      }}
      .platform-opening-card[data-show-motion="romance-glow"],
      .platform-ending-card[data-show-motion="romance-glow"] {{
        background: linear-gradient(145deg, rgba(68, 20, 54, 0.56), rgba(11, 10, 25, 0.54));
        border-radius: 38px;
      }}
      .platform-opening-card[data-show-motion="suspense-red"],
      .platform-ending-card[data-show-motion="suspense-red"] {{
        border-left-width: 6px;
        background: linear-gradient(105deg, rgba(80, 8, 16, 0.72), rgba(10, 10, 18, 0.52));
      }}
      .title-sequence {{
        background: transparent;
      }}
      .ts-backdrop {{
        position: absolute;
        inset: 0;
        display: grid;
        place-items: center;
        background: {styles["overlay_bg"]};
        pointer-events: none;
      }}
      .ts-content {{
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 14px;
        padding: 24px;
        text-align: center;
      }}
      .ts-title {{
        margin: 0;
        font-weight: 700;
        letter-spacing: {styles["title_letter"]};
        text-shadow: {styles["title_shadow"]};
        font-size: {styles["title_size"]}px;
        max-width: 92%;
        white-space: nowrap;
        line-height: 1.15;
      }}
      .ts-subtitle {{
        margin: 0;
        font-size: {max(22, int(width) // 22)}px;
        opacity: 0.92;
        text-shadow: 0 1px 10px rgba(0,0,0,0.55);
      }}
      .ts-tagline {{
        margin: 0;
        font-size: {max(16, int(width) // 30)}px;
        opacity: 0.72;
        text-shadow: 0 1px 8px rgba(0,0,0,0.50);
      }}
      .motif-cloud {{
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 8px;
        margin-top: 6px;
      }}
      .motif-tag {{
        padding: 4px 10px;
        border-radius: 999px;
        background: rgba(0,0,0,0.78);
        color: #fff;
        font-size: {max(12, int(width) // 32)}px;
        letter-spacing: 0.03em;
      }}
      .end-roll {{
        background: transparent;
      }}
      .er-track {{
        position: absolute;
        inset: 0;
        overflow: hidden;
        pointer-events: none;
      }}
      .er-inner {{
        padding: 10% 7%;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 18px;
      }}
      .er-next, .er-cta {{
        margin: 0;
        text-align: center;
        text-shadow: 0 1px 10px rgba(0,0,0,0.55);
      }}
      .er-next {{ font-size: {max(20, int(width) // 22)}px; font-weight: 700; }}
      .er-cta {{ font-size: {max(16, int(width) // 28)}px; opacity: 0.86; }}
      .er-section h3 {{
        margin: 0 0 8px;
        font-size: {max(18, int(width) // 24)}px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: rgba(255,255,255,0.80);
      }}
      .er-line {{
        display: flex;
        justify-content: space-between;
        gap: 16px;
        padding: 5px 0;
        width: 100%;
        max-width: 92%;
        border-bottom: 1px solid rgba(255,255,255,0.06);
      }}
      .er-name {{
        color: rgba(255,255,255,0.92);
        font-size: {max(16, int(width) // 28)}px;
      }}
      .er-role {{
        color: rgba(255,255,255,0.56);
        font-size: {max(14, int(width) // 30)}px;
      }}
      .er-shot {{
        display: flex;
        justify-content: space-between;
        gap: 12px;
        padding: 3px 0;
        width: 100%;
        max-width: 92%;
      }}
      .er-shot-id {{
        color: rgba(255,255,255,0.60);
        font-size: {max(12, int(width) // 32)}px;
      }}
      .er-shot-title {{
        color: rgba(255,255,255,0.80);
        font-size: {max(13, int(width) // 30)}px;
      }}
    </style>
  </head>
  <body>
    <div
      id="root"
      data-composition-id="main"
      data-compose-preset="{html.escape(resolved_preset)}"
      data-compose-layout="{html.escape(resolved_layout)}"
      data-platform-package="{html.escape(str(platform_package.get("package_id") or ""))}"
      data-caption-theme="{html.escape(caption_theme)}"
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
      tl.from(".ts-title", {{ y: 36, opacity: 0, duration: 0.70, ease: "power3.out" }}, 0.10);
      tl.from(".ts-subtitle", {{ y: 20, opacity: 0, duration: 0.55, ease: "power2.out" }}, 0.35);
      tl.from(".ts-tagline", {{ y: 14, opacity: 0, duration: 0.45, ease: "power2.out" }}, 0.55);
      tl.from(".motif-tag", {{ scale: 0.6, opacity: 0, duration: 0.38, stagger: 0.06, ease: "back.out(1.4)" }}, 0.70);
      tl.from(".platform-opening-card", {{ scale: {show_motion["scale"]}, x: {show_motion["x"]}, y: {show_motion["y"]}, opacity: 0, duration: 0.62, ease: "{show_motion["ease"]}" }}, 0.10);
      tl.from(".platform-brand", {{ y: 12, opacity: 0, duration: 0.36, ease: "power2.out" }}, 0.28);
      tl.from(".platform-ending-card", {{ scale: {show_motion["scale"]}, x: {show_motion["x"]}, y: {show_motion["y"]}, opacity: 0, duration: 0.52, ease: "{show_motion["ease"]}" }}, {platform_ending_start + 0.08:.3f});
      tl.from("#end-text", {{ y: 24, opacity: 0, duration: 0.45, ease: "power2.out" }}, {end_start + 0.1:.3f});
      tl.from(".er-section", {{ y: 30, opacity: 0, duration: 0.50, stagger: 0.12, ease: "power2.out" }}, {max(0.0, total - end_show) + 0.05:.3f});
      tl.from(".er-line", {{ x: -12, opacity: 0, duration: 0.35, stagger: 0.04, ease: "power2.out" }}, {max(0.0, total - end_show) + 0.20:.3f});
      tl.from(".er-shot", {{ x: 10, opacity: 0, duration: 0.30, stagger: 0.03, ease: "power2.out" }}, {max(0.0, total - end_show) + 0.28:.3f});
{gsap_cap_block}
{chr(10).join(transition_gsap_lines)}
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
            "transition_operations": package.get("transition_ops") or [],
            "transition_overlays_placed": len(transition_gsap_lines),
            "title_sequence": title_seq_html is not None,
            "end_roll": end_roll_html is not None,
            "platform_package": platform_package if platform_package.get("enabled") else None,
            "caption_theme": caption_theme,
            "show_package": show_package,
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
        # A final SRT can carry a trailing cue beyond a packed multiclip timeline.
        # Do not let Remotion render a caption outside its registered composition.
        if t0 >= total:
            continue
        shifted.append({"start": t0, "end": min(t1, total), "text": cue.get("text") or ""})
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
    platform_package = (
        package.get("platform_package") if isinstance(package.get("platform_package"), dict) else {}
    )
    safe_area = (
        platform_package.get("safe_area")
        if isinstance(platform_package.get("safe_area"), dict)
        else {}
    )
    caption_bottom_px = int(height * float(safe_area.get("bottom_pct") or 16.0) / 100)

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
        "captionBottomPx": caption_bottom_px,
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
    title_sequence = package.get("title_sequence") or {}
    end_roll = package.get("end_roll") or {}
    credits = package.get("credits") or {}
    has_title_seq = bool(
        title_sequence
        and any(k in title_sequence for k in ("subtitle", "tagline", "show_motifs", "style"))
    )
    has_end_roll = bool(end_roll and end_roll.get("mode") not in (None, "none"))
    composition_tsx = f"""/**
  * ai-film-grok → Remotion designed-post composition
  * Footage = approved Grok I2V (copied into public/ via media-copy-plan).
  * This file only adds title/end cards + captions — not a motion source.
  */
 import React from "react";
 import {{ AbsoluteFill, Easing, OffthreadVideo, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig }} from "remotion";
 import type {{ Caption }} from "@remotion/captions";
 import compositionData from "../public/composition-data.json";
 import captions from "../public/captions.json";
 {"import TitleSequence from './TitleSequence';" if has_title_seq else ""}
 {"import EndRoll from './EndRoll';" if has_end_roll else ""}

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
 const captionBottomPx = {caption_bottom_px};
 const overlayBg = {json.dumps(overlay_bg)};

 const CaptionCard: React.FC<{{ text: string }}> = ({{ text }}) => {{
   const frame = useCurrentFrame();
   return (
     <AbsoluteFill
       style={{{{
         justifyContent: "flex-end",
         alignItems: "center",
         paddingBottom: captionBottomPx,
         pointerEvents: "none",
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
           opacity: interpolate(frame, [0, 4, 8], [0, 0.88, 1], {{
             extrapolateRight: "clamp",
             easing: Easing.bezier(0.16, 1, 0.3, 1),
           }}),
           translate: `0 ${{interpolate(frame, [0, 8], [18, 0], {{
             extrapolateRight: "clamp",
             easing: Easing.bezier(0.16, 1, 0.3, 1),
           }})}}px`,
         }}}}
       >
         {{text.trim()}}
       </div>
     </AbsoluteFill>
   );
 }};

 export const Film: React.FC = () => {{
   const {{ fps, width, height }} = useVideoConfig();
   const frame = useCurrentFrame();
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

       <AbsoluteFill style={{{{ background: overlayBg, opacity: 0.16, pointerEvents: "none" }}}} />

       {{{str(has_title_seq).lower()} ? (
         <Sequence from={{0}} durationInFrames={{titleFrames}}>
           <TitleSequence />
         </Sequence>
       ) : (
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
               opacity: interpolate(frame, [0, 6, titleFrames], [0, 1, 1], {{
                 extrapolateRight: "clamp",
                 easing: Easing.bezier(0.16, 1, 0.3, 1),
               }}),
               translate: `0 ${{interpolate(frame, [0, 12], [24, 0], {{
                 extrapolateRight: "clamp",
                 easing: Easing.bezier(0.16, 1, 0.3, 1),
               }})}}px`,
             }}}}
             >
               {{{title_js}}}
             </h1>
           </AbsoluteFill>
         </Sequence>
       )}}

       {{{str(has_end_roll).lower()} ? (
         <Sequence from={{Math.max(0, total - endFrames)}} durationInFrames={{endFrames}}>
           <EndRoll />
         </Sequence>
       ) : (
         <Sequence from={{Math.max(0, total - endFrames)}} durationInFrames={{endFrames}}>
           <AbsoluteFill style={{{{ justifyContent: "center", alignItems: "center", background: overlayBg }}}}>
             <p style={{{{
               color: "white",
               fontSize: Math.max(28, width / 18),
               opacity: interpolate(frame - Math.max(0, total - endFrames), [0, 6], [0, 1], {{
                 extrapolateRight: "clamp",
                 easing: Easing.bezier(0.16, 1, 0.3, 1),
               }}),
             }}}}>完</p>
           </AbsoluteFill>
         </Sequence>
       )}}

       {{captionList.map((c, i) => {{
        // startMs already clock-shifted at export (caption_clock_offset applied)
        const from = Math.round((c.startMs / 1000) * fps);
        const dur = Math.max(1, Math.round(((c.endMs - c.startMs) / 1000) * fps));
        return (
          <Sequence key={{i}} from={{from}} durationInFrames={{dur}}>
            <CaptionCard text={{c.text}} />
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

    if has_title_seq:
        tsx_title = build_title_sequence_tsx(package, title_sequence, resolved_preset)
        if tsx_title:
            write_text(src_dir / "TitleSequence.tsx", tsx_title)

    if has_end_roll:
        tsx_end = build_end_roll_tsx(end_roll, credits)
        if tsx_end:
            write_text(src_dir / "EndRoll.tsx", tsx_end)

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
    title_sequence: str | dict[str, Any] | None = None,
    end_roll: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    engine = (engine or "both").strip().lower()
    if engine not in ENGINES:
        raise ComposeExportError(f"engine must be one of {ENGINES}; got {engine!r}")

    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ComposeExportError(f"Film root missing: {root}")

    try:
        platform_package = load_platform_package(root)
    except PlatformPackageError as exc:
        raise ComposeExportError(f"post-package invalid: {exc}") from exc
    if platform_package.get("enabled"):
        timing = platform_package.get("timing") or {}
        title_dur = float(timing["title_duration_sec"])
        end_dur = float(timing["end_duration_sec"])
    package = build_timeline_package(root, title_dur=title_dur, end_dur=end_dur)
    resolved_layout = resolve_layout(package, layout)
    if resolved_layout == "underlay" and final_delivery_has_burned_subtitles(root):
        raise ComposeExportError(
            "underlay double-burn blocked: final-delivery.json says subtitles.burned_in=true; "
            "rerun the plate with subtitles off or use layout=multiclip"
        )
    resolved_preset = resolve_compose_preset(package, compose_preset)
    package["layout"] = resolved_layout
    package["compose_preset"] = resolved_preset
    package["caption_clock_offset"] = caption_clock_offset_for(
        layout=resolved_layout,
        title_dur=title_dur,
        caption_source=str(package.get("caption_source") or ""),
    )
    platform_overrides = package.get("platform_package", {}).get("overrides", {})
    if not isinstance(platform_overrides, dict):
        platform_overrides = {}
    for key in ("title_sequence", "end_roll"):
        value = platform_overrides.get(key)
        if isinstance(value, dict):
            package[key] = value
            if str(value.get("mode") or "").strip().lower() == "none":
                suffix = "title" if key == "title_sequence" else "end"
                package[f"_platform_{suffix}_disabled"] = True

    if isinstance(title_sequence, str) and title_sequence.strip():
        ts = (title_sequence or "auto").strip().lower()
        if ts == "none":
            package["title_sequence"] = {"mode": "none"}
        elif ts == "auto":
            pass
        else:
            package["title_sequence"] = {"mode": ts}
    elif isinstance(title_sequence, dict):
        package["title_sequence"] = title_sequence

    if isinstance(end_roll, str) and end_roll.strip():
        er = (end_roll or "auto").strip().lower()
        if er == "none":
            package["end_roll"] = {"mode": "none"}
        elif er == "auto":
            pass
        else:
            package["end_roll"] = {"mode": er}
    elif isinstance(end_roll, dict):
        package["end_roll"] = end_roll

    if package.get("title_sequence") or package.get("end_roll"):
        spec_for_credits = (
            read_json(root / "film-spec.json") if (root / "film-spec.json").is_file() else {}
        )
        manifest_for_credits = (
            read_json(root / "manifest.json") if (root / "manifest.json").is_file() else {}
        )
        package["credits"] = derive_credits_from_spec(spec_for_credits, manifest_for_credits)

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
        "title_sequence": package.get("title_sequence"),
        "end_roll": package.get("end_roll"),
        "platform_package": package.get("platform_package"),
        "show_package": package.get("show_package"),
        "credits": package.get("credits"),
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
    p = argparse.ArgumentParser(
        description="Export film root to HyperFrames/Remotion compose packages"
    )
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
        help="Visual preset for titles/captions: auto|cinematic|noir|playful|ecchi-rnb|minimal",
    )
    p.add_argument("--title-dur", type=float, default=1.5)
    p.add_argument("--end-dur", type=float, default=1.5)
    p.add_argument(
        "--title-sequence",
        default=None,
        choices=["auto", "none"],
        help="Override film-spec title_sequence mode (auto=spec/default, none=suppress)",
    )
    p.add_argument(
        "--end-roll",
        default=None,
        choices=["auto", "none", "cast_only", "full"],
        help="Override film-spec end_roll mode (auto=spec/default, none=suppress)",
    )
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
            title_sequence=getattr(args, "title_sequence", None),
            end_roll=getattr(args, "end_roll", None),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ComposeExportError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
