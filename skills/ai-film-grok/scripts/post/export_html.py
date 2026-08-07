"""Pure HTML/preset helpers for export_composition (W4 peel)."""

from __future__ import annotations

import html
import math
import os
import struct
import tempfile
import wave
from pathlib import Path
from typing import Any


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
    if motion_preset == "suspense-red":
        return f'''    <section id="platform-opening" class="clip overlay platform-opening platform-cinematic-suspense" data-start="0.000" data-duration="{duration:.3f}" data-track-index="2" data-show-package="{html.escape(str(show_package.get("id") or ""))}">
      <div class="platform-cinematic-vignette" aria-hidden="true"></div>
      <div class="platform-riddle-mark" data-show-phase="impact" aria-hidden="true"><span></span><span></span><span></span></div>
      <div class="platform-opening-card platform-suspense-card" data-show-motion="{html.escape(motion_preset)}" style="--platform-accent:{html.escape(accent)}">
        <p class="platform-brand" data-show-phase="reveal">{html.escape(label)}</p><h1 data-show-phase="reveal">{html.escape(title)}</h1><p class="platform-episode" data-show-phase="reveal">{html.escape(episode)}</p>
      </div>
    </section>'''
    return f'''    <section id="platform-opening" class="clip overlay platform-opening" data-start="0.000" data-duration="{duration:.3f}" data-track-index="2" data-show-package="{html.escape(str(show_package.get("id") or ""))}">
      <div class="platform-opening-card" data-show-motion="{html.escape(motion_preset)}" style="--platform-accent:{html.escape(accent)}">
        <p class="platform-brand">{html.escape(label)}</p><h1>{html.escape(title)}</h1><p>{html.escape(episode)}</p>
      </div>
    </section>'''


def build_platform_ending_html(
    package: dict[str, Any],
    show_package: dict[str, Any],
    *,
    end_dur: float,
    output_duration: float | None = None,
) -> str:
    """Build an escaped reusable show ending positioned against the timeline duration."""
    ending = show_package.get("ending") if isinstance(show_package.get("ending"), dict) else {}
    timeline = (
        package.get("film_timeline") if isinstance(package.get("film_timeline"), dict) else {}
    )
    duration = float(ending.get("duration_sec") or end_dur)
    timeline_duration = float(timeline.get("output_duration") or duration)
    resolved_output_duration = timeline_duration if output_duration is None else output_duration
    start = max(0.0, resolved_output_duration - duration)
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
    if motion_preset == "suspense-red":
        return f'''    <section id="platform-ending" class="clip overlay platform-ending platform-cinematic-suspense" data-start="{start:.3f}" data-duration="{duration:.3f}" data-track-index="6" data-show-package="{html.escape(str(show_package.get("id") or ""))}">
      <div class="platform-ending-hold" data-show-phase="hold" aria-hidden="true"></div>
      <div class="platform-ending-card platform-suspense-card" data-show-motion="{html.escape(motion_preset)}" data-show-phase="hook"><p>{html.escape(hook)}</p><p>{html.escape(cta)}</p></div>
    </section>'''
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


def _write_suspense_sting(path: Path, *, kind: str) -> float:
    """Write a quiet deterministic PCM sting; it never depends on a remote audio provider."""
    duration = 0.46 if kind == "intro" else 0.82
    rate = 48_000
    frames: list[bytes] = []
    for index in range(int(rate * duration)):
        t = index / rate
        if kind == "intro":
            envelope = math.exp(-11.0 * t)
            sample = 0.72 * envelope * math.sin(2.0 * math.pi * (62.0 - 22.0 * t) * t)
            sample += 0.10 * math.exp(-22.0 * t) * math.sin(2.0 * math.pi * 178.0 * t)
        else:
            attack = min(1.0, t / 0.035)
            envelope = attack * math.exp(-4.8 * t)
            sample = 0.58 * envelope * math.sin(2.0 * math.pi * (96.0 - 36.0 * t) * t)
            sample += 0.14 * envelope * math.sin(2.0 * math.pi * 640.0 * t)
        pcm = int(max(-0.94, min(0.94, sample)) * 32767)
        frames.append(struct.pack("<hh", pcm, pcm))
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".wav", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with wave.open(str(temporary), "wb") as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(rate)
            output.writeframes(b"".join(frames))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return duration


def build_suspense_audio_tags(
    hf_dir: Path,
    show_package: dict[str, Any] | None,
    captions: list[dict[str, Any]],
    *,
    total: float,
    ending_start: float,
) -> tuple[list[str], list[dict[str, float | str]]]:
    """Add low-volume stings only where caption timing proves dialogue is clear."""
    brand = show_package.get("brand") if isinstance(show_package, dict) else {}
    if str((brand or {}).get("motion_preset") or "") != "suspense-red":
        return [], []

    media_dir = hf_dir / "media"
    tags: list[str] = []
    cues: list[dict[str, float | str]] = []
    first_caption_start = min((float(cue["start"]) for cue in captions), default=total)
    intro_duration = min(0.46, max(0.0, first_caption_start - 0.04))
    if intro_duration >= 0.20:
        full_duration = _write_suspense_sting(media_dir / "suspense-intro.wav", kind="intro")
        tags.append(
            f'    <audio id="suspense-intro" class="clip" src="media/suspense-intro.wav" '
            f'data-start="0.000" data-duration="{min(intro_duration, full_duration):.3f}" '
            'data-track-index="7" data-volume="0.16"></audio>'
        )
        cues.append(
            {
                "id": "suspense-intro",
                "start_sec": 0.0,
                "duration_sec": min(intro_duration, full_duration),
            }
        )

    last_caption_end = max((float(cue["end"]) for cue in captions), default=0.0)
    outro_start = max(ending_start + 0.50, last_caption_end + 0.05)
    outro_duration = min(0.82, total - outro_start - 0.08)
    if outro_duration >= 0.20:
        full_duration = _write_suspense_sting(media_dir / "suspense-outro.wav", kind="outro")
        tags.append(
            f'    <audio id="suspense-outro" class="clip" src="media/suspense-outro.wav" '
            f'data-start="{outro_start:.3f}" data-duration="{min(outro_duration, full_duration):.3f}" '
            'data-track-index="8" data-volume="0.12"></audio>'
        )
        cues.append(
            {
                "id": "suspense-outro",
                "start_sec": outro_start,
                "duration_sec": min(outro_duration, full_duration),
            }
        )
    return tags, cues
