#!/usr/bin/env python3
"""Automatic craft+tool dispatcher for ai-film-grok.

One entry for agents: read craft ring + capability + next actions → single
orchestration packet. Never skips pilot/user gates or silent-mutates film-spec.

  aifilm dispatch --root <film>
  aifilm dispatch --root <film> --print-cmd-only
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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
    from next_actions import build_next_actions, detect_pipeline_stage

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
                    f'# Media: i2v_provider=grok · image_edit(cast) still → media-queue image_to_video 720p → register-clip --source-endpoint image_to_video  (profile={i2v_profile}; Seedance off)',
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
                    f'aifilm frw-lipsync probe  # then: frw-lipsync run --face kf.png --audio vo.wav --shot-id …',
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
            f'# write {r}/receipts/creative-brief.md from templates/creative-brief.example.md',
            "Idea 环：先落 creative-brief（受众/时长/情绪）再 Lens",
            "agent",
        )
    if craft_stage == "story":
        pre(
            "directors-lens",
            f'# Director’s Lens → director_intent.logline/theme in film-spec; optional receipts/directors-lens.md',
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
            "音轨 dry-run：确认 TTS/BGM/lipsync 路径再 final",
            "voice",
        )

    # Merge: prepend craft items not already covered by same id
    existing_ids = {a.get("id") for a in actions}
    merged: list[dict[str, str]] = []
    for p in prepend:
        if p["id"] not in existing_ids:
            merged.append(p)
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

    primary = actions[0] if actions else None
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

    packet = {
        "ok": True,
        "kind": "ai-film-dispatch",
        "schema_version": 1,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
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
        "hard_gates": [
            "write-spec before media-queue",
            "pilot user approve before bulk (>3 shots)",
            "no silent provider switch",
            "final ≠ final_complete without review-final",
        ],
        "ref": "references/craft-spine.md · references/audio-fallback.md",
        "usage": {
            "dispatch": "aifilm dispatch --root <film>",
            "print_cmd": "aifilm dispatch --root <film> --print-cmd-only",
            "loop": "每完成一步再跑 dispatch，直到 craft=verified 且 export",
        },
    }

    if write_receipt:
        path = root / "receipts" / "dispatch.json"
        _write_json(path, packet)
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
