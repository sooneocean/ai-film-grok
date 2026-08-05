#!/usr/bin/env python3
"""Advanced subtitle typesetting for ai-film-grok (Hollywood post-production style)."""

import re
from typing import Any

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
Collisions: Normal
PlayResX: 1080
PlayResY: 1920
Timer: 100.0000

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,65,&H00FFFFFF,&H000000FF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,3.5,1.5,2,30,30,120,1
Style: Italic,Arial,65,&H00FFFFFF,&H000000FF,&H00000000,&H99000000,-1,-1,0,0,100,100,0,0,1,3.5,1.5,2,30,30,120,1
Style: TopDodged,Arial,65,&H00FFFFFF,&H000000FF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,3.5,1.5,8,30,30,200,1
Style: Heroine,Arial,68,&H00F0A0FF,&H000000FF,&H00401060,&H99000000,-1,0,0,0,100,100,0,0,1,3.8,1.8,2,30,30,120,1
Style: MaleLead,Arial,68,&H00D0E0FF,&H000000FF,&H00203040,&H99000000,-1,0,0,0,100,100,0,0,1,3.8,1.8,2,30,30,120,1
Style: Storyteller,Arial,65,&H00FFFFFF,&H000000FF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,3.5,1.5,2,30,30,120,1
Style: ClimaxKinetic,Arial,75,&H0050E0FF,&H000000FF,&H00000088,&H99000000,-1,0,0,0,100,100,0,0,1,4.5,2.0,2,30,30,130,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def format_ass_time(sec: float) -> str:
    """Format seconds to ASS time format H:MM:SS.cs"""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec % 1) * 100))
    # handle rounding up to 100
    if cs == 100:
        s += 1
        cs = 0
        if s == 60:
            m += 1
            s = 0
            if m == 60:
                h += 1
                m = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def break_text_semantically(text: str, max_chars: int = 18) -> list[str]:
    """Break text at natural linguistic boundaries (punctuation, spaces) if too long."""
    if not text or len(text) <= max_chars:
        return [text.strip()]

    # Simple semantic splitting for Chinese/English
    # Prefer to break at commas, periods, etc.
    parts = re.split(r"([，。！？、,!?\s])", text)
    lines = []
    current_line = ""

    for i in range(0, len(parts), 2):
        chunk = parts[i]
        sep = parts[i + 1] if i + 1 < len(parts) else ""
        combined = chunk + sep

        if len(current_line) + len(combined) <= max_chars or not current_line:
            current_line += combined
        else:
            lines.append(current_line.strip())
            current_line = combined

    if current_line:
        lines.append(current_line.strip())

    return [line for line in lines if line]


def resolve_cue_style(cue: dict[str, Any]) -> str:
    """Determine ASS style based on speaker identity and heat phase."""
    if cue.get("heat_phase") in {"climax", "act"} or cue.get("is_climax"):
        return "ClimaxKinetic"
    speaker = str(cue.get("speaker") or cue.get("speaker_id") or cue.get("role") or "").lower()
    if any(h in speaker for h in ("heroine", "female", "fufu", "kei", "astra", "xide")):
        return "Heroine"
    if any(m in speaker for m in ("male", "hero", "guy", "boy", "man")):
        return "MaleLead"
    if cue.get("italic") or cue.get("is_inner_monologue"):
        return "Italic"
    if cue.get("dodge_safe_area") or cue.get("dodge"):
        return "TopDodged"
    if speaker in ("narrator", "storyteller", "vo"):
        return "Storyteller"
    return "Default"


def build_ass_cues(cues: list[dict[str, Any]]) -> str:
    """Compile cues into ASS file content with speaker palettes and kinetic pop-in animations."""
    lines = [ASS_HEADER]

    for cue in cues:
        start_time = format_ass_time(float(cue["start"]))
        end_time = format_ass_time(float(cue["end"]))
        text = str(cue["text"]).strip()

        style = resolve_cue_style(cue)

        # Replace newlines with ASS newline \\N
        text = text.replace("\n", "\\N")

        # Kinetic pop-in animation for exclamations or climax beats
        is_exclamation = (
            any(p in text for p in ("!", "！", "呀", "哈", "嗯"))
            or cue.get("heat_phase") == "climax"
        )
        if is_exclamation or cue.get("kinetic"):
            text = r"{\fscx120\fscy120\t(0,120,\fscx100\fscy100)}" + text

        # Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
        event = f"Dialogue: 0,{start_time},{end_time},{style},,0,0,0,,{text}\n"
        lines.append(event)

    return "".join(lines)
