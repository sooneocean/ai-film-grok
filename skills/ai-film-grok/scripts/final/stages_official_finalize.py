"""Official final plate/master classification leaf (orchestrator relief W1).

Preserves A5 plate≠master and scale-fallback honesty. Structure-only peel.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any


def apply_official_final_classification(
    *,
    root: Path | str,
    args: Any,
    spec: dict[str, Any] | None,
    report: dict[str, Any],
    report_path: Path,
    manifest: dict[str, Any],
    final_path: Path,
    technical_qa: dict[str, Any],
    bgm_source_receipt: dict[str, Any] | None,
    build_final_film_manifest_entry: Callable[..., dict[str, Any]],
    write_json: Callable[[Path, Any], None],
    utc_now: Callable[[], str],
    log: Callable[[str], None],
) -> dict[str, Any] | None:
    """Classify official final, write receipts, patch report + manifest outputs.

    Returns official_final dict or None if classification skipped/failed.
    """
    from final.delivery_class import (
        classify_official_final,
        read_gate_auto_ok,
        write_official_final_report,
    )
    from final.manifest import build_final_film_manifest_entry as _default_entry
    from util import utc_now as _utc
    from util import write_json as _wj

    _build = build_final_film_manifest_entry or _default_entry
    _write = write_json or _wj
    _now = utc_now or _utc

    official_final: dict[str, Any] | None = None
    scale_fallback_receipt: dict[str, Any] | None = None
    try:
        gate_ok = read_gate_auto_ok(root)
        official_final = classify_official_final(
            skip_preflight=bool(getattr(args, "skip_preflight", False)),
            skip_heat_gate=bool(getattr(args, "skip_heat_gate", False)),
            allow_loop_risk=bool(getattr(args, "allow_loop_risk", False)),
            force=bool(getattr(args, "force", False)),
            gate_auto_ok=gate_ok,
            cinematic_ok=None,
            final_complete=False,
            bgm_partial=bool((bgm_source_receipt or {}).get("partial")),
            root=root,
        )
        try:
            from final.delivery_class import write_plate_boring_receipt

            write_plate_boring_receipt(root)
        except Exception:  # noqa: BLE001
            pass
        try:
            from narrative.scale_fallback import (
                flatten_spec_shots,
                report_scale_fallback_for_shots,
                write_scale_fallback_receipt,
            )

            sf = report_scale_fallback_for_shots(
                flatten_spec_shots(spec if isinstance(spec, dict) else {}),
                heat_scale=str((spec or {}).get("heat_scale") or "max"),
            )
            scale_fallback_receipt = sf
            write_scale_fallback_receipt(root, sf)
            official_final["achieved_wardrobe_tier"] = sf.get("achieved_wardrobe_tier")
            official_final["scale_fallback"] = {
                "codes": sf.get("codes"),
                "partial": sf.get("partial"),
                "recommended_tier": sf.get("recommended_tier"),
                "promote_ban": sf.get("promote_ban"),
                "honest_limits": sf.get("honest_limits"),
            }
            if sf.get("partial"):
                official_final["partial"] = True
                limits = list(official_final.get("honest_limits") or [])
                for h in sf.get("honest_limits") or []:
                    if h not in limits:
                        limits.append(h)
                official_final["honest_limits"] = limits
                if official_final.get("status") == "TECHNICAL_FINAL":
                    official_final["status"] = "OFFICIAL_FINAL_PLATE"
        except Exception as sf_exc:  # noqa: BLE001
            log(f"scale-fallback receipt skip: {sf_exc}")
        write_official_final_report(root, official_final)
        report["official_final"] = official_final
        report["scale_fallback"] = scale_fallback_receipt
        _write(Path(report_path), report)

        final_film = manifest.setdefault("outputs", {}).setdefault("final_film", {})
        if isinstance(final_film, dict) and isinstance(official_final, dict):
            final_film.update(
                _build(
                    final_path=final_path,
                    output_sha256=report["output_sha256"],
                    duration_sec=report["duration_sec"],
                    report_path=report_path,
                    technical_qa=technical_qa,
                    official_final=official_final,
                )
            )
            manifest["updated_at"] = _now()
            _write(Path(root) / "manifest.json", manifest)
    except Exception as of_exc:  # noqa: BLE001
        log(f"official-final-report skip: {of_exc}")
        return None
    return official_final
