#!/usr/bin/env python3
"""Suggest the next production commands from film root state (status / agent routing).

Internal execution layers (not the canonical production workflow):

  agent → visual → voice → design → post → deliver → done

The public workflow is the 11-stage status returned by workflow_spine.
"""

from __future__ import annotations

import os
from datetime import UTC
from pathlib import Path
from typing import Any

from security_policy import atomic_write_text
from util import read_json, write_json

# Backward-compatible internal projection (Grok Agent + layers 1–4 + delivery).
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
    "h3-fill-idle": "visual",
    "h3-lane": "visual",
    "h3-run-next": "visual",
    "h3-until-empty": "visual",
    "h3-capacity-plan": "visual",
    "pilot-window": "visual",
    "tts-rehearse": "voice",
    "compose-preview": "design",
    "final-designed": "design",
    "compose-render-remotion": "design",
    "final": "post",
    "final-audio": "post",
    "external-review": "post",
    "review-final": "post",
    "agent-review-final": "post",
    "closeout-run": "post",
    "pilot-pack": "agent",
    "plan-debrief": "agent",
    "plan-debrief-confirm": "agent",
    "fidelity-check": "agent",
    "fidelity-apply": "agent",
    "design-go": "agent",
    "post-audit": "post",
    "cinematic-gate": "post",
    "gate-auto": "post",
    "ship-prep": "post",
    "i2v-motion-gate": "post",
    "export-desktop": "deliver",
    "done": "done",
}

_STAGE_LABELS_ZH: dict[str, str] = {
    "agent": "0·Agent 规划（Lens / 定妆 / film-spec / pilot）",
    "visual": "1·视觉生成（Grok still + H3/Grok I2V）",
    "voice": "2·语音生成（Edge TTS + tts-rehearse / SRT）",
    "design": "3·设计合成（HyperFrames 优先 / Remotion）",
    "post": "4·后处理验收（FFmpeg plate · review-final）",
    "deliver": "交付导出（export-desktop）",
    "done": "完成",
}

_STAGE_RESPONSIBILITY: dict[str, tuple[str, str | None]] = {
    "agent": ("director", None),
    "visual": ("visual", "visual"),
    "voice": ("audio", "audio"),
    "design": ("post", "post"),
    "post": ("post", "post"),
    "deliver": ("delivery", None),
    "done": ("delivery", None),
}


def responsibility_for_stage(stage: str) -> dict[str, str | None]:
    """Map each pipeline stage to its one accountable owner."""
    owner, department = _STAGE_RESPONSIBILITY.get(stage, ("director", None))
    return {"owner": owner, "department": department, "stage": stage}


def with_responsibility(action: dict[str, Any]) -> dict[str, Any]:
    """Attach ownership to actions created outside the normal add() helper."""
    output = dict(action)
    output["responsibility"] = responsibility_for_stage(str(output.get("stage") or "agent"))
    return output


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


def _story_intake_active(root: Path) -> bool:
    """True when user story work has started (reception / graph / planning text)."""
    return any(
        (root / rel).is_file()
        for rel in (
            "receipts/story-reception.json",
            "drama-graph.json",
            "receipts/story-normalize.json",
        )
    )


def _past_story_planning(root: Path) -> bool:
    """Legacy/mid-production: do not block on debrief once media is underway."""
    try:
        from production_gates import load_pilot_approval, pilot_is_user_approved

        if pilot_is_user_approved(load_pilot_approval(root)):
            return True
    except Exception:
        pass
    man = read_json(root / "manifest.json") or {}
    clips = man.get("clips") if isinstance(man.get("clips"), dict) else {}
    for rec in clips.values():
        if isinstance(rec, dict) and rec.get("status") in {"approved", "ready", "ok"}:
            return True
    if (root / "receipts" / "final.json").is_file():
        return True
    if (root / "out" / "film_final.mp4").is_file():
        return True
    return False


def _debrief_next_action(root: Path, root_s: str) -> dict[str, str] | None:
    """If story intake exists (and production not past planning), require debrief."""
    if not _story_intake_active(root):
        return None
    if _past_story_planning(root):
        return None
    try:
        from script_value_debrief import load_debrief

        deb = load_debrief(root)
    except Exception:
        deb = None
    if not deb:
        return {
            "id": "plan-debrief",
            "cmd": f'aifilm plan debrief --root "{root_s}" --action seed',
            "why": "故事已接收：先 script-value-debrief（seed→填 beat/value_rank→confirm）再 lock",
        }
    if deb.get("confirmed_by_user") is not True:
        return {
            "id": "plan-debrief-confirm",
            "cmd": (
                f'aifilm plan debrief --root "{root_s}" --action confirm '
                f'--user-phrase "确认 promise 与不可砍 beat"'
            ),
            "why": "debrief 未确认：回显 promise/must_keep 后由用户 confirm（agent 不可代签）",
        }
    return None


def _final_record(root: Path) -> dict[str, Any] | None:
    man = read_json(root / "manifest.json") or {}
    outputs = man.get("outputs") if isinstance(man.get("outputs"), dict) else {}
    rec = outputs.get("final_film")
    return rec if isinstance(rec, dict) and rec else None


def _external_review_current(final_record: dict[str, Any] | None, root: Path) -> bool:
    """A sidecar is current only when it reviewed this exact final checksum."""
    if not isinstance(final_record, dict):
        return False
    final_sha = str(final_record.get("sha256") or "")
    report = read_json(root / "receipts" / "external-review.json") or {}
    inputs = report.get("inputs") if isinstance(report, dict) else None
    video = inputs.get("video") if isinstance(inputs, dict) else None
    return bool(
        isinstance(report, dict)
        and report.get("kind") == "external-review"
        and report.get("status") == "candidate_only"
        and report.get("purpose") == "final"
        and isinstance(video, dict)
        and final_sha
        and video.get("sha256") == final_sha
    )


def _pilot_user_ok(root: Path) -> bool:
    pilot_approval = read_json(root / "receipts" / "pilot-approval.json") or {}
    try:
        from production_gates import pilot_is_user_approved

        return pilot_is_user_approved(pilot_approval)
    except Exception:
        return False


def _post_audit_current(root: Path) -> bool:
    receipt = read_json(root / "receipts" / "post-audit.json") or {}
    if not isinstance(receipt, dict) or receipt.get("delivery_ready") is not True:
        return False
    try:
        from post_audit import audit_freshness

        return audit_freshness(root, receipt).get("stale") is False
    except (ImportError, OSError, ValueError):
        return False


def _export_desktop_name(root: Path) -> str:
    """Stable Desktop folder name without placeholders (advance-safe argv)."""
    import re

    for rel in ("film-spec.json", "brief.json", "manifest.json"):
        data = read_json(root / rel) or {}
        if not isinstance(data, dict):
            continue
        raw = str(data.get("title") or data.get("name") or "").strip()
        if raw:
            # Keep CJK/letters/digits; collapse other runs to single hyphen.
            cleaned = re.sub(r"[^\w\u4e00-\u9fff\-]+", "-", raw, flags=re.UNICODE)
            cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-.")
            if cleaned:
                return cleaned[:80]
    return "GrokFilm"


def detect_pipeline_stage(
    root: Path,
    *,
    gates: dict[str, Any] | None = None,
    open_reshoot_count: int = 0,
) -> dict[str, Any]:
    """Classify film-root into the internal execution layer (agent → … → done).

    The authoritative public progress is `canonical_workflow`, which uses the
    professional 11-stage contract. Existing `stage` fields remain stable for
    routing, HUD, and old project receipts.
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
    post_audit_current = _post_audit_current(root)

    blockers: list[str] = []
    stage = "agent"
    detail = "init"

    debrief_gap = _debrief_next_action(root, str(root))

    if not has_brief:
        stage, detail = "agent", "init"
        blockers.append("brief_missing")
    elif debrief_gap is not None:
        stage, detail = "agent", debrief_gap["id"]
        blockers.append("script_value_debrief_pending")
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
    elif final_ok and not post_audit_current:
        stage, detail = "post", "post-audit"
        blockers.append("post_audit_missing_or_stale")
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
    try:
        from workflow_spine import build_workflow_status

        workflow = build_workflow_status(root, gates=gates)
    except (OSError, ValueError):
        workflow = {}

    return {
        "axis": "internal_execution_layer",
        "stage": stage,
        "stage_index": stage_index,
        "stage_total": len(PIPELINE_STAGES),
        "label_zh": _STAGE_LABELS_ZH.get(stage, stage),
        "detail": detail,
        "blockers": blockers,
        "checklist": checklist,
        "flags": {
            "brief": has_brief,
            "script_value_debrief_pending": debrief_gap is not None,
            "style_locked": style_ok,
            "spec": spec_ok,
            "pilot_user_approved": pilot_ok,
            "clips_complete": clips_ok,
            "tts_rehearsal": rehearse_ok,
            "compose_preview": preview_ok,
            "final_film": bool(final_rec),
            "final_complete": final_ok,
            "post_audit_current": post_audit_current,
            "desktop_exported": export_ok,
            "open_reshoot_count": int(open_reshoot_count or 0),
            "post_engine": (final_rec or {}).get("post_engine"),
        },
        "spine": "agent → 1.visual → 2.voice → 3.design → 4.post → deliver",
        "craft_stage": craft.get("craft_stage"),
        "craft": craft,
        "craft_line": craft_line,
        "craft_spine": "idea → story → beats → shots → media → selects → rough → verified",
        "workflow": workflow,
        "workflow_stage": workflow.get("current_stage"),
        "canonical_workflow": {
            "stage": workflow.get("current_stage"),
            "stage_index": workflow.get("stage_index"),
            "stage_total": workflow.get("stage_total"),
            "label_zh": workflow.get("current_label_zh"),
        },
        "ref": "references/pipeline-methodology.md · references/craft-spine.md",
    }


def build_next_actions(
    root: Path,
    *,
    gates: dict[str, Any] | None = None,
    open_reshoot_count: int = 0,
) -> list[dict[str, Any]]:
    """Return ordered actionable steps: [{id, cmd, why, stage}, ...]. Max ~8 items."""
    root = Path(root).expanduser().resolve()
    gates = gates or {}
    actions: list[dict[str, Any]] = []

    def add(aid: str, cmd: str, why: str) -> None:
        stage = _ACTION_STAGE.get(aid, "agent")
        label = _STAGE_LABELS_ZH.get(stage, stage)
        # Keep why short; stage is a separate field for agents/UI.
        actions.append(
            {
                "id": aid,
                "cmd": cmd,
                "why": why,
                "stage": stage,
                "stage_label": label,
                "responsibility": responsibility_for_stage(stage),
            }
        )

    r = str(root)

    # Cross-modality primaries (soft) — annotate visual why strings only.
    inv_still = inv_motion = inv_edit = None
    try:
        from weapon_inventory import primary_for

        inv_still = (primary_for("text-to-image") or {}).get("id")
        inv_edit = (primary_for("local-image-edit") or {}).get("id")
        inv_motion = (primary_for("image-to-video") or {}).get("id")
    except Exception:
        pass

    def _with_primary(why: str, *, kind: str = "motion") -> str:
        """Append inventory primary tag without blowing why budgets."""
        tag = None
        if kind == "motion" and inv_motion:
            tag = f"wp={inv_motion}"
        elif kind == "still" and inv_still:
            tag = f"wp={inv_still}"
        elif kind == "edit" and inv_edit:
            tag = f"wp={inv_edit}"
        if not tag or tag in why:
            return why
        base = why.rstrip()
        if len(base) + len(tag) + 3 > 160:
            return base
        return f"{base} · {tag}"

    # A completed independent review with a failed dimension is more useful
    # than generic advisory.  Return its one evidence-backed repair instead of
    # asking an agent to choose among unrelated next steps.
    try:
        from quality_closure import repair_action

        quality_repair = repair_action(root)
    except (OSError, ValueError):
        quality_repair = None
    if quality_repair is not None:
        quality_repair["stage_label"] = _STAGE_LABELS_ZH.get(
            str(quality_repair.get("stage")), str(quality_repair.get("stage"))
        )
        return [with_responsibility(quality_repair)]

    if not (root / "brief.json").is_file() and not gates.get("brief"):
        add(
            "init",
            f'aifilm init --theme "…" --title "…" --root "{r}" --aspect 9:16',
            "项目未初始化",
        )
        return actions

    # Script-value-debrief: when story intake or graph exists, force debrief path first.
    debrief_action = _debrief_next_action(root, r)
    if debrief_action is not None:
        add(debrief_action["id"], debrief_action["cmd"], debrief_action["why"])
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

    # Input fidelity (after debrief+spec, before pilot bulk)
    if gates.get("spec") or (root / "film-spec.json").is_file():
        try:
            from input_fidelity import fidelity_status

            fid = fidelity_status(root)
            if not fid.get("ok") and fid.get("has_source"):
                codes = ",".join(str(c) for c in (fid.get("codes") or [])[:4])
                add(
                    "fidelity-apply",
                    f'aifilm fidelity apply --root "{r}"',
                    f"input 相关性不足 score={fid.get('score')} codes={codes or '—'}",
                )
                add(
                    "fidelity-check",
                    f'aifilm fidelity check --root "{r}"',
                    "重算 input-fidelity 回执",
                )
            elif fid.get("has_source") and not _pilot_user_ok(root):
                add(
                    "design-go",
                    f'aifilm design-go --root "{r}"',
                    "设计期 GO：debrief+fidelity+variety 一页（不代签 pilot）",
                )
        except Exception:
            pass

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
        add(
            "pilot-pack",
            f'aifilm pilot-pack --root "{r}"',
            "pilot GO 证据包（媒体+三拍+state+heat）— 一屏看是否可 bulk",
        )
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

    # Wave 4: adult max heat before bulk/final
    if gates.get("spec"):
        try:
            from heat_check import heat_agent_status

            hs = heat_agent_status(root)
            if hs.get("active") and (hs.get("hard_fail") or hs.get("needs_boost")):
                add(
                    "heat-boost",
                    hs.get("next_cmd") or f'aifilm heat boost --root "{r}" --apply',
                    hs.get("why") or "成人 max：impact/ecchi 未拉满 — 先 heat boost 再 bulk/final",
                )
                if hs.get("hard_fail"):
                    # Prefer heat over more I2V when scale is failing
                    pass
        except Exception:
            pass

    if not gates.get("clips_complete"):
        # M4 · weak mean + identity ok → still-challenge before re-burn
        try:
            from shot_evidence import list_still_challenge_suggestions

            sc_sug = list_still_challenge_suggestions(root)
            if sc_sug.get("count") and sc_sug.get("next_cmd"):
                first = (sc_sug.get("suggestions") or [{}])[0]
                add(
                    "still-challenge-weak-mean",
                    str(sc_sug["next_cmd"]),
                    _with_primary(
                        f"mean 弱但身份未红（{first.get('shot_id')} mean={first.get('mean')}）"
                        " — 先 still-challenge 换 still 再 I2V（人 promote）",
                        kind="still",
                    ),
                )
        except Exception:
            pass
        # Bulk / H3 only after gates.spec is green (recompute_gates / validate_film_spec).
        # Pilot-approved + invalid film-spec must not race to h3/media-queue primary.
        if pilot_ok and gates.get("spec"):
            # Wave F: bulk door before queue when pilot already GO
            if pilot_ok:
                bulk_rec = read_json(root / "receipts" / "bulk-preflight.json") or {}
                if bulk_rec.get("ok") is not True:
                    add(
                        "bulk-preflight",
                        f'aifilm bulk-preflight --root "{r}" --no-tunnel',
                        _with_primary(
                            "bulk 单门未绿 — 先 bulk-preflight 再 media-queue"
                            + (
                                f"；失败时点名 still={inv_still} motion={inv_motion}"
                                if inv_still or inv_motion
                                else ""
                            )
                        ),
                    )
            # H3 lanes: hybrid_h3 (meat) or h3_primary (film-wide local primary).
            h3_enabled = False
            film_profile = ""
            try:
                h3_block = spec.get("h3") if isinstance(spec.get("h3"), dict) else {}
                film_profile = str(spec.get("_i2v_profile") or "").strip().lower()
                h3_enabled = bool(
                    h3_block.get("enabled") is True or film_profile in {"hybrid_h3", "h3_primary"}
                )
            except Exception:
                h3_enabled = False
            is_h3_primary = film_profile == "h3_primary"
            if h3_enabled:
                if is_h3_primary:
                    # Primary production path: 5090 unlimited overnight throughput.
                    add(
                        "h3-until-empty",
                        f'aifilm h3 cycle --root "{r}" --until-empty --execute --max 5',
                        _with_primary(
                            "h3_primary 挂机：until-empty 吃光 P0→P1→P2（无限本地算力；永不 auto-promote）"
                        ),
                    )
                    add(
                        "h3-capacity-plan",
                        f'aifilm h3 capacity-plan --root "{r}"',
                        _with_primary("全片 H3 backlog ETA（按 I2V/FLF/R2V/T2V）"),
                    )
                    add(
                        "h3-run-next",
                        f'aifilm h3 run-next --root "{r}" --execute --max 5',
                        _with_primary(
                            "h3_primary 主产线：单批 5 镜；或改用 until-empty 挂机"
                        ),
                    )
                    add(
                        "h3-fill-idle",
                        f'aifilm h3 cycle --root "{r}" --execute --max 5',
                        _with_primary(
                            "Fill-Idle 一循环：evidence→run-next→pk peek（永不 auto-promote）"
                        ),
                    )
                    add(
                        "h3-lane",
                        f'aifilm h3 list --root "{r}"; aifilm h3 next --root "{r}"',
                        _with_primary(
                            "h3_primary：list/next 看模式+队列；云 bulk 默认硬拦"
                        ),
                    )
                    add(
                        "queue-or-register",
                        f"# cloud opt-in only under h3_primary\n"
                        f'AIFILM_ALLOW_CLOUD_RESTRICTED=1 media-queue add --root "{r}" …',
                        _with_primary(
                            "镜头未齐：主轨 aifilm h3 run；Grok 云仅 escape 后可选"
                        ),
                    )
                else:
                    add(
                        "h3-fill-idle",
                        f'aifilm h3 cycle --root "{r}" --execute --max 5',
                        _with_primary(
                            "Fill-Idle 一循环：evidence→run-next→pk peek（永不 auto-promote）"
                        ),
                    )
                    add(
                        "h3-lane",
                        f'aifilm h3 list --root "{r}" --challenge; aifilm h3 next --root "{r}"',
                        _with_primary(
                            "hybrid_h3：list/next 看 P0–P2；dual 粘连；P2=pilot"
                        ),
                    )
                    add(
                        "queue-or-register",
                        f'media-queue add --root "{r}" --shot-id <id> --operation image_to_video … '
                        f'&& aifilm register-clip --root "{r}" …',
                        _with_primary(
                            "镜头未齐：云 bulk 用 Grok 队列 + register-clip；H3 镜用 aifilm h3 run"
                        ),
                    )
            else:
                add(
                    "queue-or-register",
                    f'media-queue add --root "{r}" --shot-id <id> --operation image_to_video … '
                    f'&& aifilm register-clip --root "{r}" …',
                    _with_primary(
                        "镜头未齐：云 bulk 用 Grok 队列 + register-clip"
                        + (f"；本地 motion 首选 {inv_motion}" if inv_motion else "")
                    ),
                )
        else:
            add(
                "pilot-pack",
                f'aifilm pilot-pack --root "{r}"',
                "pilot GO 证据包：三镜/卸装三拍/score/heat/state — bulk 前一屏",
            )
            add(
                "pilot-window",
                f'media-queue add --root "{r}" …  # 无 pilot 批准时最多 3 个不同 shot_id',
                "仍在 pilot 窗口，勿批量第 4 镜",
            )

    if gates.get("clips_complete") and not gates.get("final_complete"):
        final_rec = _final_record(root)
        # Plate already on disk → closeout owns the ladder (not gate-auto thrash).
        # Machine lane is for pre-plate selects; re-opening it after plate is thrash.
        machine_pending = False
        if not final_rec:
            # W4 · single machine next (ship-prep owns shortlist+pk; no duplicate select-shortlist)
            try:
                from gate_auto import next_machine_lane_action

                lane = next_machine_lane_action(root, prefer_ship_prep=True)
                if lane:
                    add(lane["id"], lane["cmd"], lane["why"])
                    machine_pending = True
            except Exception:
                add(
                    "gate-auto",
                    f'aifilm gate-auto --root "{r}"',
                    "clips 齐 — gate-auto 机读过闸",
                )
                machine_pending = True
        # No plate yet + machine red → only machine (+ post-plan), skip final/tts stack
        if machine_pending and not final_rec:
            if not (root / "post-plan.json").is_file():
                add(
                    "post-plan-init",
                    f'aifilm post-plan --root "{r}" init --owner hyperframes',
                    "后期 owner 未锁 — 机读过闸后进 final 需要",
                )
            return actions
        preview_ok = _preview_ok(root)
        rehearse_ok = _tts_rehearse_ok(root)
        require_reh = bool(spec.get("tts_rehearsal_required") is True) if spec else False
        # post-plan is a pre-plate design gate. Once plate exists, closeout owns
        # the ladder — reopening post-plan-init as primary is thrash.
        if not final_rec and not (root / "post-plan.json").is_file():
            add(
                "post-plan-init",
                f'aifilm post-plan --root "{r}" init --owner hyperframes',
                "进入设计合成前先锁定后期与字幕 owner；若要 React 模板改为 --owner remotion",
            )
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
            final_path = str(final_rec.get("path") or "")
            # Wave A3: plate/final exists → prefer closeout ladder (not orphan "what next?")
            add(
                "closeout-run",
                f'aifilm closeout run --root "{r}"',
                "[交付] 成片/plate 已在 → closeout：heat→review-final→post-audit（不自动批分）",
            )
            # Phase B · film_core advisory on closeout ladder
            fc = read_json(root / "receipts" / "film-core-closeout.json") or {}
            if fc.get("ok") is False:
                add(
                    "film-core-closeout",
                    f'aifilm closeout status --root "{r}"',
                    "[advisory] 电影核 DF/want/spine 未齐 — 修 spec 或补 *.grok/*.h3.spine.txt",
                )
            external_configured = bool(
                os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY")
            )
            if external_configured and final_path and not _external_review_current(final_rec, root):
                add(
                    "external-review",
                    f'aifilm external-review run --root "{r}" --video "{final_path}" --purpose final',
                    "可选外部审片：候选问题写入 receipt，不取代本地 QA 或人工终审",
                )
            # P1: fill scorecard draft from L0 before human review-final
            try:
                from agent_review_final import agent_review_stale

                assist_stale = agent_review_stale(root)
            except Exception:
                assist_stale = True
            if assist_stale:
                add(
                    "agent-review-final",
                    f'aifilm agent-review-final --root "{r}"',
                    "[P1] L0 自动填 review-final 记分卡草案（不自动批；人看完一点确认）",
                )
            else:
                assist = read_json(root / "receipts" / "agent-review-final.json") or {}
                if assist.get("all_pass_suggested") is True:
                    add(
                        "agent-review-final-apply",
                        f'aifilm agent-review-final --root "{r}" --apply '
                        f'--reviewer <you> --user-phrase "可以" --notes "已完整观看"',
                        "[打通] L0 绿 — 完整观看后一条 --apply（需用户原话，禁 agent 自拟）",
                    )
                next_human = str(assist.get("next_cmd") or "").strip()
                if next_human and "<" not in next_human and "YOU" not in next_human:
                    add(
                        "review-final",
                        next_human if next_human.startswith("aifilm ") else f"aifilm {next_human}",
                        "[P1] assist 已写好 — 完整观看后执行（或改 --reviewer）",
                    )
                else:
                    add(
                        "review-final",
                        f'aifilm agent-review-final --root "{r}" --apply '
                        f'--reviewer <you> --user-phrase "可以"',
                        "[打通] 用 --apply 代替手搓 16 维 score（仍需用户原话）",
                    )
            if assist_stale:
                add(
                    "review-final",
                    f'aifilm review-final --root "{r}" --approve --reviewer <you> --notes "已完整观看…" '
                    "--score-identity pass --score-style pass --score-motion pass "
                    "--score-escalation pass --score-audio pass --score-subs pass --score-dead-air pass",
                    "[层4·后处理] 成片已渲，待 scorecard 审批（建议先 agent-review-final）",
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
        if _post_audit_current(root):
            export_name = _export_desktop_name(root)
            add(
                "export-desktop",
                f'aifilm export-desktop --root "{r}" --name "{export_name}"',
                "正式审批和 post-audit 完成 → 导出桌面（本地无花费，advance 可跑）",
            )
        else:
            add(
                "post-audit",
                f'aifilm post-audit --root "{r}"',
                "正式导出前需要当前且无 hard failure 的 post-audit",
            )

    if gates.get("desktop_exported"):
        add("done", f'aifilm status --root "{r}"', "本集交付门禁已齐")

    return [with_responsibility(action) for action in actions[:8]]


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
) -> dict[str, Any]:
    """Write receipts/pipeline_stage.json + optional ~/.grok/hud/aifilm-stage.* for HUD.

    Returns paths written (best-effort; never raises for HUD home failures).
    """
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
    paths: dict[str, Any] = {}
    film_path = receipts / "pipeline_stage.json"
    write_json(film_path, payload)
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
        write_json(hud_json, payload)
        line = payload["line"]
        if next_id:
            line = f"{line} → {next_id}"
        atomic_write_text(hud_txt, line + "\n")
        paths["hud_json"] = str(hud_json)
        paths["hud_txt"] = str(hud_txt)
    except OSError as exc:
        paths["errors"] = [f"hud sync failed: {exc}"]
    return paths
