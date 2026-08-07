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
from util.errors import FilmError

PILOT_MAX_SHOTS_WITHOUT_APPROVAL = 3
PILOT_APPROVAL_NAME = "pilot-approval.json"
_MAX_GATE_JSON_BYTES = 4 * 1024 * 1024
_MAX_BENCHMARK_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ProductionGateError(FilmError):
    """Raised when a production gate blocks the operation."""


def _env_skip_armed(
    name: str,
    root: Path | str | None,
    *,
    env_skip: bool = True,
    call_site: str,
) -> bool:
    """Honesty-rail: env SKIP via central skip_flag (ledger when root known)."""
    if not env_skip:
        return False
    try:
        from core.skip_audit import skip_flag

        return skip_flag(
            name,
            origin="env",
            film_root=root,
            call_site=call_site,
        )
    except Exception as exc:
        # C5.1 · surface fallback path (legacy direct env read)
        try:
            from util.logger import log

            log.debug("skip_flag unavailable for %s at %s: %s", name, call_site, exc)
        except Exception:
            pass
        return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


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
    if _env_skip_armed(
        "AIFILM_SKIP_PILOT_GATE",
        root,
        env_skip=env_skip,
        call_site="assert_pilot_user_approved",
    ):
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
    if _env_skip_armed(
        "AIFILM_SKIP_PILOT_GATE",
        root,
        env_skip=env_skip,
        call_site="assert_pilot_user_approved_for_queue",
    ):
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
        except Exception as exc:
            # Fail-closed: if the bulk allow-check cannot be verified for any
            # reason (import error, unexpected exception, ...), the gate MUST
            # block — never silently swallow and return {"ok": True}.
            raise ProductionGateError(
                f"pilot-go bulk allow-check failed (cannot verify): {exc}"
            ) from exc
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
    if _env_skip_armed(
        "AIFILM_SKIP_HEAT_QUEUE_GATE",
        root,
        env_skip=env_skip,
        call_site="assert_heat_allows_media",
    ):
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
    if env_skip:
        try:
            from core.skip_audit import skip_flag

            skipped = skip_flag(
                "AIFILM_SKIP_HEAT_FINAL_GATE",
                origin="env",
                film_root=root,
                call_site="assert_heat_allows_final",
            )
        except Exception:
            skipped = os.environ.get("AIFILM_SKIP_HEAT_FINAL_GATE", "").strip().lower() in {
                "1",
                "true",
                "yes",
            }
        if skipped:
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
            except (OSError, ValueError) as exc:
                # A1 · gate pass without receipt is dishonest — fail closed
                raise ProductionGateError(
                    "heat final gate: final_ok but cannot write "
                    f"receipts/heat-final-gate.json: {exc}"
                ) from exc
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
    """Load measured VO map for loop-risk.

    A1 · if ``receipts/tts-rehearsal.json`` exists, probe/import/parse failures
    are **fail-closed** (ProductionGateError). Never silently return ``{}`` and
    fall back to est_vo while a broken receipt is on disk.
    """
    if root is None:
        return {}
    base = Path(root).expanduser().resolve()
    receipt = base / "receipts" / "tts-rehearsal.json"
    try:
        from tts_rehearsal import measured_vo_by_shot
    except ImportError as exc:
        if receipt.is_file():
            raise ProductionGateError(
                "loop-risk measured VO: tts-rehearsal.json present but "
                f"tts_rehearsal module unavailable: {exc}"
            ) from exc
        return {}

    if receipt.is_file():
        try:
            raw = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProductionGateError(
                f"loop-risk measured VO: tts-rehearsal receipt unreadable: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise ProductionGateError(
                "loop-risk measured VO: tts-rehearsal receipt must be a JSON object"
            )

    try:
        out = measured_vo_by_shot(base)
    except Exception as exc:
        raise ProductionGateError(
            f"loop-risk measured VO: probe failed: {exc}"
        ) from exc
    return out if isinstance(out, dict) else {}


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
    if _env_skip_armed(
        "AIFILM_SKIP_LOOP_RISK_GATE",
        root,
        env_skip=env_skip,
        call_site="assert_no_loop_risk",
    ):
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


# --- Anti-boring variety hard gate (P0 · shot-variety-anti-boring) ---
# Sedimented from references/lessons-2026-07-29-shot-variety-anti-boring.md:
#   A1  forbid adjacent shots sharing the same dsl.motion (one motion language / shot)
#   B1  shot_size / dsl.shot_size / dsl.camera.shot_size must agree (else rank is ambiguous)
#   D1  main-beat plates must stay >= 4.5s (don't crush sustained beats into a PPT)
#   景别序列去重: >=3 consecutive identical size rank reads as a slide, not a cut
_ANTI_BORING_MAIN_BEAT_MIN_SEC = 4.5
_ANTI_BORING_MAX_SAME_SIZE_RUN = 2  # run length > this => flat (>=3 same in a row)
_ANTI_BORING_MAIN_BEAT_FUNCTIONS = frozenset(
    {
        "hook_strong",
        "main",
        "turn",
        "action",
        "setpiece",
        "act",
        "climax",
        "union",
        "rhythm",
        "foreplay",
        "meat",
        "reveal",
        "payoff",
        "confrontation",
        "resolution",
    }
)

_SHOT_SIZE_RANK = {
    "ews": 0,
    "extreme_wide": 0,
    "ws": 1,
    "wide": 1,
    "long": 1,
    "mws": 2,
    "medium_wide": 2,
    "ms": 3,
    "medium": 3,
    "mcu": 4,
    "medium_close_up": 4,
    "cu": 5,
    "close_up": 5,
    "ecu": 6,
    "extreme_close_up": 6,
}


def _shot_size_fields(shot: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (where, value) for every present size field on a shot."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    fields: list[tuple[str, str]] = []
    if shot.get("shot_size"):
        fields.append(("shot_size", str(shot["shot_size"]).strip().lower()))
    if dsl.get("shot_size"):
        fields.append(("dsl.shot_size", str(dsl["shot_size"]).strip().lower()))
    if cam.get("shot_size"):
        fields.append(("dsl.camera.shot_size", str(cam["shot_size"]).strip().lower()))
    return fields


def _shot_size_rank(shot: dict[str, Any]) -> int | None:
    fields = _shot_size_fields(shot)
    if not fields:
        return None
    for _where, value in fields:
        key = value.replace("-", "_").replace(" ", "_")
        if key in _SHOT_SIZE_RANK:
            return _SHOT_SIZE_RANK[key]
    return None


def _shot_motion(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    return str(dsl.get("motion") or shot.get("motion") or "").strip().lower()


def anti_boring_variety_report(spec: dict[str, Any]) -> dict[str, Any]:
    """Detect the four anti-boring failure modes.

    Returns {"ok", "checked", "codes", "issues"}. Does not raise; callers decide
    whether to block (assert_anti_boring_variety flips to hard under anti_boring_strict).
    """
    issues: list[dict[str, Any]] = []
    if not isinstance(spec, dict):
        return {"ok": True, "checked": False, "codes": [], "issues": []}
    shots = _flatten_shots(spec)
    if not shots:
        return {"ok": True, "checked": False, "codes": [], "issues": []}

    # B1: size fields declared in multiple places must agree
    for sh in shots:
        sid = str(sh.get("id") or "?")
        fields = _shot_size_fields(sh)
        if len(fields) >= 2 and len({v for _w, v in fields}) > 1:
            issues.append(
                {
                    "code": "ANTI_BORING_SIZE_FIELD_CONFLICT",
                    "shot_id": sid,
                    "fields": fields,
                    "message": (
                        f"{sid}: shot_size declared in multiple places that disagree: {fields}"
                    ),
                }
            )

    # D1: main-beat duration floor (don't crush sustained beats into a PPT)
    for sh in shots:
        sid = str(sh.get("id") or "?")
        fn = str(
            sh.get("dramatic_function") or sh.get("beat") or sh.get("function") or ""
        ).strip().lower()
        if fn not in _ANTI_BORING_MAIN_BEAT_FUNCTIONS:
            continue
        try:
            dur = float(sh.get("duration_sec") or DEFAULT_DURATION_SEC)
        except (TypeError, ValueError):
            dur = float(DEFAULT_DURATION_SEC)
        if dur + 1e-9 < _ANTI_BORING_MAIN_BEAT_MIN_SEC:
            issues.append(
                {
                    "code": "ANTI_BORING_MAIN_BEAT_TOO_SHORT",
                    "shot_id": sid,
                    "duration_sec": dur,
                    "min_sec": _ANTI_BORING_MAIN_BEAT_MIN_SEC,
                    "message": (
                        f"{sid}: main-beat plate {dur}s < min "
                        f"{_ANTI_BORING_MAIN_BEAT_MIN_SEC}s (don't crush main beats to PPT)"
                    ),
                }
            )

    # A1: adjacent shots must not share the same motion language
    prev_motion = None
    prev_id = None
    for sh in shots:
        sid = str(sh.get("id") or "?")
        motion = _shot_motion(sh)
        if motion and motion == prev_motion:
            issues.append(
                {
                    "code": "ANTI_BORING_MOTION_ADJACENT_DUP",
                    "shot_id": sid,
                    "prev_shot_id": prev_id,
                    "motion": motion,
                    "message": (
                        f"{sid}: dsl.motion {motion!r} duplicates adjacent {prev_id} "
                        "— one motion language per shot"
                    ),
                }
            )
        prev_motion = motion
        prev_id = sid

    # 景别序列去重: >=3 consecutive identical size rank reads as a slide
    run = 0
    run_rank: int | None = None
    run_ids: list[str] = []
    for sh in shots:
        sid = str(sh.get("id") or "?")
        rank = _shot_size_rank(sh)
        if rank is None:
            run, run_rank, run_ids = 0, None, []
            continue
        if rank == run_rank:
            run += 1
            run_ids.append(sid)
        else:
            run, run_rank, run_ids = 1, rank, [sid]
        if run > _ANTI_BORING_MAX_SAME_SIZE_RUN and len(run_ids) >= 3:
            issues.append(
                {
                    "code": "ANTI_BORING_SIZE_SEQUENCE_FLAT",
                    "shot_ids": list(run_ids),
                    "rank": rank,
                    "message": (
                        f"size stack flat: {len(run_ids)} consecutive shots at size rank "
                        f"{rank} ({run_ids}) — vary camera size every <=2 shots"
                    ),
                }
            )
            run, run_rank, run_ids = 0, None, []  # report the run once

    return {
        "ok": len(issues) == 0,
        "checked": True,
        "codes": sorted({i["code"] for i in issues}),
        "issues": issues,
    }


def assert_anti_boring_variety(
    root: Path | None = None,
    *,
    spec: dict[str, Any] | None = None,
    force: bool = False,
    env_skip: bool = True,
) -> dict[str, Any]:
    """P0 anti-boring hard gate (lessons-2026-07-29-shot-variety-anti-boring).

    HARD when film-spec ``anti_boring_strict`` is True. Otherwise it only surfaces the
    variety debt as a soft advisory (so authors can see it before opting in), matching
    the project's incremental ``xxx_strict`` rollout pattern.

    Emergency escapes: ``force=True`` or ``AIFILM_SKIP_ANTI_BORING_GATE=1``.
    """
    if force:
        return {"skipped": True, "reason": "force"}
    if _env_skip_armed(
        "AIFILM_SKIP_ANTI_BORING_GATE",
        root,
        env_skip=env_skip,
        call_site="assert_anti_boring_variety",
    ):
        return {"skipped": True, "reason": "env"}
    data = spec
    if data is None and root is not None:
        path = Path(root).expanduser().resolve() / "film-spec.json"
        data = read_json(path) or {}
    if not isinstance(data, dict) or not data:
        return {"ok": True, "checked": False, "reason": "no_spec"}

    strict = bool(data.get("anti_boring_strict") is True)
    report = anti_boring_variety_report(data)
    if not report["codes"]:
        return {"ok": True, "checked": report.get("checked", False), "codes": []}
    if not strict:
        return {
            "ok": True,
            "checked": True,
            "soft": True,
            "codes": report["codes"],
            "issues": report["issues"],
        }
    message = "; ".join(f"[{i['code']}] {i['message']}" for i in report["issues"][:6])
    raise ProductionGateError(
        f"anti-boring gate (strict): {message} "
        "Fix variety debt: one motion language per shot (no adjacent dsl.motion dup); "
        "vary camera size every <=2 shots; keep main-beat plates >= 4.5s; make shot_size "
        "fields agree. "
        "Emergency: --skip-anti-boring or AIFILM_SKIP_ANTI_BORING_GATE=1"
    )


# --- Headroom / anti-crop gate (P1 · shortform headroom auto-protect) ---
# "防裁头": a too-short shot gets cropped/abrupt at the head; a scene-opening shot
# needs extra lead-in so the subject's entrance isn't cut. This is the *timeline*
# half of headroom — framing_lint.lint_framing_iron covers the *frame* half
# (composition: full head + headroom in the picture). Soft advisory by default;
# hard under headroom_strict or adult max heat (incremental rollout like P0 gates).
_HEADROOM_MIN_SHOT_SEC = 2.0
_HEADROOM_FIRST_SHOT_MIN_SEC = 3.5


def headroom_report(spec: dict[str, Any]) -> dict[str, Any]:
    """Detect timeline headroom / anti-crop failures.

    Returns {"ok", "checked", "codes", "issues"}. Does not raise; callers decide
    whether to block (assert_headroom_protected flips to hard under headroom_strict
    / adult max heat).
    """
    issues: list[dict[str, Any]] = []
    if not isinstance(spec, dict):
        return {"ok": True, "checked": False, "codes": [], "issues": []}

    def _dur(sh: dict[str, Any]) -> float | None:
        raw = sh.get("duration_sec")
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    # Every shot floor: micro-shots get cropped/abrupt ("裁头" risk).
    for sh in _flatten_shots(spec):
        sid = str(sh.get("id") or "?")
        dur = _dur(sh)
        if dur is None:
            continue
        if dur + 1e-9 < _HEADROOM_MIN_SHOT_SEC:
            issues.append(
                {
                    "code": "HEADROOM_SHOT_TOO_SHORT",
                    "shot_id": sid,
                    "duration_sec": dur,
                    "min_sec": _HEADROOM_MIN_SHOT_SEC,
                    "message": (
                        f"{sid}: shot {dur}s < floor {_HEADROOM_MIN_SHOT_SEC}s "
                        f"— too short, prone to head-crop / abrupt cut"
                    ),
                }
            )

    # Scene-opening shot needs extra lead-in so the subject's entrance isn't cut.
    scenes = spec.get("scenes") or []
    if isinstance(scenes, list):
        for sci, scene in enumerate(scenes):
            if not isinstance(scene, dict):
                continue
            shots = scene.get("shots") or []
            if not isinstance(shots, list) or not shots:
                continue
            first = next((s for s in shots if isinstance(s, dict)), None)
            if first is None:
                continue
            sid = str(first.get("id") or f"scene{sci}:0")
            dur = _dur(first)
            if dur is None:
                continue
            if dur + 1e-9 < _HEADROOM_FIRST_SHOT_MIN_SEC:
                issues.append(
                    {
                        "code": "HEADROOM_FIRST_SHOT_TOO_SHORT",
                        "shot_id": sid,
                        "duration_sec": dur,
                        "min_sec": _HEADROOM_FIRST_SHOT_MIN_SEC,
                        "message": (
                            f"{sid}: scene-opening shot {dur}s < lead-in floor "
                            f"{_HEADROOM_FIRST_SHOT_MIN_SEC}s — subject entrance may be cropped"
                        ),
                    }
                )

    return {
        "ok": len(issues) == 0,
        "checked": True,
        "codes": sorted({i["code"] for i in issues}),
        "issues": issues,
    }


def assert_headroom_protected(
    root: Path | None = None,
    *,
    spec: dict[str, Any] | None = None,
    force: bool = False,
    env_skip: bool = True,
) -> dict[str, Any]:
    """P1 headroom / anti-crop hard gate.

    HARD when film-spec ``headroom_strict`` is True, or adult ``heat_scale`` is
    max/hot/extreme. Otherwise surfaces as a soft advisory (incremental rollout).

    Emergency escapes: ``force=True`` or ``AIFILM_SKIP_HEADROOM_GATE=1``.
    """
    if force:
        return {"skipped": True, "reason": "force"}
    if _env_skip_armed(
        "AIFILM_SKIP_HEADROOM_GATE",
        root,
        env_skip=env_skip,
        call_site="assert_headroom_protected",
    ):
        return {"skipped": True, "reason": "env"}
    data = spec
    if data is None and root is not None:
        path = Path(root).expanduser().resolve() / "film-spec.json"
        data = read_json(path) or {}
    if not isinstance(data, dict) or not data:
        return {"ok": True, "checked": False, "reason": "no_spec"}

    strict = bool(data.get("headroom_strict") is True) or str(
        data.get("heat_scale") or ""
    ).lower() in {"max", "hot", "extreme"}
    report = headroom_report(data)
    if not report["codes"]:
        return {"ok": True, "checked": report.get("checked", False), "codes": []}
    if not strict:
        return {
            "ok": True,
            "checked": True,
            "soft": True,
            "codes": report["codes"],
            "issues": report["issues"],
        }
    message = "; ".join(f"[{i['code']}] {i['message']}" for i in report["issues"][:6])
    raise ProductionGateError(
        f"headroom gate (strict): {message} "
        "Fix: give every shot >= 2.0s and scene-opening shots >= 3.5s lead-in so the "
        "subject's head/entrance isn't cropped. "
        "Emergency: --skip-headroom or AIFILM_SKIP_HEADROOM_GATE=1"
    )


# --- Controlled transition-policy gate (P2 · HF 转场受控策略全量) ---
# references/hf-transition-policy.md: continue 接戏缝永远 hard match-cut；场景硬切
# 禁 whip/grid 等花哨转场；段落转场限 fade/dissolve。把"编辑语法"固化成可程序化
# 校验的默认门：spec 作者写错转场意图/风格时提前报错，而非渲染时才被
# enforce_continue_hard_joins 静默改掉（掩盖意图漂移）。
# Soft advisory by default; hard under transition_policy_strict or adult max heat.
_TRANSITION_POLICY_CONTINUE = frozenset(
    {"continue", "match", "match_cut", "match-cut", "byte"}
)
# Scene hard-cut 太花哨的转场（references/hf-transition-policy.md：whip 太快 / grid 太花）
_FLASHY_SCENE_STYLES = frozenset({"whip", "grid"})
# 段落/章间转场允许的 xfade 风格（fade 家族 + dissolve）
_PARAGRAPH_STYLES = frozenset({"fade", "fadeblack", "fadewhite", "dissolve", None})
# intro/outro / 纯 MG 段：放开 HF 转场全目录
_RELAX_ROLES = frozenset({"intro", "outro", "title", "credit", "mg"})


def _shot_chain_mode(shot: dict[str, Any]) -> str:
    if not isinstance(shot, dict):
        return ""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    return str(
        shot.get("chain_mode") or dsl.get("chain_mode") or shot.get("join") or ""
    ).strip().lower()


def transition_policy_report(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate the controlled transition policy on transition_intents/transition_styles.

    Returns {"ok", "checked", "codes", "issues"}. Does not raise; callers decide
    whether to block (assert_transition_policy flips to hard under
    transition_policy_strict / adult max heat).

    Seam type per join i (between shot i and shot i+1), using the *incoming* shot:
      - chain_mode in continue-set        -> "continue"  (hard match-cut only)
      - dramatic_function == chapter_transition -> "paragraph" (soft fade/dissolve)
      - scene_id change                   -> "scene_cut" (no whip/grid)
      - else                              -> "default"   (treated like scene_cut)
    intro/outro and pure-MG roles relax to allow-all (HF catalog open).
    """
    if not isinstance(spec, dict):
        return {"ok": True, "checked": False, "codes": [], "issues": []}
    intents = spec.get("transition_intents")
    if not isinstance(intents, list) or not intents:
        return {"ok": True, "checked": False, "codes": [], "issues": []}

    shots = _flatten_shots(spec)
    n = len(shots)
    n_joins = n - 1
    if n_joins <= 0:
        return {"ok": True, "checked": False, "codes": [], "issues": []}

    # shot -> scene id mapping (scene change ⇒ cross_scene)
    shot_to_scene: dict[str, str] = {}
    scenes = spec.get("scenes") or []
    if isinstance(scenes, list):
        for sci, sc in enumerate(scenes):
            if not isinstance(sc, dict):
                continue
            sid = str(sc.get("id") or f"scene{sci}")
            for sh in sc.get("shots") or []:
                if isinstance(sh, dict) and sh.get("id"):
                    shot_to_scene[str(sh.get("id"))] = sid
    styles = spec.get("transition_styles")
    if not isinstance(styles, list):
        styles = [None] * n_joins

    issues: list[dict[str, Any]] = []
    for i in range(n_joins):
        intent = str(intents[i] if i < len(intents) else "").strip().lower()
        style = styles[i] if i < len(styles) else None
        style = str(style).strip().lower() if style else None
        incoming = shots[i + 1] if i + 1 < n else {}
        chain = _shot_chain_mode(incoming)
        df = str((incoming or {}).get("dramatic_function") or "").strip().lower()
        role = str(
            (incoming or {}).get("role") or (incoming or {}).get("kind") or ""
        ).strip().lower()

        # intro/outro / pure-MG → allow all (HF catalog open)
        if role in _RELAX_ROLES:
            continue

        if chain in _TRANSITION_POLICY_CONTINUE:
            if intent != "hard":
                issues.append(
                    {
                        "code": "HF_TRANSITION_CONTINUE_NOT_HARD",
                        "join_index": i,
                        "intent": intent or None,
                        "message": (
                            f"join {i}: chain_mode={chain!r} (continue seam) but "
                            f"transition_intent={intent!r} — must be hard match-cut "
                            f"(forbid xfade/dissolve on continue 接戏缝)"
                        ),
                    }
                )
            continue
        if df == "chapter_transition":
            if intent != "soft" or (style is not None and style not in _PARAGRAPH_STYLES):
                issues.append(
                    {
                        "code": "HF_TRANSITION_PARAGRAPH_BAD",
                        "join_index": i,
                        "intent": intent or None,
                        "style": style,
                        "message": (
                            f"join {i}: chapter/段落转场 but intent={intent!r} "
                            f"style={style!r} — must be soft with fade/dissolve"
                        ),
                    }
                )
            continue
        # scene_cut / default
        if intent in {"hard", "soft", "hold"}:
            if style in _FLASHY_SCENE_STYLES:
                issues.append(
                    {
                        "code": "HF_TRANSITION_SCENE_FLASHY_STYLE",
                        "join_index": i,
                        "intent": intent,
                        "style": style,
                        "message": (
                            f"join {i}: scene cut transition intent={intent!r} "
                            f"style={style!r} — whip/grid too busy for narrative scene cut"
                        ),
                    }
                )
        elif style in _FLASHY_SCENE_STYLES:
            issues.append(
                {
                    "code": "HF_TRANSITION_SCENE_FLASHY_STYLE",
                    "join_index": i,
                    "intent": intent or None,
                    "style": style,
                    "message": (
                        f"join {i}: scene cut uses flashy transition style={style!r} "
                        f"(whip/grid too busy for narrative scene cut)"
                    ),
                }
            )

    return {
        "ok": len(issues) == 0,
        "checked": True,
        "codes": sorted({i["code"] for i in issues}),
        "issues": issues,
    }


def assert_transition_policy(
    root: Path | None = None,
    *,
    spec: dict[str, Any] | None = None,
    force: bool = False,
    env_skip: bool = True,
) -> dict[str, Any]:
    """P2 controlled transition-policy hard gate (HF 转场受控策略全量).

    HARD when film-spec ``transition_policy_strict`` is True, or adult ``heat_scale``
    is max/hot/extreme. Otherwise surfaces as a soft advisory (incremental rollout).

    Emergency escapes: ``force=True`` or ``AIFILM_SKIP_TRANSITION_POLICY_GATE=1``.
    """
    if force:
        return {"skipped": True, "reason": "force"}
    if _env_skip_armed(
        "AIFILM_SKIP_TRANSITION_POLICY_GATE",
        root,
        env_skip=env_skip,
        call_site="assert_transition_policy",
    ):
        return {"skipped": True, "reason": "env"}
    data = spec
    if data is None and root is not None:
        path = Path(root).expanduser().resolve() / "film-spec.json"
        data = read_json(path) or {}
    if not isinstance(data, dict) or not data:
        return {"ok": True, "checked": False, "reason": "no_spec"}

    strict = bool(data.get("transition_policy_strict") is True) or str(
        data.get("heat_scale") or ""
    ).lower() in {"max", "hot", "extreme"}
    report = transition_policy_report(data)
    if not report["codes"]:
        return {"ok": True, "checked": report.get("checked", False), "codes": []}
    if not strict:
        return {
            "ok": True,
            "checked": True,
            "soft": True,
            "codes": report["codes"],
            "issues": report["issues"],
        }
    message = "; ".join(f"[{i['code']}] {i['message']}" for i in report["issues"][:6])
    raise ProductionGateError(
        f"transition-policy gate (strict): {message} "
        "Fix: continue seams → hard match-cut; scene cuts → no whip/grid; "
        "chapter transitions → soft fade/dissolve. "
        "Emergency: --skip-transition-policy or AIFILM_SKIP_TRANSITION_POLICY_GATE=1"
    )


def transition_export_readback_report(spec: dict[str, Any]) -> dict[str, Any]:
    """Read back built transition_ops and verify full coverage + policy consistency.

    The controlled transition-policy gate (transition_policy_report) validates the
    *plan* (transition_intents/transition_styles). This read-back validates the
    *exported operations* (spec["transition_ops"]) actually materialise every
    declared seam and match the policy — catching seams dropped or styles silently
    drifted during export/build.

    Returns {"ok", "checked", "codes", "issues", "seam_count", "ops_count"}.
    Does not raise.
    """
    if not isinstance(spec, dict):
        return {
            "ok": True,
            "checked": False,
            "codes": [],
            "issues": [],
            "seam_count": 0,
            "ops_count": 0,
        }
    # Only meaningful if the spec declares transition seams.
    intents = spec.get("transition_intents")
    styles = spec.get("transition_styles")
    if not isinstance(intents, list) and not isinstance(styles, list):
        return {
            "ok": True,
            "checked": False,
            "codes": [],
            "issues": [],
            "seam_count": 0,
            "ops_count": 0,
        }
    n_seams = max(
        len(intents) if isinstance(intents, list) else 0,
        len(styles) if isinstance(styles, list) else 0,
    )
    if n_seams <= 0:
        return {
            "ok": True,
            "checked": False,
            "codes": [],
            "issues": [],
            "seam_count": 0,
            "ops_count": 0,
        }

    shots = _flatten_shots(spec)
    ops = spec.get("transition_ops")
    if not isinstance(ops, list):
        # Declared seams but no built/read-back operations → coverage gap.
        return {
            "ok": False,
            "checked": True,
            "codes": ["EXPORT_READBACK_NO_OPS"],
            "issues": [
                {
                    "code": "EXPORT_READBACK_NO_OPS",
                    "seam_count": n_seams,
                    "ops_count": 0,
                    "message": (
                        f"spec declares {n_seams} transition seam(s) but has no "
                        f"transition_ops — export/build must materialise every seam"
                    ),
                }
            ],
            "seam_count": n_seams,
            "ops_count": 0,
        }
    ops_count = len(ops)
    issues: list[dict[str, Any]] = []
    if ops_count != n_seams:
        issues.append(
            {
                "code": "EXPORT_READBACK_OP_COUNT_MISMATCH",
                "seam_count": n_seams,
                "ops_count": ops_count,
                "message": (
                    f"transition_ops count={ops_count} != declared seam count={n_seams} "
                    f"— a transition seam was dropped or duplicated during export"
                ),
            }
        )

    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            issues.append(
                {
                    "code": "EXPORT_READBACK_OP_INVALID",
                    "join_index": i,
                    "message": f"transition_ops[{i}] is not an object",
                }
            )
            continue
        intent = (
            str(intents[i]).strip().lower()
            if isinstance(intents, list) and i < len(intents)
            else None
        )
        style = styles[i] if isinstance(styles, list) and i < len(styles) else None
        style = str(style).strip().lower() if style else None
        picture = op.get("picture") if isinstance(op.get("picture"), dict) else {}
        base = str(picture.get("base") or "").strip().lower()
        op_style = str(picture.get("style") or "").strip().lower() or None
        try:
            dur = float(picture.get("duration_sec") or 0.0)
        except (TypeError, ValueError):
            dur = 0.0
        overlay = str(picture.get("hyperframes_overlay") or "").strip().lower()

        incoming = shots[i + 1] if i + 1 < len(shots) else {}
        chain = _shot_chain_mode(incoming)
        role = str(
            (incoming or {}).get("role") or (incoming or {}).get("kind") or ""
        ).strip().lower()
        df = str((incoming or {}).get("dramatic_function") or "").strip().lower()

        # intro/outro / pure-MG → relax (HF catalog open), but op base must still be valid
        if role in _RELAX_ROLES:
            if base not in {"hard_cut", "xfade"}:
                issues.append(
                    {
                        "code": "EXPORT_READBACK_OP_BASE_INVALID",
                        "join_index": i,
                        "base": base,
                        "message": (
                            f"join {i} (relaxed role): op base={base!r} must be "
                            f"hard_cut|xfade"
                        ),
                    }
                )
            continue

        if chain in _TRANSITION_POLICY_CONTINUE:
            # continue seam must stay hard_cut, zero-duration, no HyperFrames overlay
            if base != "hard_cut" or abs(dur) > 1e-6 or overlay != "none":
                issues.append(
                    {
                        "code": "EXPORT_READBACK_CONTINUE_NOT_HARD",
                        "join_index": i,
                        "base": base,
                        "duration_sec": dur,
                        "overlay": overlay,
                        "message": (
                            f"join {i}: chain_mode={chain!r} (continue seam) but built "
                            f"op base={base!r} duration_sec={dur} overlay={overlay!r} — "
                            f"must be hard_cut, 0.0s, no HyperFrames overlay"
                        ),
                    }
                )
            continue
        if df == "chapter_transition":
            if base != "xfade" or (
                op_style is not None and op_style not in _PARAGRAPH_STYLES
            ):
                issues.append(
                    {
                        "code": "EXPORT_READBACK_PARAGRAPH_BAD",
                        "join_index": i,
                        "base": base,
                        "style": op_style,
                        "message": (
                            f"join {i}: chapter/段落转场 but built op base={base!r} "
                            f"style={op_style!r} — must be soft xfade with fade/dissolve"
                        ),
                    }
                )
            continue
        # scene_cut / default
        if intent == "soft":
            if base != "xfade":
                issues.append(
                    {
                        "code": "EXPORT_READBACK_SOFT_NOT_XFADE",
                        "join_index": i,
                        "base": base,
                        "message": (
                            f"join {i}: intent=soft but built op base={base!r} "
                            f"(must be xfade)"
                        ),
                    }
                )
            elif style is not None and op_style != style:
                issues.append(
                    {
                        "code": "EXPORT_READBACK_STYLE_DRIFT",
                        "join_index": i,
                        "declared_style": style,
                        "op_style": op_style,
                        "message": (
                            f"join {i}: declared style={style!r} but built op "
                            f"style={op_style!r} — export drifted the transition style"
                        ),
                    }
                )
            if op_style in _FLASHY_SCENE_STYLES:
                issues.append(
                    {
                        "code": "EXPORT_READBACK_FLASHY_STYLE",
                        "join_index": i,
                        "style": op_style,
                        "message": (
                            f"join {i}: built op uses flashy style={op_style!r} "
                            f"(whip/grid too busy for narrative scene cut)"
                        ),
                    }
                )
        elif intent == "hard":
            if base != "hard_cut":
                issues.append(
                    {
                        "code": "EXPORT_READBACK_HARD_NOT_CUT",
                        "join_index": i,
                        "base": base,
                        "message": (
                            f"join {i}: intent=hard but built op base={base!r} "
                            f"(must be hard_cut)"
                        ),
                    }
                )
        else:
            # intent None/unknown → still block flashy styles on non-continue seams
            if op_style in _FLASHY_SCENE_STYLES:
                issues.append(
                    {
                        "code": "EXPORT_READBACK_FLASHY_STYLE",
                        "join_index": i,
                        "style": op_style,
                        "message": (
                            f"join {i}: built op uses flashy style={op_style!r} "
                            f"(whip/grid too busy for narrative scene cut)"
                        ),
                    }
                )

    return {
        "ok": len(issues) == 0,
        "checked": True,
        "codes": sorted({i["code"] for i in issues}),
        "issues": issues,
        "seam_count": n_seams,
        "ops_count": ops_count,
    }


def assert_transition_export_readback(
    root: Path | None = None,
    *,
    spec: dict[str, Any] | None = None,
    force: bool = False,
    env_skip: bool = True,
) -> dict[str, Any]:
    """P2 export read-back hard gate (HF 转场 export read-back 全量).

    Verifies the built transition_ops fully cover and match the declared
    transition_intents/transition_styles. HARD under transition_policy_strict or
    adult max heat; otherwise a soft advisory (incremental rollout).

    Emergency escapes: ``force=True`` or ``AIFILM_SKIP_TRANSITION_READBACK_GATE=1``.
    """
    if force:
        return {"skipped": True, "reason": "force"}
    if _env_skip_armed(
        "AIFILM_SKIP_TRANSITION_READBACK_GATE",
        root,
        env_skip=env_skip,
        call_site="assert_transition_export_readback",
    ):
        return {"skipped": True, "reason": "env"}
    data = spec
    if data is None and root is not None:
        path = Path(root).expanduser().resolve() / "film-spec.json"
        data = read_json(path) or {}
    if not isinstance(data, dict) or not data:
        return {"ok": True, "checked": False, "reason": "no_spec"}

    strict = bool(data.get("transition_policy_strict") is True) or str(
        data.get("heat_scale") or ""
    ).lower() in {"max", "hot", "extreme"}
    report = transition_export_readback_report(data)
    if not report["codes"]:
        return {
            "ok": True,
            "checked": report.get("checked", False),
            "codes": [],
            "seam_count": report.get("seam_count", 0),
            "ops_count": report.get("ops_count", 0),
        }
    if not strict:
        return {
            "ok": True,
            "checked": True,
            "soft": True,
            "codes": report["codes"],
            "issues": report["issues"],
            "seam_count": report.get("seam_count", 0),
            "ops_count": report.get("ops_count", 0),
        }
    message = "; ".join(f"[{i['code']}] {i['message']}" for i in report["issues"][:6])
    raise ProductionGateError(
        f"transition export read-back gate (strict): {message} "
        "Fix: build one operation per declared seam (continue→hard_cut/0.0s/no overlay; "
        "soft→xfade with declared style; chapter→soft fade/dissolve). "
        "Emergency: --skip-transition-readback or AIFILM_SKIP_TRANSITION_READBACK_GATE=1"
    )


def style_bible_consistency_report(
    spec: dict[str, Any], root: Path | None = None
) -> dict[str, Any]:
    """Validate visual style-bible consistency with the spec (P2 visual_bible 自动生成).

    The style-bible is the canonical visual source of truth (palette / lighting /
    cast masters). When the spec declares visual content (shots / cast), this reads
    back the on-disk ``style-bible.json`` and verifies it is consistent:

      - ``STYLE_BIBLE_MISSING``      spec has visual content but no style-bible.json
                                     (run ``derive_style_bible_from_spec`` to auto-gen)
      - ``STYLE_BIBLE_HERO_CAST_MISSING``  spec has hero shots but bible lacks
                                     ``cast_masters.hero``
      - ``STYLE_BIBLE_LIGHTING_MISMATCH``  bible lighting_timeline count != shot count

    Returns {"ok", "checked", "codes", "issues"}. Does not raise.
    """
    if not isinstance(spec, dict):
        return {"ok": True, "checked": False, "codes": [], "issues": []}
    from assets.visual_bible import derive_lighting_timeline, load_bible  # lazy

    shots = _flatten_shots(spec)
    has_visual = bool(shots) or bool(spec.get("cast_masters"))
    if not has_visual:
        return {"ok": True, "checked": False, "codes": [], "issues": []}

    if root is None:
        # Can't read the on-disk bible without a root; spec-only readiness only.
        return {"ok": True, "checked": False, "codes": [], "issues": []}

    issues: list[dict[str, Any]] = []
    bible_path = Path(root) / "style-bible.json"
    if not bible_path.is_file():
        issues.append(
            {
                "code": "STYLE_BIBLE_MISSING",
                "message": (
                    "spec declares visual content but no style-bible.json — "
                    "run derive_style_bible_from_spec to auto-generate it"
                ),
            }
        )
        return {
            "ok": False,
            "checked": True,
            "codes": ["STYLE_BIBLE_MISSING"],
            "issues": issues,
        }

    bible = load_bible(Path(root))
    hero_shots = [
        s for s in shots if str(s.get("shot_role") or "").strip().lower() == "hero"
    ]
    cm = bible.get("cast_masters") if isinstance(bible.get("cast_masters"), dict) else {}
    if hero_shots and "hero" not in cm:
        issues.append(
            {
                "code": "STYLE_BIBLE_HERO_CAST_MISSING",
                "message": (
                    "spec has hero shots but style-bible.cast_masters.hero is missing — "
                    "auto-derive or register the hero cast master"
                ),
            }
        )
    if shots:
        tl = bible.get("lighting_timeline")
        derived = derive_lighting_timeline(shots)
        if not isinstance(tl, list) or len(tl) != len(shots):
            issues.append(
                {
                    "code": "STYLE_BIBLE_LIGHTING_MISMATCH",
                    "message": (
                        f"style-bible lighting_timeline count "
                        f"({len(tl) if isinstance(tl, list) else 0}) != shot count "
                        f"({len(shots)}) — auto-derive to refresh"
                    ),
                }
            )
            _ = derived  # keep lazy import referenced for clarity

    return {
        "ok": len(issues) == 0,
        "checked": True,
        "codes": sorted({i["code"] for i in issues}),
        "issues": issues,
    }


def assert_style_bible_consistency(
    root: Path | None = None,
    *,
    spec: dict[str, Any] | None = None,
    force: bool = False,
    env_skip: bool = True,
) -> dict[str, Any]:
    """P2 visual_bible consistency hard gate (visual_bible 自动生成).

    HARD under ``style_bible_strict`` or adult ``heat_scale`` max/hot/extreme; otherwise
    a soft advisory (incremental rollout). Emergency escapes: ``force=True`` or
    ``AIFILM_SKIP_STYLE_BIBLE_GATE=1``.
    """
    if force:
        return {"skipped": True, "reason": "force"}
    if _env_skip_armed(
        "AIFILM_SKIP_STYLE_BIBLE_GATE",
        root,
        env_skip=env_skip,
        call_site="assert_style_bible_consistency",
    ):
        return {"skipped": True, "reason": "env"}
    data = spec
    if data is None and root is not None:
        path = Path(root).expanduser().resolve() / "film-spec.json"
        data = read_json(path) or {}
    if not isinstance(data, dict) or not data:
        return {"ok": True, "checked": False, "reason": "no_spec"}

    report = style_bible_consistency_report(data, root=root)
    if not report["codes"]:
        return {
            "ok": True,
            "checked": report.get("checked", False),
            "codes": [],
        }
    strict = bool(data.get("style_bible_strict") is True) or str(
        data.get("heat_scale") or ""
    ).lower() in {"max", "hot", "extreme"}
    if not strict:
        return {
            "ok": True,
            "checked": True,
            "soft": True,
            "codes": report["codes"],
            "issues": report["issues"],
        }
    message = "; ".join(f"[{i['code']}] {i['message']}" for i in report["issues"][:6])
    raise ProductionGateError(
        f"style-bible consistency gate (strict): {message} "
        "Fix: run derive_style_bible_from_spec to auto-generate / refresh style-bible.json. "
        "Emergency: --skip-style-bible or AIFILM_SKIP_STYLE_BIBLE_GATE=1"
    )


# --- Face-identity post_audit gate (P0 · face-identity-pixel) ---
# A post_audit that ran and found keyframe pixel drift means an approved clip would
# carry a face-identity break; register-clip / final must reject until re-audited.
_FACE_IDENTITY_RECEIPT = "face-identity.json"


def _face_identity_report(root: Path) -> dict[str, Any]:
    """Return {ok, checked, codes, issues, ...} for face-identity post_audit status."""
    root = Path(root).expanduser().resolve()
    bible_path = root / "style-bible.json"
    cast_masters: dict[str, Any] = {}
    if bible_path.is_file():
        try:
            bible = json.loads(bible_path.read_text(encoding="utf-8"))
            cm = bible.get("cast_masters")
            if isinstance(cm, dict):
                cast_masters = cm
        except Exception as exc:  # noqa: BLE001 — fail-closed: corrupt bible ≠ skip gate
            return {
                "ok": False,
                "checked": True,
                "codes": ["STYLE_BIBLE_PARSE_FAILED"],
                "issues": [
                    {
                        "code": "STYLE_BIBLE_PARSE_FAILED",
                        "message": (
                            f"style-bible.json present but unreadable ({exc!s:.120}); "
                            "fix JSON before face-identity / promote"
                        ),
                    }
                ],
            }
    if not cast_masters:
        return {"ok": True, "checked": False, "codes": [], "issues": []}

    receipt_path = root / "receipts" / _FACE_IDENTITY_RECEIPT
    if not receipt_path.is_file():
        return {
            "ok": True,
            "checked": True,
            "codes": ["FACE_IDENTITY_NOT_AUDITED"],
            "issues": [
                {
                    "code": "FACE_IDENTITY_NOT_AUDITED",
                    "message": (
                        "cast_masters present but no receipts/face-identity.json — "
                        "run: aifilm face-identity enroll-bible && aifilm face-identity audit"
                    ),
                }
            ],
            "absent": True,
        }

    try:
        from face_identity import load_receipt
    except ImportError:  # pragma: no cover - flat layout fallback
        from assets.face_identity import load_receipt  # type: ignore

    receipt = load_receipt(root)
    enrolled = receipt.get("enrolled") if isinstance(receipt.get("enrolled"), dict) else {}
    audit = receipt.get("audit") if isinstance(receipt.get("audit"), dict) else {}
    verified = bool(receipt.get("verified"))
    n_fail = int(audit.get("n_fail") or 0)
    issues: list[dict[str, Any]] = []
    if verified is False and n_fail > 0:
        issues.append(
            {
                "code": "FACE_IDENTITY_DRIFT",
                "message": (
                    f"face-identity post_audit failed on {n_fail} keyframe(s) — "
                    "reject clip register/final until re-audited"
                ),
            }
        )
    missing = [c for c in cast_masters if c not in enrolled and c != "hero"]
    if missing:
        issues.append(
            {
                "code": "FACE_IDENTITY_ENROLL_GAP",
                "message": f"cast_masters not enrolled: {', '.join(missing)}",
            }
        )
    return {
        "ok": len(issues) == 0,
        "checked": True,
        "codes": sorted({i["code"] for i in issues}),
        "issues": issues,
        "verified": verified,
        "n_fail": n_fail,
    }


def assert_face_identity_passed(
    root: Path,
    *,
    force: bool = False,
    env_skip: bool = True,
    proven_drift_only: bool = False,
) -> dict[str, Any]:
    """P0 face-identity post_audit gate (lessons face-identity-pixel).

    Fail-closed on proven drift: a post_audit that ran and found n_fail>0 means the
    approved clip would carry a face break, so it must be rejected. Enroll/audit gaps
    are hard only when the film opts into ``face_identity_strict`` (or adult max heat);
    otherwise they surface as soft advisory — matching the project's incremental rollout.

    ``proven_drift_only=True`` (used by register-clip) blocks exclusively on a failed
    post_audit, so normal approval flows are never surprised by a soft advisory.

    Emergency escapes: ``force=True`` or ``AIFILM_SKIP_FACE_IDENTITY_GATE=1``.
    """
    if force:
        return {"skipped": True, "reason": "force"}
    if _env_skip_armed(
        "AIFILM_SKIP_FACE_IDENTITY_GATE",
        root,
        env_skip=env_skip,
        call_site="assert_face_identity_passed",
    ):
        return {"skipped": True, "reason": "env"}
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json") or {}
    report = _face_identity_report(root)
    if not report.get("codes"):
        return {"ok": True, "checked": report.get("checked", False), "codes": []}
    strict = bool(spec.get("face_identity_strict") is True) or (
        str(spec.get("heat_scale") or "").lower() in {"max", "hot", "extreme"}
    )
    proven_drift = "FACE_IDENTITY_DRIFT" in report["codes"]
    # Infrastructure failures (corrupt bible) are always hard — never soft-skip.
    infra_fail = "STYLE_BIBLE_PARSE_FAILED" in (report.get("codes") or [])
    if proven_drift_only:
        if not proven_drift and not infra_fail:
            return {
                "ok": True,
                "checked": True,
                "soft": True,
                "codes": report["codes"],
                "issues": report["issues"],
            }
        if proven_drift:
            message = "; ".join(
                f"[{i['code']}] {i['message']}"
                for i in report["issues"]
                if i["code"] == "FACE_IDENTITY_DRIFT"
            )
            raise ProductionGateError(
                f"face-identity gate (proven drift): {message} "
                "Re-run aifilm face-identity enroll-bible && aifilm face-identity audit --root … "
                "(re-shoot/re-edit drifting stills before approving). "
                "Emergency: --skip-face-identity or AIFILM_SKIP_FACE_IDENTITY_GATE=1"
            )
        # infra_fail falls through to hard raise below
    if not (proven_drift or strict or infra_fail):
        return {
            "ok": True,
            "checked": True,
            "soft": True,
            "codes": report["codes"],
            "issues": report["issues"],
        }
    message = "; ".join(f"[{i['code']}] {i['message']}" for i in report["issues"][:6])
    raise ProductionGateError(
        f"face-identity gate: {message} "
        "Re-run aifilm face-identity enroll-bible && aifilm face-identity audit --root … "
        "(re-shoot/re-edit drifting stills before approving). "
        "Emergency: --skip-face-identity or AIFILM_SKIP_FACE_IDENTITY_GATE=1"
    )


# --- Continuity-chain gate (P0 · nine-item 接戏程序化校验) ---
# Long-form films must keep a continuity_chain.md, byte-reuse the approved last frame
# for continue joins, pass the nine-item checklist, and must NOT mask a break with a
# long dissolve / freeze / reverse / unrelated insert. Fail-closed on hard issues;
# soft advisory otherwise. See references/continuity_chain.md.
def assert_continuity_chain_passed(
    root: Path,
    *,
    force: bool = False,
    env_skip: bool = True,
) -> dict[str, Any]:
    """P0 continuity-chain gate (lessons continuity_chain / P0-3).

    Hard-fails on: long-form missing continuity_chain.md, continue-join byte mismatch,
    nine-item checklist FAIL (under strict), or dissolve coverup on a byte-identical
    match-cut join (under strict). Soft advisory for incomplete checklists / warnings.

    Emergency escapes: ``force=True`` or ``AIFILM_SKIP_CONTINUITY_GATE=1``.
    """
    if force:
        return {"skipped": True, "reason": "force"}
    if _env_skip_armed(
        "AIFILM_SKIP_CONTINUITY_GATE",
        root,
        env_skip=env_skip,
        call_site="assert_continuity_chain_passed",
    ):
        return {"skipped": True, "reason": "env"}
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json") or {}
    try:
        from continuity_chain import check_continuity_chain
    except ImportError:  # pragma: no cover - flat layout fallback
        from assets.continuity_chain import check_continuity_chain  # type: ignore
    strict = bool(spec.get("continuity_chain_strict") is True)
    report = check_continuity_chain(root, spec, strict=strict, require_doc_if_long=True)
    if report.get("ok"):
        return {
            "ok": True,
            "checked": True,
            "strict": strict,
            "codes": report.get("codes", []),
        }
    hard = [i for i in (report.get("hard") or []) if i.get("severity") == "error"]
    if hard:
        message = "; ".join(f"[{i['code']}] {i['message']}" for i in hard[:6])
        raise ProductionGateError(
            f"continuity-chain gate: {message} "
            "Fix: aifilm continuity-chain init + nine-item pass; extract-frame --promote-keyframe "
            "for continue joins; hard match-cut (no long dissolve). "
            "Emergency: --skip-continuity or AIFILM_SKIP_CONTINUITY_GATE=1"
        )
    return {
        "ok": True,
        "checked": True,
        "soft": True,
        "codes": report.get("codes", []),
        "issues": report.get("soft"),
    }
