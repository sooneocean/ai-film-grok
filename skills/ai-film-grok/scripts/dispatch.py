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
import time
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
    "dialogue-candidate-review": "quality.inspect",
    "audio-plan": "sound.design",
    "selects-report": "projection.verify",
    "post-audit-gate": "projection.verify",
    "closeout-run": "projection.verify",
    "production-evidence-gate": "projection.verify",
    "bulk-preflight": "image.animate",
    "pilot-pack": "quality.inspect",
    "variety-precheck": "story.validate",
    "i2v-motion-gate": "projection.verify",
    "film-core-closeout": "projection.verify",
    "select-shortlist": "projection.verify",
    "export-desktop": "export.package",
    "dailies_review-evidence": "dispatch.orchestrate",
    "agent-review-final": "quality.inspect",
}
_SKILL_POLICIES = {
    "keyframe.generate": ("external", "human_required"),
    "image.animate": ("paid", "human_required"),
    "voice.synthesize": ("external", "human_required"),
    "video.render": ("external", "human_required"),
    # quality.inspect stays human: skill_runner maps it to review-final scorecard.
    "quality.inspect": ("local", "human_required"),
    # P0: local package copy after final_complete + post-audit (command still fail-closed).
    "export.package": ("local", "none"),
}
_COMMAND_POLICIES = {
    # P0: local read-only / post-gate delivery helpers (no spend, no artistic approve).
    "dailies": ("local", "none"),
    "export-desktop": ("local", "none"),
    "final": ("external", "human_required"),
    # closeout run = local post-audit ladder (does NOT auto-approve review-final)
    "closeout": ("local", "none"),
    "grok-oauth": ("external", "human_required"),
    "media-queue": ("external", "human_required"),
    "pilot": ("local", "human_required"),
    "pilot-pack": ("local", "none"),  # GO evidence write; approve remains human
    "bulk-preflight": ("local", "none"),
    "variety-precheck": ("local", "none"),
    "i2v-motion-gate": ("local", "none"),
    "film-core-closeout": ("local", "none"),
    "select-shortlist": ("local", "none"),
    "queue-progress": ("local", "none"),
    "tunnel-probe": ("local", "none"),
    "gpu-lease": ("local", "none"),
    # P1: write assist draft only — never sets final_complete
    "agent-review-final": ("local", "none"),
    "queue-run-oauth": ("paid", "human_required"),
    "review-ui": ("local", "human_required"),
    "review-final": ("local", "human_required"),
    "tts-rehearse": ("external", "human_required"),
}
_STAGE_OWNERS = {
    "agent": ("director", None),
    "visual": ("visual", "visual"),
    "voice": ("audio", "audio"),
    "design": ("post", "post"),
    "post": ("post", "post"),
    "deliver": ("delivery", None),
    "done": ("delivery", None),
}


def responsibility_for_action(action: dict[str, Any] | None) -> dict[str, str | None]:
    """Return the single accountable owner for a routed action."""
    explicit = (action or {}).get("responsibility")
    if isinstance(explicit, dict) and isinstance(explicit.get("owner"), str):
        return {
            "owner": explicit["owner"],
            "department": explicit.get("department")
            if isinstance(explicit.get("department"), str)
            else None,
            "stage": explicit.get("stage")
            if isinstance(explicit.get("stage"), str)
            else str((action or {}).get("stage") or "agent"),
        }
    stage = str((action or {}).get("stage") or "agent")
    owner, department = _STAGE_OWNERS.get(stage, ("director", None))
    return {"owner": owner, "department": department, "stage": stage}


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
    # P0: `aifilm pilot pack` shares the pilot CLI but only writes GO evidence.
    if operation == "pilot" and len(argv) >= 2 and argv[1] == "pack":
        operation = "pilot-pack"
        if not action_id or action_id == "pilot":
            action_id = "pilot-pack"
    skill_id = _ACTION_SKILLS.get(action_id, "dispatch.orchestrate")
    spend_class, approval_class = _SKILL_POLICIES.get(skill_id, ("local", "none"))
    command_policy = _COMMAND_POLICIES.get(operation)
    if command_policy is not None:
        spend_class, approval_class = command_policy
    if operation == "plan" and "lock" in argv:
        approval_class = "human_required"
    # pilot approve/score/report stay human; only pack is local-none (above remap).
    if operation == "pilot":
        approval_class = "human_required"
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
        "responsibility": responsibility_for_action(action),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload["transaction_id"] = f"tx-{digest[:24]}"
    return payload


def bind_action_to_state(
    action: dict[str, Any] | None,
    *,
    root: Path,
    state_hash: str,
) -> dict[str, Any] | None:
    if action is None:
        return None
    bound = dict(action)
    payload = dict(bound)
    payload.pop("transaction_id", None)
    payload["project_root"] = str(Path(root).expanduser().resolve())
    payload["state_hash"] = state_hash
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    bound["state_hash"] = state_hash
    bound["transaction_id"] = f"tx-{digest[:24]}"
    return bound


def skill_scripts() -> Path:
    return Path(__file__).resolve().parent


def _capability_cache_key(root: Path, i2v_profile: str) -> str:
    digest = hashlib.sha256(i2v_profile.encode("utf-8"))
    inputs = [
        skill_scripts().parent / "runtime-lock.json",
        skill_scripts().parent / "config.env",
        skill_scripts().parent / "config.env.example",
        root / "film-spec.json",
    ]
    for path in inputs:
        digest.update(str(path.name).encode("utf-8"))
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"missing")
    return digest.hexdigest()


def _safe_capability_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: report.get(key)
        for key in (
            "ok",
            "error",
            "recommendations",
            "tts",
            "frw",
            "grok_oauth",
            "music",
            "suggested_film_spec_patch",
        )
        if key in report
    }


def _capability_report_cached(
    root: Path,
    *,
    i2v_profile: str,
    refresh: bool,
    write_cache: bool,
    ttl_sec: int = 600,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from capability_report import build_capability_report

    cache_path = root / "receipts" / "capability-cache.json"
    cache_key = _capability_cache_key(root, i2v_profile)
    now = time.time()
    cached = read_json(cache_path)
    if (
        not refresh
        and isinstance(cached, dict)
        and cached.get("cache_key") == cache_key
        and now - float(cached.get("cached_at_epoch") or 0) <= ttl_sec
        and isinstance(cached.get("report"), dict)
    ):
        return dict(cached["report"]), {
            "hit": True,
            "ttl_sec": ttl_sec,
            "age_sec": round(now - float(cached.get("cached_at_epoch") or now), 3),
            "cached_at_epoch": float(cached.get("cached_at_epoch") or 0),
            "cache_key": cache_key,
        }

    report = build_capability_report(root=root, run_canary=False, suggest_i2v=False)
    safe = _safe_capability_report(report)
    if write_cache and safe.get("ok") is not False:
        write_json(
            cache_path,
            {
                "schema_version": 1,
                "kind": "capability-cache",
                "cached_at_epoch": now,
                "cache_key": cache_key,
                "ttl_sec": ttl_sec,
                "report": safe,
            },
        )
    return safe, {
        "hit": False,
        "ttl_sec": ttl_sec,
        "age_sec": 0,
        "cached_at_epoch": now,
        "cache_key": cache_key,
    }


def _cached_packet_is_reusable(
    packet: dict[str, Any],
    *,
    state_hash: str,
    include_capability: bool,
    refresh_capability: bool,
) -> bool:
    if refresh_capability or packet.get("state_hash") != state_hash:
        return False
    action = packet.get("next_action") if isinstance(packet.get("next_action"), dict) else {}
    if action.get("spend_class") != "local" or action.get("approval_class") == "human_required":
        return False
    if not include_capability:
        return True
    cap_cache = (
        packet.get("capability_cache") if isinstance(packet.get("capability_cache"), dict) else {}
    )
    cached_at = float(cap_cache.get("cached_at_epoch") or 0)
    ttl_sec = int(cap_cache.get("ttl_sec") or 600)
    return cached_at > 0 and time.time() - cached_at <= ttl_sec


def build_dispatch(
    root: Path,
    *,
    gates: dict[str, Any] | None = None,
    open_reshoot_count: int = 0,
    include_capability: bool = True,
    write_receipt: bool = True,
    refresh_capability: bool = False,
    use_state_cache: bool = True,
) -> dict[str, Any]:
    """Assemble auto-dispatch packet for agent orchestration."""
    started = time.perf_counter()
    root = Path(root).expanduser().resolve()
    scripts = skill_scripts()
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))

    from dispatch_compact import compute_state_hash
    from scene_sound import reconcile as reconcile_scene_sound

    gates = gates or {}
    scene_sound = reconcile_scene_sound(root, write=write_receipt)
    state_hash = compute_state_hash(
        root,
        gates=gates,
        open_reshoot_count=open_reshoot_count,
    )
    receipt_path = root / "receipts" / "dispatch.json"
    previous = read_json(receipt_path) if use_state_cache else None
    if (
        isinstance(previous, dict)
        and _cached_packet_is_reusable(
            previous,
            state_hash=state_hash,
            include_capability=include_capability,
            refresh_capability=refresh_capability,
        )
        and "weapon_route" in previous
    ):
        packet = dict(previous)
        packet["scene_sound"] = scene_sound
        packet["at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
        packet["metrics"] = {
            "build_elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "state_cache_hit": True,
            "capability_cache_hit": bool((packet.get("capability_cache") or {}).get("hit", True)),
        }
        if write_receipt:
            write_json(receipt_path, packet)
            packet["receipt_path"] = str(receipt_path)
        return packet

    from craft_spine import craft_status_report, detect_craft_stage
    from narrative_control import control_status
    from next_actions import build_next_actions, detect_pipeline_stage
    from production_evidence import build_evidence

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

    spec_for_routing = read_json(root / "film-spec.json") or {}
    routed_shots = (
        spec_for_routing.get("shots") if isinstance(spec_for_routing.get("shots"), list) else []
    )
    shots_are_timed = bool(routed_shots) and all(
        isinstance(shot, dict)
        and str(shot.get("id") or shot.get("shot_id") or "").strip()
        and isinstance(shot.get("duration_sec"), (int, float))
        and not isinstance(shot.get("duration_sec"), bool)
        and float(shot["duration_sec"]) > 0
        for shot in routed_shots
    )
    scene_sound_is_due = bool(shots_are_timed and spec_for_routing.get("audio_timeline_v1"))
    if scene_sound_is_due and scene_sound.get("status") != "ok":
        summary = scene_sound.get("summary") or {}
        pre(
            "scene-sound-plan",
            f'aifilm audio-plan --root "{r}" --compile --validate',
            "场景声音待办："
            f"required={summary.get('required', 0)} / blocked={summary.get('blocked', 0)} / "
            f"needs_review={summary.get('needs_review', 0)}；先补环境音、脚步、门或道具拟音",
            "voice",
        )
    elif scene_sound.get("status") != "ok":
        summary = scene_sound.get("summary") or {}
        actions.append(
            {
                "id": "scene-sound-plan",
                "cmd": f'aifilm audio-plan --root "{r}" --compile --validate',
                "why": (
                    "场景声音已发现但尚未到声音阶段："
                    f"required={summary.get('required', 0)} / "
                    f"blocked={summary.get('blocked', 0)}；先完成故事、镜头与投影"
                ),
                "stage": "voice",
                "stage_label": "voice",
                "source": "deferred_scene_sound",
            }
        )

    # Action motion profile.  Capability checks may skip an unready lane, but
    # the policy order remains FRW LTX → FRW API I2V → Grok Video 1.5.
    i2v_profile = "ltx23_primary"
    try:
        from film_spec import resolve_i2v_profile

        i2v_profile = resolve_i2v_profile()
    except Exception:
        pass

    # Capability hygiene once per media-ish ring
    if craft_stage in {"shots", "media", "selects", "rough", "verified"}:
        canary = root / "receipts" / "frw-key-capability.json"
        if i2v_profile == "ltx23_primary":
            if craft_stage in {"shots", "media"}:
                pre(
                    "action-i2v-chain",
                    f"# Motion: FRW LTX 2.3 → FRW API img2video → Grok Video 1.5  (profile={i2v_profile})",
                    "动作镜按固定优先级逐级探测；未就绪可跳过，已启动路线只在明确技术失败后签名降级",
                    "visual",
                )
        elif i2v_profile == "grok_primary":
            if craft_stage in {"shots", "media"}:
                pre(
                    "grok-i2v-bulk",
                    f"# Media: i2v_provider=grok · image_edit(cast) still → media-queue image_to_video 720p → register-clip --source-endpoint image_to_video  (profile={i2v_profile}; Seedance off)",
                    "Grok 为人物动主力；FRW 仅在明确技术失败后 fallback，不提交默认 FRW bulk",
                    "visual",
                )
        elif i2v_profile == "hybrid_h3":
            if craft_stage in {"shots", "media"}:
                pre(
                    "hybrid-h3-lanes",
                    f"# Dual lane (profile={i2v_profile}): bulk Grok media-queue · restricted/meat → aifilm h3 plan|run --register (comfy-h3 film-lane ≤8s; prefer_native; pilot approval for bulk)",
                    "云 bulk 仍 Grok；敏感/肉戏 soft-lock 本地 MiniMax H3 film-lane；原声可用则保留",
                    "visual",
                )
        else:
            # Never make an FRW canary a normal Grok-primary step.  A typed
            # upload-probe is requested only after a provider-switch receipt.
            if craft_stage == "media" and canary.is_file():
                pre(
                    "frw-fallback-review",
                    f'aifilm manifest preflight --root "{r}"',
                    "仅在已有 provider-switch receipt 时审计 FRW fallback 的输入/合同/媒体绑定",
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
    from workflow_spine import build_workflow_status

    workflow = build_workflow_status(root, gates=gates, narrative=narrative)
    professional_stage = str(workflow.get("current_stage") or "")
    if workflow.get("mode") == "professional":
        if professional_stage and workflow.get("readiness", {}).get(professional_stage):
            pre(
                "workflow-stage-lock",
                (
                    f'aifilm director lock-stage --root "{r}" --stage {professional_stage} '
                    '--approver user --user-phrase "<VERBATIM_USER_APPROVAL>"'
                ),
                (
                    "Professional：原生证据已齐；由使用者批准当前 hash 后锁定 "
                    f"{professional_stage}，再进入下一阶段"
                ),
                "agent",
            )
        elif professional_stage == "concept_lock":
            pre(
                "workflow-concept",
                "# StoryReception → aifilm plan run --received-file <receipt>",
                "Professional 1/11：先接收并确认故事命题；未形成 canonical drama-graph 前不进入视觉",
                "agent",
            )
        elif professional_stage == "dailies_review":
            pre(
                "selects-report",
                f'aifilm selects --root "{r}"',
                "Professional 7/11：逐镜 review 已齐，写入当前 Selects 证据后才能粗剪",
                "visual",
            )
        elif professional_stage == "selects_rough_cut":
            pre(
                "rough-cut-review",
                f'aifilm editor-cut --root "{r}"',
                "Professional 8/11：检查 active take、时长与 Continue 接戏，形成粗剪证据",
                "post",
            )
        elif professional_stage == "picture_lock":
            pre(
                "picture-lock-review",
                f'aifilm review-ui serve --root "{r}"',
                "Professional 9/11：在本机审核预览/粗剪，批准当前 hash 后锁定画面",
                "post",
            )
        elif professional_stage == "post_locks":
            if not (root / "post-plan.json").is_file():
                pre(
                    "post-plan-init",
                    f'aifilm post-plan --root "{r}" init --owner hyperframes',
                    "Professional 10/11：先固定唯一 post/caption owner",
                    "post",
                )
            elif not (root / "receipts" / "tts-rehearsal.json").is_file():
                pre(
                    "tts-rehearse",
                    f'aifilm tts-rehearse --root "{r}" --backend edge',
                    "Professional 10/11：先锁定中文旁白/日文角色的实测声音时间",
                    "voice",
                )
            else:
                pre(
                    "post-lock-review",
                    f'aifilm review-ui serve --root "{r}"',
                    "Professional 10/11：审核声音与后期输入 hash 后再渲染母版候选",
                    "post",
                )
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
    # A3: when a plate exists, prefer closeout chain over scattered review/post-audit cmds
    plate_exists = any(
        (root / rel).is_file()
        for rel in (
            "out/film_final.mp4",
            "out/film_hyperframes.mp4",
            "out/final.mp4",
            "final.mp4",
        )
    )
    if not plate_exists:
        man_out = read_json(root / "manifest.json") or {}
        ff = (
            ((man_out.get("outputs") or {}).get("final_film") or {})
            if isinstance(man_out, dict)
            else {}
        )
        raw_ff = str(ff.get("path") or "").strip()
        if raw_ff:
            pff = Path(raw_ff)
            plate_exists = pff.is_file() if pff.is_absolute() else (root / pff).is_file()
    if plate_exists and craft_stage in {"post", "verified", "design"} and not post_audit_gate:
        pre(
            "closeout-run",
            f'aifilm closeout run --root "{r}"',
            "plate exists — run closeout chain (heat → review-final gate → post-audit → export next)",
            "post",
        )
    elif craft_stage in {"post", "verified"} and not post_audit_gate:
        pre(
            "post-audit-gate",
            f'aifilm post-audit --root "{r}"',
            "final delivery requires a current post-audit receipt with no hard failures",
            "post",
        )
    # P1: after plate, if final not human-approved, fill assist scorecard (local none)
    if plate_exists and not gates.get("final_complete"):
        assist_rec = read_json(root / "receipts" / "agent-review-final.json") or {}
        assist_fresh = (
            isinstance(assist_rec, dict)
            and assist_rec.get("kind") == "agent-review-final"
            and assist_rec.get("ok") is True
        )
        if not assist_fresh:
            pre(
                "agent-review-final",
                f'aifilm agent-review-final --root "{r}"',
                "P1 L0 assist draft for review-final (never auto-approve; human still signs)",
                "post",
            )
    # Wave F · design-time variety + bulk door before media (agent loop glue)
    if craft_stage in {"shots", "agent"} and gates.get("spec") and not gates.get("clips_complete"):
        variety_rec = read_json(root / "receipts" / "variety-precheck.json") or {}
        if variety_rec.get("ok") is not True:
            pre(
                "variety-precheck",
                f'aifilm variety-precheck --root "{r}"',
                "设计期抗无聊矩阵未绿 — 先 variety-precheck 再 still/I2V（bulk 后返工更贵）",
                "agent",
            )
    if craft_stage in {"media", "shots", "selects"} and gates.get("spec"):
        try:
            from production_gates import load_pilot_approval, pilot_is_user_approved

            pilot_ok_now = pilot_is_user_approved(load_pilot_approval(root))
        except Exception:
            pilot_ok_now = False
        if pilot_ok_now and not gates.get("clips_complete"):
            bulk_rec = read_json(root / "receipts" / "bulk-preflight.json") or {}
            if bulk_rec.get("ok") is not True:
                pre(
                    "bulk-preflight",
                    f'aifilm bulk-preflight --root "{r}" --no-tunnel',
                    "pilot 已批但 bulk-preflight 未绿 — 单门过闸后再 media-queue bulk",
                    "visual",
                )
    # Wave H · after clips: select-shortlist once (multi-take preferred, never deletes)
    if craft_stage in {"selects", "media", "rough"} and gates.get("clips_complete"):
        sel_rec = read_json(root / "receipts" / "select-shortlist.json") or {}
        takes_dir = root / "takes"
        has_takes = takes_dir.is_dir() and any(takes_dir.rglob("*.mp4"))
        if has_takes and not sel_rec.get("shots"):
            pre(
                "select-shortlist",
                f'aifilm select-shortlist --root "{r}"',
                "clips 齐且有 takes — 先 select-shortlist 标 preferred（不删 take）再粗剪/final",
                "visual",
            )
    # Phase B · motion-core surface: DF-aware gate + film-core advisory after clips
    if craft_stage in {"selects", "media", "rough", "post"} and gates.get("clips_complete"):
        gate_rec = read_json(root / "receipts" / "i2v-final-gate.json") or {}
        if gate_rec.get("ok") is not True:
            pre(
                "i2v-motion-gate",
                f'aifilm i2v-motion-gate --root "{r}" --write',
                "clips 齐但 i2v-final-gate 未绿 — 从 film-spec 自动填 DF 后跑 motion gate",
                "visual",
            )
    if craft_stage in {"post", "deliver", "rough"} and (
        gates.get("clips_complete") or gates.get("final_complete")
    ):
        fc = read_json(root / "receipts" / "film-core-closeout.json") or {}
        if fc and fc.get("ok") is False:
            pre(
                "film-core-closeout",
                f'aifilm closeout status --root "{r}"  # film_core advisory',
                "电影核审计未绿（DF/want/spine）— advisory，修 spec 或重装 spine 收据",
                "post",
            )
        elif not fc and gates.get("final_complete"):
            pre(
                "film-core-closeout",
                f'aifilm closeout status --root "{r}"',
                "final 已齐但尚无 film-core-closeout — closeout status 会写 advisory 审计",
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
    competition_receipts = root / "receipts" / "dialogue-competitions"
    if competition_receipts.is_dir():
        pending_candidate_reviews: list[str] = []
        for receipt_path in sorted(competition_receipts.glob("*.json")):
            receipt = read_json(receipt_path)
            if not isinstance(receipt, dict):
                continue
            if (
                isinstance(receipt.get("provisional_selection"), dict)
                and (receipt.get("approval") or {}).get("status") != "approved"
            ):
                pending_candidate_reviews.append(str(receipt.get("shot_id") or receipt_path.stem))
        if pending_candidate_reviews:
            pre(
                "dialogue-candidate-review",
                f'aifilm review-ui --root "{r}"',
                (
                    f"{len(pending_candidate_reviews)} 个讲话镜已有 provisional winner，"
                    "必须完整观看并人工批准，败选素材不得进入 final"
                ),
                "visual",
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
    from workflow_spine import prioritize_actions, professional_stage_actions

    actions = prioritize_actions(workflow, unique)[:10]
    actions = professional_stage_actions(root, workflow, actions)

    # Wave 5: heat status before primary selection so next_cmd can be heat-boost
    heat_status: dict[str, Any] | None = None
    try:
        from heat_check import heat_agent_status

        heat_status = heat_agent_status(root)
        if (
            workflow.get("current_stage") != "complete"
            and heat_status.get("active")
            and (heat_status.get("hard_fail") or heat_status.get("needs_boost"))
            and heat_status.get("next_cmd")
        ):
            heat_action = {
                "id": "heat-boost",
                "cmd": heat_status["next_cmd"],
                "why": heat_status.get("why") or "adult max impact/ecchi 未拉满 — 先 heat boost",
                "stage": "agent",
                "stage_label": "0·叙事尺度",
                "source": "heat_agent_status",
            }
            # Prefer heat over bulk when hard_fail; still surface when only needs_boost
            actions = [a for a in actions if a.get("id") != "heat-boost"]
            actions.insert(0, heat_action)
    except Exception:
        heat_status = None

    provisional_primary = (
        actions[0]
        if workflow.get("mode") == "professional" and actions
        else next(
            (action for action in actions if structured_next_action(action) is not None),
            None,
        )
    )
    provisional_action = structured_next_action(provisional_primary)
    requires_live_capability = bool(
        provisional_action
        and (
            provisional_action.get("spend_class") != "local"
            or provisional_action.get("approval_class") == "human_required"
        )
    )
    cap: dict[str, Any] | None = None
    capability_cache: dict[str, Any] = {
        "hit": False,
        "ttl_sec": 600,
        "cached_at_epoch": 0,
        "skipped": not include_capability,
    }
    if include_capability:
        try:
            cap, capability_cache = _capability_report_cached(
                root,
                i2v_profile=i2v_profile,
                refresh=bool(refresh_capability or requires_live_capability),
                write_cache=write_receipt,
            )
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
            capability_cache = {
                "hit": False,
                "ttl_sec": 600,
                "cached_at_epoch": 0,
                "error": str(exc)[:200],
            }

    primary = (
        actions[0]
        if workflow.get("mode") == "professional" and actions
        else next(
            (action for action in actions if structured_next_action(action) is not None),
            None,
        )
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
        # Wave 4/5: surface heat boost already selected as primary (see pre-primary insert)
        if (
            heat_status
            and heat_status.get("active")
            and (heat_status.get("hard_fail") or heat_status.get("needs_boost"))
            and heat_status.get("next_cmd")
        ):
            agent_do.insert(
                0,
                f"优先尺度：{heat_status['next_cmd']}  # impact={heat_status.get('grade')}:{heat_status.get('score')}",
            )
            agent_do.insert(
                1,
                "成人 MAX：尺度+完整办事弧 ＞ 一切装饰；禁静默降 heat_scale；"
                "heat hard_fail 时 media-queue 硬拦",
            )
    if quality["failed_count"]:
        agent_do.append(
            "质量硬拦：先修复 quality receipt 中的 hero/keyframe 阻塞，再允许该镜头重新 I2V"
        )
    agent_do.append("禁止：自批 pilot、静默改 i2v_provider、Ken Burns 当戏、说书默认 lipsync")
    agent_do.append("用户说「可以/ok/一路做完」才 pilot approve / run_to_completion")

    # Fallback routing summary for media + Grok Build native tools
    i2v_line = (
        "ltx23_primary: still=image_edit(cast) · motion=FRW LTX 2.3 → "
        "FRW API img2video → Grok Video 1.5"
        if i2v_profile == "ltx23_primary"
        else "grok_primary: still=image_edit(cast) · motion=image_to_video · "
        "FRW Wan/local only after readiness or technical-failure gates"
    )
    routing = {
        "tts_default": "edge",
        "tts_quality": "voicebox if app up",
        "bgm": "film audio → skill assets/bgm → procedural rnb",
        "lipsync": "off default; canary after backend-lock",
        "i2v_profile": i2v_profile,
        "i2v": i2v_line,
        "env_plate": "FRW LTX no-face path first; then Grok and verified local fallback",
        "lipsync_frw": "FRW lipsync is fallback-only; upload-probe and new receipt required",
        "ref": "references/frw-lipsync.md · ltx-env-plate.md · i2v-grok-primary.md",
        "grok_build": {
            "host": "Grok Build session (native tools)",
            "oauth": "aifilm grok-oauth doctor — ~/.grok/auth.json SuperGrok path",
            "text": "Reasoning + structured JSON → brief / director_intent / beats / film-spec",
            "tools": "web_search · x_* · shell/aifilm · optional MCP collections",
            "image": "image_gen · image_edit(cast); batch: grok-oauth image|image-edit",
            "video": "SECOND: image_to_video after FRW LTX; batch OAuth: grok-oauth video --image kf --wait",
            "voice": "session chat ≠ VO; default Edge（旁白中文、角色日文）；其他后端须显式选择并留回执",
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

    # Collectors above may prepend a stricter action (notably state-index).
    # Re-select after collection so next_action and weapon routing cannot keep
    # pointing at a stale bulk action.
    primary = (
        actions[0]
        if workflow.get("mode") == "professional" and actions
        else next(
            (action for action in actions if structured_next_action(action) is not None),
            None,
        )
    )
    next_cmd = (primary or {}).get("cmd")
    next_id = (primary or {}).get("id")
    next_why = (primary or {}).get("why")
    agent_do.append(f"最终 next_action={next_id or 'none'}：{next_why or '—'}")

    # Phase 1+2: Vertical Drama Graph + Execution jobs summary (non-breaking)
    graph_digest: dict[str, Any] | None = None
    jobs_summary: dict[str, Any] | None = None
    try:
        from drama_graph import build_jobs_summary, graph_status

        # Dispatch is observation-only: deriving a canonical graph here can make
        # the already-selected write-spec action stale before it executes.
        graph_digest = graph_status(root, auto_derive=False)
        jobs_summary = build_jobs_summary(
            root,
            craft_stage=craft_stage,
            auto_derive=False,
        )
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

    from weapon_router import build_weapon_route

    weapon_route = build_weapon_route(
        root,
        workflow=workflow,
        primary_job=primary_job,
        primary_action=primary,
    )
    if weapon_route.get("status") == "ready":
        agent_do.append(
            "检测到未锁定的静帧需求：按 weapon_route 自动使用已验证本地武器；"
            "执行时先实时读取模型，失败即停止，不静默换供应商"
        )
    elif weapon_route.get("status") == "blocked":
        agent_do.append(f"武器库阻断：{weapon_route.get('reason')}；未验证能力不得替代")

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
    # Bind after all collectors have read the project so the action represents
    # the exact state returned in this packet.
    state_hash = compute_state_hash(
        root,
        gates=gates,
        open_reshoot_count=open_reshoot_count,
    )
    next_action = bind_action_to_state(
        structured_next_action(primary, context=action_context),
        root=root,
        state_hash=state_hash,
    )
    responsibility = responsibility_for_action(primary)
    department_handoff: dict[str, Any] | None = None
    department = responsibility.get("department")
    if isinstance(department, str):
        try:
            from department_cli import handoff_department

            department_handoff = handoff_department(root, department)
        except (FileNotFoundError, ValueError) as exc:
            department_handoff = {
                "ok": False,
                "to": department,
                "owner": responsibility["owner"],
                "blocked_by": [{"id": department, "reason": "handoff_unavailable"}],
                "error": str(exc),
            }
    agent_do.insert(2, f"本动作负责人：{responsibility['owner']}")
    if department_handoff is not None and department_handoff.get("ok") is False:
        blockers = department_handoff.get("blocked_by") or []
        agent_do.append(f"部门交接未就绪：{blockers}；不得越过上游锁定")
    try:
        from generation_usage import usage_status

        usage_report = usage_status(root)
        generation_usage = {
            "tracking_status": usage_report.get("tracking_status"),
            "requests_total": usage_report.get("requests_total"),
            "operation_counts": usage_report.get("operation_counts"),
            "cost_in_usd_ticks": usage_report.get("cost_in_usd_ticks"),
            "cost_usd": usage_report.get("cost_usd"),
            "unknown_cost_requests": usage_report.get("unknown_cost_requests"),
            "token_reported_requests": usage_report.get("token_reported_requests"),
        }
    except (OSError, ValueError):
        generation_usage = {
            "tracking_status": "unavailable",
            "requests_total": 0,
            "unknown_cost_requests": 0,
        }

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
        "responsibility": responsibility,
        "department_handoff": department_handoff,
        "next_why": next_why,
        "next_actions": actions,
        "agent_do": agent_do,
        "agent_instruction": "\n".join(f"- {x}" for x in agent_do),
        "routing": routing,
        "weapon_route": weapon_route,
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
        "workflow": workflow,
        "generation_usage": generation_usage,
        "state_hash": state_hash,
        "capability_cache": capability_cache,
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
        "heat": (
            {
                "active": True,
                "hard_fail": bool(heat_status.get("hard_fail")),
                "needs_boost": bool(heat_status.get("needs_boost")),
                "final_ok": bool(heat_status.get("final_ok")),
                "score": heat_status.get("score"),
                "grade": heat_status.get("grade"),
                "floor": heat_status.get("floor"),
                "target_s": heat_status.get("target_s"),
                "ecchi_score": heat_status.get("ecchi_score"),
                "ecchi_need": heat_status.get("ecchi_need"),
                "codes": heat_status.get("codes") or [],
                "next_cmd": heat_status.get("next_cmd"),
                "why": heat_status.get("why"),
                "line": heat_status.get("line"),
            }
            if heat_status and heat_status.get("active")
            else {"active": False, "reason": (heat_status or {}).get("reason")}
            if heat_status is not None
            else None
        ),
        "scene_sound": scene_sound,
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
            "adult max heat_agent hard_fail blocks media-queue add (Wave 5)",
            "adult max heat final_ok (S-grade) required before final/export (Wave 6)",
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
    packet["metrics"] = {
        "build_elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
        "state_cache_hit": False,
        "capability_cache_hit": bool(capability_cache.get("hit")),
    }

    if write_receipt:
        write_json(receipt_path, packet)
        packet["receipt_path"] = str(receipt_path)
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
