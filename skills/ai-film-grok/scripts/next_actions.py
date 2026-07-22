#!/usr/bin/env python3
"""Suggest the next production commands from film root state (status / agent routing).

Pipeline stages (product spine — see references/pipeline-methodology.md):

  agent → visual → voice → design → post → deliver → done
"""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from typing import Any

from util import read_json

# Product methodology stages (Grok Agent + layers 1–4 + delivery).
PIPELINE_STAGES: tuple[str, ...] = (
    "agent",
    "visual",
    "voice",
    "design",
    "post",
    "deliver",
    "done",
)

# action id → primary stage (for status.next_actions[].stage)
_ACTION_STAGE: dict[str, str] = {
    "init": "agent",
    "lock-style": "agent",
    "write-spec": "agent",
    "fix-framing": "agent",
    "pilot-report": "agent",
    "pilot-reshoot": "visual",
    "pilot-score": "agent",
    "pilot-approve": "agent",
    "director-notes": "visual",
    "queue-or-register": "visual",
    "pilot-window": "visual",
    "tts-rehearse": "voice",
    "compose-preview": "design",
    "final-designed": "design",
    "compose-render-remotion": "design",
    "final": "post",
    "final-audio": "post",
    "review-final": "post",
    "export-desktop": "deliver",
    "done": "done",
}

_STAGE_LABELS_ZH: dict[str, str] = {
    "agent": "0·Agent 规划（Lens / 定妆 / film-spec / pilot）",
    "visual": "1·视觉生成（Grok still + Seedance/Grok I2V）",
    "voice": "2·语音生成（Edge TTS + tts-rehearse / SRT）",
    "design": "3·设计合成（HyperFrames 优先 / Remotion）",
    "post": "4·后处理验收（FFmpeg plate · review-final）",
    "deliver": "交付导出（export-desktop）",
    "done": "完成",
}


def _preview_ok(root: Path) -> bool:
    try:
        from compose_preview import has_valid_preview_receipt

        return has_valid_preview_receipt(root)
    except Exception:
        rec = read_json(root / "receipts" / "compose-preview.json") or {}
        return bool(
            isinstance(rec, dict)
            and isinstance(rec.get("url"), str)
            and str(rec.get("url")).startswith("http")
            and rec.get("ok") is not False
        )


def _tts_rehearse_ok(root: Path) -> bool:
    rehearse = read_json(root / "receipts" / "tts-rehearsal.json") or {}
    return bool(
        isinstance(rehearse, dict)
        and rehearse.get("ok") is True
        and (rehearse.get("shots") or rehearse.get("shot_count"))
    )


def _final_record(root: Path) -> dict[str, Any] | None:
    man = read_json(root / "manifest.json") or {}
    outputs = man.get("outputs") if isinstance(man.get("outputs"), dict) else {}
    rec = outputs.get("final_film")
    return rec if isinstance(rec, dict) and rec else None


def _pilot_user_ok(root: Path) -> bool:
    pilot_approval = read_json(root / "receipts" / "pilot-approval.json") or {}
    try:
        from production_gates import pilot_is_user_approved

        return pilot_is_user_approved(pilot_approval)
    except Exception:
        return False


def detect_pipeline_stage(
    root: Path,
    *,
    gates: dict[str, Any] | None = None,
    open_reshoot_count: int = 0,
) -> dict[str, Any]:
    """Classify film-root into product pipeline stage (agent → … → done).

    Returns a stable dict for `aifilm status` / `aifilm next` so agents can say
    「当前在第几层」 without re-deriving from raw gates.
    """
    root = Path(root).expanduser().resolve()
    gates = gates or {}
    has_brief = (root / "brief.json").is_file() or bool(gates.get("brief"))
    style_ok = bool(gates.get("style_locked"))
    spec_ok = bool(gates.get("spec"))
    clips_ok = bool(gates.get("clips_complete"))
    final_ok = bool(gates.get("final_complete"))
    export_ok = bool(gates.get("desktop_exported"))
    pilot_ok = _pilot_user_ok(root)
    final_rec = _final_record(root)
    rehearse_ok = _tts_rehearse_ok(root)
    preview_ok = _preview_ok(root)

    blockers: list[str] = []
    stage = "agent"
    detail = "init"

    if not has_brief:
        stage, detail = "agent", "init"
        blockers.append("brief_missing")
    elif not style_ok:
        stage, detail = "agent", "lock-style"
        blockers.append("style_not_locked")
    elif not spec_ok:
        stage, detail = "agent", "write-spec"
        blockers.append("spec_invalid")
    elif not pilot_ok and not clips_ok:
        stage, detail = "agent", "pilot"
        blockers.append("pilot_not_user_approved")
    elif open_reshoot_count > 0 and not final_ok:
        stage, detail = "visual", "reshoot"
        blockers.append(f"open_reshoots:{open_reshoot_count}")
    elif not clips_ok:
        stage, detail = "visual", "bulk-i2v"
        blockers.append("clips_incomplete")
    elif final_ok and export_ok:
        stage, detail = "done", "complete"
    elif final_ok and not export_ok:
        stage, detail = "deliver", "export-desktop"
        blockers.append("desktop_not_exported")
    elif final_rec and not final_ok:
        stage, detail = "post", "review-final"
        blockers.append("final_not_approved")
    elif not rehearse_ok:
        stage, detail = "voice", "tts-rehearse"
        blockers.append("tts_rehearsal_missing")
    elif not preview_ok:
        stage, detail = "design", "compose-preview"
        blockers.append("compose_preview_missing")
    else:
        stage, detail = "design", "final-hyperframes"
        blockers.append("designed_final_pending")

    # Progress checklist for HUD / status
    checklist = {
        "agent": bool(has_brief and style_ok and spec_ok and (pilot_ok or clips_ok)),
        "visual": clips_ok,
        "voice": bool(rehearse_ok or final_rec or final_ok),
        "design": bool(
            final_ok
            or (
                final_rec and str(final_rec.get("post_engine") or "") in {"hyperframes", "remotion"}
            )
            or preview_ok
        ),
        "post": bool(final_rec or final_ok),
        "deliver": export_ok,
    }

    stage_index = PIPELINE_STAGES.index(stage) if stage in PIPELINE_STAGES else 0
    craft: dict[str, Any] = {}
    try:
        from craft_spine import detect_craft_stage, format_craft_line

        craft = detect_craft_stage(
            root,
            gates={
                "brief": has_brief,
                "style_locked": style_ok,
                "spec": spec_ok,
                "clips_complete": clips_ok,
                "final_complete": final_ok,
                "desktop_exported": export_ok,
            },
        )
        craft_line = format_craft_line(craft, compact=True)
    except Exception:
        craft = {}
        craft_line = ""

    return {
        "stage": stage,
        "stage_index": stage_index,
        "stage_total": len(PIPELINE_STAGES),
        "label_zh": _STAGE_LABELS_ZH.get(stage, stage),
        "detail": detail,
        "blockers": blockers,
        "checklist": checklist,
        "flags": {
            "brief": has_brief,
            "style_locked": style_ok,
            "spec": spec_ok,
            "pilot_user_approved": pilot_ok,
            "clips_complete": clips_ok,
            "tts_rehearsal": rehearse_ok,
            "compose_preview": preview_ok,
            "final_film": bool(final_rec),
            "final_complete": final_ok,
            "desktop_exported": export_ok,
            "open_reshoot_count": int(open_reshoot_count or 0),
            "post_engine": (final_rec or {}).get("post_engine"),
        },
        "spine": "agent → 1.visual → 2.voice → 3.design → 4.post → deliver",
        "craft_stage": craft.get("craft_stage"),
        "craft": craft,
        "craft_line": craft_line,
        "craft_spine": "idea → story → beats → shots → media → selects → rough → verified",
        "ref": "references/pipeline-methodology.md · references/craft-spine.md",
    }


def build_next_actions(
    root: Path,
    *,
    gates: dict[str, Any] | None = None,
    open_reshoot_count: int = 0,
) -> list[dict[str, str]]:
    """Return ordered actionable steps: [{id, cmd, why, stage}, ...]. Max ~8 items."""
    root = Path(root).expanduser().resolve()
    gates = gates or {}
    actions: list[dict[str, str]] = []

    def add(aid: str, cmd: str, why: str) -> None:
        stage = _ACTION_STAGE.get(aid, "agent")
        label = _STAGE_LABELS_ZH.get(stage, stage)
        # Keep why short; stage is a separate field for agents/UI.
        actions.append({"id": aid, "cmd": cmd, "why": why, "stage": stage, "stage_label": label})

    r = str(root)

    if not (root / "brief.json").is_file() and not gates.get("brief"):
        add(
            "init",
            f'aifilm init --theme "…" --title "…" --root "{r}" --aspect 9:16',
            "项目未初始化",
        )
        return actions

    if not gates.get("style_locked"):
        add(
            "lock-style",
            f'aifilm lock-style --root "{r}" --canonical "…" --cast-master "…" --signature "…"',
            "画风/定妆未锁定",
        )

    if not gates.get("spec"):
        add("write-spec", f'aifilm write-spec --root "{r}"', "film-spec 未通过校验")

    # Framing crop risk after write-spec (soft routing)
    spec = read_json(root / "film-spec.json") or {}
    framing = spec.get("_framing_lint") if isinstance(spec.get("_framing_lint"), dict) else {}
    if framing and framing.get("ok") is False:
        codes = ",".join(str(c) for c in (framing.get("codes") or [])[:4])
        add(
            "fix-framing",
            f'aifilm write-spec --root "{r}"  # framing_lint: {codes or "crop risk"}',
            "构图裁头风险：改 framing/motion 去 ECU/fill-frame 后重 write-spec",
        )

    # Pilot path (before bulk clips)
    pilot_approval = read_json(root / "receipts" / "pilot-approval.json") or {}
    pilot_score = read_json(root / "receipts" / "pilot-scorecard.json") or {}
    try:
        from production_gates import pilot_is_user_approved

        pilot_ok = pilot_is_user_approved(pilot_approval)
    except Exception:
        pilot_ok = False

    score_ok = (
        isinstance(pilot_score, dict)
        and pilot_score.get("kind") == "pilot-scorecard"
        and pilot_score.get("all_pass") is True
    )

    if not pilot_ok:
        add("pilot-report", f'aifilm pilot report --root "{r}"', "查看 pilot 三镜素材与评分状态")
        if not score_ok:
            if pilot_score.get("failures"):
                fails = ",".join(str(x) for x in (pilot_score.get("failures") or []))
                add(
                    "pilot-reshoot",
                    f'aifilm pilot report --root "{r}"  # score failed: {fails}',
                    "pilot scorecard 未过，先修 still/I2V 再 pilot score",
                )
            else:
                add(
                    "pilot-score",
                    f'aifilm pilot score --root "{r}" --shots <id,id,id> '
                    "--score-identity pass --score-style pass --score-motion pass "
                    '--reviewer <you> --notes "…"',
                    "三镜看完后写 pilot scorecard",
                )
        else:
            add(
                "pilot-approve",
                f'aifilm pilot approve --root "{r}" --user-phrase "pilot 过"',
                "score 已过，等用户原话批准后再批量",
            )

    if open_reshoot_count > 0:
        add(
            "director-notes",
            f'aifilm director-notes list --root "{r}"',
            f"仍有 {open_reshoot_count} 条开放重拍",
        )

    if not gates.get("clips_complete"):
        if pilot_ok or not gates.get("spec"):
            add(
                "queue-or-register",
                f'media-queue add --root "{r}" --shot-id <id> --operation image_to_video … '
                f'&& aifilm register-clip --root "{r}" …',
                "镜头未齐：队列生成 + register-clip",
            )
        else:
            add(
                "pilot-window",
                f'media-queue add --root "{r}" …  # 无 pilot 批准时最多 3 个不同 shot_id',
                "仍在 pilot 窗口，勿批量第 4 镜",
            )

    if gates.get("clips_complete") and not gates.get("final_complete"):
        final_rec = _final_record(root)
        preview_ok = _preview_ok(root)
        rehearse_ok = _tts_rehearse_ok(root)
        require_reh = bool(spec.get("tts_rehearsal_required") is True) if spec else False
        if not final_rec and not rehearse_ok:
            add(
                "tts-rehearse",
                f'aifilm tts-rehearse --root "{r}" --backend edge',
                (
                    "[层2·语音] final 前真测旁白秒数（receipts/tts-rehearsal.json）；"
                    + (
                        "film-spec 要求 tts_rehearsal_required"
                        if require_reh
                        else "有回执则 measured 优先于估时"
                    )
                ),
            )
        if not final_rec:
            if not preview_ok:
                # Designed-post first: preview writes receipts/compose-preview.json
                add(
                    "compose-preview",
                    f'aifilm compose-preview --root "{r}"',
                    "[层3·设计] clips 齐了 → 先 Studio 预览设计字幕/片头（写 receipts/compose-preview.json）",
                )
                add(
                    "final",
                    f'aifilm final --root "{r}" --lipsync off --music-mood rnb --tts-backend edge',
                    "[层4·后处理] 或直接 FFmpeg 成片；设计字幕：--post-engine hyperframes（建议先 preview）",
                )
                add(
                    "final-designed",
                    f'aifilm final --root "{r}" --post-engine hyperframes '
                    f"--lipsync off --music-mood rnb --tts-backend edge --compose-preset auto "
                    f"--title-sequence auto --end-roll auto",
                    "[层3·设计] 跳过预览一键设计成片（排版风险更高；可用 --require-preview 强制先预览）",
                )
            else:
                add(
                    "final-designed",
                    f'aifilm final --root "{r}" --post-engine hyperframes '
                    f"--lipsync off --music-mood rnb --tts-backend edge --compose-preset auto "
                    f"--title-sequence auto --end-roll auto",
                    "[层3·设计] 已 compose-preview → 推荐 HyperFrames 设计字幕成片",
                )
                rem_pkg = root / "compose" / "remotion" / "package.json"
                if rem_pkg.is_file():
                    add(
                        "compose-render-remotion",
                        f'aifilm compose-render --root "{r}" --engine remotion --npm-install '
                        f"--title-sequence auto --end-roll auto",
                        "[层3·设计] Remotion 包已导出 → compose-render（首次 --npm-install）",
                    )
                add(
                    "final",
                    f'aifilm final --root "{r}" --lipsync off --music-mood rnb --tts-backend edge',
                    "[层4·后处理] 或 FFmpeg 烧字幕成片",
                )
        else:
            add(
                "review-final",
                f'aifilm review-final --root "{r}" --approve --reviewer <you> --notes "已完整观看…" '
                "--score-identity pass --score-style pass --score-motion pass "
                "--score-escalation pass --score-audio pass --score-subs pass --score-dead-air pass",
                "[层4·后处理] 成片已渲，待七维 scorecard 审批",
            )

    # Evidence: sound_plan intent without mix/final when clips ready
    if gates.get("clips_complete") and not gates.get("final_complete"):
        try:
            from evidence_status import classify_evidence

            evidence = classify_evidence(root)
            risks = evidence.get("impersonation_risks") or []
            risk_codes = {str(x.get("code")) for x in risks if isinstance(x, dict)}
            if "SOUND_PLAN_NOT_EXECUTED" in risk_codes and not any(
                a.get("id") in {"final", "final-designed", "final-audio"} for a in actions
            ):
                add(
                    "final-audio",
                    f'aifilm final --root "{r}" --lipsync off --music-mood rnb --tts-backend edge',
                    "sound_plan 仍是 intent — 需 final/混音才算 executed",
                )
        except Exception:
            pass

    if gates.get("final_complete") and not gates.get("desktop_exported"):
        add(
            "export-desktop",
            f'aifilm export-desktop --root "{r}" --name "<中文名>"',
            "正式审批完成 → 导出桌面",
        )

    if gates.get("desktop_exported"):
        add("done", f'aifilm status --root "{r}"', "本集交付门禁已齐")

    return actions[:8]


def pilot_gate_hint(root: Path) -> str:
    """One-liner appended to pilot ProductionGateError messages."""
    root = Path(root).expanduser().resolve()
    return (
        f' Next: aifilm pilot report --root "{root}" '
        f'→ pilot score … → pilot approve --user-phrase "pilot 过"'
    )


def format_stage_line(pipeline: dict[str, Any], *, compact: bool = True) -> str:
    """Human one-liner for CLI / HUD strip (tool layer + optional craft ring)."""
    stage = str(pipeline.get("stage") or "?")
    label = str(pipeline.get("label_zh") or stage)
    detail = str(pipeline.get("detail") or "")
    idx = pipeline.get("stage_index")
    total = pipeline.get("stage_total")
    prog = f"{int(idx) + 1}/{total}" if idx is not None and total else ""
    craft_bit = ""
    cl = pipeline.get("craft_line") or ""
    if not cl and isinstance(pipeline.get("craft"), dict):
        try:
            from craft_spine import format_craft_line

            cl = format_craft_line(pipeline["craft"], compact=True)
        except Exception:
            cl = ""
    if cl:
        craft_bit = f" | {cl}"
    if compact:
        # short: 片 2/7 voice·tts-rehearse | craft 5/8 · Media
        short_label = {
            "agent": "规划",
            "visual": "视觉",
            "voice": "语音",
            "design": "设计",
            "post": "后处理",
            "deliver": "导出",
            "done": "完成",
        }.get(stage, stage)
        bit = f"{short_label}"
        if detail and detail not in {"complete", short_label}:
            bit = f"{short_label}·{detail}"
        prefix = f"片 {prog} " if prog else "片 "
        return f"{prefix}{bit}{craft_bit}".strip()
    return f"[{prog}] {label}" + (f" · {detail}" if detail else "") + craft_bit


def persist_pipeline_stage(
    root: Path,
    pipeline: dict[str, Any],
    *,
    next_cmd: str | None = None,
    next_id: str | None = None,
    grok_home: Path | None = None,
) -> dict[str, str]:
    """Write receipts/pipeline_stage.json + optional ~/.grok/hud/aifilm-stage.* for HUD.

    Returns paths written (best-effort; never raises for HUD home failures).
    """
    import json
    import os
    from datetime import datetime

    root = Path(root).expanduser().resolve()
    receipts = root / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    payload = {
        **pipeline,
        "updated_at": datetime.now(UTC).isoformat(),
        "root": str(root),
        "next_cmd": next_cmd,
        "next_id": next_id,
        "line": format_stage_line(pipeline, compact=True),
        "line_full": format_stage_line(pipeline, compact=False),
    }
    paths: dict[str, str] = {}
    film_path = receipts / "pipeline_stage.json"
    film_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths["film"] = str(film_path)

    # HUD sidecar (opt-out: AIFILM_HUD_STAGE=0)
    if os.environ.get("AIFILM_HUD_STAGE", "1").strip().lower() in {"0", "false", "no", "off"}:
        return paths
    try:
        home = Path(grok_home) if grok_home else Path.home() / ".grok"
        hud = home / "hud"
        hud.mkdir(parents=True, exist_ok=True)
        hud_json = hud / "aifilm-stage.json"
        hud_txt = hud / "aifilm-stage.txt"
        hud_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        line = payload["line"]
        if next_id:
            line = f"{line} → {next_id}"
        hud_txt.write_text(line + "\n", encoding="utf-8")
        paths["hud_json"] = str(hud_json)
        paths["hud_txt"] = str(hud_txt)
    except OSError:
        pass
    return paths
