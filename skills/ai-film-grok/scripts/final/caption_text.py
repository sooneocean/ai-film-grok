"""Caption / subtitle / spoken-text helpers (peeled from render_final · W4).

Public symbols remain re-exported by ``render_final`` for hard-compat tests.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from edit_policy import film_segment_timeline
from film_spec import FilmSpecError, validate_film_spec
from final.errors import RenderError
from narrative_timeline import (
    NarrativeTimelineError,
)
from narrative_timeline import (
    validate_linear_narration as _validate_linear_narration,
)

# Voice / caption defaults (peeled from render_final W4)
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"  # edge 显式后端默认女声
STORYTELLER_VOICE = "zh-CN-XiaoxiaoNeural"
# P0 · 2026-08-04: Chinese-only character dialogue (Japanese retired)
HEROINE_ZH_VOICE = "zh-CN-XiaoyiNeural"
PARTNER_ZH_VOICE = "zh-CN-YunxiNeural"
_NARRATOR_SPEAKERS = frozenset({"storyteller", "narrator", "vo", "旁白", "os", "inner", "内心"})
_HEROINE_SPEAKERS = frozenset(
    {"heroine", "female", "fufu", "girl", "woman", "she", "女主", "沈筱", "astra"}
)
_PARTNER_SPEAKERS = frozenset(
    {"partner", "male_hero", "hero", "male", "boy", "man", "he", "男主", "杨舟"}
)


def split_units(text: str, max_len: int = 12) -> list[str]:
    """Chinese subtitle units: **one short phrase per cue** for 9:16 HF captions.

    Prefer natural clause boundaries (。！？ and ，、) so long storyteller nars
    become readable one-liners — never dump a full 20–30 char shot nar in one card.

    Hard cap: no unit longer than max_len (trailing ，。… may make it max_len+1).
    """
    text = (text or "").strip()
    if not text:
        return []
    text = text.replace("……", "…").replace("...", "…")
    # Normalize multi-dash so we split once after the whole dash run
    text = re.sub(r"[—–-]{2,}", "——", text)
    # Phrase-first: strong end + comma/顿号; keep —— as a single end marker
    # (user: 一句話一個字幕；太長字串要拆開)
    segs = re.split(r"(?<=[。！？!?；;…，,、])|(?<=——)", text)
    units: list[str] = []
    soft_particles = "的了着过吗呢吧啊哦喔与和是在把被给让"

    def flush(buf: str) -> None:
        buf = buf.strip(" \t")
        # keep trailing ，。 for natural reading; strip only spaces
        buf = buf.strip()
        if buf:
            units.append(buf)

    def hard_wrap(part: str) -> None:
        """Wrap long phrase at soft boundaries; never keep a >max_len blob."""
        if len(part) <= max_len:
            flush(part)
            return
        # If only over by a single trailing punct, keep as one card
        if len(part) == max_len + 1 and part[-1] in "，。！？…、,.;!?—":
            flush(part)
            return
        i = 0
        while i < len(part):
            remain = part[i:]
            if len(remain) <= max_len:
                flush(remain)
                break
            if len(remain) == max_len + 1 and remain[-1] in "，。！？…、,.;!?—":
                flush(remain)
                break
            # Search soft cut only inside first max_len chars (not past the hard cap)
            window = remain[:max_len]
            cut = None
            for j, ch in enumerate(window):
                if j < 3:
                    continue
                if ch in "，,、；;…—：:":
                    cut = j + 1
            if cut is None:
                for j in range(len(window) - 1, 2, -1):
                    if window[j] in soft_particles:
                        cut = j + 1
                        break
            if cut is None or cut < 3:
                cut = max_len
            # Avoid 1–2 char tails: leave ≥3 chars for the rest when possible
            rest_len = len(remain) - cut
            if 0 < rest_len < 3 and len(remain) > max_len:
                cut = max(3, min(max_len, len(remain) - 3))
            chunk = remain[:cut]
            # Never emit oversize chunk
            if len(chunk) > max_len:
                chunk = remain[:max_len]
            flush(chunk)
            i += len(chunk)

    for seg in segs:
        seg = seg.strip()
        if not seg:
            continue
        if len(seg) <= max_len:
            flush(seg)
            continue
        # Long clause: split on colon / full-width dash run, then hard wrap
        parts = re.split(r"(?<=[：:])|(?<=——)", seg)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if len(part) <= max_len:
                flush(part)
            else:
                hard_wrap(part)

    # Only merge accidental 1–2 char orphans — never re-glue past max_len
    merged: list[str] = []
    for u in units:
        if (
            merged
            and len(u) <= 2
            and len(merged[-1]) + len(u) <= max_len
            or merged
            and len(merged[-1]) <= 2
            and len(merged[-1]) + len(u) <= max_len
        ):
            merged[-1] = merged[-1] + u
        else:
            merged.append(u)
    # Drop punctuation-only noise (comma / dash crumbs)
    cleaned = [u.strip(" \t") for u in merged if u.strip(" \t，,、—–-…")]
    # Safety net: re-hard-wrap any unit still over max_len (should be rare)
    final: list[str] = []
    for u in cleaned:
        if len(u) <= max_len:
            final.append(u)
        else:
            # allow single trailing punct beyond max_len
            if len(u) == max_len + 1 and u[-1] in "，。！？…、,.;!?——":
                final.append(u)
            else:
                k = 0
                while k < len(u):
                    final.append(u[k : k + max_len])
                    k += max_len
    return final or [text[:max_len]]

def _split_one_soft(u: str) -> tuple[str, str] | None:
    """Split one line near the middle at a soft boundary; None if too short."""
    if len(u) < 8:
        return None
    mid = len(u) // 2
    best = None
    best_score = 10**9
    for i, ch in enumerate(u):
        if i < 3 or i > len(u) - 3:
            continue
        score = abs(i - mid)
        if ch in "，,、；;…—：:":
            score -= 14
        elif ch in "的了着过吗呢吧啊哦喔么":
            score -= 4
        # Avoid splitting compounds like 只准 / 还可以 / 十分
        if i + 1 < len(u) and u[i : i + 2] in (
            "只准",
            "还可",
            "十分",
            "几乎",
            "已经",
            "没有",
            "不在",
            "一点",
        ):
            score += 20
        # Prefer even-ish length halves
        left, right = i + 1, len(u) - (i + 1)
        if min(left, right) < 3:
            score += 6
        if score < best_score:
            best_score = score
            best = i + 1
    if best is None:
        best = mid
    a, b = u[:best].strip(), u[best:].strip()
    if not a or not b or len(a) < 2 or len(b) < 2:
        return None
    return a, b

def _ensure_caption_density(units: list[str], max_len: int = 14) -> list[str]:
    """Only split *long* phrase lines — never force a target cue count.

    Old logic required ceil(vo_dur/max_unit) cues and shredded good phrases
    into 「是罚你眼睛只 / 准看我。」. Timing rebalance already caps line duration.
    """
    units = list(units)
    # Only split lines that are genuinely long for 9:16 (≥ max_len chars)
    guard = 0
    while guard < 8:
        guard += 1
        long_idx = [i for i, u in enumerate(units) if len(u) >= max_len]
        if not long_idx:
            break
        i = max(long_idx, key=lambda k: len(units[k]))
        parts = _split_one_soft(units[i])
        if not parts:
            break
        a, b = parts
        if len(a) < 4 or len(b) < 4:
            break
        units = units[:i] + [a, b] + units[i + 1 :]
    return units

def unit_timings(
    units: list[str],
    vo_dur: float,
    *,
    min_unit: float = 0.45,
    max_unit: float = 1.55,
    gap: float = 0.02,
) -> list[tuple[str, float, float]]:
    """Full-VO continuous captions, char-weighted, hard-capped per line."""
    if not units:
        return []
    vo_dur = max(0.4, float(vo_dur))
    units = _ensure_caption_density(units)
    n = len(units)
    if n == 1:
        return [(units[0], 0.0, vo_dur)]

    weights = [max(1.0, float(len(u))) for u in units]
    total_w = sum(weights)
    usable = max(0.3, vo_dur - gap * (n - 1))
    durs = [usable * w / total_w for w in weights]
    # Cap and rebalance so no line exceeds max_unit
    for _ in range(8):
        over_idx = [i for i, d in enumerate(durs) if d > max_unit + 1e-6]
        if not over_idx:
            break
        pool = sum(durs[i] - max_unit for i in over_idx)
        for i in over_idx:
            durs[i] = max_unit
        under = [i for i, d in enumerate(durs) if d < max_unit - 1e-6]
        if not under:
            break
        share = pool / len(under)
        for i in under:
            durs[i] = min(max_unit, durs[i] + share)
    durs = [max(min_unit, d) for d in durs]
    span = sum(durs) + gap * (n - 1)
    if span > 0:
        scale = vo_dur / span
        durs = [d * scale for d in durs]

    segs: list[tuple[str, float, float]] = []
    t = 0.0
    for i, (u, dur) in enumerate(zip(units, durs, strict=False)):
        start = t
        end = t + dur
        segs.append((u, start, min(vo_dur, end)))
        t = end + gap
    segs[-1] = (segs[-1][0], segs[-1][1], vo_dur)
    return segs

def flatten_shots(spec: dict[str, Any], film_root: Path | None = None) -> list[dict[str, Any]]:
    try:
        return validate_film_spec(spec, assign_missing_ids=False, film_root=film_root)
    except FilmSpecError as exc:
        raise RenderError(str(exc)) from exc

def _shot_speaker_key(shot: dict[str, Any]) -> str:
    raw = shot.get("speaker") or shot.get("role") or ""
    return str(raw).strip().lower()

def is_character_speech_shot(shot: dict[str, Any]) -> bool:
    """True when this plate should use character-dialogue TTS (not pure storyteller).

    Chinese-only product: narrator speaker always wins; character speakers and
    Chinese dialogue/caption fields mark character speech. Legacy ja fields are ignored.
    """
    sp = _shot_speaker_key(shot)
    if sp in _NARRATOR_SPEAKERS:
        return False
    if sp and sp not in _NARRATOR_SPEAKERS:
        return True
    for key in ("dialogue", "dialogue_zh", "spoken_zh", "caption_text"):
        val = shot.get(key)
        if isinstance(val, str) and val.strip() and re.search(r"[\u4e00-\u9fff]", val):
            return True
    return False

def narration_for_shot(shot: dict[str, Any]) -> str:
    """Chinese/default spoken text; never promote shot metadata into narration."""
    for key in ("nar", "narration", "nar_zh", "dialogue", "vo", "caption"):
        val = shot.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""

def _narration_fingerprint(text: str) -> str:
    """Compare VO semantic text without harmless whitespace/punctuation drift."""
    return re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE).casefold()

def _legacy_validate_linear_narration(
    shots: list[dict[str, Any]],
    *,
    vo_mode: str,
    dialogue_spoken_lang: str,
    narration_spoken_lang: str,
) -> None:
    """Fail closed when the timeline would replay a narration beat or metadata."""
    seen: dict[str, str] = {}
    for shot in shots:
        sid = str(shot.get("id") or "<unknown>")
        text = spoken_text_for_shot(
            shot,
            dialogue_spoken_lang=dialogue_spoken_lang,
            narration_spoken_lang=narration_spoken_lang,
            vo_mode=vo_mode,
        )
        if not text:
            raise RenderError(
                f"Shot {sid} has no authored narration/dialogue; metadata is not playable VO"
            )
        fingerprint = _narration_fingerprint(text)
        if fingerprint in seen:
            raise RenderError(
                f"Shot {sid} repeats narration from {seen[fingerprint]}; "
                "write the next causal story beat instead"
            )
        seen[fingerprint] = sid

def validate_linear_narration(
    shots: list[dict[str, Any]],
    *,
    vo_mode: str,
    dialogue_spoken_lang: str,
    narration_spoken_lang: str,
) -> None:
    """Renderer-facing error wrapper around the shared story-timeline guard."""
    try:
        _validate_linear_narration(
            shots,
            vo_mode=vo_mode,
            dialogue_spoken_lang=dialogue_spoken_lang,
            narration_spoken_lang=narration_spoken_lang,
        )
    except NarrativeTimelineError as exc:
        raise RenderError(str(exc)) from exc

def caption_text_for_shot(shot: dict[str, Any], *, caption_lang: str = "zh") -> str:
    """On-screen subtitle text for HyperFrames (sole designed-caption owner). Chinese-only."""
    for key in (
        "caption_text",
        "subtitle_zh",
        "dialogue_zh",
        "spoken_zh",
        "nar",
        "narration",
        "nar_zh",
        "caption",
        "dialogue",
    ):
        val = shot.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for cue in shot.get("audio_cues") or []:
        if not isinstance(cue, dict) or cue.get("kind") != "voice":
            continue
        for key in ("caption_text", "spoken_text"):
            val = cue.get(key)
            if isinstance(val, str) and val.strip() and re.search(r"[\u4e00-\u9fff]", val):
                return val.strip()
    return narration_for_shot(shot)

def spoken_text_for_shot(
    shot: dict[str, Any],
    *,
    dialogue_spoken_lang: str = "zh",
    narration_spoken_lang: str = "zh",
    vo_mode: str = "storyteller",
) -> str:
    """Text fed to TTS. Chinese-only product path (Japanese retired)."""
    dlang = (dialogue_spoken_lang or "zh").strip().lower()
    if dlang in {"ja", "jp", "japanese"}:
        # Soft: ignore ja policy; still speak Chinese if present.
        dlang = "zh"
    character = is_character_speech_shot(shot)
    if character:
        for key in (
            "spoken_zh",
            "dialogue_zh",
            "dialogue",
            "caption_text",
            "nar",
            "spoken_text",
        ):
            val = shot.get(key)
            if isinstance(val, str) and val.strip() and re.search(r"[\u4e00-\u9fff]", val):
                return val.strip()
        for cue in shot.get("audio_cues") or []:
            if (
                isinstance(cue, dict)
                and cue.get("kind") == "voice"
                and str(cue.get("spoken_text") or "").strip()
            ):
                text = str(cue.get("spoken_text")).strip()
                if re.search(r"[\u4e00-\u9fff]", text):
                    return text
    return narration_for_shot(shot)

def build_subtitle_cues_for_shots(
    shot_audio: list[dict[str, Any]],
    *,
    title_duration: float,
    end_duration: float,
    transition_sec: float,
    sub_lead: float = 0.0,
    sub_min: float = 0.48,
    sub_max: float = 1.75,
    story_join_intents: list[str] | None = None,
    default_intent: str = "soft",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Place captions on the xfade timeline (same starts as video/native/VO joins).

    Returns (cues, film_timeline). Using hard-cut t0+=target would lag ~transition_sec
    per join once xfade shortens the picture clock.

    P0 · 2026-07-24: default ``sub_lead=0`` and clamp non-overlapping cues so SRT
    write never fails with ``segment N starts before previous segment ends``.
    """
    film_tl = film_segment_timeline(
        title_duration=title_duration,
        shot_targets=[float(item["target"]) for item in shot_audio],
        end_duration=end_duration,
        transition_sec=transition_sec,
        story_join_intents=story_join_intents,
        default_intent=default_intent,
    )
    cues: list[dict[str, Any]] = []
    shot_starts = list(film_tl["shot_starts"])
    for i, item in enumerate(shot_audio):
        t0 = float(shot_starts[i])
        voice_offset = float(item.get("voice_start_offset_sec") or 0.0)
        # CRITICAL: use raw speech length, NOT padded plate vo_dur.
        # After pad_natural, item["vo_dur"] == plate (silence tail); spreading
        # phrases over that makes late cards appear with no VO (user: 字幕對不上口白).
        speech_dur = float(item.get("raw_vo_dur") or item.get("vo_dur") or item["target"] or 0.0)
        plate = float(item.get("target") or speech_dur or 0.0)
        # never schedule captions into the pad tail (keep ≥0.15s headroom if pad)
        if plate > speech_dur + 0.2:
            speech_dur = min(speech_dur, plate - 0.05)
        speech_dur = max(0.4, speech_dur)
        units = list(item.get("units") or [])
        segs = unit_timings(
            units,
            speech_dur,
            min_unit=sub_min,
            max_unit=sub_max,
            gap=0.03,
        )
        speech_start = t0 + voice_offset
        speech_end = speech_start + speech_dur
        shot_end = t0 + plate - 0.02
        hard_end = min(speech_end, shot_end)
        # Determine italic from voice_type or intent
        is_monologue = False
        nar_item = item.get("narration") or {}
        if isinstance(nar_item, dict) and nar_item.get("voice_type") == "internal_monologue":
            is_monologue = True

        for u, bs, be in segs:
            sb = max(0.0, speech_start + bs - sub_lead)
            eb = speech_start + be
            if eb - sb < sub_min:
                eb = sb + sub_min
            if eb > hard_end:
                eb = hard_end
            if eb <= sb:
                eb = min(hard_end, sb + 0.4)
            cues.append(
                {"start": sb, "end": eb, "text": u, "shot_index": i, "is_monologue": is_monologue}
            )
    # Non-overlap clamp (sub_lead or dense units can otherwise fail SRT validation)
    clamped: list[dict[str, Any]] = []
    prev_end = 0.0
    for cue in cues:
        text = str(cue.get("text") or "").strip()
        if not text:
            continue
        start = float(cue["start"])
        end = float(cue["end"])
        if start < prev_end:
            start = prev_end
        if end <= start:
            end = start + max(0.2, min(sub_min, 0.4))
        clamped.append({**cue, "start": start, "end": end, "text": text})
        prev_end = end
    return clamped, film_tl

def write_srt(path: Path, cues: list[dict[str, Any]], *, preserve_overlaps: bool = False) -> None:
    """Write an SRT sidecar file. Delegates to the shared subtitle_srt module.

    v1.23: extracted to subtitle_srt.write_srt_file so all post-engines
    (ffmpeg / hyperframes / remotion) share one validated SRT generator.
    Kept as a thin wrapper for backward compatibility with internal callers.

    P0 · 2026-07-24: clamp non-overlapping starts before validate (dense units / sub_lead).
    """
    from subtitle_srt import write_srt_file

    if preserve_overlaps:
        from subtitle_srt import write_srt_file

        write_srt_file(path, cues, allow_overlaps=True)
        return
    try:
        from caption_pixel_check import fix_chinese_caption_text
    except Exception:  # pragma: no cover  # noqa: BLE001

        def fix_chinese_caption_text(t: str) -> str:  # type: ignore
            return t

    fixed: list[dict[str, Any]] = []
    prev_end = 0.0
    for cue in cues:
        text = fix_chinese_caption_text(str(cue.get("text") or "").strip())
        if not text:
            continue
        start = float(cue["start"])
        end = float(cue["end"])
        if start < prev_end:
            start = prev_end
        if end <= start:
            end = start + 0.35
        fixed.append({**cue, "start": start, "end": end, "text": text})
        prev_end = end
    write_srt_file(path, fixed)

