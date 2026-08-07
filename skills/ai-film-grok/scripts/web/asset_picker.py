"""Web-facing "选素材" core.

The web console never invents asset state.  Every selection is recorded through
the *existing* pipeline modules / receipts so the browser stays a thin, safe
front-end over the single source of truth:

* BGM      -> validated by ``bgm_library.get_approved_asset``; receipt written to
             ``receipts/bgm-selection.json`` (the same file the CLI writes).
* shot     -> read from ``review_control.review_queue`` cloud candidates.
* character / voice -> recorded in ``receipts/`` selection receipts the pipeline
             already consumes.

Selections are hash-bound to the upstream workspace files
(``bgm-library/catalog.json`` + ``film-spec.json``) and carry an
``expected_revision`` so two tabs / two reviewers cannot clobber each other
(reuses the same conflict model as ``review_control``).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from util import read_json
from web_core import (
    WebConsoleConflict,
    WebConsoleError,
    WebConsoleForbidden,
    now_iso,
    workspace_binding_sha256,
    write_json_locked,
)

# Soft-degrade paths (S4): empty library is silent; unexpected errors log.
_log = logging.getLogger("aifilm.web.asset_picker")

SELECTION_NAME = "selection-ledger.json"
VALID_KINDS = ("bgm", "character", "voice", "shot", "scene", "prop")


def _ledger_path(root: Path) -> Path:
    return root / "receipts" / SELECTION_NAME


def load_ledger(root: Path) -> dict[str, Any]:
    value = read_json(_ledger_path(root))
    if isinstance(value, dict):
        value.setdefault("revision", 0)
        value.setdefault("selections", [])
        return value
    return {"schema_version": 1, "kind": "selection-ledger", "revision": 0, "selections": []}


def _bgm_library_root() -> Path:
    from bgm_library import default_library_root

    return default_library_root()


def list_assets(root: Path | str, kind: str) -> dict[str, Any]:
    """Return the catalogue entries the picker UI needs for ``kind``."""
    base = Path(root).expanduser().resolve()
    if kind not in VALID_KINDS:
        raise WebConsoleError(f"unknown asset kind: {kind}")
    if kind == "bgm":
        return {"kind": "bgm", "items": _list_bgm(base)}
    if kind == "character":
        return {"kind": "character", "items": _list_characters(base)}
    if kind == "voice":
        return {"kind": "voice", "items": _list_voices(base)}
    if kind == "scene":
        return {"kind": "scene", "items": _list_scenes(base)}
    if kind == "prop":
        return {"kind": "prop", "items": _list_props(base)}
    return {"kind": "shot", "items": _list_shots(base)}


def _list_bgm(base: Path) -> list[dict[str, Any]]:
    try:
        library = _bgm_library_root()
    except Exception as exc:  # noqa: BLE001
        _log.warning("bgm library root unavailable: %s", exc)
        return []
    try:
        catalog = read_json(library / "catalog.json")
        if not isinstance(catalog, dict):
            return []
        assets = catalog.get("assets") if isinstance(catalog.get("assets"), dict) else {}
        items: list[dict[str, Any]] = []
        for asset_id, asset in assets.items():
            if not isinstance(asset, dict) or asset.get("status") != "approved":
                continue
            recipe = asset.get("recipe") if isinstance(asset.get("recipe"), dict) else {}
            items.append(
                {
                    "asset_id": asset_id,
                    "mood": asset.get("mood") or recipe.get("mood"),
                    "energy": asset.get("energy", recipe.get("energy")),
                    "duration": (asset.get("technical") or {}).get("duration_sec"),
                    "bpm": asset.get("bpm", recipe.get("bpm")),
                    "path": asset.get("path"),
                }
            )
        return items
    except Exception as exc:  # noqa: BLE001
        _log.warning("bgm catalog list failed: %s", exc)
        return []


def _list_characters(base: Path) -> list[dict[str, Any]]:
    registry = read_json(base / "assets.json")
    if not isinstance(registry, dict):
        return []
    characters = registry.get("characters") if isinstance(registry.get("characters"), list) else []
    return [
        {"asset_id": str(c.get("id")), "name": c.get("name"), "role": c.get("role")}
        for c in characters
        if isinstance(c, dict) and c.get("id")
    ]


def _list_voices(base: Path) -> list[dict[str, Any]]:
    spec = read_json(base / "film-spec.json")
    voices = (
        (spec.get("cast_voices") or {})
        if isinstance(spec, dict)
        else {}
    )
    # Always keep the documented Chinese pool selectable so that pinning one
    # voice (which writes cast_voices back to film-spec.json) never hides the
    # other slots from the picker.
    fallback = [
        {"asset_id": "female_lead", "voice": "zh-CN-XiaoyiNeural"},
        {"asset_id": "male_lead", "voice": "zh-CN-YunxiNeural"},
    ]
    if isinstance(voices, dict) and voices:
        items = [{"asset_id": k, "voice": v} for k, v in voices.items()]
        pinned = {it["asset_id"] for it in items}
        for f in fallback:
            if f["asset_id"] not in pinned:
                items.append(f)
        return items
    return fallback


def _list_shots(base: Path) -> list[dict[str, Any]]:
    try:
        from review_control import review_queue

        queue = review_queue(base)
    except Exception as exc:  # noqa: BLE001
        _log.warning("review_queue unavailable for shot assets: %s", exc)
        return []
    return [
        {
            "shot_id": item["id"].removeprefix("shot:"),
            "state": item.get("state"),
            "cloud_candidates": item.get("cloud_candidates", []),
        }
        for item in queue.get("items", [])
        if item.get("id", "").startswith("shot:")
    ]


def _list_scenes(base: Path) -> list[dict[str, Any]]:
    """Read-only view of ``film-spec.json`` scenes (structured planning data)."""
    spec = read_json(base / "film-spec.json")
    if not isinstance(spec, dict):
        return []
    scenes = spec.get("scenes") if isinstance(spec.get("scenes"), list) else []
    items: list[dict[str, Any]] = []
    for idx, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            continue
        shots = sc.get("shots") if isinstance(sc.get("shots"), list) else []
        items.append(
            {
                "scene_id": str(sc.get("id") or f"sc{idx + 1:02d}"),
                "title": sc.get("title") or sc.get("name") or f"Scene {idx + 1}",
                "shot_count": len(shots),
            }
        )
    return items


def _list_props(base: Path) -> list[dict[str, Any]]:
    """Read-only view of ``assets.json`` ``bible.props`` (continuity props)."""
    reg = read_json(base / "assets.json")
    if not isinstance(reg, dict):
        return []
    bible = reg.get("bible") if isinstance(reg.get("bible"), dict) else {}
    props = bible.get("props") if isinstance(bible.get("props"), dict) else {}
    return [
        {
            "prop_id": str(pid),
            "description": (v.get("description") if isinstance(v, dict) else str(v)),
        }
        for pid, v in props.items()
    ]


def select_asset(
    root: Path | str,
    *,
    kind: str,
    asset_id: str,
    target_id: str | None = None,
    expected_revision: int | None = None,
    value: str | None = None,
) -> dict[str, Any]:
    """Record a human asset selection.  Hash-bound + revision-conflict safe.

    For ``kind == "voice"`` an optional ``value`` carries the chosen voice id
    (e.g. ``zh-CN-XiaoyiNeural``); when omitted the currently paired voice for
    the slot is pinned.  The selection is also written back into the pipeline's
    canonical file (``film-spec.json`` ``cast_voices`` / ``assets.json``
    ``characters[].selected``) so the console drives production — mirroring the
    shot -> ``manifest.json`` binding.  Canonical writes fail soft (reported,
    never raised) and only happen after the P6 gate check passes.
    """
    base = Path(root).expanduser().resolve()
    if kind not in VALID_KINDS:
        raise WebConsoleError(f"unknown asset kind: {kind}")
    if not asset_id:
        raise WebConsoleError("asset_id is required")

    binding = workspace_binding_sha256(
        base, "bgm-library/catalog.json", "film-spec.json"
    )

    ledger = load_ledger(base)
    if expected_revision is not None and int(expected_revision) != int(ledger["revision"]):
        raise WebConsoleConflict("selection ledger revision is stale")

    # P6 — fail-closed gate enforcement: reject BEFORE any write when a hard
    # gate has failed.  ``collect_gates`` only marks ``blocking`` on a required
    # gate with status == "fail"; "unknown"/"skipped"/"warn" do NOT block, so an
    # unwired heavy gate module never false-locks the console.  If the gate
    # panel module is unavailable we degrade (allow) — the authoritative
    # enforcement still lives in the pipeline's own gates.
    try:
        from gate_panel import collect_gates
    except Exception as exc:  # noqa: BLE001 -- gate module missing: do not block on it
        _log.warning("gate_panel import soft-fail (allow select): %s", exc)
        collect_gates = None
    if collect_gates is not None:
        try:
            gates = collect_gates(base)
        except Exception as exc:  # noqa: BLE001 -- never let the panel crash selection
            _log.warning("collect_gates soft-fail (allow select): %s", exc)
            gates = None
        if gates and gates.get("blocking"):
            raise WebConsoleForbidden(
                "硬门禁未通过，拒绝选择/批准: " + ", ".join(gates.get("hard_fail") or [])
            )

    _validate_selection(base, kind, asset_id)

    # P7 — canonical binding for character / voice: write the human selection back
    # into the pipeline's own canonical file so it drives production.  Fails soft
    # (reported, not raised) and only runs AFTER the gate check above passed.
    canon_value = value
    if kind == "voice" and canon_value is None:
        canon_value = next(
            (v["voice"] for v in _list_voices(base) if v["asset_id"] == asset_id), None
        )
    canonical_binding = _bind_canonical(base, kind, asset_id, canon_value)

    selection = {
        "kind": kind,
        "asset_id": asset_id,
        "target_id": target_id,
        "value": canon_value,
        "binding_sha": binding,
        "recorded_at": now_iso(),
    }
    _write_kind_receipt(base, selection)

    ledger["revision"] = int(ledger["revision"]) + 1
    ledger["binding_sha"] = binding
    ledger["selections"].append(selection)
    write_json_locked(_ledger_path(base), ledger)

    manifest_binding = _bind_shot_to_manifest(base, kind, asset_id) if kind == "shot" else None
    return {
        "ok": True,
        "revision": ledger["revision"],
        "selection": selection,
        "canonical_binding": canonical_binding,
        "manifest_binding": manifest_binding,
    }


def _bind_canonical(
    base: Path, kind: str, asset_id: str, value: str | None
) -> dict[str, Any]:
    """Best-effort canonical write-back for character / voice selections.

    Mirrors the shot -> manifest pattern: a human console selection is persisted
    into the pipeline's own canonical file so it drives production rather than
    living only in the ledger.  Failures are reported in the returned dict and
    never raised, so a broken canonical file can never crash ``select_asset``.
    """
    result: dict[str, Any] = {"bound": False, "kind": kind}
    if kind not in ("character", "voice") or not asset_id:
        result["reason"] = "no canonical file for this kind"
        return result
    try:
        if kind == "voice" and value:
            spec_path = base / "film-spec.json"
            spec = read_json(spec_path) if spec_path.is_file() else {}
            if not isinstance(spec, dict):
                spec = {}
            cv = spec.get("cast_voices") if isinstance(spec.get("cast_voices"), dict) else {}
            cv[asset_id] = value
            spec["cast_voices"] = cv
            write_json_locked(spec_path, spec)
            result.update(bound=True, field="cast_voices", value=value)
        elif kind == "character":
            reg_path = base / "assets.json"
            reg = read_json(reg_path) if reg_path.is_file() else {}
            chars = reg.get("characters") if isinstance(reg.get("characters"), list) else None
            if not isinstance(reg, dict) or chars is None:
                result["reason"] = "assets.json missing or malformed"
            else:
                for c in chars:
                    if isinstance(c, dict) and str(c.get("id")) == asset_id:
                        c["selected"] = True
                        write_json_locked(reg_path, reg)
                        result.update(bound=True, field="characters[].selected")
                        break
                else:
                    result["reason"] = "character id not found in assets.json"
    except Exception as exc:  # noqa: BLE001 -- report, never crash selection
        result["reason"] = f"canonical bind failed: {exc}"
    return result


def _validate_selection(base: Path, kind: str, asset_id: str) -> None:
    """Best-effort validation through existing modules; never invents state."""
    if kind == "bgm":
        try:
            from bgm_library import get_approved_asset

            get_approved_asset(_bgm_library_root(), asset_id)
        except Exception as exc:  # noqa: BLE001
            raise WebConsoleError(f"invalid BGM asset: {asset_id} ({exc})") from exc
    elif kind == "character":
        if not any(c["asset_id"] == asset_id for c in _list_characters(base)):
            raise WebConsoleError(f"unknown character: {asset_id}")
    elif kind == "voice":
        if not any(v["asset_id"] == asset_id for v in _list_voices(base)):
            raise WebConsoleError(f"unknown voice: {asset_id}")
    # shot candidates are validated implicitly by the cloud queue at review time.


def _write_kind_receipt(base: Path, selection: dict[str, Any]) -> None:
    kind = selection["kind"]
    if kind == "bgm":
        receipt = base / "receipts" / "bgm-selection.json"
        payload: dict[str, Any] = read_json(receipt) if isinstance(read_json(receipt), dict) else {}
        payload.setdefault("selections", [])
        payload["selections"].append(
            {"asset_id": selection["asset_id"], "target_id": selection["target_id"]}
        )
        write_json_locked(receipt, payload)
    else:
        receipt = base / "receipts" / f"{kind}-selection.json"
        payload = read_json(receipt) if isinstance(read_json(receipt), dict) else {}
        payload.setdefault("selections", [])
        payload["selections"].append(selection)
        write_json_locked(receipt, payload)


# --------------------------------------------------------------------------- #
# shot -> manifest.json binding (the only kind that lives in the production
# manifest; cast / voice / bgm are owned by assets.json / film-spec.json /
# bgm-library/catalog.json and must NOT be invented into manifest.json)
# --------------------------------------------------------------------------- #
def _best_shot_candidate(base: Path, shot_id: str) -> dict[str, Any] | None:
    """Best-effort enrichment from the existing review queue (no state invented)."""
    try:
        from review_control import review_queue

        queue = review_queue(base)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(queue, dict):
        return None
    for item in queue.get("items", []):
        if not isinstance(item, dict):
            continue
        if item.get("id") != f"shot:{shot_id}":
            continue
        cands = item.get("cloud_candidates") or []
        if isinstance(cands, list) and cands:
            approved = [c for c in cands if isinstance(c, dict) and c.get("status") == "approved"]
            return approved[0] if approved else cands[0]
    return None


def _bind_shot_to_manifest(
    base: Path, kind: str, shot_id: str
) -> dict[str, Any]:
    """Mark ``clips[shot_id]`` as approved in the canonical ``manifest.json``.

    Reuses ``core.film_io.save_manifest`` so the shape stays compatible with the
    pipeline's preflight/manifest-truth checks.  Fails soft: any problem is
    reported back in the returned dict instead of crashing ``select_asset``.
    """
    if kind != "shot":
        return {"bound": False, "reason": "non-shot kind"}
    try:
        from core.film_io import empty_manifest, load_manifest, save_manifest
    except Exception as exc:  # noqa: BLE001
        return {"bound": False, "reason": f"manifest I/O unavailable: {exc}"}

    try:
        manifest = load_manifest(base)
        bootstrapped = False
    except Exception:  # noqa: BLE001 -- no manifest yet: bootstrap a minimal one
        try:
            manifest = empty_manifest(title=base.name, theme="", aspect="9:16")
            bootstrapped = True
        except Exception as exc:  # noqa: BLE001
            return {"bound": False, "reason": f"cannot bootstrap manifest: {exc}"}

    clips = manifest.setdefault("clips", {}) if isinstance(manifest, dict) else {}
    if not isinstance(clips, dict):
        return {"bound": False, "reason": "manifest.clips is not a dict"}

    cand = _best_shot_candidate(base, shot_id) or {}
    rec = clips.get(shot_id) if isinstance(clips.get(shot_id), dict) else {}
    rec.update(
        {
            "shot_id": shot_id,
            "role": rec.get("role", "selected"),
            "status": "approved",
            "path": rec.get("path") or cand.get("path") or "",
            "sha256": rec.get("sha256") or cand.get("sha256") or "",
            "provider": rec.get("provider") or cand.get("provider") or "console",
            "registered_at": now_iso(),
        }
    )
    clips[shot_id] = rec
    try:
        save_manifest(base, manifest)
    except Exception as exc:  # noqa: BLE001
        return {"bound": False, "reason": f"save_manifest failed: {exc}"}
    return {
        "bound": True,
        "bootstrapped": bootstrapped,
        "shot_id": shot_id,
        "status": "approved",
        "path": rec.get("path"),
        "provider": rec.get("provider"),
    }


# --------------------------------------------------------------------------- #
# console overview state (P9) — powers the status panel and multi-tab sync.
# Pure read-only aggregation; never writes.
# --------------------------------------------------------------------------- #
def console_state(root: Path | str) -> dict[str, Any]:
    """Aggregated read-only view for the overview panel + cross-tab sync.

    Returns the selection ledger revision / counts, gate blocking state, the
    number of approved manifest clips, onboarding progress, and a short recent
    selection audit trail.  Every sub-source is isolated so a missing module
    or file degrades gracefully instead of crashing the endpoint.
    """
    base = Path(root).expanduser().resolve()
    ledger = load_ledger(base)
    selections = ledger.get("selections", []) if isinstance(ledger.get("selections"), list) else []
    counts: dict[str, int] = {}
    for sel in selections:
        if isinstance(sel, dict) and sel.get("kind"):
            counts[sel["kind"]] = counts.get(sel["kind"], 0) + 1

    gates_blocking = False
    hard_fail: list[str] = []
    degrade: list[str] = []
    try:
        from gate_panel import collect_gates

        g = collect_gates(base)
        gates_blocking = bool(g.get("blocking"))
        hard_fail = list(g.get("hard_fail") or [])
    except Exception as exc:  # noqa: BLE001
        degrade.append("gates")
        _log.warning("console_state gates soft-fail: %s", exc)

    approved_clips = 0
    try:
        from core.film_io import load_manifest

        m = load_manifest(base)
        clips = m.get("clips") if isinstance(m, dict) else None
        if isinstance(clips, dict):
            approved_clips = sum(
                1 for c in clips.values() if isinstance(c, dict) and c.get("status") == "approved"
            )
    except Exception as exc:  # noqa: BLE001
        degrade.append("manifest")
        _log.warning("console_state manifest soft-fail: %s", exc)

    onboarding_progress: dict[str, Any] = {"done": 0, "total": 0, "completed": False}
    try:
        from onboarding import STEPS, get_state

        st = get_state(base)
        steps = st.get("steps") if isinstance(st, dict) else None
        if isinstance(steps, dict):
            done = sum(1 for s in steps.values() if isinstance(s, dict) and s.get("done"))
            onboarding_progress = {
                "done": done,
                "total": len(STEPS),
                "completed": bool(st.get("completed_at")),
            }
    except Exception as exc:  # noqa: BLE001
        degrade.append("onboarding")
        _log.warning("console_state onboarding soft-fail: %s", exc)

    recent = [
        {"kind": s.get("kind"), "asset_id": s.get("asset_id"), "recorded_at": s.get("recorded_at")}
        for s in selections[-10:]
        if isinstance(s, dict)
    ]

    state = {
        "kind": "console-state",
        "ledger_revision": int(ledger.get("revision", 0)),
        "selection_counts": counts,
        "selection_total": len(selections),
        "gate_blocking": gates_blocking,
        "hard_fail": hard_fail,
        "approved_clips": approved_clips,
        "onboarding": onboarding_progress,
        "recent_selections": recent,
    }
    if degrade:
        state["degraded"] = degrade
    try:
        from console_projection import enrich_console_state

        return enrich_console_state(base, state)
    except Exception as exc:  # noqa: BLE001 — overview must never 500 on projection soft-fail
        _log.warning("console_state projection soft-fail: %s", exc)
        state["dispatch_projection"] = {"available": False, "hint": "dispatch 投影不可用"}
        state["queue_snapshot"] = {"available": False}
        state.setdefault("degraded", []).append("projection")
        return state
