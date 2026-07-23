#!/usr/bin/env python3
"""Automatic craft+tool dispatcher for ai-film-grok.

One entry for agents: read craft ring + capability + next actions → single
orchestration packet. Never skips pilot/user gates or silent-mutates film-spec.

  aifilm dispatch --root <film>
  aifilm dispatch --root <film> --print-cmd-only
"""

from __future__ import annotations

import hashlib
import json
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quality_gates import summarize_quality
from util import read_json, write_json

_ACTION_SKILLS = {
    "narrative-validate": "story.validate",
    "narrative-project": "graph.project",
    "narrative-lock": "story.validate",
    "grok-i2v-bulk": "image.animate",
    "state-index-plan": "character.state.update",
    "audio-plan": "sound.design",
    "selects-report": "quality.inspect",
    "post-audit-gate": "quality.inspect",
    "production-evidence-gate": "projection.verify",
}


def _quality_summary(root: Path) -> dict[str, Any]:
    """Compatibility wrapper around the shared quality receipt summary."""
    return summarize_quality(root)


def structured_next_action(
    action: dict[str, Any] | None,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Turn the legacy next command into a fixed, directly executable action."""
    if not action:
        return None
    context = context or {}
    raw_cmd = str(action.get("cmd") or "")
    if (
        not raw_cmd.strip()
        or raw_cmd.lstrip().startswith("#")
        or "…" in raw_cmd
        or "<" in raw_cmd
        or ">" in raw_cmd
    ):
        return None
    try:
        tokens = shlex.split(raw_cmd)
    except ValueError:
        tokens = []
    argv = tokens[1:] if tokens[:1] == ["aifilm"] else []
    if not argv:
        return None
    operation = argv[0] if argv else str(action.get("id") or "status")
    action_id = str(action.get("id") or "")
    skill_id = _ACTION_SKILLS.get(action_id, "dispatch.orchestrate")
    paid_or_external = any(
        word in action_id.lower() for word in ("bulk", "grok", "frw", "export")
    ) or skill_id in {"image.animate", "keyframe.generate", "video.render", "export.package"}
    spend_class = "paid" if paid_or_external else "local"
    approval_class = "human_required" if paid_or_external else "none"
    payload = {
        "skill_id": skill_id,
        "operation": operation,
        "argv": argv,
        "node_refs": list(context.get("node_refs") or []),
        "input_hashes": dict(context.get("input_hashes") or {}),
        "dependencies": list(context.get("dependencies") or []),
        "spend_class": spend_class,
        "approval_class": approval_class,
        "expected_outputs": list(context.get("expected_outputs") or []),
        "verification": list(context.get("verification") or []),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload["transaction_id"] = f"tx-{digest[:24]}"
    return payload


def skill_scripts() -> Path:
    return Path(__file__).resolve().parent


def build_dispatch(
    root: Path,
    *,
    gates: dict[str, Any] | None = None,
    open_reshoot_count: int = 0,
    include_capability: bool = True,
    write_receipt: bool = True,
) -> dict[str, Any]:
    """Assemble auto-dispatch packet for agent orchestration."""
    root = Path(root).expanduser().resolve()
    scripts = skill_scripts()
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))

    from craft_spine import craft_status_report, detect_craft_stage
    from narrative_control import control_status
    from next_actions import build_next_actions, detect_pipeline_stage
    from production_evidence import build_evidence

    gates = gates or {}
    craft_report = craft_status_report(root, gates=gates)
    craft = craft_report.get("craft") or detect_craft_stage(root, gates=gates)
    pipeline = detect_pipeline_stage(root, gates=gates, open_reshoot_count=open_reshoot_count)
    actions = build_next_actions(root, gates=gates, open_reshoot_count=open_reshoot_count)

    # Craft-first prepends (soft routing — before bulk tool steps)
    r = str(root)
    craft_stage = str(craft.get("craft_stage") or "idea")
    prepend: list[dict[str, str]] = []

    def pre(aid: str, cmd: str, why: str, stage: str = "agent") -> None:
        prepend.append(
            {
                "id": aid,
                "cmd": cmd,
                "why": why,
                "stage": stage,
                "stage_label": stage,
                "source": "craft_dispatch",
            }
        )

    # I2V profile (Seedance outage → grok_primary)
    i2v_profile = "grok_primary"
    try:
        from film_spec import resolve_i2v_profile

        i2v_profile = resolve_i2v_profile()
    except Exception:
        pass

    # Capability hygiene once per media-ish ring
    if craft_stage in {"shots", "media", "selects", "rough", "verified"}:
        canary = root / "receipts" / "frw-key-capability.json"
        if i2v_profile == "grok_primary":
            if craft_stage in {"shots", "media"}:
                pre(
                    "grok-i2v-bulk",
                    f"# Media: i2v_provider=grok · image_edit(cast) still → media-queue image_to_video 720p → register-clip --source-endpoint image_to_video  (profile={i2v_profile}; Seedance off)",
                    "Seedance 暂不可用：人物动走 Grok Imagine Video，勿提交 seedance bulk",
                    "visual",
                )
            # FRW canary optional — only for env LTX beds
            if craft_stage in {"shots", "media"}:
                pre(
                    "env-ltx-t2v",
                    f'aifilm env-plate --root "{r}" --shot-id <env_shot> --prompt "… no people no faces" --wait',
                    "无角色/环境床：FRW ltx-t2v（无限额度，已验证 completed）→ clip+首帧；禁锁脸",
                    "visual",
                )
                pre(
                    "frw-lipsync-probe",
                    "aifilm frw-lipsync probe  # then: frw-lipsync run --face kf.png --audio vo.wav --shot-id …",
                    "对白近景可选 FRW 口型（probe 201 才 run）；说书默认 off；403/502 则跳过",
                    "visual",
                )
        else:
            if craft_stage in {"shots", "media"} and not canary.is_file():
                pre(
                    "frw-canary",
                    f'aifilm frw canary --root "{r}"',
                    "Media 前缺 FRW key canary 回执 — 先探测 403/502 再 bulk",
                    "visual",
                )
            elif craft_stage == "media" and canary.is_file():
                pre(
                    "i2v-suggest",
                    f'aifilm capability --root "{r}" --suggest-i2v',
                    "有 canary：核对 I2V 路由建议（改 spec 须显式 --apply）",
                    "visual",
                )

    if craft_stage == "idea" and not (root / "receipts" / "creative-brief.md").is_file():
        pre(
            "creative-brief",
            f"# write {r}/receipts/creative-brief.md from templates/creative-brief.example.md",
            "Idea 环：先落 creative-brief（受众/时长/情绪）再 Lens",
            "agent",
        )
    if craft_stage == "story":
        pre(
            "directors-lens",
            "# Director’s Lens → director_intent.logline/theme in film-spec; optional receipts/directors-lens.md",
            "Story 环：锁 logline/theme，禁止原文插图化",
            "agent",
        )
    if craft_stage == "beats":
        pre(
            "beat-spine",
            f'aifilm write-spec --root "{r}"  # ensure dramatic_function + visible_change',
            "Beats 环：补叙事节点字段后 write-spec",
            "agent",
        )
    if craft_stage == "selects":
        pre(
            "selects-report",
            f'aifilm selects --root "{r}"',
            "Selects 环：对照 planned vs approved，未 register 的先补",
            "visual",
        )
    if craft_stage in {"rough", "verified"}:
        pre(
            "audio-plan",
            f'aifilm audio-plan --root "{r}"',
            "音轨 dry-run：確認 TTS/BGM/lipsync 路徑再 final",
            "voice",
        )

    if craft_stage == "post":
        pre(
            "design-title-sequence",
            f'aifilm final --root "{r}" --post-engine hyperframes --compose-preset auto',
            "片頭片尾：final 會自動讀取 film-spec 的 title_sequence / end_roll（預設 minimal + 完）",
            "post",
        )

    # Merge: prepend craft items not already covered by same id
    narrative = control_status(root)
    evidence = build_evidence(root)
    evidence_gate = bool(evidence.get("ready_for_bulk"))
    if craft_stage in {"media", "rough", "verified"} and not evidence_gate:
        pre(
            "production-evidence-gate",
            f'aifilm production-evidence --root "{r}"',
            "production evidence incomplete; bulk motion remains blocked until canonical graph, current projection, and user-approved pilot are present",
            "agent",
        )
    post_audit = read_json(root / "receipts" / "post-audit.json") or {}
    from post_audit import audit_freshness

    freshness = audit_freshness(root, post_audit)
    post_audit_gate = bool(post_audit.get("delivery_ready")) and not freshness.get("stale")
    if craft_stage in {"post", "verified"} and not post_audit_gate:
        pre(
            "post-audit-gate",
            f'aifilm post-audit --root "{r}"',
            "final delivery requires a current post-audit receipt with no hard failures",
            "post",
        )
    quality = _quality_summary(root)
    if quality["failed_count"]:
        pre(
            "quality-gate-repair",
            f'aifilm preflight --root "{r}"',
            quality["next_action"]
            or "quality gate failed; inspect receipts/quality before regeneration",
            "visual",
        )
    narrative_action_id: str | None = None
    if narrative.get("canonical") and not narrative.get("ready_for_media"):
        semantic = narrative.get("semantic") or {}
        projection = narrative.get("projection") or {}
        if semantic.get("errors"):
            narrative_action_id = "narrative-validate"
            pre(
                "narrative-validate",
                f'aifilm plan validate --root "{r}" --strict',
                "劇情／Beat／分鏡語義尚未完成，先修正 draft，不得進入 write-spec 或 media",
                "agent",
            )
        elif projection.get("stale"):
            narrative_action_id = "narrative-project"
            pre(
                "narrative-project",
                f'aifilm graph project --root "{r}" --force',
                "film-spec projection hash 已過期，重新投影後才能繼續",
                "agent",
            )
        else:
            missing = [
                s
                for s in ("story", "beats", "shots", "panels")
                if s not in (narrative.get("locked_scopes") or [])
            ]
            scope = missing[0] if missing else "story"
            narrative_action_id = "narrative-lock"
            pre(
                "narrative-lock",
                f'aifilm plan lock --root "{r}" --scope {scope} --user-phrase "<USER_APPROVAL>"',
                f"等待使用者審閱並鎖定 {scope} scope；Agent 不得自批",
                "agent",
            )
    existing_ids = {a.get("id") for a in actions}
    merged: list[dict[str, str]] = []
    for p in prepend:
        if p["id"] not in existing_ids:
            merged.append(p)
    if narrative_action_id:
        merged.sort(key=lambda item: 0 if item.get("id") == narrative_action_id else 1)
    merged.extend(actions)
    # de-dupe by id keep first
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for a in merged:
        aid = str(a.get("id") or "")
        if aid in seen:
            continue
        seen.add(aid)
        unique.append(a)
    actions = unique[:10]

    cap: dict[str, Any] | None = None
    if include_capability:
        try:
            from capability_report import build_capability_report

            cap = build_capability_report(root=root, run_canary=False, suggest_i2v=False)
            # Surface critical recs as soft actions
            for rec in (cap.get("recommendations") or [])[:3]:
                rid = "cap-" + str(abs(hash(rec)) % 10000)
                if any(rec[:40] in (x.get("why") or "") for x in actions):
                    continue
                actions.append(
                    {
                        "id": rid,
                        "cmd": f'aifilm capability --root "{r}"',
                        "why": f"[机位] {rec}",
                        "stage": "agent",
                        "stage_label": "机位",
                        "source": "capability",
                    }
                )
            actions = actions[:12]
        except Exception as exc:  # noqa: BLE001
            cap = {"ok": False, "error": str(exc)[:200]}

    primary = next(
        (action for action in actions if structured_next_action(action) is not None),
        None,
    )
    next_cmd = (primary or {}).get("cmd")
    next_id = (primary or {}).get("id")
    next_why = (primary or {}).get("why")

    # Agent playbook: what to do this turn
    agent_do: list[str] = [
        f"当前工序环 craft={craft_stage}（{craft.get('label_zh')}）",
        f"当前工具层 stage={pipeline.get('stage')}（{pipeline.get('label_zh')}）",
        f"本回合只执行：{next_cmd or '（无下一步 — status）'}",
        f"原因：{next_why or '—'}",
    ]
    if craft_stage in {"media", "shots"} and cap and not (cap.get("frw") or {}).get("present"):
        agent_do.append("bulk 前先 frw canary；403 走 Grok，勿死磕 Seedance")
    if craft_stage == "shots" and not gates.get("style_locked"):
        agent_do.append("先 lock-style 再 pilot / bulk")
    if craft_stage in {"shots", "media", "selects"}:
        agent_do.append(
            "Grok Build：静帧 image_edit(cast)/image_gen；动 bulk FRW 或 image_to_video；加载 /imagine"
        )
        agent_do.append("推理产出 structured film-spec 字段；事实先 web_search；记忆写 film-root")
        agent_do.append(
            "生成串行 first/last（必触发）：register-clip 后自动 promote 末帧→下镜首帧；"
            "下镜 I2V 只用 keyframes/<next>.png，禁 cast 全装重起（防回穿/姿势断）"
        )
        agent_do.append(
            "剧情接戏：按实际 last frame 衣着/姿势优化下一镜 prompt；"
            "卸装后只 image_edit 已 promote 帧，不写 full wardrobe"
        )
        agent_do.append(
            "状态照/keyframe 检查门：aifilm state-index check|plan — "
            "有缺口可在本阶段补生成状态照/keyframe/promote，保障运镜转场流畅"
        )
        # Inject state-index plan as next when gaps
        try:
            from state_index_gate import run_state_index_check

            si = run_state_index_check(root)
            if si.get("generate_plan"):
                actions.insert(
                    0,
                    {
                        "id": "state-index-plan",
                        "cmd": f'aifilm state-index plan --root "{r}"',
                        "why": (
                            f"state-index 有 {len(si.get('generate_plan') or [])} 项待补 "
                            "（状态照/keyframe/promote）— 先补再 bulk，转场才顺"
                        ),
                        "stage": "visual",
                        "stage_label": "1·视觉",
                        "source": "state_index_gate",
                    },
                )
                agent_do.insert(
                    2,
                    f"优先：aifilm state-index plan（{len(si.get('generate_plan') or [])} 项）",
                )
        except Exception:
            pass
    if quality["failed_count"]:
        agent_do.append(
            "质量硬拦：先修复 quality receipt 中的 hero/keyframe 阻塞，再允许该镜头重新 I2V"
        )
    agent_do.append("禁止：自批 pilot、静默改 i2v_provider、Ken Burns 当戏、说书默认 lipsync")
    agent_do.append("用户说「可以/ok/一路做完」才 pilot approve / run_to_completion")

    # Fallback routing summary for media + Grok Build native tools
    i2v_line = (
        "grok_primary: still=image_edit(cast) · motion=image_to_video 720p · register image_to_video · env optional ltx-t2v"
        if i2v_profile == "grok_primary"
        else "seedance_first: canary → seedance i2v · else grok/ltx"
    )
    routing = {
        "tts_default": "edge",
        "tts_quality": "voicebox if app up",
        "bgm": "film audio → skill assets/bgm → procedural rnb",
        "lipsync": "off default; canary after backend-lock",
        "i2v_profile": i2v_profile,
        "i2v": i2v_line,
        "env_plate": "FRW ltx-t2v (ltx-文生视频) unlimited — aifilm env-plate; no faces",
        "lipsync_frw": "opt-in CU dialogue: aifilm frw-lipsync probe → run face+audio (403/502 common)",
        "ref": "references/frw-lipsync.md · ltx-env-plate.md · i2v-grok-primary.md",
        "grok_build": {
            "host": "Grok Build session (native tools)",
            "oauth": "aifilm grok-oauth doctor — ~/.grok/auth.json SuperGrok path",
            "text": "Reasoning + structured JSON → brief / director_intent / beats / film-spec",
            "tools": "web_search · x_* · shell/aifilm · optional MCP collections",
            "image": "image_gen · image_edit(cast); batch: grok-oauth image|image-edit",
            "video": (
                "BULK: image_to_video; batch OAuth: grok-oauth video --image kf --wait"
                if i2v_profile == "grok_primary"
                else "bulk FRW Seedance; Grok I2V fallback; batch: grok-oauth video"
            ),
            "voice": "session chat ≠ VO; default edge; opt-in: --tts-backend grok (speech tags)",
            "memory": "film-root + receipts (project RAG default)",
            "sdk_optional": "OAuth first; XAI_API_KEY only if no auth.json",
            "matrix": "references/grok-build-sdk.md · references/grok-oauth.md",
        },
    }
    # attach live oauth summary when capability ran
    if isinstance(cap, dict) and isinstance(cap.get("grok_oauth"), dict):
        routing["grok_oauth"] = {
            "ok": cap["grok_oauth"].get("ok"),
            "ttl_sec": cap["grok_oauth"].get("ttl_sec"),
            "has_imagine_image": cap["grok_oauth"].get("has_imagine_image"),
            "has_imagine_video": cap["grok_oauth"].get("has_imagine_video"),
            "has_tts": cap["grok_oauth"].get("has_tts"),
            "pack": cap["grok_oauth"].get("pack"),
            "source": cap["grok_oauth"].get("source"),
        }
    if isinstance(cap, dict):
        tts = cap.get("tts") or {}
        routing["tts_active"] = tts.get("active") or tts.get("preferred")
        routing["voicebox_ok"] = tts.get("voicebox")
        music = cap.get("music") or {}
        routing["bgm_will_use"] = music.get("will_use") or (
            "skill_or_procedural" if music.get("skill_library_ready") else "procedural"
        )
        if cap.get("suggested_film_spec_patch"):
            routing["i2v_patch_available"] = cap.get("suggested_film_spec_patch")

    # Phase 1+2: Vertical Drama Graph + Execution jobs summary (non-breaking)
    graph_digest: dict[str, Any] | None = None
    jobs_summary: dict[str, Any] | None = None
    try:
        from drama_graph import build_jobs_summary, graph_status

        graph_digest = graph_status(root, auto_derive=bool((root / "film-spec.json").is_file()))
        jobs_summary = build_jobs_summary(root, craft_stage=craft_stage)
    except Exception as exc:  # noqa: BLE001
        graph_digest = {"ok": False, "error": str(exc)[:200]}
        jobs_summary = {"ok": False, "error": str(exc)[:200]}

    execution_plan_digest: dict[str, Any] | None = None
    primary_job: dict[str, Any] | None = None
    if isinstance(jobs_summary, dict) and jobs_summary.get("jobs") is not None:
        primary_job = jobs_summary.get("primary_job")
        execution_plan_digest = {
            "total": jobs_summary.get("total"),
            "ready_count": jobs_summary.get("ready_count"),
            "done_count": jobs_summary.get("done_count"),
            "blocked_count": jobs_summary.get("blocked_count"),
            "counts_by_status": jobs_summary.get("counts_by_status"),
            "primary_job_id": (primary_job or {}).get("id"),
            "primary_skill_id": (primary_job or {}).get("skillId"),
            "graph_line": jobs_summary.get("graph_line") or (graph_digest or {}).get("line"),
        }
        agent_do.append(
            f"ExecutionGraph: ready={execution_plan_digest.get('ready_count')} "
            f"done={execution_plan_digest.get('done_count')} "
            f"blocked={execution_plan_digest.get('blocked_count')} "
            f"/ total={execution_plan_digest.get('total')}"
        )
        if execution_plan_digest.get("graph_line"):
            agent_do.append(f"DramaGraph: {execution_plan_digest.get('graph_line')}")

    context_digest: dict[str, Any] = {
        "rigor": None,
        "department_locks": {},
        "department_stale_reasons": {},
        "asset_versions": [],
        "unresolved_notes": [],
        "approval_scope": [],
        "budget_scope": {},
    }
    try:
        from production_book import read_production_book

        book = read_production_book(root)
        context_digest.update(
            {
                "rigor": book.get("rigor"),
                "department_locks": {
                    key: value.get("state") == "locked"
                    for key, value in (book.get("departments") or {}).items()
                },
                "department_stale_reasons": {
                    key: value.get("stale_reasons") or []
                    for key, value in (book.get("departments") or {}).items()
                    if value.get("stale_reasons")
                },
                "asset_versions": [
                    {
                        "id": item.get("id"),
                        "version": item.get("version"),
                        "hash": item.get("hash"),
                    }
                    for item in book.get("assets") or []
                    if isinstance(item, dict)
                ],
                "unresolved_notes": book.get("unresolved_notes") or [],
                "approval_scope": book.get("approval_scope") or [],
                "budget_scope": book.get("budget_scope") or {},
            }
        )
    except (FileNotFoundError, ValueError):
        pass
    action_context = {
        "node_refs": [primary_job.get("nodeRef")]
        if isinstance(primary_job, dict) and primary_job.get("nodeRef")
        else [],
        "input_hashes": {str(primary_job.get("id") or "job"): str(primary_job["inputHash"])}
        if isinstance(primary_job, dict) and primary_job.get("inputHash")
        else {},
        "dependencies": list(primary_job.get("dependsOn") or [])
        if isinstance(primary_job, dict)
        else [],
        "expected_outputs": list(primary_job.get("produces") or [])
        if isinstance(primary_job, dict)
        else [],
        "verification": list(primary_job.get("verification") or [])
        if isinstance(primary_job, dict)
        else [],
    }
    next_action = structured_next_action(primary, context=action_context)

    packet = {
        "ok": True,
        "kind": "ai-film-dispatch",
        "schema_version": 2,
        "at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "root": str(root),
        "auto": True,
        "craft_stage": craft_stage,
        "craft": craft,
        "craft_line": craft_report.get("line") or craft.get("label_zh"),
        "pipeline_stage": pipeline.get("stage"),
        "pipeline": {
            "stage": pipeline.get("stage"),
            "label_zh": pipeline.get("label_zh"),
            "craft_line": pipeline.get("craft_line"),
        },
        "next_id": next_id,
        "next_cmd": next_cmd,
        "next_action": next_action,
        "next_why": next_why,
        "next_actions": actions,
        "agent_do": agent_do,
        "agent_instruction": "\n".join(f"- {x}" for x in agent_do),
        "routing": routing,
        "capability_summary": {
            "ok": (cap or {}).get("ok"),
            "tts_edge": ((cap or {}).get("tts") or {}).get("edge"),
            "voicebox": ((cap or {}).get("tts") or {}).get("voicebox"),
            "frw_present": ((cap or {}).get("frw") or {}).get("present"),
            "recommendations": ((cap or {}).get("recommendations") or [])[:5],
        }
        if cap
        else None,
        "graph": {
            "ok": (graph_digest or {}).get("ok"),
            "line": (graph_digest or {}).get("line"),
            "counts": (graph_digest or {}).get("counts"),
            "path": (graph_digest or {}).get("path"),
            "exists": (graph_digest or {}).get("exists"),
        }
        if graph_digest
        else None,
        "jobs_summary": {
            "total": (jobs_summary or {}).get("total"),
            "ready_count": (jobs_summary or {}).get("ready_count"),
            "done_count": (jobs_summary or {}).get("done_count"),
            "blocked_count": (jobs_summary or {}).get("blocked_count"),
            "counts_by_status": (jobs_summary or {}).get("counts_by_status"),
            "primary_job": (jobs_summary or {}).get("primary_job"),
            "jobs_preview": (jobs_summary or {}).get("jobs_preview"),
            "error": (jobs_summary or {}).get("error"),
        }
        if jobs_summary
        else None,
        "execution_plan_digest": execution_plan_digest,
        "context_digest": context_digest,
        "narrative_control": {
            "canonical": narrative.get("canonical"),
            "state": narrative.get("state"),
            "revision": narrative.get("revision"),
            "locked_scopes": narrative.get("locked_scopes") or [],
            "ready_for_media": narrative.get("ready_for_media"),
            "issue_codes": (narrative.get("semantic") or {}).get("issue_codes") or [],
            "projection": narrative.get("projection"),
        },
        "production_evidence": evidence,
        "quality": quality,
        "post_audit": {
            "receipt_present": bool(post_audit),
            "delivery_ready": post_audit_gate,
            "hard_failure_count": len(post_audit.get("hard_failures") or []),
            "warning_count": len(post_audit.get("warnings") or []),
            "freshness": freshness,
        },
        "hard_gates": [
            "write-spec before media-queue",
            "pilot user approve before bulk (>3 shots)",
            "no silent provider switch",
            "final ≠ final_complete without review-final",
            "state-index check before bulk when undress/continue (fluency)",
            "canonical narrative graph validated + all scopes locked + projection hash current",
            "production evidence ready before bulk motion",
            "hero quality receipt pass before clip promote",
            "provider fallback writes routing receipt and requires hero re-pilot",
        ],
        "ref": (
            "references/craft-spine.md · references/keyframe-first-state-index.md · "
            "references/audio-fallback.md · docs/plans/2026-07-21-vertical-drama-upgrade.md"
        ),
        "usage": {
            "dispatch": "aifilm dispatch --root <film>",
            "print_cmd": "aifilm dispatch --root <film> --print-cmd-only",
            "loop": "每完成一步再跑 dispatch，直到 craft=verified 且 export",
            "graph": "aifilm graph derive|validate|status --root <film>",
            "skill": "aifilm skill list|show --id <skill_id>",
        },
    }

    if write_receipt:
        path = root / "receipts" / "dispatch.json"
        write_json(path, packet)
        packet["receipt_path"] = str(path)
        # also HUD-friendly slim
        try:
            hud = Path.home() / ".grok" / "hud"
            hud.mkdir(parents=True, exist_ok=True)
            slim = {
                "craft_stage": craft_stage,
                "pipeline_stage": pipeline.get("stage"),
                "next_cmd": next_cmd,
                "next_why": next_why,
                "line": f"{craft_report.get('line') or craft_stage} | next={next_id}",
                "at": packet["at"],
                "jobs_ready": (execution_plan_digest or {}).get("ready_count"),
                "jobs_done": (execution_plan_digest or {}).get("done_count"),
                "graph_line": (execution_plan_digest or {}).get("graph_line"),
            }
            (hud / "aifilm-dispatch.json").write_text(
                json.dumps(slim, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            (hud / "aifilm-dispatch.txt").write_text(
                f"{slim['line']}\n{next_cmd or ''}\n", encoding="utf-8"
            )
        except OSError:
            pass

    return packet
