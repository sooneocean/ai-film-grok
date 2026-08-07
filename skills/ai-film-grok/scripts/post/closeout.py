"""Closeout one-shot — plate/final → review → post-audit → optional export.

Wave A1 · workflow optimize: stop hand-rolling 6 commands after a plate exists.
Does **not** auto-approve review-final (human scorecard required).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

RECEIPT_REL = Path("receipts/closeout.json")


def _export_name(root: Path) -> str:
    """Desktop folder name without placeholders (advance-safe)."""
    try:
        from next_actions import _export_desktop_name

        return _export_desktop_name(root)
    except Exception:
        return "GrokFilm"


class CloseoutError(RuntimeError):
    """Hard stop with a single next action for agents."""

    def __init__(
        self,
        message: str,
        *,
        next_cmd: str | None = None,
        required_proof: str | None = None,
        code: str = "CLOSEOUT_BLOCKED",
    ) -> None:
        super().__init__(message)
        self.next_cmd = next_cmd
        self.required_proof = required_proof
        self.code = code


def _root(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _gates(root: Path) -> dict[str, Any]:
    man = read_json(root / "manifest.json") or {}
    raw = man.get("gates") if isinstance(man.get("gates"), dict) else {}
    return dict(raw)


def _final_record(root: Path) -> dict[str, Any] | None:
    man = read_json(root / "manifest.json") or {}
    outputs = man.get("outputs") if isinstance(man.get("outputs"), dict) else {}
    rec = outputs.get("final_film") if isinstance(outputs.get("final_film"), dict) else None
    if rec and rec.get("path"):
        p = Path(str(rec["path"]))
        if not p.is_absolute():
            p = root / p
        if p.is_file():
            return rec
    # plate fallbacks often used before register-final
    for rel in (
        "out/film_final.mp4",
        "out/final.mp4",
        "out/plate.mp4",
        "out/final-plate.mp4",
        "out/film_native_h3.mp4",
    ):
        if (root / rel).is_file():
            return {"path": str(root / rel), "source": "filesystem"}
    return None


def plate_delivery_honesty(root: Path | str) -> dict[str, Any]:
    """S1.4 · detect OFFICIAL_FINAL_PLATE (not master) so closeout never pretends complete.

    I1.3: plate-boring meat mean also marks plate-only (no master).
    """
    base = _root(root)
    plate_markers: list[str] = []
    for rel in (
        "receipts/official-final-report.json",
        "receipts/h3-ship-native.json",
        "receipts/delivery-class.json",
        "receipts/plate-boring-mean.json",
    ):
        data = read_json(base / rel) or {}
        if not isinstance(data, dict):
            continue
        status = str(
            data.get("status")
            or data.get("delivery_class")
            or data.get("kind")
            or ""
        )
        if "OFFICIAL_FINAL_PLATE" in status or status in {
            "h3_ship_native",
            "OFFICIAL_FINAL_PLATE",
        }:
            plate_markers.append(rel)
        if data.get("master_lock") is False and (
            data.get("delivery_class") == "OFFICIAL_FINAL_PLATE"
            or data.get("status") == "OFFICIAL_FINAL_PLATE"
        ):
            if rel not in plate_markers:
                plate_markers.append(rel)
        if data.get("boring") is True or "PLATE_BORING_MEAT_MEAN" in (
            data.get("codes") or []
        ):
            if rel not in plate_markers:
                plate_markers.append(rel)
    boring = False
    try:
        from final.delivery_class import assess_plate_boring_meat_mean

        br = assess_plate_boring_meat_mean(base)
        boring = bool(br.get("boring"))
        if boring and "receipts/i2v-high-motion-audit.json" not in plate_markers:
            plate_markers.append("receipts/i2v-high-motion-audit.json#plate_boring")
    except Exception:  # noqa: BLE001
        pass
    is_plate = bool(plate_markers) or boring
    return {
        "is_official_plate": is_plate,
        "markers": plate_markers,
        "plate_boring": boring,
        "master_eligible": not is_plate,
        "note": (
            "OFFICIAL_FINAL_PLATE is not final_complete; need gate-auto green + review-final"
            if is_plate
            else "no plate-only receipt"
        ),
    }


def _post_audit_current(root: Path) -> dict[str, Any]:
    try:
        from post_audit import audit_freshness

        return audit_freshness(root)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}


def closeout_status(root: Path | str) -> dict[str, Any]:
    """Read-only ladder: heat → plate → final_complete → post-audit → export."""
    base = _root(root)
    gates = _gates(base)
    final_rec = _final_record(base)
    heat: dict[str, Any] = {}
    try:
        from heat_check import heat_agent_status

        heat = heat_agent_status(base) or {}
    except Exception as exc:  # noqa: BLE001
        heat = {"active": False, "error": str(exc)[:160]}

    post = _post_audit_current(base)
    plate = plate_delivery_honesty(base)
    # S1.4: plate-only receipts can never satisfy final_complete
    final_complete_ok = bool(gates.get("final_complete")) and not plate["is_official_plate"]
    if plate["is_official_plate"] and gates.get("final_complete"):
        final_complete_detail = (
            "BLOCKED: gates.final_complete set but delivery is OFFICIAL_FINAL_PLATE "
            f"({', '.join(plate['markers'][:3])}) — not master"
        )
    elif final_complete_ok:
        final_complete_detail = "review-final scorecard approved"
    elif plate["is_official_plate"]:
        final_complete_detail = (
            "plate only (OFFICIAL_FINAL_PLATE); gate-auto green + human review-final required"
        )
    else:
        final_complete_detail = "needs human review-final"
    steps = [
        {
            "id": "heat",
            "ok": not (
                heat.get("active")
                and (heat.get("hard_fail") or heat.get("needs_boost") is True)
                and heat.get("blocks_final", heat.get("hard_fail"))
            ),
            "detail": heat.get("why") or heat.get("error") or "heat ok or inactive",
            "next_cmd": heat.get("next_cmd"),
        },
        {
            "id": "plate_or_final",
            "ok": final_rec is not None,
            "detail": (final_rec or {}).get("path") or "no final/plate mp4",
            "next_cmd": (
                None
                if final_rec
                else f'aifilm final --root "{base}" --lipsync off --music-mood rnb --tts-backend edge'
            ),
        },
        {
            "id": "final_complete",
            "ok": final_complete_ok,
            "detail": final_complete_detail,
            "plate_honesty": plate,
            "next_cmd": (
                None
                if final_complete_ok
                else (
                    f'aifilm gate-auto --root "{base}"  # then review-final'
                    if plate["is_official_plate"]
                    else f'aifilm agent-review-final --root "{base}"'
                )
            ),
            "required_proof": None
            if final_complete_ok
            else (
                "OFFICIAL_FINAL_PLATE ≠ master; gate-auto green + review-final phrase "
                if plate["is_official_plate"]
                else "agent-review-final → --apply --reviewer … --user-phrase 可以 "
                "(never forge phrase; technical gates still apply)"
            ),
        },
        {
            "id": "post_audit",
            "ok": bool(post.get("ok") or post.get("current")),
            "detail": post.get("error") or ("current" if post.get("ok") else "stale or missing"),
            "next_cmd": (
                None
                if (post.get("ok") or post.get("current"))
                else f'aifilm post-audit --root "{base}"'
            ),
        },
        {
            "id": "desktop_exported",
            "ok": bool(gates.get("desktop_exported")),
            "detail": "export-desktop done"
            if gates.get("desktop_exported")
            else "optional export remaining",
            "next_cmd": (
                None
                if gates.get("desktop_exported")
                else f'aifilm export-desktop --root "{base}" --name "{_export_name(base)}"'
            ),
        },
    ]
    # Soft heat: if active hard_fail for final, mark heat not ok more clearly
    if heat.get("active") and heat.get("hard_fail"):
        steps[0]["ok"] = False
        steps[0]["detail"] = heat.get("why") or "heat hard_fail"
        steps[0]["next_cmd"] = heat.get("next_cmd") or f'aifilm heat boost --root "{base}" --apply'
        steps[0]["required_proof"] = "heat_agent_status.hard_fail cleared"

    # P0-B · caption pixel ink (SRT cues → bottom-band has soup). Soft until plate/final exists.
    caption_step: dict[str, Any] = {
        "id": "caption_pixel",
        "ok": False,
        "detail": "missing caption-pixel-check",
        "next_cmd": f'aifilm caption-pixel-check --root "{base}"',
        "advisory": False,
    }
    srt_present = any((base / rel).is_file() for rel in ("out/final.srt", "final.srt"))
    if final_rec is None:
        caption_step = {
            "id": "caption_pixel",
            "ok": True,
            "detail": "skipped — no final/plate yet",
            "next_cmd": None,
            "advisory": True,
            "skipped": True,
        }
    elif not srt_present:
        caption_step = {
            "id": "caption_pixel",
            "ok": True,
            "detail": "skipped — no final.srt (no dialogue cues to probe)",
            "next_cmd": None,
            "advisory": True,
            "skipped": True,
        }
    else:
        try:
            from caption_pixel_check import caption_pixel_status

            cap = caption_pixel_status(base)
            caption_step = {
                "id": "caption_pixel",
                "ok": bool(cap.get("ok")),
                "detail": cap.get("detail") or ("ok" if cap.get("ok") else "pixel red"),
                "next_cmd": None
                if cap.get("ok")
                else (cap.get("next_cmd") or caption_step["next_cmd"]),
                "advisory": False,
                "stale": bool(cap.get("stale")),
                "missing_ink": bool(cap.get("missing_ink")),
                "skipped": bool(cap.get("skipped")),
            }
        except Exception as exc:  # noqa: BLE001
            caption_step = {
                "id": "caption_pixel",
                "ok": False,
                "detail": str(exc)[:200],
                "next_cmd": f'aifilm caption-pixel-check --root "{base}"',
                "advisory": False,
            }
    steps.append(caption_step)

    # S1.4 · plate ≠ master: OFFICIAL_FINAL_PLATE must not pair with final_complete
    plate_step: dict[str, Any] = {
        "id": "plate_vs_master",
        "ok": True,
        "detail": "no plate/master conflict",
        "next_cmd": None,
        "advisory": True,
    }
    try:
        from final.delivery_class import plate_blocks_final_complete

        plate_adv = plate_blocks_final_complete(base, gates=gates)
        plate_step = {
            "id": "plate_vs_master",
            "ok": bool(plate_adv.get("ok")),
            "detail": plate_adv.get("note") or ("ok" if plate_adv.get("ok") else "plate conflict"),
            "next_cmd": None
            if plate_adv.get("ok")
            else f'aifilm gate-auto --root "{base}"  # then review-final; plate≠master',
            "advisory": True,
            "codes": list(plate_adv.get("codes") or []),
            "is_plate": bool(plate_adv.get("is_plate")),
            "blocks_ship_complete": bool(plate_adv.get("blocks_ship_complete")),
            "required_proof": (
                None
                if plate_adv.get("ok")
                else "gate-auto green + human review-final; clear plate-only final_complete"
            ),
        }
        # If plate claims final_complete, fail closed on this step (blocks overall ok)
        if plate_adv.get("blocks_ship_complete"):
            plate_step["advisory"] = False
            plate_step["ok"] = False
    except Exception as exc:  # noqa: BLE001
        plate_step = {
            "id": "plate_vs_master",
            "ok": True,
            "detail": f"plate advisory probe failed: {exc}"[:160],
            "next_cmd": None,
            "advisory": True,
            "skipped": True,
        }
    steps.append(plate_step)

    # P0-C · evidence stale after final rewrite (quality-report / caption)
    evidence_step: dict[str, Any] = {
        "id": "evidence_fresh",
        "ok": True,
        "detail": "ok",
        "next_cmd": None,
        "advisory": True,
    }
    try:
        from caption_pixel_check import evidence_stale_after_final

        ev = evidence_stale_after_final(base)
        evidence_step = {
            "id": "evidence_fresh",
            "ok": bool(ev.get("ok")),
            "detail": (
                "ok"
                if ev.get("ok")
                else "; ".join(
                    str(i.get("code") or i.get("detail")) for i in (ev.get("issues") or [])
                )
                or "stale evidence"
            ),
            "next_cmd": None
            if ev.get("ok")
            else (ev.get("next_cmd") or f'aifilm caption-pixel-check --root "{base}"'),
            "advisory": False,
            "actions": ev.get("actions") or [],
            "honest_limits": ev.get("honest_limits") or [],
            "mix_partial": bool(ev.get("mix_partial")),
        }
        # mix partial is honesty flag, not hard block by itself
        if ev.get("mix_partial") and ev.get("ok"):
            evidence_step["detail"] = "ok; " + "; ".join(ev.get("honest_limits") or ["mix partial"])
            evidence_step["advisory"] = True
    except Exception as exc:  # noqa: BLE001 — AF6: probe crash must not fake green when final exists
        has_final = final_rec is not None
        evidence_step = {
            "id": "evidence_fresh",
            "ok": not has_final,
            "detail": (
                f"evidence probe failed: {exc}"[:160]
                if has_final
                else f"advisory skip (no final): {exc}"[:160]
            ),
            "next_cmd": (f'aifilm caption-pixel-check --root "{base}"' if has_final else None),
            "advisory": not has_final,
            "probe_error": True,
        }
    steps.append(evidence_step)

    # AF3 · post-doctor hard codes on the closeout ladder (MIX_PARTIAL stays soft inside doctor)
    post_doctor_step: dict[str, Any] = {
        "id": "post_doctor",
        "ok": True,
        "detail": "skipped — no final/plate yet",
        "next_cmd": None,
        "advisory": True,
        "skipped": True,
    }
    if final_rec is not None:
        try:
            from post_doctor import run_post_doctor

            doctor = run_post_doctor(base, write=True)
            hard = list(doctor.get("hard") or [])
            soft = list(doctor.get("soft") or [])
            hard_codes = [str(i.get("code") or "") for i in hard if isinstance(i, dict)]
            soft_codes = [str(i.get("code") or "") for i in soft if isinstance(i, dict)]
            mix_only = not hard and any(c == "MIX_PARTIAL" for c in soft_codes)
            post_doctor_step = {
                "id": "post_doctor",
                "ok": bool(doctor.get("ok") if doctor.get("ok") is not None else not hard),
                "detail": (
                    "ok"
                    if not hard and not mix_only
                    else (
                        "ok; MIX_PARTIAL (honest amix fallback)"
                        if mix_only
                        else "; ".join(hard_codes) or "post-doctor hard"
                    )
                ),
                "next_cmd": None
                if not hard
                else (
                    doctor.get("next_cmd")
                    or (hard[0].get("fix") if hard else None)
                    or f'aifilm post-doctor --root "{base}"'
                ),
                "advisory": bool(mix_only and not hard),
                "hard_codes": hard_codes,
                "soft_codes": soft_codes,
                "mix_partial": "MIX_PARTIAL" in soft_codes,
            }
        except Exception as exc:  # noqa: BLE001
            post_doctor_step = {
                "id": "post_doctor",
                "ok": False,
                "detail": f"post-doctor probe failed: {exc}"[:160],
                "next_cmd": f'aifilm post-doctor --root "{base}"',
                "advisory": False,
                "probe_error": True,
            }
    steps.append(post_doctor_step)

    # Delivery Truth · i2v-final-gate must be green before delivery_ready
    motion_gate_step: dict[str, Any] = {
        "id": "i2v_motion",
        "ok": False,
        "detail": "missing i2v-final-gate",
        "next_cmd": f'aifilm i2v-motion-gate --root "{base}" --write',
        "advisory": False,
    }
    try:
        from i2v_motion_gate import assert_i2v_final_gate_for_export, i2v_motion_gate_skip_enabled

        if i2v_motion_gate_skip_enabled():
            motion_gate_step = {
                "id": "i2v_motion",
                "ok": True,
                "detail": "skipped AIFILM_SKIP_I2V_MOTION_GATE=1",
                "next_cmd": None,
                "advisory": False,
                "skipped": True,
            }
        else:
            g = assert_i2v_final_gate_for_export(base)
            motion_gate_step = {
                "id": "i2v_motion",
                "ok": True,
                "detail": "i2v-final-gate ok",
                "next_cmd": None,
                "advisory": False,
                "path": g.get("path"),
            }
    except Exception as exc:  # noqa: BLE001 — gate miss/fail must not silent-pass
        motion_gate_step = {
            "id": "i2v_motion",
            "ok": False,
            "detail": str(exc)[:200],
            "next_cmd": f'aifilm i2v-motion-gate --root "{base}" --write',
            "advisory": False,
        }
    steps.append(motion_gate_step)

    # Wave ε · composite cinematic-gate (true-video / variety / five-track / inventory)
    cin_step: dict[str, Any] = {
        "id": "cinematic_gate",
        "ok": False,
        "detail": "missing cinematic-gate",
        "next_cmd": f'aifilm cinematic-gate --root "{base}"',
        "advisory": False,
    }
    try:
        from cinematic_gate import assert_cinematic_gate_for_export, skip_enabled

        if skip_enabled():
            cin_step = {
                "id": "cinematic_gate",
                "ok": True,
                "detail": "skipped AIFILM_SKIP_CINEMATIC_GATE=1",
                "next_cmd": None,
                "advisory": False,
                "skipped": True,
            }
        else:
            g = assert_cinematic_gate_for_export(base)
            cin_step = {
                "id": "cinematic_gate",
                "ok": True,
                "detail": "cinematic-gate ok",
                "next_cmd": None,
                "advisory": False,
                "path": g.get("path"),
            }
    except Exception as exc:  # noqa: BLE001
        cin_step = {
            "id": "cinematic_gate",
            "ok": False,
            "detail": str(exc)[:200],
            "next_cmd": f'aifilm cinematic-gate --root "{base}"',
            "advisory": False,
        }
    steps.append(cin_step)

    # Narrative rebind + adult sex arc (P1 · 2026-08-06) — receipt always written
    rebind_step: dict[str, Any] = {
        "id": "narrative_rebind",
        "ok": True,
        "detail": "skipped",
        "next_cmd": None,
        "advisory": True,
    }
    try:
        from narrative_rebind import check_narrative_rebind

        rebind = check_narrative_rebind(base, write=True)
        hard_issues = [
            i for i in (rebind.get("issues") or []) if i.get("severity") == "hard"
        ]
        rebind_step = {
            "id": "narrative_rebind",
            "ok": bool(rebind.get("ok")),
            "detail": (
                "graph projection current + adult arc ok"
                if rebind.get("ok")
                else f"hard={len(hard_issues)} soft={rebind.get('soft_count')}"
            ),
            "next_cmd": rebind.get("next_cmd"),
            "advisory": False if hard_issues else True,
            "hard": bool(hard_issues),
            "receipt": "receipts/narrative-rebind.json",
        }
    except Exception as exc:  # noqa: BLE001
        rebind_step = {
            "id": "narrative_rebind",
            "ok": False,
            "detail": str(exc)[:200],
            "next_cmd": f'aifilm closeout status --root "{base}"',
            "advisory": False,
            "hard": True,
        }
    steps.append(rebind_step)

    # film-core audit: max/premium/strict → hard; else advisory
    core_audit: dict[str, Any] = {}
    film_core_hard = False
    try:
        _spec = read_json(base / "film-spec.json") or {}
        heat_scale = str(_spec.get("heat_scale") or "").strip().lower()
        film_core_hard = (
            heat_scale == "max"
            or _spec.get("dramatic_meaning_strict") is True
            or _spec.get("premium_vertical") is True
            or str(_spec.get("delivery_tier") or "").strip().lower() in {"max", "premium"}
        )
    except Exception:  # noqa: BLE001
        film_core_hard = False
    try:
        from workflow_pack import film_core_closeout_audit

        core_audit = film_core_closeout_audit(base, write=True)
        steps.append(
            {
                "id": "film_core",
                "ok": bool(core_audit.get("ok")),
                "detail": (
                    "motion core DF/want/dialogue aligned"
                    if core_audit.get("ok")
                    else f"issues={len(core_audit.get('issues') or [])}"
                ),
                "next_cmd": core_audit.get("next_cmd"),
                "advisory": not film_core_hard,
                "hard": film_core_hard,
            }
        )
    except Exception as exc:  # noqa: BLE001 — never mask as ok
        core_audit = {"ok": False, "error": str(exc)[:160]}
        steps.append(
            {
                "id": "film_core",
                "ok": False,
                "detail": f"film_core audit error: {exc}"[:200],
                "next_cmd": f'aifilm closeout status --root "{base}"',
                "advisory": not film_core_hard,
                "hard": film_core_hard,
            }
        )

    # F3 · input fidelity ladder step (soft unless strict mode / score hard floor)
    fid_step: dict[str, Any] = {
        "id": "input_fidelity",
        "ok": True,
        "detail": "skipped (no report)",
        "next_cmd": f'aifilm fidelity check --root "{base}"',
        "advisory": True,
    }
    try:
        from input_fidelity import (
            assert_fidelity_allows_final,
            fidelity_check,
            human_fidelity_summary,
        )

        fid_rep = fidelity_check(base, write=True)
        summary = human_fidelity_summary(fid_rep)
        hard_fid = bool(fid_rep.get("strict"))
        if hard_fid:
            try:
                assert_fidelity_allows_final(base)
                fid_step = {
                    "id": "input_fidelity",
                    "ok": True,
                    "detail": f"score={fid_rep.get('score')} strict ok\n{summary}",
                    "next_cmd": None,
                    "advisory": False,
                    "hard": True,
                    "human_summary": summary,
                }
            except Exception as exc:  # noqa: BLE001
                fid_step = {
                    "id": "input_fidelity",
                    "ok": False,
                    "detail": str(exc)[:240],
                    "next_cmd": (
                        f'aifilm fidelity apply --root "{base}" && '
                        f'aifilm fidelity check --root "{base}" --strict'
                    ),
                    "advisory": False,
                    "hard": True,
                    "human_summary": summary,
                }
        else:
            fid_step = {
                "id": "input_fidelity",
                "ok": bool(fid_rep.get("ok")),
                "detail": f"score={fid_rep.get('score')} (advisory)\n{summary}",
                "next_cmd": (
                    None if fid_rep.get("ok") else f'aifilm fidelity apply --root "{base}"'
                ),
                "advisory": True,
                "hard": False,
                "human_summary": summary,
            }
    except Exception as exc:  # noqa: BLE001
        fid_step = {
            "id": "input_fidelity",
            "ok": True,
            "detail": f"fidelity skip error: {exc}"[:160],
            "next_cmd": f'aifilm fidelity check --root "{base}"',
            "advisory": True,
            "skipped": True,
        }
    steps.append(fid_step)

    # AD A4/B · duration honesty canary + final report read-back (advisory soft)
    duration_honesty: dict[str, Any] = {
        "ok": True,
        "advisory": True,
        "planned_sec": None,
        "media_sec": None,
        "shot_n": None,
        "target_sec": None,
        "codes": [],
    }
    try:
        from plan.duration_target import (
            check_duration_target,
            flatten_shots,
            planned_sum_duration_sec,
            resolve_target_duration_sec,
        )

        spec = read_json(base / "film-spec.json") or {}
        shots = flatten_shots(spec if isinstance(spec, dict) else {})
        duration_honesty["shot_n"] = len(shots)
        duration_honesty["planned_sec"] = round(planned_sum_duration_sec(shots), 3)
        duration_honesty["target_sec"] = resolve_target_duration_sec(
            spec if isinstance(spec, dict) else {}
        )
        # media sum from approved clips when available
        media_sum = None
        try:
            man = read_json(base / "manifest.json") or {}
            clips = man.get("clips") if isinstance(man, dict) else {}
            if isinstance(clips, dict):
                total_m = 0.0
                n_m = 0
                for _sid, c in clips.items():
                    if not isinstance(c, dict):
                        continue
                    if str(c.get("status") or "") not in {"approved", "selected", "hero"}:
                        continue
                    for k in ("duration_sec", "duration", "mean_duration_sec"):
                        if c.get(k) is not None:
                            try:
                                total_m += float(c[k])
                                n_m += 1
                                break
                            except (TypeError, ValueError):
                                pass
                if n_m:
                    media_sum = total_m
        except Exception:  # noqa: BLE001
            media_sum = None
        duration_honesty["media_sec"] = (
            None if media_sum is None else round(float(media_sum), 3)
        )
        rep = check_duration_target(
            spec if isinstance(spec, dict) else {},
            media_sum_sec=media_sum,
        )
        duration_honesty["codes"] = list(rep.get("codes") or [])
        duration_honesty["severity"] = rep.get("severity")
        duration_honesty["ok"] = bool(rep.get("ok"))
        duration_honesty["message"] = rep.get("message")
        duration_honesty["next"] = rep.get("next") or []
        write_json(
            base / "receipts" / "duration-honesty-closeout.json",
            {**duration_honesty, "kind": "duration_honesty_closeout", "at": utc_now()},
        )
    except Exception as exc:  # noqa: BLE001
        duration_honesty["ok"] = True
        duration_honesty["error"] = str(exc)[:160]

    official_final_readback: dict[str, Any] = {
        "required_fields": [
            "status/delivery_class",
            "master_lock",
            "path or plate path",
        ],
        "present": False,
        "plate_vs_master": "unknown",
        "note": "agent must read official-final-report before claiming final done",
    }
    ofr = read_json(base / "receipts" / "official-final-report.json") or {}
    if isinstance(ofr, dict) and ofr:
        official_final_readback["present"] = True
        official_final_readback["status"] = ofr.get("status") or ofr.get("delivery_class")
        official_final_readback["master_lock"] = ofr.get("master_lock")
        if plate["is_official_plate"] or ofr.get("master_lock") is False:
            official_final_readback["plate_vs_master"] = "PLATE_NOT_MASTER"
        elif ofr.get("master_lock") is True:
            official_final_readback["plate_vs_master"] = "MASTER"
        else:
            official_final_readback["plate_vs_master"] = str(
                ofr.get("status") or ofr.get("delivery_class") or "present"
            )

    steps.append(
        {
            "id": "duration_honesty",
            "ok": True,  # advisory; hard path is bulk-preflight / duration_target
            "advisory": True,
            "detail": duration_honesty.get("message")
            or (
                f"planned={duration_honesty.get('planned_sec')} "
                f"target={duration_honesty.get('target_sec')} "
                f"shots={duration_honesty.get('shot_n')}"
            ),
            "codes": duration_honesty.get("codes") or [],
            "next_cmd": (
                None
                if duration_honesty.get("ok")
                else (
                    (duration_honesty.get("next") or [None])[0]
                    or f'aifilm bulk-preflight --root "{base}"'
                )
            ),
        }
    )
    steps.append(
        {
            "id": "official_final_readback",
            "ok": True,
            "advisory": True,
            "detail": official_final_readback.get("plate_vs_master"),
            "readback": official_final_readback,
            "next_cmd": (
                None
                if official_final_readback.get("present")
                else 'cat receipts/official-final-report.json  # after final'
            ),
        }
    )

    soft_ids = {
        "desktop_exported",
        "input_fidelity",
        "duration_honesty",
        "official_final_readback",
    }
    if not film_core_hard:
        soft_ids.add("film_core")
    # hard fidelity when marked hard and not ok
    if fid_step.get("hard") and not fid_step.get("ok"):
        soft_ids.discard("input_fidelity")
    # evidence honesty-only (mix partial) stays soft when ok+advisory
    for s in steps:
        if s.get("id") == "evidence_fresh" and s.get("ok") and s.get("advisory"):
            soft_ids.add("evidence_fresh")
        # AF3 · MIX_PARTIAL-only post_doctor is advisory honesty, not hard block.
        # When film_core is hard, post_doctor is also soft — film_core is the
        # primary hard gate and takes priority as blocked_by.
        if s.get("id") == "post_doctor" and (
            (s.get("ok") and s.get("advisory")) or film_core_hard
        ):
            soft_ids.add("post_doctor")
    blocked = next(
        (s for s in steps if not s["ok"] and s["id"] not in soft_ids),
        None,
    )
    delivery_ready = all(s["ok"] for s in steps if s["id"] not in soft_ids)
    export_cmd = f'aifilm export-desktop --root "{base}" --name "{_export_name(base)}"'
    return {
        "kind": "closeout-status",
        "schema_version": 1,
        "root": str(base),
        "at": utc_now(),
        "ok": blocked is None and delivery_ready,
        "delivery_ready": delivery_ready,
        "film_core": core_audit,
        "gates": {
            "final_complete": final_complete_ok,
            "desktop_exported": bool(gates.get("desktop_exported")),
            "clips_complete": bool(gates.get("clips_complete")),
        },
        "plate_honesty": plate,
        "duration_honesty": duration_honesty,
        "official_final_readback": official_final_readback,
        "final": final_rec,
        "heat": {
            "active": heat.get("active"),
            "hard_fail": heat.get("hard_fail"),
            "needs_boost": heat.get("needs_boost"),
            "why": heat.get("why"),
        },
        "steps": steps,
        "blocked_by": blocked["id"] if blocked else None,
        "next_cmd": (blocked or {}).get("next_cmd"),
        "required_proof": (blocked or {}).get("required_proof"),
        "next_action": {
            "id": f"closeout-{(blocked or {}).get('id') or 'done'}",
            "cmd": (blocked or {}).get("next_cmd")
            or (
                export_cmd
                if not gates.get("desktop_exported")
                else f'aifilm status --root "{base}"'
            ),
            "why": (blocked or {}).get("detail") or "closeout ladder clear",
        },
    }


def closeout_run(
    root: Path | str,
    *,
    execute: bool = True,
    export: bool = False,
    export_name: str | None = None,
    write_receipt: bool = True,
) -> dict[str, Any]:
    """Run automatable closeout steps; stop at first human/hard gate.

    ``execute=False`` is status-only (same as closeout_status).
    ``execute=True`` runs post-audit when review is already complete.
    Never auto-approves review-final.
    """
    base = _root(root)
    status = closeout_status(base)
    ran: list[dict[str, Any]] = []

    if not execute:
        status["mode"] = "status"
        if write_receipt:
            path = base / RECEIPT_REL
            write_json(path, {**status, "receipt_path": str(path)})
            status["receipt_path"] = str(path)
        return status

    status["mode"] = "run"
    # Heat hard fail → stop
    heat_step = next(s for s in status["steps"] if s["id"] == "heat")
    if not heat_step["ok"]:
        payload = {
            **status,
            "ok": False,
            "stopped_at": "heat",
            "ran": ran,
            "next_cmd": heat_step.get("next_cmd"),
            "required_proof": heat_step.get("required_proof"),
        }
        if write_receipt:
            write_json(base / RECEIPT_REL, payload)
        return payload

    if not status["final"]:
        payload = {
            **status,
            "ok": False,
            "stopped_at": "plate_or_final",
            "ran": ran,
            "next_cmd": next(s for s in status["steps"] if s["id"] == "plate_or_final").get(
                "next_cmd"
            ),
            "required_proof": "out/*.mp4 plate or registered final_film",
        }
        if write_receipt:
            write_json(base / RECEIPT_REL, payload)
        return payload

    if not status["gates"].get("final_complete"):
        rev = next(s for s in status["steps"] if s["id"] == "final_complete")
        payload = {
            **status,
            "ok": False,
            "stopped_at": "final_complete",
            "ran": ran,
            "next_cmd": rev.get("next_cmd"),
            "required_proof": rev.get("required_proof"),
            "note": "closeout does not auto-approve review-final",
        }
        if write_receipt:
            write_json(base / RECEIPT_REL, payload)
        return payload

    # P0-B · after human review: auto-run caption pixel when missing/stale
    try:
        cap_step = next(s for s in status["steps"] if s["id"] == "caption_pixel")
    except StopIteration:
        cap_step = {"ok": True}
    if not cap_step.get("ok") and not cap_step.get("skipped"):
        try:
            from caption_pixel_check import run_caption_pixel_check

            pixel = run_caption_pixel_check(base, write=True)
            ran.append(
                {
                    "id": "caption_pixel",
                    "ok": bool(pixel.get("ok")),
                    "missing_ink": bool(pixel.get("missing_ink")),
                    "path": pixel.get("path"),
                }
            )
            if not pixel.get("ok"):
                payload = {
                    **status,
                    "ok": False,
                    "stopped_at": "caption_pixel",
                    "ran": ran,
                    "caption_pixel": pixel,
                    "next_cmd": pixel.get("next_cmd")
                    or f'aifilm caption-pixel-check --root "{base}"',
                    "required_proof": "receipts/caption-pixel-check.json ok (burned Chinese ink)",
                }
                if write_receipt:
                    write_json(base / RECEIPT_REL, payload)
                return payload
            status = closeout_status(base)
            status["mode"] = "run"
        except Exception as exc:  # noqa: BLE001
            payload = {
                **status,
                "ok": False,
                "stopped_at": "caption_pixel",
                "ran": ran,
                "error": str(exc)[:300],
                "next_cmd": f'aifilm caption-pixel-check --root "{base}"',
            }
            if write_receipt:
                write_json(base / RECEIPT_REL, payload)
            return payload

    # Single machine-lane ensure when cinematic red
    try:
        cin = next(s for s in status["steps"] if s["id"] == "cinematic_gate")
    except StopIteration:
        cin = {"ok": True}
    if not cin.get("ok") and not cin.get("skipped"):
        try:
            from gate_auto import ensure_machine_lane

            auto = ensure_machine_lane(base, force=False, write=True)
            ran.append(
                {
                    "id": "gate_auto",
                    "ok": bool(auto.get("ok")),
                    "blocked_by": auto.get("blocked_by"),
                    "human_pending": auto.get("human_pending"),
                    "fast_path": auto.get("fast_path"),
                }
            )
            if not auto.get("ok"):
                payload = {
                    **status,
                    "ok": False,
                    "stopped_at": "gate_auto",
                    "ran": ran,
                    "gate_auto": auto,
                    "next_cmd": auto.get("next_cmd") or f'aifilm gate-auto --root "{base}"',
                    "required_proof": "receipts/gate-auto.json + cinematic-gate ok",
                }
                if write_receipt:
                    write_json(base / RECEIPT_REL, payload)
                return payload
        except Exception as exc:  # noqa: BLE001
            payload = {
                **status,
                "ok": False,
                "stopped_at": "gate_auto",
                "ran": ran,
                "error": str(exc)[:300],
                "next_cmd": f'aifilm gate-auto --root "{base}"',
            }
            if write_receipt:
                write_json(base / RECEIPT_REL, payload)
            return payload

    # post-audit
    post_step = next(s for s in status["steps"] if s["id"] == "post_audit")
    if not post_step["ok"]:
        try:
            from post_audit import audit

            report = audit(base, write=True)
            ran.append(
                {
                    "id": "post_audit",
                    "ok": bool(report.get("delivery_ready") or report.get("ok")),
                    "delivery_ready": report.get("delivery_ready"),
                }
            )
            if not (report.get("delivery_ready") or report.get("ok")):
                payload = {
                    **status,
                    "ok": False,
                    "stopped_at": "post_audit",
                    "ran": ran,
                    "post_audit": report,
                    "next_cmd": f'aifilm post-audit --root "{base}"',
                    "required_proof": "receipts/post-audit.json delivery_ready",
                }
                if write_receipt:
                    write_json(base / RECEIPT_REL, payload)
                return payload
        except Exception as exc:  # noqa: BLE001
            payload = {
                **status,
                "ok": False,
                "stopped_at": "post_audit",
                "ran": ran,
                "error": str(exc)[:300],
                "next_cmd": f'aifilm post-audit --root "{base}"',
            }
            if write_receipt:
                write_json(base / RECEIPT_REL, payload)
            return payload

    # optional export — only when requested; still needs a name
    if export:
        name = (export_name or "").strip()
        if not name:
            payload = {
                **closeout_status(base),
                "mode": "run",
                "ok": False,
                "stopped_at": "export_desktop",
                "ran": ran,
                "next_cmd": f'aifilm export-desktop --root "{base}" --name "{_export_name(base)}"',
                "required_proof": "export name (derived from film title when available)",
            }
            if write_receipt:
                write_json(base / RECEIPT_REL, payload)
            return payload
        # export is side-effect heavy; leave to CLI cmd_export_desktop via next_cmd
        # when agent passes --export, still emit explicit next for aifilm_grok to run
        payload = {
            **closeout_status(base),
            "mode": "run",
            "ok": True,
            "ran": ran,
            "export_requested": True,
            "export_name": name,
            "next_cmd": f'aifilm export-desktop --root "{base}" --name "{name}"',
            "note": "post-audit ok; run export-desktop with provided name",
        }
        if write_receipt:
            write_json(base / RECEIPT_REL, payload)
        return payload

    fresh = closeout_status(base)
    payload = {
        **fresh,
        "mode": "run",
        "ok": fresh.get("delivery_ready"),
        "ran": ran,
        "next_cmd": fresh.get("next_cmd"),
    }
    if write_receipt:
        path = base / RECEIPT_REL
        write_json(path, {**payload, "receipt_path": str(path)})
        payload["receipt_path"] = str(path)
    return payload
