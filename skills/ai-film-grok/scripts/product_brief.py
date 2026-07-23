"""Product brief expansion: turn a product intro into a structured video brief.

This module extends ai-film-grok from pure narrative films to product intro
videos (30-60s launch films, demos, product explainers).  Given a rough
product description, website link, or feature list, it produces a structured
"video packet" that can feed the existing story_plan / write-spec pipeline.

Inspired by the reference-driven-cinematic-video "Product Brief Expansion"
workflow, adapted to ai-film-grok's schema conventions.

The output is a ``product-brief.json`` receipt that an agent reads to
populate film-spec.json with a ``product`` genre and product-specific
scene/shot structure.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from util import write_json


class ProductBriefError(ValueError):
    """The product brief cannot be expanded into a video packet."""


# Brochure phrases that signal low-quality AI-generated copy.  When detected
# in VO text, the vo_lint module flags them.  Here they're used to scrub
# product brief text that would otherwise pollute the video script.
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
)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def detect_brochure_phrases(text: str) -> list[str]:
    """Return list of brochure/AI-buzzword phrases found in *text*."""
    found: list[str] = []
    for phrase in BROCHURE_PHRASES:
        if phrase in text:
            found.append(phrase)
    return found


def expand_product_brief(
    raw_text: str,
    *,
    title: str | None = None,
    target_duration: float = 40.0,
    voice_style: str = "warm",
    language: str = "zh",
) -> dict[str, Any]:
    """Expand a raw product description into a structured video brief packet.

    This is a **deterministic** text-analysis pass — no LLM calls.  It extracts:
      * product name (first non-empty line or first quoted term)
      * audience signals (pain words, familiarity)
      * promise (central one-liner)
      * proof markers (stats, screenshots, demo mentions)
      * objections (doubt markers)
      * missing assets (what the agent must search for or request)
      * brochure-phrase warnings

    The agent then uses this to populate film-spec + story_plan with
    ``genre=product``.
    """
    if not raw_text or not raw_text.strip():
        raise ProductBriefError("product brief text is empty")

    lines = [ln.strip() for ln in raw_text.strip().splitlines() if ln.strip()]

    # Product name heuristic: first short line or first line with colons
    product_name = title or ""
    if not product_name:
        for ln in lines:
            if len(ln) <= 30 and not ln.endswith(("。", ".")):
                product_name = ln
                break
        if not product_name:
            product_name = lines[0][:30]

    # Audience signals
    pain_markers = re.findall(r"(?:痛点|问题|困扰|麻烦|不够|难|痛|烦|卡|慢|复杂|低效)", raw_text)
    familiarity = (
        "unfamiliar"
        if any(w in raw_text for w in ("什么是", "介绍", "什么是", "概念"))
        else "familiar"
    )

    # Promise: first sentence with 是/能/让/帮
    promise = ""
    for ln in lines:
        if re.search(r"(?:是|能|让|帮|提供|带来|实现).{2,}", ln):
            promise = ln
            break
    if not promise:
        promise = lines[0] if lines else ""

    # Proof markers
    proof_markers: list[str] = []
    if re.search(r"\d+(?:\.\d+)?\s*%|\d+\s*倍|\d+\s*x", raw_text):
        proof_markers.append("stats")
    if any(w in raw_text for w in ("截图", "screenshot", "UI", "界面")):
        proof_markers.append("screenshot")
    if any(w in raw_text for w in ("demo", "演示", "试用", "体验")):
        proof_markers.append("demo")
    if any(w in raw_text for w in ("GitHub", "github", "开源", "repo")):
        proof_markers.append("repo")
    if any(w in raw_text for w in ("官网", "网站", "website", "link")):
        proof_markers.append("website")

    # Objections / doubt markers
    objection_markers = re.findall(
        r"(?:真的吗|靠谱吗|真的|值得吗|太贵|复杂|安全|隐私|兼容)", raw_text
    )

    # Missing assets
    missing_assets: list[str] = []
    if "screenshot" not in proof_markers:
        missing_assets.append("product_screenshots")
    if "logo" not in raw_text.lower() and "logo" not in raw_text:
        missing_assets.append("logo")
    if "brand_color" not in raw_text.lower():
        missing_assets.append("brand_colors")
    if voice_style and language == "zh":
        missing_assets.append("voice_sample_optional")

    # Brochure phrases
    brochure_hits = detect_brochure_phrases(raw_text)

    # Scene plan (product 5-beat spine)
    scene_plan = _product_scene_plan(target_duration, proof_markers)

    packet = {
        "schema_version": 1,
        "kind": "product-video-brief",
        "product_name": product_name,
        "target_duration_sec": target_duration,
        "language": language,
        "voice_style": voice_style,
        "audience": {
            "familiarity": familiarity,
            "pain_markers": list(set(pain_markers))[:8],
        },
        "promise": promise[:200],
        "proof_markers": proof_markers,
        "objection_markers": list(set(objection_markers))[:5],
        "missing_assets": missing_assets,
        "brochure_phrase_warnings": brochure_hits,
        "scene_plan": scene_plan,
        "narrative_angle": _suggest_narrative_angle(proof_markers, pain_markers),
        "research_needed": len(proof_markers) < 2 or familiarity == "unfamiliar",
        "created_at": _utc_now(),
        "note": (
            "Deterministic text analysis only. An agent should use web search "
            "to fill missing_assets and verify claims before writing film-spec."
        ),
    }
    return packet


def _product_scene_plan(duration: float, proof: list[str]) -> list[dict[str, Any]]:
    """Generate a 5-beat product scene plan scaled to target duration."""
    # 5 beats: hook / pain / reveal / proof / close
    # proportions: 12% / 18% / 20% / 35% / 15%
    beats = [
        ("hook", 0.12, "第一秒抓住注意力"),
        ("pain", 0.18, "让观众感受到痛点"),
        ("reveal", 0.20, "产品亮相"),
        ("proof", 0.35, "证据/工作流/数据"),
        ("close", 0.15, "收束 + 记忆点"),
    ]
    plan: list[dict[str, Any]] = []
    for i, (purpose, ratio, desc) in enumerate(beats, start=1):
        plan.append(
            {
                "scene": i,
                "purpose": purpose,
                "duration_sec": round(duration * ratio, 1),
                "on_screen_text_hint": "短，视觉化，不是段落"
                if purpose != "proof"
                else "数据/截图",
                "motion_hint": {
                    "hook": "flash/sweep",
                    "pain": "hard_cut",
                    "reveal": "mesh_bend/zoom",
                    "proof": "parallax/card_rail",
                    "close": "match_cut/fade",
                }[purpose],
                "visual_carrier": "product_render" if purpose == "reveal" else "general",
                "description": desc,
            }
        )
    return plan


def _suggest_narrative_angle(proof: list[str], pain: list[str]) -> str:
    if "demo" in proof or "screenshot" in proof:
        return "demo_first"
    if len(pain) >= 3:
        return "problem_solution"
    if "stats" in proof:
        return "before_after"
    return "category_education"


def save_product_brief(root: Path | str, packet: dict[str, Any]) -> Path:
    """Persist the product brief packet to ``<root>/receipts/product-brief.json``."""
    root = Path(root).expanduser().resolve()
    out = root / "receipts" / "product-brief.json"
    write_json(out, packet)
    return out
