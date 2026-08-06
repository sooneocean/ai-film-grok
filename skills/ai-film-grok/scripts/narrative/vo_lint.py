"""VO script lint: detect brochure phrases, AI-buzzword patterns, and PPT-style copy.

Voice is a quality gate, not decoration.  This module inspects the narration
(``nar``) text of each shot and flags phrases that make the VO sound like a
product brochure or AI-generated marketing copy rather than spoken narration.

Inspired by the reference-driven-cinematic-video "Voiceover Gate" rules:
  * avoid "赋能、无缝、革命性、生态闭环、行业领先" etc.
  * prefer 5-8 short spoken sentences over dense brochure paragraphs
  * catch generic AI cadence patterns

This lint is **advisory** (warnings, not hard fails) for narrative films.
For ``genre=product`` it can be elevated to a hard gate via configuration.
"""

from __future__ import annotations

from typing import Any

# Brochure / AI-buzzword phrases that make VO sound like marketing copy.
# When detected, a VO_BROCHURE_PHRASE warning is emitted.
BROCHURE_PHRASES: tuple[str, ...] = (
    "赋能",
    "无缝",
    "革命性",
    "生态闭环",
    "行业领先",
    "不仅是",
    "更是",
    "一站式",
    "全栈",
    "极致",
    "匠心",
    "领航",
    "深耕",
    "擎动",
    "智领",
    "创领",
    "全方位",
    "多维",
    "多维度",
    "深度赋能",
    "降本增效",
    "提质增效",
    "数字化转型",
    "产业升级",
    "核心竞争力",
)

# AI-cadence patterns: overly formal sentence starters that sound robotic.
AI_CADENCE_STARTERS: tuple[str, ...] = (
    "众所周知",
    "综上所述",
    "总而言之",
    "首先",
    "其次",
    "再次",
    "最后",
    "值得一提的是",
    "需要指出的是",
)

# Maximum characters for a single VO sentence before it's flagged as "too long
# for spoken delivery" (rule of thumb: ~25 chars per spoken second).
MAX_SPOKEN_SENTENCE_CHARS = 45


class VoLintWarning:
    """A single advisory warning from VO script lint."""

    __slots__ = ("code", "shot_id", "phrase", "message")

    def __init__(self, code: str, shot_id: str, phrase: str, message: str) -> None:
        self.code = code
        self.shot_id = shot_id
        self.phrase = phrase
        self.message = message

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "shot_id": self.shot_id,
            "phrase": self.phrase,
            "message": self.message,
        }


def _split_sentences(text: str) -> list[str]:
    """Split Chinese/English text into sentences."""
    import re

    parts = re.split(r"[。！？!?\n]+", text)
    return [p.strip() for p in parts if p.strip()]


def lint_nar_text(
    nar: str,
    *,
    shot_id: str = "",
) -> list[VoLintWarning]:
    """Lint a single shot's narration text for brochure/AI patterns.

    Returns a list of advisory :class:`VoLintWarning` objects (may be empty).
    """
    warnings: list[VoLintWarning] = []
    text = (nar or "").strip()
    if not text:
        return warnings

    # 1. Brochure phrase detection
    for phrase in BROCHURE_PHRASES:
        if phrase in text:
            warnings.append(
                VoLintWarning(
                    code="VO_BROCHURE_PHRASE",
                    shot_id=shot_id,
                    phrase=phrase,
                    message=f"shot {shot_id}: nar contains brochure/AI phrase '{phrase}' — rewrite as spoken",
                )
            )

    # 2. AI cadence starter detection
    for starter in AI_CADENCE_STARTERS:
        if text.startswith(starter):
            warnings.append(
                VoLintWarning(
                    code="VO_AI_CADENCE_STARTER",
                    shot_id=shot_id,
                    phrase=starter,
                    message=f"shot {shot_id}: nar starts with formal/AI cadence '{starter}' — use spoken language",
                )
            )
            break  # one starter warning per shot is enough

    # 3. Overly long sentences (not suitable for spoken delivery)
    sentences = _split_sentences(text)
    for sentence in sentences:
        if len(sentence) > MAX_SPOKEN_SENTENCE_CHARS:
            warnings.append(
                VoLintWarning(
                    code="VO_SENTENCE_TOO_LONG",
                    shot_id=shot_id,
                    phrase=sentence[:20] + "…",
                    message=(
                        f"shot {shot_id}: sentence {len(sentence)} chars > {MAX_SPOKEN_SENTENCE_CHARS} "
                        f"— split into shorter spoken phrases"
                    ),
                )
            )
            break  # one per shot

    # 4. Paragraph density: if the whole nar has no sentence breaks and is long,
    #    it's likely a dense paragraph rather than spoken VO.
    if len(sentences) == 1 and len(text) > 60:
        warnings.append(
            VoLintWarning(
                code="VO_PARAGRAPH_NOT_SPOKEN",
                shot_id=shot_id,
                phrase=text[:20] + "…",
                message=(
                    f"shot {shot_id}: nar is a single {len(text)}-char block with no sentence breaks "
                    f"— break into 5-8 short spoken phrases"
                ),
            )
        )

    return warnings


def lint_film_spec_vo(spec: dict[str, Any]) -> dict[str, Any]:
    """Lint all shot nar text in a film-spec.

    Returns a summary dict with warnings grouped by code and a pass/fail flag.
    This is advisory: ``ok=True`` means no warnings, but warnings don't block
    write-spec (unless genre=product elevates to hard gate).
    """
    all_warnings: list[VoLintWarning] = []
    shot_count = 0
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            shot_id = str(shot.get("id") or f"shot_{shot_count}")
            nar = str(shot.get("nar") or "")
            all_warnings.extend(lint_nar_text(nar, shot_id=shot_id))
            shot_count += 1

    # Also lint director_intent.logline if present
    intent = spec.get("director_intent") or {}
    if isinstance(intent, dict):
        logline = str(intent.get("logline") or "")
        all_warnings.extend(lint_nar_text(logline, shot_id="director_intent.logline"))

    by_code: dict[str, list[dict[str, Any]]] = {}
    for w in all_warnings:
        by_code.setdefault(w.code, []).append(w.to_dict())

    return {
        "schema_version": 1,
        "kind": "vo-lint",
        "ok": len(all_warnings) == 0,
        "warning_count": len(all_warnings),
        "shot_count": shot_count,
        "warnings": [w.to_dict() for w in all_warnings],
        "by_code": by_code,
        "codes": sorted(by_code.keys()),
    }
