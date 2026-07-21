#!/usr/bin/env python3
"""One-page capability report for ai-film-grok.

Merges TTS / lipsync / runtime-lock / tools readiness with optional FRW canary
receipt summary and I2V film-spec suggestions.

  aifilm capability
  aifilm capability --root <film>
  aifilm capability --root <film> --suggest-i2v
  aifilm capability --root <film> --suggest-i2v --apply
  aifilm capability --root <film> --run-canary   # costs FRW credits

Default never mutates film-spec; never hits FRW unless --run-canary.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FRW_RECEIPT_REL = "receipts/frw-key-capability.json"
SPEC_REL = "film-spec.json"

# Fields we may patch under --apply (nothing else)
APPLY_I2V_KEYS = (
    "i2v_provider",
    "frw_video_model",
    "frw_env_model",
)


class CapabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def skill_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def load_frw_receipt(root: Path) -> dict[str, Any] | None:
    return _read_json(Path(root).expanduser().resolve() / FRW_RECEIPT_REL)


def summarize_frw_receipt(receipt: dict[str, Any] | None) -> dict[str, Any] | None:
    if not receipt:
        return None
    return {
        "present": True,
        "ok": bool(receipt.get("ok")),
        "probed_at": receipt.get("probed_at"),
        "seedance_i2v": receipt.get("seedance_i2v"),
        "ltx_t2v": receipt.get("ltx_t2v"),
        "ltx_i2v": receipt.get("ltx_i2v"),
        "classic_img2video": receipt.get("classic_img2video"),
        "recommended_l1": receipt.get("recommended_l1"),
        "recommended_l2": receipt.get("recommended_l2"),
        "seedance_permission": receipt.get("seedance_permission"),
        "notes": receipt.get("notes"),
        "credits_remaining": receipt.get("credits_remaining"),
        "error": receipt.get("error"),
        "receipt_path": FRW_RECEIPT_REL,
    }


def suggest_i2v_from_canary(
    receipt: dict[str, Any] | None,
    *,
    current_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map FRW canary signals → film-spec patch + rationale.

    Aligns with references/frw-degrade-dispatch.md + i2v profile (grok_primary).
    Does not invent legacy-img2video as default apply target.
    """
    cur = current_spec or {}
    out: dict[str, Any] = {
        "ok": False,
        "has_canary": bool(receipt),
        "patch": {},
        "rationale": [],
        "warnings": [],
        "recommendations": [],
    }
    # Profile gate: Seedance-unavailable season defaults to grok without canary
    try:
        from film_spec import resolve_i2v_profile

        profile = resolve_i2v_profile()
    except Exception:
        profile = "grok_primary"
    out["i2v_profile"] = profile
    if profile == "grok_primary" and not receipt:
        out["ok"] = True
        out["patch"] = {
            "i2v_provider": "grok",
            "frw_env_model": "ltx-t2v",
            "frw_video_model": cur.get("frw_video_model") or "seedance-2-fast-i2v",
        }
        out["rationale"] = [
            "AIFILM_I2V_PROFILE=grok_primary (Seedance unavailable) → L1 Grok image_to_video"
        ]
        out["recommendations"] = [
            "still: image_edit(cast); motion: media-queue image_to_video; "
            "register --source-endpoint image_to_video",
            "env beds optional: frw canary for ltx-t2v only",
            "when Seedance returns: AIFILM_I2V_PROFILE=seedance_first + canary 201",
        ]
        out["changes"] = {
            k: {"from": cur.get(k), "to": v}
            for k, v in out["patch"].items()
            if cur.get(k) != v
        }
        out["current"] = {
            "i2v_provider": cur.get("i2v_provider"),
            "frw_video_model": cur.get("frw_video_model"),
            "frw_env_model": cur.get("frw_env_model"),
            "tts_backend": cur.get("tts_backend"),
        }
        return out
    if not receipt:
        out["recommendations"].append(
            "no FRW canary receipt — run: aifilm frw canary --root <film> "
            "or: aifilm capability --root <film> --run-canary"
        )
        if profile == "grok_primary":
            out["recommendations"].append("or keep i2v_provider=grok without canary")
        return out

    l1 = str(receipt.get("recommended_l1") or "").strip()
    l2 = str(receipt.get("recommended_l2") or "").strip()
    seedance = str(receipt.get("seedance_i2v") or "")
    notes = str(receipt.get("notes") or "")
    patch: dict[str, Any] = {}
    rationale: list[str] = []
    warnings: list[str] = []
    recs: list[str] = []

    if l1 == "seedance-2-fast-i2v" or seedance.startswith("201"):
        patch["i2v_provider"] = "frw"
        patch["frw_video_model"] = "seedance-2-fast-i2v"
        rationale.append("seedance_i2v accepted (201) → L1 FRW Seedance")
    elif l1 == "ltx-i2v":
        patch["i2v_provider"] = "frw"
        patch["frw_video_model"] = "ltx-i2v"
        rationale.append("seedance blocked/unusable; ltx-i2v usable → L1 FRW ltx-i2v")
        warnings.append("ltx-i2v often 502 on some keys — re-canary if bulk fails")
    elif l1 == "grok" or "403" in seedance or "l1_prefer_grok" in notes:
        patch["i2v_provider"] = "grok"
        # Keep frw_video_model documented as aspirational seedance for when key opens
        if not cur.get("frw_video_model"):
            patch["frw_video_model"] = "seedance-2-fast-i2v"
        rationale.append(
            "seedance blocked or recommended_l1=grok → L1 Grok 720p (do not pretend Seedance)"
        )
        recs.append("hero/face shots: Grok image_to_video 720p; re-register with grok endpoint")
        if "frw_only_lifeboat" in notes or "legacy" in notes:
            recs.append(
                "FRW-only lifeboat: explicit frw_video_model=legacy-img2video + WARN "
                "(not auto-applied)"
            )
    else:
        warnings.append(f"unclear L1 from canary (recommended_l1={l1!r} seedance={seedance!r})")
        recs.append("re-run canary with --full or check FRW_API_KEY")

    if l2 == "ltx-t2v" or str(receipt.get("ltx_t2v") or "").startswith("201") or receipt.get(
        "ltx_t2v"
    ) == "completed":
        patch["frw_env_model"] = "ltx-t2v"
        rationale.append("ltx-t2v usable → L2 env beds ltx-t2v")
    elif l2:
        patch["frw_env_model"] = "ltx-t2v" if "ltx" in l2 else l2
        rationale.append(f"recommended_l2={l2}")
        if "legacy" in l2:
            recs.append("L2 fallback: classic text2video for env/bridge/insert")

    # Diff vs current
    changes: dict[str, Any] = {}
    for k, v in patch.items():
        if cur.get(k) != v:
            changes[k] = {"from": cur.get(k), "to": v}

    out["ok"] = bool(patch) and not (warnings and not rationale)
    out["patch"] = patch
    out["changes"] = changes
    out["rationale"] = rationale
    out["warnings"] = warnings
    out["recommendations"] = recs
    out["current"] = {
        "i2v_provider": cur.get("i2v_provider"),
        "frw_video_model": cur.get("frw_video_model"),
        "frw_env_model": cur.get("frw_env_model"),
        "tts_backend": cur.get("tts_backend"),
    }
    return out


def apply_i2v_patch(root: Path, patch: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """Patch only APPLY_I2V_KEYS on film-spec.json. Never silent."""
    root = Path(root).expanduser().resolve()
    spec_path = root / SPEC_REL
    if not spec_path.is_file():
        raise CapabilityError(f"film-spec missing: {spec_path}")
    spec = _read_json(spec_path)
    if not spec:
        raise CapabilityError(f"cannot read film-spec: {spec_path}")

    applied: dict[str, Any] = {}
    for k in APPLY_I2V_KEYS:
        if k not in patch:
            continue
        if spec.get(k) != patch[k]:
            applied[k] = {"from": spec.get(k), "to": patch[k]}
            if not dry_run:
                spec[k] = patch[k]

    if not dry_run and applied:
        # lightweight audit trail on spec (optional metadata; does not affect schema hard fields)
        meta = spec.get("_capability_apply")
        if not isinstance(meta, dict):
            meta = {}
        meta["at"] = utc_now()
        meta["patch"] = {k: v["to"] for k, v in applied.items()}
        spec["_capability_apply"] = meta
        _write_json(spec_path, spec)

    return {
        "ok": True,
        "dry_run": dry_run,
        "spec_path": str(spec_path),
        "applied": applied,
        "note": (
            "re-run write-spec before media-queue"
            if applied and not dry_run
            else ("no field changes" if not applied else "dry_run only")
        ),
    }


def build_capability_report(
    *,
    root: Path | None = None,
    run_canary: bool = False,
    suggest_i2v: bool = False,
    apply: bool = False,
    canary_wait: bool = False,
    canary_full: bool = False,
) -> dict[str, Any]:
    """Assemble one-page capability JSON."""
    scripts = skill_dir() / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))

    recommendations: list[str] = []
    tts_info: dict[str, Any] = {}
    lipsync_info: dict[str, Any] = {}
    runtime: dict[str, Any] = {}
    designed: dict[str, Any] = {}
    music_block: dict[str, Any] = {"source": None, "mood": "rnb", "path": None}

    try:
        from tts_backend import probe as tts_probe  # type: ignore

        tts_info = tts_probe()
    except Exception as exc:  # noqa: BLE001
        tts_info = {"ok": False, "error": str(exc)}

    try:
        from lipsync_backend import probe as lipsync_probe  # type: ignore

        lipsync_info = lipsync_probe()
    except Exception as exc:  # noqa: BLE001
        lipsync_info = {"ok": False, "error": str(exc)}

    try:
        from runtime_policy import verify_runtime_lock  # type: ignore

        sd = skill_dir()
        runtime = verify_runtime_lock(sd, sd / "runtime-lock.json")
    except Exception as exc:  # noqa: BLE001
        runtime = {"ok": False, "error": str(exc)}

    try:
        from compose_render import probe_designed_post_tooling  # type: ignore

        designed = probe_designed_post_tooling()
        designed["ok"] = bool(designed.get("npx") and designed.get("hyperframes_ok"))
    except Exception as exc:  # noqa: BLE001
        designed = {"ok": False, "error": str(exc)[:200]}

    edge_ok = bool((tts_info.get("backends") or {}).get("edge"))
    vb_ok = bool(tts_info.get("voicebox_ok") or (tts_info.get("backends") or {}).get("voicebox"))
    fallback = bool(tts_info.get("voicebox_fallback"))

    tts_summary = {
        "ok": bool(tts_info.get("ok")),
        "preferred": tts_info.get("preferred"),
        "active": tts_info.get("active"),
        "edge": edge_ok,
        "voicebox": vb_ok,
        "voicebox_profile": tts_info.get("voicebox_profile"),
        "voicebox_error": tts_info.get("voicebox_error"),
        "fallback_enabled": fallback,
        "fish": bool((tts_info.get("ready") or {}).get("fish")),
        "minimax": bool((tts_info.get("backends") or {}).get("minimax")),
        "external": bool((tts_info.get("backends") or {}).get("external")),
        "strict_voice_lock": tts_info.get("strict_voice_lock"),
    }

    if edge_ok and not vb_ok:
        recommendations.append(
            "tts: edge ready; start Voicebox + set VOICEBOX_PROFILE for quality/clone path"
        )
    if not fallback and edge_ok:
        recommendations.append(
            "tts: optional AIFILM_TTS_VOICEBOX_FALLBACK=1 for edge→local voicebox on failure"
        )
    if vb_ok and not tts_info.get("voicebox_profile") and not tts_info.get("voicebox_profile_id"):
        recommendations.append("tts: Voicebox up but set VOICEBOX_PROFILE for one-speaker lock")
    if runtime and not runtime.get("ok"):
        recommendations.append(
            "runtime-lock drift — after trusted script edits: aifilm lock-runtime"
        )
    if not designed.get("ok"):
        recommendations.append(
            "designed-post soft: HyperFrames/npx not ready — ffmpeg final still works"
        )

    # skill BGM library presence (global)
    try:
        from sound_plan import MUSIC_TEMPLATE_EXTS, _first_existing_music

        skill_bgm = skill_dir() / "assets" / "bgm"
        skill_hits: list[str] = []
        for mood_name in ("rnb", "warm", "playful", "dark", "default"):
            cands = []
            for ext in MUSIC_TEMPLATE_EXTS:
                cands.append(skill_bgm / mood_name / f"bed{ext}")
                cands.append(skill_bgm / f"{mood_name}{ext}")
            hit = _first_existing_music(cands)
            if hit:
                skill_hits.append(mood_name)
        music_block = {
            "skill_library_dir": str(skill_bgm),
            "skill_moods_present": skill_hits,
            "skill_library_ready": bool(skill_hits),
            "note": "film audio/* wins over skill assets/bgm; missing → procedural",
        }
        if not skill_hits:
            recommendations.append(
                "BGM: place licensed assets/bgm/rnb/bed.wav (+ .license.txt) for shared template"
            )
    except Exception as exc:  # noqa: BLE001
        music_block = {"error": str(exc)[:200]}

    ls_ready = list(lipsync_info.get("ready") or [])
    if not ls_ready:
        w2 = lipsync_info.get("wav2lip_root")
        if w2:
            recommendations.append(
                "lipsync: Wav2Lip path found but not locked — "
                f'backend-lock inspect/lock --backend wav2lip --root "{w2}"'
            )
        else:
            recommendations.append(
                "lipsync: no backend (default off is OK for storyteller)"
            )

    # Grok OAuth (grok login → ~/.grok/auth.json)
    grok_oauth: dict[str, Any] = {"ok": False}
    try:
        from grok_oauth import probe as grok_oauth_probe

        grok_oauth = grok_oauth_probe()
        if grok_oauth.get("ok"):
            recommendations.append(
                "Grok OAuth ready — chat/image API via auth.json; in-session still prefer image_gen/edit tools"
            )
        else:
            recommendations.append(
                "Grok OAuth not ready — run: grok login  (or set XAI_API_KEY)"
            )
    except Exception as exc:  # noqa: BLE001
        grok_oauth = {"ok": False, "error": str(exc)[:200]}

    tools = {
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "edge_tts": edge_ok,
        "npx": bool(shutil.which("npx")),
        "python": sys.executable,
    }
    if not tools["ffmpeg"] or not tools["ffprobe"]:
        recommendations.append("install ffmpeg/ffprobe on PATH")

    frw_block: dict[str, Any] | None = None
    film_block: dict[str, Any] | None = None
    suggest_block: dict[str, Any] | None = None
    apply_block: dict[str, Any] | None = None
    root_resolved: Path | None = None

    if root is not None:
        root_resolved = Path(root).expanduser().resolve()
        if not root_resolved.is_dir():
            raise CapabilityError(f"root not a directory: {root_resolved}")

        if run_canary:
            from frw_canary import run_canary as _run, write_receipt  # type: ignore

            report = _run(wait=canary_wait, full=canary_full)
            path = write_receipt(root_resolved, report)
            report["receipt_path"] = str(path)
            frw_block = summarize_frw_receipt(report)
            frw_block["ran_canary"] = True
            if not report.get("ok"):
                recommendations.append(
                    f"frw canary failed: {report.get('error') or report.get('notes') or 'see receipt'}"
                )
        else:
            receipt = load_frw_receipt(root_resolved)
            frw_block = summarize_frw_receipt(receipt)
            if frw_block is None:
                frw_block = {
                    "present": False,
                    "ok": None,
                    "receipt_path": FRW_RECEIPT_REL,
                    "hint": "aifilm frw canary --root <film> (or capability --run-canary)",
                }
                recommendations.append(
                    "frw: no canary receipt — run before bulk I2V when using FRW key"
                )
            elif not frw_block.get("ok"):
                recommendations.append(
                    "frw canary receipt not ok — re-run canary or switch L1 to Grok per degrade doc"
                )

        spec = _read_json(root_resolved / SPEC_REL)
        if spec:
            film_block = {
                "present": True,
                "i2v_provider": spec.get("i2v_provider"),
                "frw_video_model": spec.get("frw_video_model"),
                "frw_env_model": spec.get("frw_env_model"),
                "tts_backend": spec.get("tts_backend"),
                "vo_voice": spec.get("vo_voice"),
                "title": spec.get("title"),
            }
            # per-film music resolve (dry)
            try:
                from sound_plan import resolve_music_template

                sp = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else {}
                mood = str(sp.get("mood") or "rnb")
                mr = resolve_music_template(root_resolved, mood=mood, plan=sp or None, mode="auto")
                music_block = {
                    **music_block,
                    "film_mood": mood,
                    "resolved": mr,
                    "will_use": "template_or_library" if mr else "procedural",
                }
            except Exception as exc:  # noqa: BLE001
                music_block["film_resolve_error"] = str(exc)[:200]
        else:
            film_block = {"present": False}
            recommendations.append("film-spec.json missing under root")

        if suggest_i2v or apply:
            receipt_full = load_frw_receipt(root_resolved)
            # if we just ran canary, re-load
            if run_canary:
                receipt_full = load_frw_receipt(root_resolved)
            suggest_block = suggest_i2v_from_canary(receipt_full, current_spec=spec or {})
            for r in suggest_block.get("recommendations") or []:
                if r not in recommendations:
                    recommendations.append(r)
            for w in suggest_block.get("warnings") or []:
                recommendations.append(f"warn: {w}")

            if apply:
                if not suggest_i2v:
                    # allow --apply to imply suggest
                    pass
                patch = suggest_block.get("patch") or {}
                if not patch:
                    apply_block = {
                        "ok": False,
                        "error": "no patch from canary — refuse apply",
                    }
                else:
                    apply_block = apply_i2v_patch(root_resolved, patch, dry_run=False)
                    if apply_block.get("applied"):
                        recommendations.append(
                            "applied i2v patch — run: aifilm write-spec --root <film> before queue"
                        )

    # overall ok: core tools + edge TTS; voicebox/frw optional yellow
    core_ok = bool(tools["ffmpeg"] and tools["ffprobe"] and edge_ok)
    report: dict[str, Any] = {
        "ok": core_ok,
        "at": utc_now(),
        "skill_dir": str(skill_dir()),
        "root": str(root_resolved) if root_resolved else None,
        "tts": tts_summary,
        "music": music_block,
        "grok_oauth": {
            "ok": bool(grok_oauth.get("ok")),
            "source": grok_oauth.get("source"),
            "auth_mode": grok_oauth.get("auth_mode"),
            "email": grok_oauth.get("email"),
            "ttl_sec": grok_oauth.get("ttl_sec"),
            "has_imagine_image": grok_oauth.get("has_imagine_image"),
            "has_imagine_video": grok_oauth.get("has_imagine_video"),
            "has_imagine_video_15": grok_oauth.get("has_imagine_video_15"),
            "has_tts": grok_oauth.get("has_tts"),
            "pack": grok_oauth.get("pack"),
            "recommended": grok_oauth.get("recommended"),
            "models": (grok_oauth.get("models") or [])[:12],
            "error": grok_oauth.get("error"),
            "hint": grok_oauth.get("hint"),
        },
        "lipsync": {
            "ok": bool(lipsync_info.get("ok")),
            "env_backend": lipsync_info.get("env_backend"),
            "ready": lipsync_info.get("ready") or [],
            "default": lipsync_info.get("env_backend") or "off",
            "wav2lip_root": lipsync_info.get("wav2lip_root"),
            "musetalk_root": lipsync_info.get("musetalk_root"),
            "next_unlock": (
                None
                if (lipsync_info.get("ready") or [])
                else (
                    f'backend-lock lock --backend wav2lip --root "{lipsync_info.get("wav2lip_root")}" '
                    "--acknowledge-trusted-weights"
                    if lipsync_info.get("wav2lip_root")
                    else "see references/audio-fallback.md"
                )
            ),
        },
        "runtime_lock": {
            "ok": bool(runtime.get("ok")),
            "errors": runtime.get("errors") or ([runtime.get("error")] if runtime.get("error") else []),
        },
        "tools": tools,
        "designed_post": {
            "ok": bool(designed.get("ok")),
            "soft": not bool(designed.get("ok")),
            "error": designed.get("error") or designed.get("soft_warning"),
        },
        "frw": frw_block,
        "film": film_block,
        "suggested_film_spec_patch": (suggest_block or {}).get("patch") if suggest_block else None,
        "i2v_suggest": suggest_block,
        "apply": apply_block,
        "recommendations": recommendations,
        "usage": {
            "doctor": "aifilm doctor",
            "capability": "aifilm capability [--root FILM]",
            "canary": "aifilm frw canary --root FILM",
            "suggest": "aifilm capability --root FILM --suggest-i2v",
            "apply": "aifilm capability --root FILM --suggest-i2v --apply",
            "tts_ab": "aifilm tts-ab --root FILM --shot SHOT01 --backends edge,voicebox",
            "audio_plan": "aifilm audio-plan --root FILM",
            "craft": "aifilm craft status --root FILM",
            "lipsync_canary": "aifilm lipsync-canary --root FILM --shot SHOT",
        },
        "ref": "references/craft-spine.md · references/audio-fallback.md",
    }
    return report


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="capability_report", description="ai-film-grok capability one-pager")
    p.add_argument("--root", default=None)
    p.add_argument("--run-canary", action="store_true")
    p.add_argument("--suggest-i2v", action="store_true")
    p.add_argument("--apply", action="store_true", help="Write suggested i2v fields into film-spec (opt-in)")
    p.add_argument("--canary-wait", action="store_true")
    p.add_argument("--canary-full", action="store_true")
    args = p.parse_args(argv)

    if args.apply and not args.root:
        print(json.dumps({"ok": False, "error": "--apply requires --root"}, ensure_ascii=False))
        return 2
    if args.run_canary and not args.root:
        print(json.dumps({"ok": False, "error": "--run-canary requires --root"}, ensure_ascii=False))
        return 2

    try:
        report = build_capability_report(
            root=Path(args.root) if args.root else None,
            run_canary=bool(args.run_canary),
            suggest_i2v=bool(args.suggest_i2v) or bool(args.apply),
            apply=bool(args.apply),
            canary_wait=bool(args.canary_wait),
            canary_full=bool(args.canary_full),
        )
    except CapabilityError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
