"""Caption cue phrase split (export closeout)."""
from __future__ import annotations

from typing import Any

try:
    from final.caption_text import split_units
except Exception:
    try:
        from render_final import split_units
    except Exception:
        split_units = None  # type: ignore
HF_CAPTION_MAX_CHARS = 14
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

