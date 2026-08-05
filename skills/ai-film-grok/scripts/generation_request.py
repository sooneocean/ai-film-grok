#!/usr/bin/env python3
"""GenerationRequest — single material pack for model consumption.

Facade only: composes StillSource + motion_prompt_spine / PromptInjector +
h3_media_pack. Does not re-implement wardrobe ranks or H3 mode tables.

Receipt: receipts/prompts/<shot_id>.request.json
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from util import read_json, sha256_file, utc_now, write_json

KIND_STILL = "still"
KIND_I2V = "i2v"
KIND_FLF = "flf"
KIND_R2V = "r2v"
KIND_T2V = "t2v"
VALID_KINDS = frozenset({KIND_STILL, KIND_I2V, KIND_FLF, KIND_R2V, KIND_T2V})


class GenerationRequestError(ValueError):
    """Generation request could not be built or validated."""


def _root(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def generation_request_skip_strict() -> bool:
    return os.environ.get("AIFILM_SKIP_GENERATION_REQUEST", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _find_shot(root: Path, shot_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    spec = read_json(root / "film-spec.json") or {}
    if not isinstance(spec, dict):
        raise GenerationRequestError("film-spec.json missing or invalid")
    try:
        from continue_handoff import find_shot

        shot = find_shot(spec, shot_id)
    except Exception:
        shot = None
    if not isinstance(shot, dict):
        raise GenerationRequestError(f"shot not found: {shot_id}")
    return spec, shot


def _asset_hints(root: Path, shot: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """Location/prop fixed lines from assets-registry (M3 · single helper)."""
    try:
        from asset_registry import build_asset_prompt_hints

        rep = build_asset_prompt_hints(root, shot)
        return list(rep.get("lines") or []), rep
    except Exception as exc:
        return [], {"ok": False, "error": str(exc)[:120]}


def _assemble_text(
    root: Path,
    spec: dict[str, Any],
    shot: dict[str, Any],
    *,
    kind: str,
) -> tuple[str, str, dict[str, Any]]:
    """Return (prompt, negative, meta)."""
    meta: dict[str, Any] = {"assembler": None}
    negative = ""
    if kind == KIND_STILL:
        bible = read_json(root / "style-bible.json") or {}
        if not isinstance(bible, dict):
            bible = {}
        try:
            from prompt_injector import PromptInjector

            inj = PromptInjector(bible)
            assembled = inj.assemble(shot, root)
            prompt = str(
                assembled.get("prompt_text")
                or assembled.get("prompt")
                or assembled.get("text")
                or ""
            )
            # negatives already embedded as --no in prompt_text when present
            negative = str(assembled.get("negative") or assembled.get("negatives") or "")
            meta["assembler"] = "PromptInjector"
            meta["state_photo_paths"] = assembled.get("state_photo_paths")
        except Exception as exc:
            prompt = str(shot.get("nar") or shot.get("action") or "")
            meta["assembler"] = f"fallback:{type(exc).__name__}"
    else:
        try:
            from motion_prompt_spine import build_motion_prompt

            mode = kind if kind in {"i2v", "flf", "r2v", "t2v"} else "i2v"
            prompt = build_motion_prompt(spec, shot, mode=mode, include_provider_prefix=True)
            meta["assembler"] = "motion_prompt_spine"
        except Exception as exc:
            prompt = str(
                shot.get("dsl", {}).get("motion") if isinstance(shot.get("dsl"), dict) else ""
            ) or str(shot.get("nar") or "")
            meta["assembler"] = f"fallback:{type(exc).__name__}"
    hints, hint_meta = _asset_hints(root, shot)
    if hints:
        prompt = (prompt + "\n" + "\n".join(hints)).strip()
        meta["asset_hints"] = hints
    meta["asset_hint_meta"] = {
        k: hint_meta.get(k)
        for k in ("registry_present", "codes", "missing", "location_id", "hint")
        if k in hint_meta
    }
    return prompt, negative, meta


def build_generation_request(
    root: Path | str,
    shot_id: str,
    *,
    kind: str = KIND_I2V,
    still_override: Path | str | None = None,
    last_override: Path | str | None = None,
    refs_override: list[Path | str] | None = None,
    write: bool = False,
) -> dict[str, Any]:
    """Build machine-readable GenerationRequest for one shot."""
    base = _root(root)
    k = str(kind or KIND_I2V).strip().lower()
    if k not in VALID_KINDS:
        raise GenerationRequestError(
            f"unknown kind {kind!r}; expected one of {sorted(VALID_KINDS)}"
        )

    spec, shot = _find_shot(base, shot_id)

    from still_source import resolve_still_source

    cont_end = None
    wants_cont = False
    try:
        from continue_handoff import resolve_continue_handoff, shot_wants_continue

        wants_cont = shot_wants_continue(shot)
        cont = resolve_continue_handoff(base, shot_id, shot=shot, spec=spec)
        if cont.get("ok") and cont.get("end_frame"):
            cont_end = cont.get("end_frame")
    except Exception:
        cont = None

    still_entry = resolve_still_source(
        base,
        shot_id,
        shot=shot,
        still_override=still_override,
        continue_end_frame=cont_end,
        wants_continue=wants_cont,
        kind=k if k == KIND_STILL else KIND_I2V,
    )

    media_pack: dict[str, Any] = {}
    if k != KIND_STILL:
        try:
            from h3_media_pack import resolve_media_pack

            approved = Path(still_entry["path"]) if still_entry.get("path") else None
            media_pack = resolve_media_pack(
                base,
                shot_id,
                shot=shot,
                still_override=still_override,
                last_override=last_override,
                approved_still=approved,
                continue_end_frame=cont_end,
                wants_continue=wants_cont,
                refs_override=refs_override,
            )
        except Exception as exc:
            media_pack = {"error": str(exc)[:200]}

    prompt, negative, text_meta = _assemble_text(base, spec, shot, kind=k)

    # M4 · prior take evidence (budget 3 lines)
    prior_lines: list[str] = []
    try:
        from shot_evidence import prior_evidence_lines

        prior_lines = prior_evidence_lines(base, shot_id, max_lines=3)
        if prior_lines:
            prompt = ("\n".join(prior_lines) + "\n" + prompt).strip()
            text_meta["prior_evidence"] = prior_lines
    except Exception:
        prior_lines = []

    image_refs: list[dict[str, Any]] = []
    if still_entry.get("path") and still_entry.get("ok"):
        image_refs.append(
            {
                "role": still_entry.get("role") or "first",
                "path": still_entry["path"],
                "sha256": still_entry.get("sha256"),
                "source": still_entry.get("source"),
            }
        )
    last = media_pack.get("last") if isinstance(media_pack.get("last"), dict) else None
    if last and last.get("path"):
        image_refs.append(
            {
                "role": "last",
                "path": last["path"],
                "sha256": last.get("sha256"),
                "source": last.get("source"),
            }
        )
    for ref in media_pack.get("refs") or []:
        if isinstance(ref, dict) and ref.get("path"):
            image_refs.append(
                {
                    "role": ref.get("role") or "identity",
                    "path": ref["path"],
                    "sha256": ref.get("sha256"),
                    "source": ref.get("source"),
                }
            )

    constraints: list[str] = []
    if still_entry.get("blocked"):
        constraints.append(str(still_entry.get("block_reason") or "STILL_BLOCKED"))
    if k in {KIND_I2V, KIND_FLF, KIND_R2V} and not still_entry.get("ok"):
        constraints.append("REQUIRES_STILL")

    req: dict[str, Any] = {
        "schema_version": 1,
        "kind": "generation-request",
        "shot_id": shot_id,
        "generation_kind": k,
        "created_at": utc_now(),
        "text_prompt": prompt,
        "negative": negative,
        "text_sha256": _text_hash(prompt + "\n" + negative),
        "image_refs": image_refs,
        "still_source": still_entry,
        "media_pack": {
            "has_first": media_pack.get("has_first"),
            "has_last": media_pack.get("has_last"),
            "has_refs": media_pack.get("has_refs"),
            "missing_last_hint": media_pack.get("missing_last_hint"),
            "reasons": media_pack.get("reasons"),
        },
        "continue_handoff": cont,
        "text_meta": text_meta,
        "prior_evidence": prior_lines,
        "constraints": constraints,
        "ok": not constraints and bool(prompt.strip() or k == KIND_T2V),
    }
    if k == KIND_T2V:
        req["ok"] = bool(prompt.strip()) and not still_entry.get("blocked")
    if k in {KIND_I2V, KIND_FLF, KIND_R2V}:
        req["ok"] = (
            bool(prompt.strip())
            and bool(still_entry.get("ok"))
            and not still_entry.get("blocked")
            and not constraints
        )

    if write:
        write_generation_request(base, req)
    return req


def request_receipt_path(root: Path | str, shot_id: str) -> Path:
    return _root(root) / "receipts" / "prompts" / f"{shot_id}.request.json"


def write_generation_request(root: Path | str, req: dict[str, Any]) -> Path:
    sid = str(req.get("shot_id") or "").strip()
    if not sid:
        raise GenerationRequestError("shot_id required to write receipt")
    path = request_receipt_path(root, sid)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, req)
    return path


def load_generation_request(root: Path | str, shot_id: str) -> dict[str, Any] | None:
    path = request_receipt_path(root, shot_id)
    data = read_json(path)
    return data if isinstance(data, dict) else None


def validate_pixel_pack_hashes(
    root: Path | str,
    *,
    shot_id: str | None = None,
    req: dict[str, Any] | None = None,
    inputs: list[Path] | None = None,
) -> dict[str, Any]:
    """Verify image_refs files exist and match recorded sha256.

    When ``inputs`` given (media-queue), first input must match first image_ref sha.
    """
    if generation_request_skip_strict():
        return {"ok": True, "skipped": True, "reason": "AIFILM_SKIP_GENERATION_REQUEST"}
    base = _root(root)
    data = req
    if data is None and shot_id:
        data = load_generation_request(base, shot_id)
    if not isinstance(data, dict):
        return {
            "ok": True,
            "skipped": True,
            "reason": "no_request_receipt",
        }
    errors: list[str] = []
    refs = data.get("image_refs") if isinstance(data.get("image_refs"), list) else []
    for i, ref in enumerate(refs):
        if not isinstance(ref, dict):
            continue
        path_s = ref.get("path")
        expect = str(ref.get("sha256") or "").strip()
        if not path_s:
            continue
        p = Path(str(path_s))
        if not p.is_file():
            errors.append(f"ref[{i}] missing file: {path_s}")
            continue
        if expect:
            actual = sha256_file(p)
            if actual != expect:
                errors.append(f"ref[{i}] sha mismatch path={path_s}")
    if inputs:
        resolved = [Path(p).expanduser().resolve() for p in inputs]
        first_refs = [
            r for r in refs if isinstance(r, dict) and r.get("role") in {"first", "state_photo"}
        ]
        if first_refs and resolved:
            expect = str(first_refs[0].get("sha256") or "").strip()
            if expect and sha256_file(resolved[0]) != expect:
                errors.append("queue first input does not match generation-request first ref sha")
    return {
        "ok": not errors,
        "errors": errors,
        "shot_id": data.get("shot_id") or shot_id,
        "ref_count": len(refs),
    }


def assert_pixel_pack_current(
    root: Path | str,
    shot_id: str,
    *,
    inputs: list[Path] | None = None,
) -> None:
    report = validate_pixel_pack_hashes(root, shot_id=shot_id, inputs=inputs)
    if report.get("skipped"):
        return
    if not report.get("ok"):
        raise GenerationRequestError(
            "generation request pixel pack invalid: " + "; ".join(report.get("errors") or [])
        )
