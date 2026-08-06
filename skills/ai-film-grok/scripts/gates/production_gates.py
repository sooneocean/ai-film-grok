#!/usr/bin/env python3
"""Production hard gates: pilot user-approval + VO loop-risk (shared by queue / final).

S3 (2026-07-16 Kei): bulk media-queue add requires user pilot approval.
Without approval, at most PILOT_MAX_SHOTS_WITHOUT_APPROVAL distinct shot_ids may queue
(the pilot window). Agent self-approve is rejected.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from film_spec import (
    DEFAULT_DURATION_SEC,
    LOOP_RISK_VO_SEC,
    VO_PACING_SLACK_SEC,
    FilmSpecError,
    estimate_nar_vo_sec,
    validate_film_spec,
)
from util import read_json

PILOT_MAX_SHOTS_WITHOUT_APPROVAL = 3
PILOT_APPROVAL_NAME = "pilot-approval.json"
_MAX_GATE_JSON_BYTES = 4 * 1024 * 1024
_MAX_BENCHMARK_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ProductionGateError(RuntimeError):
    """Raised when a production gate blocks the operation."""


def _open_gate_root(root: Path) -> tuple[Path, int]:
    raw = Path(root).expanduser()
    base = Path(os.path.abspath(raw))
    if raw.is_symlink() or not all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW")):
        raise ProductionGateError("dialogue evidence gate: unsafe film root")
    try:
        root_fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise ProductionGateError("dialogue evidence gate: unsafe film root") from exc
    return base, root_fd


def _open_root_file(
    root_fd: int,
    relative: Path,
    *,
    code: str,
    max_bytes: int,
) -> tuple[int, os.stat_result]:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ProductionGateError(code)
    directory_fd = os.dup(root_fd)
    try:
        for component in relative.parts[:-1]:
            next_fd = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(
            relative.parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory_fd,
        )
    except OSError as exc:
        os.close(directory_fd)
        raise ProductionGateError(code) from exc
    os.close(directory_fd)
    try:
        metadata = os.fstat(file_fd)
    except OSError as exc:
        os.close(file_fd)
        raise ProductionGateError(code) from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0 or metadata.st_size > max_bytes:
        os.close(file_fd)
        raise ProductionGateError(code)
    return file_fd, metadata


def _read_regular_json(root_fd: int, relative: Path, *, code: str) -> dict[str, Any]:
    """Read bounded JSON through a root-bound, non-symlink file descriptor."""
    file_fd, before = _open_root_file(
        root_fd,
        relative,
        code=code,
        max_bytes=_MAX_GATE_JSON_BYTES,
    )
    try:
        chunks = bytearray()
        while chunk := os.read(
            file_fd,
            min(1024 * 1024, _MAX_GATE_JSON_BYTES + 1 - len(chunks)),
        ):
            chunks.extend(chunk)
            if len(chunks) > _MAX_GATE_JSON_BYTES:
                break
        after = os.fstat(file_fd)
        if len(chunks) != before.st_size or (
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ProductionGateError(code)
        value = json.loads(chunks)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise ProductionGateError(code) from exc
    finally:
        os.close(file_fd)
    if not isinstance(value, dict):
        raise ProductionGateError(code)
    return value


def _root_file_sha256(root_fd: int, relative: object) -> str | None:
    if not isinstance(relative, str) or not relative.strip():
        return None
    code = "dialogue benchmark gate: unsafe arm artifact"
    try:
        file_fd, before = _open_root_file(
            root_fd,
            Path(relative),
            code=code,
            max_bytes=_MAX_BENCHMARK_ARTIFACT_BYTES,
        )
    except ProductionGateError:
        return None
    digest = hashlib.sha256()
    try:
        while chunk := os.read(file_fd, 1024 * 1024):
            digest.update(chunk)
        after = os.fstat(file_fd)
    except OSError:
        return None
    finally:
        os.close(file_fd)
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        return None
    return digest.hexdigest()


def _dialogue_package_line_ids(package: dict[str, Any]) -> set[str]:
    return {
        line_id
        for scene in package.get("scenes") or []
        if isinstance(scene, dict)
        for line in scene.get("lines") or []
        if isinstance(line, dict)
        if isinstance((line_id := line.get("line_id")), str) and line_id.strip()
    }


def _assert_dialogue_benchmark_receipt(
    root_fd: int,
    package: dict[str, Any],
    benchmark: dict[str, Any],
) -> None:
    message = (
        "dialogue benchmark gate: Qwen, Wan, and LatentSync must use the same 30–60s "
        "dialogue, retain current artifact hashes, receive human review, and have one "
        "signed approved stable-parameter receipt."
    )
    try:
        from dialogue_benchmark import MAX_DURATION_SEC, MIN_DURATION_SEC, WEAPONS
        from performance_candidates import receipt_is_signed
    except ImportError as exc:
        raise ProductionGateError("dialogue benchmark gate: validator unavailable") from exc

    if not receipt_is_signed(benchmark):
        raise ProductionGateError(message)
    try:
        duration_sec = float(benchmark.get("duration_sec"))
    except (TypeError, ValueError):
        raise ProductionGateError(message) from None
    line_ids = benchmark.get("line_ids")
    weapons = benchmark.get("weapons")
    arms = benchmark.get("arms")
    selection = benchmark.get("selection")
    if (
        benchmark.get("status") != "planned"
        or not MIN_DURATION_SEC <= duration_sec <= MAX_DURATION_SEC
        or not isinstance(line_ids, list)
        or not line_ids
        or any(not isinstance(line_id, str) or not line_id.strip() for line_id in line_ids)
        or len(line_ids) != len(set(line_ids))
        or not set(line_ids).issubset(_dialogue_package_line_ids(package))
        or not isinstance(weapons, list)
        or len(weapons) != len(WEAPONS)
        or set(weapons) != set(WEAPONS)
        or not isinstance(arms, list)
        or len(arms) != len(WEAPONS)
        or not isinstance(selection, dict)
    ):
        raise ProductionGateError(message)

    reviewed: dict[str, dict[str, Any]] = {}
    for arm in arms:
        if not isinstance(arm, dict):
            raise ProductionGateError(message)
        weapon = arm.get("weapon")
        parameters = arm.get("stable_parameters")
        expected_hash = arm.get("artifact_sha256")
        if (
            weapon not in WEAPONS
            or weapon in reviewed
            or arm.get("status") != "reviewed"
            or not isinstance(arm.get("reviewer"), str)
            or not arm["reviewer"].strip()
            or not isinstance(arm.get("review_note"), str)
            or not arm["review_note"].strip()
            or not isinstance(parameters, dict)
            or not parameters
            or not isinstance(expected_hash, str)
            or not _SHA256_RE.fullmatch(expected_hash)
        ):
            raise ProductionGateError(message)
        current_hash = _root_file_sha256(root_fd, arm.get("artifact"))
        if current_hash is None or not hmac.compare_digest(current_hash, expected_hash):
            raise ProductionGateError(message)
        reviewed[weapon] = arm

    selected_weapons = selection.get("required_weapons")
    selected_parameters = selection.get("stable_parameters")
    approved_parameters = {weapon: reviewed[weapon]["stable_parameters"] for weapon in WEAPONS}
    if (
        selection.get("status") != "approved"
        or not isinstance(selection.get("reviewer"), str)
        or not selection["reviewer"].strip()
        or not isinstance(selection.get("rationale"), str)
        or not selection["rationale"].strip()
        or not isinstance(selected_weapons, list)
        or len(selected_weapons) != len(WEAPONS)
        or set(selected_weapons) != set(WEAPONS)
        or selected_parameters != approved_parameters
    ):
        raise ProductionGateError(message)


def assert_dialogue_drama_production_evidence(
    root: Path, *, force: bool = False
) -> dict[str, Any]:
    """Hard-gate dialogue final/bulk on TTS, package, lipsync, and benchmark proof.

    H3 prefer_native / post-lipsync freeze: skip when force or
    AIFILM_SKIP_DIALOGUE_PACKAGE_GATE=1 (plate path; not master).
    """
    if force or os.environ.get("AIFILM_SKIP_DIALOGUE_PACKAGE_GATE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return {
            "checked": False,
            "reason": "skipped_force_or_env",
            "note": "post lipsync frozen; H3 prefer_native plate may skip package gate",
        }
    base, root_fd = _open_gate_root(root)
    try:
        spec = _read_regular_json(
            root_fd,
            Path("film-spec.json"),
            code="dialogue evidence gate: missing or unsafe film-spec.json",
        )
        if spec.get("vo_mode") != "dialogue_drama":
            return {"checked": False, "reason": "not_dialogue_drama"}
        package = _read_regular_json(
            root_fd,
            Path("dialogue-scene-package.json"),
            code="dialogue package gate: missing or unsafe dialogue-scene-package.json",
        )
        try:
            from dialogue_scene_package import validate_dialogue_scene_package
        except ImportError as exc:
            raise ProductionGateError("dialogue package gate: validator unavailable") from exc
        result = validate_dialogue_scene_package(package, production=True, root=base)
        if not result.get("ok"):
            codes = ", ".join(str(item.get("code")) for item in result.get("errors") or [])
            raise ProductionGateError(
                "dialogue package gate: production evidence incomplete "
                f"[{codes or 'PACKAGE_INVALID'}]; H3 prefer_native: "
                "AIFILM_SKIP_DIALOGUE_PACKAGE_GATE=1 or --allow-loop-risk force path; "
                "not LatentSync (frozen)."
            )
        if spec.get("dialogue_benchmark_required") is True:
            benchmark = _read_regular_json(
                root_fd,
                Path("receipts/dialogue-weapon-benchmark.json"),
                code="dialogue benchmark gate: missing or unsafe benchmark receipt",
            )
            _assert_dialogue_benchmark_receipt(root_fd, package, benchmark)
        return {"ok": True, "checked": True, "line_package": True}
    finally:
        os.close(root_fd)


def pilot_approval_path(root: Path) -> Path:
    return Path(root).expanduser().resolve() / "receipts" / PILOT_APPROVAL_NAME


def load_pilot_approval(root: Path) -> dict[str, Any]:
    return read_json(pilot_approval_path(root) or {})


def pilot_is_user_approved(data: dict[str, Any] | None) -> bool:
    """True only when user (not agent) approved pilot."""
    if not isinstance(data, dict) or data.get("approved") is not True:
        return False
    by = str(data.get("approved_by") or "").strip().lower()
    # Agent self-approve is never enough
    if by in {"agent", "bot", "system", "auto", "grok", "grok-agent"}:
        return False
    if by in {"user", "human", "owner"}:
        return True
    notes = str(data.get("notes") or "")
    if "pilot 过" in notes or "pilot过" in notes:
        return True
    return bool("user approved pilot" in notes.lower() or "pilot passed by user" in notes.lower())


def assert_provider_pilot_current(root: Path) -> dict[str, Any]:
    """Prevent a provider fallback from silently reusing an old hero pilot."""
    routing = read_json(Path(root).expanduser().resolve() / "receipts" / "i2v-routing.json") or {}
    if routing.get("requires_hero_repilot") is not True:
        return {"ok": True, "checked": False}
    approval = load_pilot_approval(root)
    pilot_route = approval.get("i2v_routing") if isinstance(approval, dict) else None
    selected = str(routing.get("selected_provider") or "")
    if (
        not isinstance(pilot_route, dict)
        or str(pilot_route.get("selected_provider") or "") != selected
    ):
        raise ProductionGateError(
            "provider fallback changed the hero route; obtain a new user-approved pilot "
            f"for provider={selected!r} before bulk media"
        )
    return {"ok": True, "checked": True, "provider": selected}


def assert_pilot_user_approved(
    root: Path,
    *,
    force: bool = False,
    env_skip: bool = True,
) -> dict[str, Any]:
    """Strict check: user pilot must already be on disk (used by final / status helpers)."""
    if force:
        return {"skipped": True, "reason": "force"}
    if env_skip and os.environ.get("AIFILM_SKIP_PILOT_GATE", "").strip() in {"1", "true", "yes"}:
        return {"skipped": True, "reason": "env"}
    data = load_pilot_approval(root)
    if pilot_is_user_approved(data):
        _assert_pilot_quality_evidence(root, data)
        return {"ok": True, "pilot": data}
    path = pilot_approval_path(root)
    if not path.is_file():
        raise ProductionGateError(
            "pilot gate: missing receipts/pilot-approval.json with "
            '{"approved": true, "approved_by": "user", ...}. '
            f"Generate ≤{PILOT_MAX_SHOTS_WITHOUT_APPROVAL} pilot shots, get user approval, "
            "then queue bulk work. Emergency: --allow-without-pilot or AIFILM_SKIP_PILOT_GATE=1"
        )
    raise ProductionGateError(
        "pilot gate: pilot-approval.json exists but is not user-approved "
        f"(need approved=true and approved_by=user). got approved={data.get('approved')!r} "
        f"approved_by={data.get('approved_by')!r}. "
        "Do not self-approve. Wait for user phrase like 'pilot 过'."
    )


def _assert_pilot_adult_three_beat(root: Path, approval: dict[str, Any]) -> None:
    """max heat bulk requires pilot cover undress + union/rhythm impact trio.

    Wave 2 · 2026-07-29: pick_pilot already prefers these beats; approval must
    not silently approve only hook/setup.
    """
    base = Path(root).expanduser().resolve()
    spec = read_json(base / "film-spec.json") or {}
    heat = str(spec.get("heat_scale") or "").strip().lower()
    if heat not in {"max", "hot"}:
        return
    if spec.get("adult_max_iron") is False:
        return
    if approval.get("skip_adult_pilot_beats") is True:
        return
    pilot_shots = {str(s) for s in (approval.get("shots") or []) if s}
    if not pilot_shots:
        return
    covered: set[str] = set()
    film_has_coitus = False
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for sh in scene.get("shots") or []:
            if not isinstance(sh, dict):
                continue
            dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
            cb = str(sh.get("coitus_beat") or dsl.get("coitus_beat") or "").strip().lower()
            if cb in {"undress", "union", "rhythm", "entry", "lock", "finish"}:
                film_has_coitus = True
            sid = str(sh.get("id") or "")
            if sid not in pilot_shots:
                continue
            ph = str(sh.get("heat_phase") or dsl.get("heat_phase") or "").strip().lower()
            if cb:
                covered.add(cb)
            if ph in {"act", "climax", "foreplay"}:
                covered.add(ph)
    if not film_has_coitus:
        return
    has_undress = bool(covered & {"undress", "foreplay"})
    has_union = bool(covered & {"union", "entry", "lock"})
    has_rhythm = bool(covered & {"rhythm", "act", "finish", "climax"})
    # require undress ladder evidence + at least one meat beat
    if not has_undress or not (has_union or has_rhythm):
        raise ProductionGateError(
            "pilot gate (adult max): approval shots must cover undress ladder + "
            "union/rhythm impact (pick undress + union + rhythm). "
            f"covered={sorted(covered) or 'none'} pilot={sorted(pilot_shots)}. "
            "Re-run: aifilm pilot report / pick → score → approve with those shot ids. "
            "Override: pilot-approval skip_adult_pilot_beats:true (not recommended)."
        )


def _assert_pilot_quality_evidence(root: Path, approval: dict[str, Any]) -> None:
    """New evidence-contract projects cannot bulk from stale pilot approvals."""
    # Adult three-beat is always-on for max heat (Wave 2); quality evidence stays contract-gated
    _assert_pilot_adult_three_beat(root, approval)
    manifest = read_json(Path(root).expanduser().resolve() / "manifest.json") or {}
    if int(manifest.get("quality_evidence_contract_version") or 0) < 1:
        return
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    pilot_shots = approval.get("shots") if isinstance(approval.get("shots"), list) else []
    if not pilot_shots:
        raise ProductionGateError("pilot approval lacks reviewed pilot shot ids")
    try:
        from quality_evidence import quality_evidence_is_current
    except ImportError as exc:
        raise ProductionGateError("quality evidence verifier is unavailable") from exc
    stale: list[str] = []
    for shot_id in pilot_shots:
        record = clips.get(str(shot_id))
        if not isinstance(record, dict):
            stale.append(str(shot_id))
            continue
        clip = Path(str(record.get("path") or ""))
        if not quality_evidence_is_current(record.get("quality_evidence"), clip=clip):
            stale.append(str(shot_id))
    if stale:
        raise ProductionGateError(
            "pilot approval is missing current shot-quality evidence for: "
            + ", ".join(sorted(stale))
        )


def assert_pilot_allows_add(
    root: Path,
    *,
    shot_id: str,
    existing_shot_ids: set[str],
    force: bool = False,
    env_skip: bool = True,
) -> dict[str, Any]:
    """S3 gate for media-queue add.

    - User-approved pilot → allow any shot.
    - Else allow at most PILOT_MAX_SHOTS_WITHOUT_APPROVAL distinct shot_ids (pilot window).
    - force / AIFILM_SKIP_PILOT_GATE=1 → skip (tests / emergency).
    """
    # A bounded concept pilot may precede its compiled film spec. Once a
    # strict production contract exists, force cannot bypass its audit.
    spec = read_json(root / "film-spec.json")
    if isinstance(spec, dict) and (spec.get("cinematic_audit_strict") is True or force):
        try:
            from cinematic_audit import audit

            cinematic = audit(root, require_authored_contract=True)
        except Exception as exc:  # noqa: BLE001
            raise ProductionGateError(f"cinematic queue gate unavailable: {exc}") from exc
        if not cinematic.get("ok"):
            raise ProductionGateError(
                "cinematic queue gate: HARD block media-queue add — impact: "
                + ",".join(cinematic.get("blocking_codes") or ["UNKNOWN"])
            )
    if force:
        return {"skipped": True, "reason": "force"}
    if env_skip and os.environ.get("AIFILM_SKIP_PILOT_GATE", "").strip() in {"1", "true", "yes"}:
        return {"skipped": True, "reason": "env"}
    pilot = load_pilot_approval(root)
    if pilot_is_user_approved(pilot):
        assert_provider_pilot_current(root)
        # Wave A2: when pilot-go.json exists, require ok before bulk beyond pilot window
        try:
            from pilot_pack import assert_pilot_go_allows_bulk

            assert_pilot_go_allows_bulk(root, force=force)
        except ProductionGateError:
            raise
        except Exception:
            pass
        return {"ok": True, "pilot": pilot}
    known = set(existing_shot_ids) | {shot_id}
    if len(known) <= PILOT_MAX_SHOTS_WITHOUT_APPROVAL:
        return {
            "ok": True,
            "pilot_window": True,
            "distinct_shots": sorted(known),
            "max_without_approval": PILOT_MAX_SHOTS_WITHOUT_APPROVAL,
        }
    path = pilot_approval_path(root)
    root_s = str(Path(root).expanduser().resolve())
    raise ProductionGateError(
        f"pilot gate: cannot add shot_id={shot_id!r} — already have {len(existing_shot_ids)} "
        f"distinct shot(s) queued without user pilot approval "
        f"(max {PILOT_MAX_SHOTS_WITHOUT_APPROVAL}). Write {path} with "
        f'{{"approved": true, "approved_by": "user", "shots": ["shot01",...], "notes": "..."}} '
        f"after the user confirms pilot stills, then retry add. Agent must not self-approve. "
        f'Next: aifilm pilot report --root "{root_s}" → '
        f'pilot score … → pilot approve --user-phrase "pilot 过". '
        f"Emergency: --allow-without-pilot or AIFILM_SKIP_PILOT_GATE=1"
    )


def assert_heat_allows_media(
    root: Path,
    *,
    force: bool = False,
    env_skip: bool = True,
) -> dict[str, Any]:
    """Wave 5: fail-closed bulk when adult-max heat_agent_status is hard_fail.

    Pilot skip (allow_without_pilot) does **not** bypass this — scale is orthogonal
    to pilot approval. Emergency: force=True or AIFILM_SKIP_HEAT_QUEUE_GATE=1.
    """
    if force:
        return {"skipped": True, "reason": "force"}
    if env_skip and os.environ.get("AIFILM_SKIP_HEAT_QUEUE_GATE", "").strip() in {
        "1",
        "true",
        "yes",
    }:
        return {"skipped": True, "reason": "env"}
    try:
        from heat_check import heat_agent_status
    except ImportError as exc:
        raise ProductionGateError(
            "heat queue gate: heat_check unavailable — cannot verify adult max scale"
        ) from exc
    try:
        hs = heat_agent_status(root)
    except Exception as exc:  # noqa: BLE001
        raise ProductionGateError(
            f"heat queue gate: heat_agent_status failed ({exc!s:.160}); "
            "fix heat / film-spec before media-queue add"
        ) from exc
    if not hs.get("active"):
        return {"ok": True, "active": False, "reason": hs.get("reason")}
    if not hs.get("hard_fail"):
        return {
            "ok": True,
            "active": True,
            "hard_fail": False,
            "needs_boost": bool(hs.get("needs_boost")),
            "score": hs.get("score"),
            "grade": hs.get("grade"),
        }
    root_s = str(Path(root).expanduser().resolve())
    boost = hs.get("next_cmd") or f'aifilm heat boost --root "{root_s}" --apply'
    why = hs.get("why") or (f"adult max heat hard_fail impact={hs.get('grade')}:{hs.get('score')}")
    raise ProductionGateError(
        f"heat queue gate: HARD block media-queue add — {why}. "
        f"Run {boost} first (scale before bulk). "
        "Emergency: AIFILM_SKIP_HEAT_QUEUE_GATE=1 (not recommended)."
    )


def assert_heat_allows_final(
    root: Path,
    *,
    force: bool = False,
    env_skip: bool = True,
    require_s: bool = True,
    write_receipt: bool = True,
) -> dict[str, Any]:
    """Wave 6: fail-closed final/export when adult-max heat is not final_ok.

    - hard_fail (below A / field codes) always blocks
    - needs_boost (below S target, default 90) blocks when require_s=True
    Emergency: force=True or AIFILM_SKIP_HEAT_FINAL_GATE=1
    """
    if force:
        return {"skipped": True, "reason": "force"}
    if env_skip and os.environ.get("AIFILM_SKIP_HEAT_FINAL_GATE", "").strip() in {
        "1",
        "true",
        "yes",
    }:
        return {"skipped": True, "reason": "env"}
    try:
        from heat_check import heat_agent_status
    except ImportError as exc:
        raise ProductionGateError(
            "heat final gate: heat_check unavailable — cannot verify adult max scale"
        ) from exc
    try:
        hs = heat_agent_status(root)
    except Exception as exc:  # noqa: BLE001
        raise ProductionGateError(
            f"heat final gate: heat_agent_status failed ({exc!s:.160}); "
            "fix heat / film-spec before final"
        ) from exc
    if not hs.get("active"):
        return {"ok": True, "active": False, "reason": hs.get("reason")}
    final_ok = bool(hs.get("final_ok"))
    if not require_s:
        final_ok = not bool(hs.get("hard_fail")) and bool(hs.get("field_ok", True))
    if final_ok:
        out = {
            "ok": True,
            "active": True,
            "final_ok": True,
            "score": hs.get("score"),
            "grade": hs.get("grade"),
            "target_s": hs.get("target_s"),
        }
        if write_receipt:
            try:
                from util import utc_now, write_json

                write_json(
                    Path(root).expanduser().resolve() / "receipts" / "heat-final-gate.json",
                    {
                        "ok": True,
                        "at": utc_now(),
                        "score": hs.get("score"),
                        "grade": hs.get("grade"),
                        "floor": hs.get("floor"),
                        "target_s": hs.get("target_s"),
                        "final_ok": True,
                        "source": "assert_heat_allows_final",
                    },
                )
            except (OSError, ValueError):
                pass
        return out
    root_s = str(Path(root).expanduser().resolve())
    boost = hs.get("next_cmd") or f'aifilm heat boost --root "{root_s}" --apply'
    why = hs.get("why") or (
        f"adult max heat not final_ok impact={hs.get('grade')}:{hs.get('score')} "
        f"(need S≥{hs.get('target_s') or 90})"
    )
    raise ProductionGateError(
        f"heat final gate: HARD block final/export — {why}. "
        f"Run {boost} until impact ≥S and heat arc/duration ok. "
        "Emergency: AIFILM_SKIP_HEAT_FINAL_GATE=1 or --skip-heat-gate (not recommended)."
    )


def _flatten_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    scenes = spec.get("scenes") or []
    if isinstance(scenes, list):
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            for shot in scene.get("shots") or []:
                if isinstance(shot, dict):
                    out.append(shot)
    # Top-level shots (short-form film-spec may only use this list)
    top = spec.get("shots") or []
    if isinstance(top, list) and top:
        seen = {str(s.get("id") or "") for s in out}
        for shot in top:
            if not isinstance(shot, dict):
                continue
            sid = str(shot.get("id") or "")
            if sid and sid in seen:
                continue
            out.append(shot)
    return out


def _measured_map_for_root(root: Path | None) -> dict[str, float]:
    if root is None:
        return {}
    try:
        from tts_rehearsal import measured_vo_by_shot

        return measured_vo_by_shot(Path(root))
    except Exception:
        return {}


def _shot_would_stream_loop(
    *,
    plate_sec: float,
    vo_sec: float,
    dramatic_function: str | None,
) -> bool:
    """True only if edit_policy.plan_stretch would still use stream_loop.

    P0 · 2026-07-23: short I2V plates clamp/forbid_loop instead of replaying —
    VO slightly over 5.5s is no longer a hard gate when loops=0.
    """
    try:
        from edit_policy import plan_stretch

        # Target ≈ VO + tiny pad (render_final adds vo_pad); plate is I2V source.
        target = max(float(vo_sec), 0.05)
        src = max(float(plate_sec), 0.05)
        plan = plan_stretch(
            src,
            target,
            dramatic_function=dramatic_function,
        )
        return int(plan.get("loops") or 0) > 0
    except Exception:
        # Fall back to legacy threshold if policy import fails
        return float(vo_sec) > LOOP_RISK_VO_SEC and float(plate_sec) <= 6.5


def loop_risk_shots_from_spec(
    spec: dict[str, Any],
    *,
    measured_by_shot: dict[str, float] | None = None,
    root: Path | None = None,
) -> list[str]:
    """Return shot ids whose VO would still force stream_loop after edit policy.

    When measured_by_shot (or root rehearsal receipt) is present, prefer measured
    seconds over estimate_nar_vo_sec / cached _vo_budget.
    """
    measured = dict(measured_by_shot or {})
    if not measured and root is not None:
        measured = _measured_map_for_root(root)

    risk: list[str] = []
    for shot in _flatten_shots(spec):
        sid = str(shot.get("id") or "?")
        nar = str(shot.get("nar") or shot.get("narration") or "")
        if measured:
            try:
                from tts_rehearsal import effective_vo_sec

                vo, _src = effective_vo_sec(
                    sid,
                    nar,
                    est_vo_sec=shot.get("est_vo_sec"),
                    measured_by_shot=measured,
                )
            except Exception:
                vo = float(shot.get("est_vo_sec") or estimate_nar_vo_sec(nar))
        else:
            try:
                vo = float(shot.get("est_vo_sec") or estimate_nar_vo_sec(nar))
            except (TypeError, ValueError):
                vo = estimate_nar_vo_sec(nar)
        try:
            dur = float(shot.get("duration_sec") or DEFAULT_DURATION_SEC)
        except (TypeError, ValueError):
            dur = float(DEFAULT_DURATION_SEC)
        beat = str(shot.get("dramatic_function") or shot.get("beat") or shot.get("function") or "")
        # P0 · 2026-07-23: only flag when plan_stretch still uses stream_loop.
        # Shortform clamp forbids loop on ≤7.5s plates — VO slightly >5.5s is OK.
        if _shot_would_stream_loop(plate_sec=dur, vo_sec=vo, dramatic_function=beat or None) or (
            vo > LOOP_RISK_VO_SEC and dur <= 6.5
        ):
            risk.append(sid)
    # Do not trust stale _vo_budget.loop_risk_shots (pre shortform clamp policy)
    return risk


def measured_over_plate_shots(
    spec: dict[str, Any],
    measured_by_shot: dict[str, float],
    *,
    slack_sec: float | None = None,
) -> list[str]:
    """Shot ids where measured VO exceeds duration_sec + vo_pacing slack."""
    slack = VO_PACING_SLACK_SEC if slack_sec is None else float(slack_sec)
    over: list[str] = []
    for shot in _flatten_shots(spec):
        sid = str(shot.get("id") or "").strip()
        if not sid or sid not in measured_by_shot:
            continue
        try:
            plate = float(shot.get("duration_sec") or DEFAULT_DURATION_SEC)
        except (TypeError, ValueError):
            plate = float(DEFAULT_DURATION_SEC)
        try:
            m = float(measured_by_shot[sid])
        except (TypeError, ValueError):
            continue
        if m > plate + slack:
            over.append(sid)
    return over


def assert_tts_rehearsal_timing(
    root: Path,
    *,
    strict: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Gate final/preflight on measured VO when rehearsal receipt is present/required.

    - Receipt present → measured preferred; over-plate shots hard-fail.
    - strict=True (or film-spec tts_rehearsal_required / env) → missing receipt hard-fails.
    """
    if force:
        return {"skipped": True, "reason": "force"}
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json") or {}
    env_strict = os.environ.get("AIFILM_STRICT_TTS_REHEARSAL", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    spec_strict = bool(spec.get("tts_rehearsal_required") is True) if spec else False
    strict = bool(strict or env_strict or spec_strict)

    try:
        from tts_rehearsal import TTSRehearsalError, bind_receipt_to_spec_timing
    except ImportError as exc:
        if strict:
            raise ProductionGateError(
                f"tts rehearsal timing: tts_rehearsal unavailable: {exc}"
            ) from exc
        return {"present": False, "ok": True, "skipped": True, "reason": "module_missing"}

    try:
        report = bind_receipt_to_spec_timing(root, strict=strict, raise_on_fail=False)
    except TTSRehearsalError as exc:
        raise ProductionGateError(str(exc)) from exc

    if strict and not report.get("present"):
        raise ProductionGateError(
            "tts rehearsal timing (strict): missing receipts/tts-rehearsal.json — "
            'run aifilm tts-rehearse --root "<root>" before final/bulk '
            "(or drop tts_rehearsal_required / --strict-tts-rehearsal)."
        )
    over = list(report.get("over_plate_shots") or [])
    if over:
        raise ProductionGateError(
            "tts rehearsal timing: measured VO exceeds plate on "
            f"{over} (vo_pacing with measured_duration_sec, slack "
            f"{VO_PACING_SLACK_SEC}s). Shorten nar, raise duration_sec, split shots, "
            "or re-run tts-rehearse after edits. "
            "--allow-loop-risk does NOT skip measured over-plate; fix VO budget."
        )
    return report


def assert_no_loop_risk(
    root: Path | None = None,
    *,
    spec: dict[str, Any] | None = None,
    force: bool = False,
    env_skip: bool = True,
    strict_tts_rehearsal: bool = False,
) -> list[str]:
    """Block final when loop_risk_shots non-empty (defense in depth after write-spec vo_pacing).

    When root has receipts/tts-rehearsal.json, prefers measured_duration_sec over
    estimate_nar_vo_sec for risk detection. Measured over-plate hard-fails even when
    force/allow_loop_risk is set (separate vo_pacing truth).
    """
    data = spec
    if data is None and root is not None:
        path = Path(root).expanduser().resolve() / "film-spec.json"
        data = read_json(path) or {}
        if not data:
            if force:
                return []
            raise ProductionGateError(f"loop-risk gate: film-spec missing at {path}")
        try:
            validate_film_spec(data, assign_missing_ids=False)
        except FilmSpecError as exc:
            if force:
                return []
            raise ProductionGateError(f"loop-risk gate: film-spec invalid: {exc}") from exc
    if data is None and root is None:
        raise ProductionGateError("assert_no_loop_risk requires root or spec")

    # Measured over-plate always enforced when root given (receipt present → use it)
    if root is not None:
        assert_tts_rehearsal_timing(
            Path(root),
            strict=strict_tts_rehearsal,
            force=False,
        )
        assert_dialogue_drama_production_evidence(Path(root), force=bool(force))

    if force:
        return []
    if env_skip and os.environ.get("AIFILM_SKIP_LOOP_RISK_GATE", "").strip() in {
        "1",
        "true",
        "yes",
    }:
        return []
    if data is None:
        return []

    measured = _measured_map_for_root(Path(root) if root is not None else None)
    risk = loop_risk_shots_from_spec(
        data, measured_by_shot=measured or None, root=Path(root) if root else None
    )
    if risk:
        src = "measured" if measured else "est_vo"
        raise ProductionGateError(
            "loop-risk gate: these shots have VO too long for a 6s plate "
            f"({src} > {LOOP_RISK_VO_SEC}s) and would stream_loop (boring replay): {risk}. "
            "Split into more shots with shorter nar (≤28 chars recommended), then write-spec. "
            "If tts-rehearsal receipt exists, measured_duration_sec is used. "
            "Emergency only: --allow-loop-risk or AIFILM_SKIP_LOOP_RISK_GATE=1"
        )
    return risk
