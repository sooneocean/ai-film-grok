"""Pure export helpers (closeout)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

COMPOSE_PRESET_RESOLVED = ("ecchi-rnb", "minimal")


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


def narration_for_shot(shot: dict[str, Any]) -> str:
    """Return narrator text for a shot dict."""
    for key in ("nar", "narration", "vo", "text"):
        val = shot.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def narration_en_for_shot(shot: dict[str, Any]) -> str:
    """Return English narrator text for a shot dict."""
    for key in ("nar_en", "narration_en", "vo_en", "text_en"):
        val = shot.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _err(msg: str) -> Exception:
    try:
        from export_composition import ComposeExportError as E
    except Exception:
        E = ValueError  # type: ignore
    return E(msg)
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
        raise _err(f"compose_preset must be auto|ecchi-rnb|minimal; got {preset!r}")

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

