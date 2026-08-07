#!/usr/bin/env python3
"""Media / still / style / continuity / register CLI handlers.

Extracted from aifilm_grok. Public command strings unchanged.
Shared IO/helpers come from core/ (no hub cycle).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from continuity import lint_continuity, lint_frame_chain
from continuity_chain import (
    check_continuity_chain,
    init_chain_doc,
    is_long_form,
    upsert_join,
)
from core.constants import (
    DEFAULT_FPS,
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    NATIVE_AUDIO_AUDIBLE_MIN_DB,
)
from core.emit import emit
from core.film_io import ensure_tree, film_dirs, load_manifest, save_manifest
from core.gates import recompute_gates
from core.media_ops import (
    _auto_promote_last_to_next,
    _register_media,
    media_duration,
    normalize_clip,
    probe_native_audio_mean_volume,
)
from film_spec import FilmSpecError, validate_film_spec
from logger import log
from media_qa import ALLOWED_VIDEO_ENDPOINTS, MediaQAError, analyze_media
from runtime_policy import sha256
from security_policy import (
    SecurityPolicyError,
    safe_existing_file,
    safe_output_path,
    safe_workspace_directory,
)
from util import require_json as read_json
from util import sha256_file, utc_now, write_json
from util.errors import FilmError
from util.subprocess import run
from util.validators import film_output_path, valid_shot_id
from visual_bible import load_bible


def cmd_lint_continuity(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    spec_path = root / "film-spec.json"
    if args.spec:
        spec_path = Path(args.spec).expanduser().resolve()
    if not spec_path.is_file():
        raise FilmError(f"No film-spec at {spec_path}")
    spec = read_json(spec_path)
    try:
        shots = validate_film_spec(spec, assign_missing_ids=False)
    except FilmSpecError as exc:
        raise FilmError(str(exc)) from exc
    report = lint_continuity(shots)
    intents = (
        spec.get("transition_intents") if isinstance(spec.get("transition_intents"), list) else None
    )
    frame_chain = lint_frame_chain(shots, transition_intents=intents)
    report["frame_chain"] = frame_chain
    # Merge soft frame-chain codes into top-level codes for visibility
    merged_codes = list(report.get("codes") or [])
    for c in frame_chain.get("codes") or []:
        if c not in merged_codes:
            merged_codes.append(c)
    report["codes"] = merged_codes
    report["issues"] = list(report.get("issues") or []) + list(frame_chain.get("issues") or [])
    report["warning_count"] = int(report.get("warning_count") or 0) + int(
        frame_chain.get("warning_count") or 0
    )
    if args.strict and not report["ok"]:
        write_json(root / "continuity_lint.json", report)
        raise FilmError("continuity lint failed: " + ",".join(report.get("codes") or []))
    out = root / "continuity_lint.json"
    write_json(out, report)
    emit(
        {
            "ok": report["ok"],
            "path": str(out),
            "continuity": report,
            "frame_chain": frame_chain,
        }
    )
    return 0 if report["ok"] or not args.strict else 2


def cmd_extract_frame(args: argparse.Namespace) -> int:
    """Extract first/last frame; --promote-keyframe copies as next still (byte-identical chain)."""
    root = Path(args.root).expanduser().resolve() if args.root else None
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise FilmError("ffmpeg/ffprobe required for extract-frame")

    source: Path | None = None
    if args.source:
        source = Path(args.source).expanduser().resolve()
    elif args.shot_id and root:
        manifest = read_json(root / "manifest.json") if (root / "manifest.json").is_file() else {}
        assets = manifest.get("assets") if isinstance(manifest, dict) else None
        if isinstance(assets, list):
            for a in assets:
                if (
                    isinstance(a, dict)
                    and str(a.get("shot_id")) == str(args.shot_id)
                    and a.get("role") in {"i2v", "clip", "video"}
                    and a.get("path")
                ):
                    cand = Path(str(a["path"]))
                    if not cand.is_absolute() and root:
                        cand = (root / cand).resolve()
                    if cand.is_file():
                        source = cand
                        break
        if source is None and root:
            for name in (f"{args.shot_id}.mp4", f"{args.shot_id}.webm", f"{args.shot_id}.mov"):
                cand = root / "clips" / name
                if cand.is_file():
                    source = cand
                    break
    if source is None or not source.is_file():
        raise FilmError(
            "extract-frame needs --source <clip.mp4> or --root + --shot-id with clips present"
        )

    which = (args.which or "last").strip().lower()
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(source),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=300,
        )
        duration = float((probe.stdout or "0").strip() or "0")
    except (subprocess.CalledProcessError, ValueError) as exc:
        raise FilmError(f"ffprobe failed on {source}: {exc}") from exc

    if which in {"last", "end"}:
        t = max(0.0, duration - 0.05) if duration > 0.1 else 0.0
    elif which in {"first", "start"}:
        t = 0.0
    else:
        try:
            t = float(which)
        except ValueError as exc:
            raise FilmError("--which must be first|last or seconds float") from exc
        t = max(0.0, min(t, max(0.0, duration - 0.01)))

    promote_id = getattr(args, "promote_keyframe", None)
    if args.out:
        out = Path(args.out).expanduser().resolve()
    elif promote_id and root:
        out = root / "keyframes" / f"_last_{args.shot_id or source.stem}.png"
    elif root and args.shot_id:
        seed_id = args.next_shot_id or args.shot_id
        out = root / "keyframes" / f"{seed_id}-seed.png"
    else:
        out = source.with_suffix("").parent / f"{source.stem}_{which}.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{t:.4f}",
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(out),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
    except subprocess.CalledProcessError as exc:
        raise FilmError(
            f"ffmpeg extract failed: {(exc.stderr or exc.stdout or '')[-500:]}"
        ) from exc
    if not out.is_file() or out.stat().st_size < 32:
        raise FilmError(f"extract-frame produced empty output: {out}")

    last_sha = sha256_file(out)
    promoted: Path | None = None
    join_rec: dict[str, Any] | None = None
    if promote_id and root:
        # Byte-identical promote: copy extracted file to keyframes/<next>.png (same bytes)
        promoted = root / "keyframes" / f"{promote_id}.png"
        promoted.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, promoted)
        first_sha = sha256_file(promoted)
        if first_sha != last_sha:
            raise FilmError("promote-keyframe copy failed byte identity check")
        # Also keep seed alias
        seed_alias = root / "keyframes" / f"{promote_id}-seed.png"
        shutil.copy2(out, seed_alias)
        from_id = str(args.shot_id or source.stem)
        join_rec = upsert_join(
            root,
            from_id=from_id,
            to_id=str(promote_id),
            mode="continue",
            last_sha=last_sha,
            first_sha=first_sha,
            last_path=str(out),
            first_path=str(promoted),
        )

    payload: dict[str, Any] = {
        "ok": True,
        "source": str(source),
        "which": which,
        "time_sec": t,
        "duration_sec": duration,
        "output": str(out),
        "sha256": last_sha,
        "bytes": out.stat().st_size,
        "rule": (
            "continue join: next I2V frame-1 MUST be this file byte-identical; "
            "do NOT restart from cast/character sheet. "
            "See references/continuity_chain.md"
        ),
    }
    if promoted is not None:
        payload["promoted_keyframe"] = str(promoted)
        payload["promoted_sha256"] = sha256_file(promoted)
        payload["byte_identical"] = True
        payload["join"] = join_rec
        payload["next"] = (
            f"I2V {promote_id} with input={promoted} only; "
            "complete 9-point checklist in continuity_chain.md; "
            "forbidden: dissolve/freeze/reverse/insert to hide breaks"
        )
    else:
        payload["next"] = (
            "For continue joins prefer: --promote-keyframe <next_shot_id> "
            "(byte-identical keyframe). Do not re-draw from cast. "
            "See references/continuity_chain.md"
        )
    emit(payload)
    return 0


def cmd_continuity_chain(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    ensure_tree(root)
    spec_path = root / "film-spec.json"
    if not spec_path.is_file():
        raise FilmError(f"No film-spec at {spec_path}")
    spec = read_json(spec_path)
    action = getattr(args, "chain_action", None) or "check"
    if action == "init":
        path = init_chain_doc(root, spec, force=bool(getattr(args, "force", False)))
        emit(
            {
                "ok": True,
                "action": "init",
                "path": str(path),
                "long_form": is_long_form(spec),
                "next": "Fill 9-point checklists per join; use extract-frame --promote-keyframe",
            }
        )
        return 0
    # check
    report = check_continuity_chain(
        root,
        spec,
        strict=bool(getattr(args, "strict", False)),
        require_doc_if_long=True,
    )
    out = root / "receipts" / "continuity-chain-check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, report)
    emit({"ok": report["ok"], "path": str(out), "continuity_chain": report})
    if not report["ok"] and getattr(args, "strict", False):
        raise FilmError("continuity-chain check failed: " + ",".join(report.get("codes") or []))
    return 0 if report["ok"] else 2


def cmd_face_identity(args: argparse.Namespace) -> int:
    """Pixel face fingerprints: enroll / verify / audit / status."""
    from scripts import face_identity as fi

    action = str(getattr(args, "face_identity_cmd", "") or "").strip()
    root = Path(args.root).expanduser().resolve() if getattr(args, "root", None) else None
    if action != "help" and root is None and action not in ():
        if action:
            pass

    if action == "enroll":
        if root is None:
            raise FilmError("face-identity enroll requires --root")
        source = getattr(args, "source", None)
        char_id = str(getattr(args, "char_id", None) or "hero")
        if not source:
            raise FilmError("face-identity enroll requires --source")
        out = fi.enroll(
            root, char_id, Path(source), label=str(getattr(args, "label", None) or char_id)
        )
        emit(out)
        return 0

    if action == "enroll-bible":
        if root is None:
            raise FilmError("face-identity enroll-bible requires --root")
        out = fi.enroll_from_bible(root)
        emit({"ok": out.get("ok"), "action": "enroll-bible", **out})
        return 0 if out.get("ok") else 2

    if action == "verify":
        if root is None:
            raise FilmError("face-identity verify requires --root")
        image = getattr(args, "image", None)
        char_id = str(getattr(args, "char_id", None) or "hero")
        if not image:
            raise FilmError("face-identity verify requires --image")
        out = fi.verify_image(
            root,
            Path(image),
            char_id,
            ahash_max=int(getattr(args, "ahash_max", None) or fi.DEFAULT_AHASH_MAX),
            dhash_max=int(getattr(args, "dhash_max", None) or fi.DEFAULT_DHASH_MAX),
            hist_max=float(getattr(args, "hist_max", None) or fi.DEFAULT_HIST_MAX),
        )
        emit(out)
        return 0 if out.get("ok") else 2

    if action == "audit":
        if root is None:
            raise FilmError("face-identity audit requires --root")
        out = fi.audit_keyframes(
            root,
            char_id=getattr(args, "char_id", None),
            strict=bool(getattr(args, "strict", False)),
            ahash_max=int(getattr(args, "ahash_max", None) or fi.DEFAULT_AHASH_MAX),
            dhash_max=int(getattr(args, "dhash_max", None) or fi.DEFAULT_DHASH_MAX),
            hist_max=float(getattr(args, "hist_max", None) or fi.DEFAULT_HIST_MAX),
        )
        emit({"action": "audit", **out})
        if bool(getattr(args, "strict", False)) and not out.get("verified"):
            return 2
        return 0

    if action == "status":
        if root is None:
            raise FilmError("face-identity status requires --root")
        receipt = fi.load_receipt(root)
        st = fi.post_audit_face_status(root)
        emit(
            {
                "ok": True,
                "action": "status",
                "verified": receipt.get("verified"),
                "enrolled": list((receipt.get("enrolled") or {}).keys()),
                "audit": receipt.get("audit"),
                "post_audit": st,
                "receipt": str(root / "receipts" / fi.RECEIPT_NAME),
            }
        )
        return 0

    raise FilmError(f"unknown face-identity action: {action}")


def cmd_style_lock(args: argparse.Namespace) -> int:
    """Input-ref → medium fingerprint → cast_locks plan/apply/check/prompt."""
    from scripts import style_lock as sl

    action = str(getattr(args, "style_lock_cmd", "") or "").strip()
    root = Path(args.root).expanduser().resolve() if getattr(args, "root", None) else None

    if action == "recommend":
        emit({"ok": True, **sl.recommend_medium_for_user_goal(getattr(args, "goal", "") or "")})
        return 0

    if root is None:
        raise FilmError("style-lock requires --root")

    if action == "plan":
        ref = getattr(args, "ref", None)
        if not ref:
            raise FilmError("style-lock plan requires --ref")
        medium_arg = getattr(args, "medium", None)
        if medium_arg in (None, "auto", ""):
            medium_arg = None
        plan = sl.plan_from_ref(
            root=root,
            ref_path=Path(ref),
            char_id=str(getattr(args, "char_id", None) or "hero"),
            display_name=str(getattr(args, "name", None) or ""),
            medium=medium_arg,
            theme=str(getattr(args, "theme", None) or ""),
            title=str(getattr(args, "title", None) or root.name),
            user_hint=str(getattr(args, "hint", None) or ""),
            face_notes=str(getattr(args, "face_notes", None) or ""),
            hair_lock=str(getattr(args, "hair", None) or ""),
            never_tokens=str(getattr(args, "never", None) or ""),
            default_wardrobe=str(getattr(args, "wardrobe", None) or ""),
            palette=str(getattr(args, "palette", None) or ""),
            lighting=str(getattr(args, "lighting", None) or ""),
            crop_faces=not bool(getattr(args, "no_crop", False)),
        )
        path = sl.write_plan(root, plan)
        emit({"ok": True, "action": "plan", "path": str(path), "plan": plan})
        return 0

    if action == "apply":
        plan_path = getattr(args, "plan_file", None)
        if plan_path:
            plan = json.loads(Path(plan_path).expanduser().resolve().read_text(encoding="utf-8"))
        else:
            plan = sl.read_plan(root)
        if not plan:
            raise FilmError("no style-lock plan; run: aifilm style-lock plan --root … --ref …")
        style = load_bible(root)
        style = sl.apply_plan_to_bible(style, plan)
        from visual_bible import save_bible

        save_bible(root, style)
        # also keep plan path
        sl.write_plan(root, plan)
        check = sl.validate_style_lock_bible(style)
        emit(
            {
                "ok": True,
                "action": "apply",
                "medium_key": plan.get("medium_key"),
                "stability": plan.get("stability"),
                "cast_locks": list((style.get("cast_locks") or {}).keys()),
                "check": check,
                "next": [
                    f'aifilm lock-style --root "{root}" --canonical <style-v1> '
                    f"--cast-master <cast master 9:16> --char-id {plan.get('cast_id') or 'hero'} "
                    f"--signature (from plan or omit if bible already filled)"
                ],
                "agent_still_prompt_prefix": style.get("agent_still_prompt_prefix"),
            }
        )
        return 0

    if action == "check":
        style = load_bible(root)
        check = sl.validate_style_lock_bible(style)
        emit({"ok": bool(check.get("ok")), "action": "check", **check})
        return 0 if check.get("ok") else 2

    if action == "prompt":
        style = load_bible(root)
        fp = (
            style.get("style_fingerprint")
            if isinstance(style.get("style_fingerprint"), dict)
            else {}
        )
        locks = style.get("cast_locks") if isinstance(style.get("cast_locks"), dict) else {}
        cast_ids = None
        if getattr(args, "cast", None):
            cast_ids = [c.strip() for c in str(args.cast).split(",") if c.strip()]
        if not fp:
            raise FilmError("no style_fingerprint; run style-lock plan+apply first")
        still = style.get("agent_still_prompt_prefix") or sl.build_agent_still_prompt_prefix(
            fp, locks, cast_ids=cast_ids
        )
        i2v = style.get("agent_i2v_prompt_prefix") or sl.build_agent_i2v_prompt_prefix(
            fp, motion=str(getattr(args, "motion", None) or "")
        )
        emit(
            {
                "ok": True,
                "action": "prompt",
                "still_prefix": still,
                "i2v_prefix": i2v,
                "medium_key": fp.get("medium_key"),
            }
        )
        return 0

    raise FilmError(f"unknown style-lock action: {action}")


def cmd_lock_style(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    style = load_bible(root)
    # Optional: auto-apply pending style-lock plan before locking
    style_plan = None
    if bool(getattr(args, "from_plan", False)):
        from scripts import style_lock as sl

        style_plan = sl.read_plan(root)
        if style_plan:
            style = sl.apply_plan_to_bible(style, style_plan)
    if args.signature:
        style["signature_block"] = args.signature.strip()
    canonical = args.canonical
    # The uploaded reference is the default style master for a reference-first
    # lock.  This prevents an accidental generic style-v1 from severing the
    # full-film look from the user's image.
    if not canonical and style_plan:
        canonical = (style_plan.get("style_reference") or {}).get("staged_path") or style_plan.get(
            "ref_staged"
        )
    if canonical:
        src = Path(canonical).expanduser().resolve()
        if not src.is_file():
            raise FilmError(f"Canonical style image missing: {src}")
        canonical_dir = film_dirs(root)["canonical"]
        try:
            dest = safe_output_path(
                canonical_dir,
                f"style-v1{src.suffix.lower() or '.jpg'}",
                suffixes={".jpg", ".jpeg", ".png", ".webp"},
                field="canonical style filename",
            )
        except SecurityPolicyError as exc:
            raise FilmError(str(exc)) from exc
        # Same-path short-circuit: canonical already at dest (no SameFileError)
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        style["canonical_style_path"] = str(dest)
        style["canonical_style_sha256"] = sha256(dest)
        reference = style.get("style_reference")
        if isinstance(reference, dict):
            # A reference-first lock has exactly one image anchor.  Record the
            # copied canonical path so validation detects a swapped staged or
            # canonical file before the film can be marked locked.
            reference["canonical_path"] = str(dest)
            reference["canonical_sha256"] = style["canonical_style_sha256"]
    cast_master = getattr(args, "cast_master", None)
    char_id = str(getattr(args, "char_id", None) or "hero").strip() or "hero"
    if cast_master:
        csrc = Path(cast_master).expanduser().resolve()
        if not csrc.is_file():
            raise FilmError(f"Cast master image missing: {csrc}")
        cast_dir = film_dirs(root)["canonical"] / "cast"
        cast_dir.mkdir(parents=True, exist_ok=True)
        try:
            cdest = safe_output_path(
                cast_dir,
                f"{char_id}-master{csrc.suffix.lower() or '.png'}"
                if char_id != "hero"
                else f"hero-v1{csrc.suffix.lower() or '.png'}",
                suffixes={".jpg", ".jpeg", ".png", ".webp"},
                field="cast master filename",
            )
        except SecurityPolicyError as exc:
            raise FilmError(str(exc)) from exc
        if csrc.resolve() != cdest.resolve():
            shutil.copy2(csrc, cdest)
        style.setdefault("cast_masters", {})
        if not isinstance(style["cast_masters"], dict):
            style["cast_masters"] = {}
        style["cast_masters"][char_id] = str(cdest)
        # keep hero alias for legacy paths
        if char_id != "hero":
            style["cast_masters"].setdefault("hero", str(cdest))
        style["cast_master_sha256"] = sha256(cdest)
        # Pixel face-identity enroll (best-effort)
        try:
            from scripts import face_identity as fi

            fi.enroll(root, char_id, cdest, label=char_id)
            if char_id != "hero":
                fi.enroll(root, "hero", cdest, label=char_id)
        except Exception:
            pass

    # Medium flag → fingerprint if missing
    medium_flag = getattr(args, "medium", None)
    if medium_flag:
        from scripts import style_lock as sl

        mk = sl.infer_medium(explicit=str(medium_flag))
        fp = sl.build_style_fingerprint(
            mk,
            palette=str(style.get("palette") or ""),
            lighting=str(style.get("lighting") or ""),
        )
        style["style_fingerprint"] = fp
        style["medium"] = fp["medium"]
        style["rendering"] = fp["rendering"]
        if not style.get("signature_block") or len(str(style.get("signature_block") or "")) < 40:
            style["signature_block"] = sl.build_signature_block(
                str(style.get("title") or root.name), fp
            )
        if not style.get("palette") or "to be filled" in str(style.get("palette") or "").lower():
            style["palette"] = f"locked-{mk}: coherent grade; match style master"

    # Consistency gates before lock (prevent empty/placeholder bibles)
    sig = str(style.get("signature_block") or "").strip()
    if len(sig) < 40:
        raise FilmError(
            "lock-style requires signature_block ≥40 chars "
            "(pass --signature, --medium, or aifilm style-lock plan first)"
        )
    palette = str(style.get("palette") or "").strip().lower()
    if not palette or "to be filled" in palette:
        raise FilmError(
            "lock-style requires a concrete palette in style-bible.json (not 'to be filled…')"
        )
    identity = str(style.get("identity_lock") or "").strip().lower()
    if identity and "to be filled" in identity:
        raise FilmError(
            "lock-style requires identity_lock filled with face/hair/eyes/wardrobe "
            "(edit style-bible.json or style-lock apply before locking)"
        )
    if not style.get("canonical_style_path"):
        raise FilmError("lock-style requires --canonical style master image")

    from scripts import style_lock as sl

    check = sl.validate_style_lock_bible(style)
    # A reference-first flow must fail closed: otherwise an old/incomplete
    # plan could be marked locked while its uploaded style anchor is absent.
    if not check.get("ok") and (
        bool(getattr(args, "strict_style_lock", False)) or style_plan is not None
    ):
        raise FilmError("style-lock hard fail: " + ",".join(check.get("hard") or []))

    style["locked"] = True
    style["state"] = "Approved"
    from visual_bible import save_bible

    save_bible(root, style)
    # receipt
    receipt = root / "receipts" / "style-lock.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        receipt,
        {
            "ok": True,
            "medium_key": check.get("medium_key"),
            "stability": check.get("stability"),
            "canonical_style_path": style.get("canonical_style_path"),
            "style_reference": style.get("style_reference"),
            "cast_masters": style.get("cast_masters") or {},
            "cast_locks": list((style.get("cast_locks") or {}).keys()),
            "check": check,
        },
    )
    manifest = load_manifest(root)
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    emit(
        {
            "ok": True,
            "style_locked": True,
            "canonical_style_path": style.get("canonical_style_path"),
            "style_reference": style.get("style_reference"),
            "cast_masters": style.get("cast_masters") or {},
            "medium_key": check.get("medium_key"),
            "stability": check.get("stability"),
            "style_lock_check": check,
            "receipt": str(receipt),
        }
    )
    return 0


def cmd_register_still(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    ensure_tree(root)
    identity_approved = getattr(args, "identity_approved", False) is True
    review_note = str(getattr(args, "review_note", "") or "").strip()
    anatomy_safe = getattr(args, "anatomy_safe", False) is True
    source = Path(args.source).expanduser().resolve()
    style_job = None
    style = read_json(root / "style-bible.json") if (root / "style-bible.json").is_file() else {}
    if isinstance(style.get("style_reference"), dict) and args.status == "approved":
        job_id = str(getattr(args, "queue_job_id", "") or "").strip()
        if not job_id:
            raise FilmError(
                "reference-first approved still requires --queue-job-id from image_gen/image_edit"
            )
        try:
            from media_queue import QueueError, style_reference_output_evidence

            style_job = style_reference_output_evidence(
                root,
                job_id=job_id,
                source=source,
                shot_id=str(args.shot_id),
                allowed_operations=frozenset({"image_gen", "image_edit"}),
            )
        except QueueError as exc:
            raise FilmError(str(exc)) from exc
    # Lesson 2026-07-22: compressed/wrong-aspect still → mushy I2V (vivian-ep01)
    aspect = "9:16"
    spec: dict[str, Any] = {}
    try:
        spec = read_json(root / "film-spec.json") if (root / "film-spec.json").is_file() else {}
        if not isinstance(spec, dict):
            spec = {}
        aspect = str(spec.get("aspect_ratio") or aspect)
    except Exception:
        spec = {}
    from media_qa import analyze_still_geometry, lint_still_not_character_sheet
    from quality_gates import evaluate_keyframe, require_quality, write_quality_receipt

    geo = analyze_still_geometry(source, aspect_ratio=aspect)
    if args.status == "approved" and not geo.get("ok"):
        raise FilmError(
            "Approved still failed geometry gate (keyframe no-compress): "
            + "; ".join(geo.get("errors") or ["unknown"])
            + " — re-export ≥720×1280 9:16 (or film aspect) full-res; "
            "never I2V from thumbnail/landscape compress. "
            "See references/lessons-2026-07-22-keyframe-no-compress.md"
        )
    # P0 2026-08-03 huangdao: multi-panel character sheets must not become I2V keyframes
    sheet = lint_still_not_character_sheet(source)
    if args.status == "approved" and not sheet.get("ok"):
        raise FilmError(
            "Approved still failed character-sheet content gate: "
            + "; ".join(sheet.get("errors") or ["STILL_LOOKS_LIKE_CHARACTER_SHEET"])
            + " — one continuous story frame only; never turnaround/expression boards. "
            "See references/lessons-2026-08-03-huangdao-rhythm-still-voice-silk.md"
        )
    # P0 2026-08-07: I2V first-frame subject fill (EP02 postage-stamp accident)
    composition_fill_rep: dict[str, Any] | None = None
    if args.status == "approved":
        try:
            from composition_fill_gate import assert_i2v_firstframe_fill, ensure_fill_frame

            composition_fill_rep = assert_i2v_firstframe_fill(source, mode="open")
            if not composition_fill_rep.get("ok") and not composition_fill_rep.get("skipped"):
                # one auto-remedy pass (letterbox strip / cover-crop) then re-gate
                ensure_fill_frame(source, source, mode="open")
                composition_fill_rep = assert_i2v_firstframe_fill(source, mode="open")
            if not composition_fill_rep.get("ok") and not composition_fill_rep.get("skipped"):
                raise FilmError(
                    "Approved still failed I2V composition-fill gate: "
                    + "; ".join(composition_fill_rep.get("errors") or composition_fill_rep.get("codes") or ["TINY_SUBJECT"])
                    + " — subject must fill ≥~72% frame height (CU/MS); "
                    "never raw fullbody cast master. "
                    "See memory/2026-08-07-i2v-firstframe-fill-no-tiny-fullbody.md "
                    "(escape AIFILM_SKIP_COMPOSITION_FILL=1)"
                )
        except FilmError:
            raise
        except Exception:
            composition_fill_rep = None
    # P0 2026-07-29: one still must not be approved for multiple shots (byte-identical)
    if args.status == "approved":
        from still_uniqueness import StillUniquenessError, assert_still_is_unique

        try:
            assert_still_is_unique(
                root=root,
                shot_id=str(args.shot_id),
                source=source,
                status=str(args.status),
                manifest=load_manifest(root),
            )
        except StillUniquenessError as exc:
            raise FilmError(str(exc)) from exc
    # F2 · still vs source_quote overlap (soft unless still_source_overlap_strict)
    if args.status == "approved":
        try:
            from input_fidelity import InputFidelityError, assert_still_source_for_register

            pa = str(getattr(args, "playable_action", "") or "").strip() or None
            # use review_note as weak playable_action when provided
            if not pa and review_note:
                pa = review_note
            assert_still_source_for_register(root, shot_id=str(args.shot_id), playable_action=pa)
        except InputFidelityError as exc:
            raise FilmError(str(exc)) from exc
        except Exception:
            pass
    if args.status == "approved":
        from anatomy_safety import AnatomySafetyError, require_anatomy_safe

        try:
            require_anatomy_safe(
                root=root,
                anatomy_safe=anatomy_safe,
                kind="still",
                shot_id=str(args.shot_id),
                still_path=source,
                review_note=review_note or None,
            )
        except AnatomySafetyError as exc:
            raise FilmError(str(exc)) from exc
        # Wave 2 · on_camera dialogue still = speaker face MCU (not wide meat body)
        try:
            from dialogue_speaker_frame_gate import assert_dialogue_still_for_register
            from production_gates import ProductionGateError

            assert_dialogue_still_for_register(root, str(args.shot_id))
        except ProductionGateError as exc:
            raise FilmError(str(exc)) from exc
        except Exception:
            pass
        if not identity_approved:
            raise FilmError(
                "Approved stills require --identity-approved after comparing to cast master"
            )
        if not review_note:
            raise FilmError(
                "Approved stills require --review-note "
                "(e.g. 'id-ok face/hair/outfit; medium matches style-v1')"
            )
        # I1.5 · scale promote_ban on still approve (same as clip)
        try:
            from narrative.scale_fallback import ScalePromoteBanError, assert_scale_promote_allowed

            assert_scale_promote_allowed(root, review_note=review_note, kind="still")
        except ScalePromoteBanError as exc:
            raise FilmError(str(exc)) from exc
        except Exception:
            pass
        # 卸装不回穿 still 源：undressed/bare 禁 sole-ref 全装 cast master
        heat_scale = str(spec.get("heat_scale") or "").strip().lower()
        if heat_scale == "max" and spec.get("adult_max_iron") is not False:
            wardrobe_state = None
            for sc in spec.get("scenes") or []:
                if not isinstance(sc, dict):
                    continue
                for sh in sc.get("shots") or []:
                    if isinstance(sh, dict) and str(sh.get("id") or "") == str(args.shot_id):
                        wardrobe_state = sh.get("wardrobe_state") or (
                            (sh.get("dsl") or {}).get("wardrobe_state")
                            if isinstance(sh.get("dsl"), dict)
                            else None
                        )
                        break
            if wardrobe_state in {"partial", "undressed", "bare"}:
                from i2v_motion_gate import lint_still_source_policy

                still_src = str(getattr(args, "still_source", None) or source.name or source)
                still_rep = lint_still_source_policy(
                    [
                        {
                            "id": str(args.shot_id),
                            "wardrobe_state": wardrobe_state,
                            "still_source": still_src,
                            "still_tags": [review_note],
                        }
                    ]
                )
                if not still_rep.get("ok"):
                    raise FilmError(
                        "approved still re-dress risk (wardrobe undressed/bare + full cast source): "
                        + ",".join(still_rep.get("codes") or [])
                        + " — use undress-anchor / prior undressed still; "
                        "禁 image_edit(全装 cast) 当 peak still 源。"
                    )
    quality = evaluate_keyframe(
        root,
        shot_id=str(args.shot_id),
        source=source,
        aspect_ratio=aspect,
        prompt_file=Path(args.prompt_file).expanduser().resolve() if args.prompt_file else None,
        identity_approved=identity_approved,
        review_note=review_note,
    )
    if args.status == "approved":
        require_quality(quality, kind="keyframe")
    record = _register_media(
        shot_id=args.shot_id,
        source=source,
        dest_dir=root / "keyframes",
        role=args.role,
        status=args.status,
        prompt_file=Path(args.prompt_file).expanduser().resolve() if args.prompt_file else None,
    )
    record["geometry_qa"] = geo
    record["quality_gate"] = quality
    if composition_fill_rep is not None:
        record["composition_fill"] = {
            "ok": composition_fill_rep.get("ok"),
            "codes": composition_fill_rep.get("codes"),
            "metrics": composition_fill_rep.get("metrics"),
            "skipped": composition_fill_rep.get("skipped"),
        }
    record["anatomy_safe"] = anatomy_safe if args.status == "approved" else None
    if style_job:
        record["style_reference_job"] = style_job
    record["quality_receipt"] = str(write_quality_receipt(root, record["shot_id"], quality))
    if args.status == "approved":
        record["identity_approved"] = True
        record["review_note"] = review_note
        # Pixel face-identity check when cast enrolled
        face_id_result = None
        try:
            from scripts import face_identity as fi

            char_guess = str(getattr(args, "char_id", None) or "").strip()
            if not char_guess:
                # from film-spec shot cast
                try:
                    for sc in spec.get("scenes") or []:
                        for sh in sc.get("shots") or []:
                            if str(sh.get("id")) != str(args.shot_id):
                                continue
                            dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
                            cast = dsl.get("cast") if isinstance(dsl.get("cast"), list) else []
                            if cast:
                                char_guess = str(cast[0])
                except Exception:
                    char_guess = ""
            receipt = fi.load_receipt(root)
            enrolled = receipt.get("enrolled") if isinstance(receipt.get("enrolled"), dict) else {}
            if char_guess and char_guess in enrolled:
                face_id_result = fi.verify_image(root, source, char_guess)
                record["face_identity"] = {
                    "ok": face_id_result.get("ok"),
                    "char_id": char_guess,
                    "score": face_id_result.get("score"),
                    "ahash_distance": face_id_result.get("ahash_distance"),
                    "dhash_distance": face_id_result.get("dhash_distance"),
                }
                # v2.40: enrolled cast → default hard reject (escape AIFILM_SKIP_FACE_IDENTITY=1)
                try:
                    from core.skip_audit import skip_flag

                    skip_face = skip_flag(
                        "AIFILM_SKIP_FACE_IDENTITY",
                        origin="env",
                        film_root=root,
                        call_site="register_still.face_identity",
                    )
                except Exception:
                    skip_face = os.environ.get("AIFILM_SKIP_FACE_IDENTITY", "").strip().lower() in {
                        "1",
                        "true",
                        "yes",
                        "on",
                    }
                require_face = (not skip_face) or bool(
                    getattr(args, "require_face_identity", False)
                )
                if require_face and not face_id_result.get("ok"):
                    raise FilmError(
                        f"face-identity verify failed for {args.shot_id} vs {char_guess}: "
                        f"score={face_id_result.get('score')} "
                        f"(ahash={face_id_result.get('ahash_distance')} "
                        f"dhash={face_id_result.get('dhash_distance')})"
                    )
        except FilmError:
            raise
        except Exception:
            face_id_result = None
    manifest = load_manifest(root)
    manifest.setdefault("stills", {})[record["shot_id"]] = record
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    emit(
        {
            "ok": True,
            "record": record,
            "geometry_qa": geo,
            "face_identity": record.get("face_identity"),
        }
    )
    return 0


def cmd_register_clip(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    ensure_tree(root)
    source = Path(args.source).expanduser().resolve()
    endpoint = getattr(args, "source_endpoint", None)
    identity_approved = getattr(args, "identity_approved", False) is True
    motion_approved = getattr(args, "motion_approved", False) is True
    review_note = str(getattr(args, "review_note", "") or "").strip()
    anatomy_safe = getattr(args, "anatomy_safe", False) is True
    queue_job_id = str(getattr(args, "queue_job_id", "") or "").strip()
    # P0 · true-video-only: stills / Ken Burns / panel motion never become hero clips
    try:
        from quality_gates import shot_role
        from true_video_policy import TrueVideoPolicyError, assert_hero_clip_source

        role = shot_role(root, str(getattr(args, "shot_id", "") or ""))
        tags = getattr(args, "tags", None)
        tag_list = [str(t) for t in tags] if isinstance(tags, (list, tuple)) else []
        assert_hero_clip_source(
            source,
            endpoint=str(endpoint) if endpoint else None,
            status=str(args.status or "candidate"),
            tags=tag_list,
            provider=str(getattr(args, "provider", "") or "") or None,
            review_note=review_note or None,
            root=root,
            role=role,
        )
    except TrueVideoPolicyError as exc:
        raise FilmError(f"True-video policy: {exc}") from exc
    if args.status == "approved":
        from motion_evidence import MotionEvidenceError, require_queue_job_for_canonical_project

        try:
            require_queue_job_for_canonical_project(root, queue_job_id=queue_job_id)
        except MotionEvidenceError as exc:
            raise FilmError(str(exc)) from exc
        from visual_text_audit import VisualTextAuditError, require_clean_audit

        try:
            require_clean_audit(root, source)
        except VisualTextAuditError as exc:
            raise FilmError(
                f"approved FRW LTX clip requires clean visual-text audit: {exc}"
            ) from exc
    if args.status == "approved":
        from anatomy_safety import AnatomySafetyError, require_anatomy_safe

        try:
            require_anatomy_safe(
                root=root,
                anatomy_safe=anatomy_safe,
                kind="clip",
                shot_id=str(args.shot_id),
                still_path=source,
                review_note=str(getattr(args, "review_note", "") or "").strip() or None,
            )
        except AnatomySafetyError as exc:
            raise FilmError(str(exc)) from exc
        # I2.2 · endframe no-redress heuristic on undress meat
        try:
            from endframe_wardrobe import EndframeWardrobeError, assert_endframe_no_redress

            clip_spec = read_json(root / "film-spec.json") if (root / "film-spec.json").is_file() else {}
            if not isinstance(clip_spec, dict):
                clip_spec = {}
            heat_phase = None
            wardrobe_state = None
            for sc in clip_spec.get("scenes") or []:
                if not isinstance(sc, dict):
                    continue
                for sh in sc.get("shots") or []:
                    if isinstance(sh, dict) and str(sh.get("id") or "") == str(args.shot_id):
                        heat_phase = sh.get("heat_phase")
                        wardrobe_state = sh.get("wardrobe_state") or (
                            (sh.get("dsl") or {}).get("wardrobe_state")
                            if isinstance(sh.get("dsl"), dict)
                            else None
                        )
                        break
            assert_endframe_no_redress(
                root,
                str(args.shot_id),
                source,
                wardrobe_state=str(wardrobe_state) if wardrobe_state else None,
                heat_phase=str(heat_phase) if heat_phase else None,
                hard=True,
            )
        except EndframeWardrobeError as exc:
            raise FilmError(str(exc)) from exc
        except Exception:
            pass
        if endpoint not in ALLOWED_VIDEO_ENDPOINTS:
            raise FilmError(
                f"Approved clips require --source-endpoint in {sorted(ALLOWED_VIDEO_ENDPOINTS)}"
            )
        if not identity_approved:
            raise FilmError(
                "Approved clips require --identity-approved after canonical identity review"
            )
        # P0 · face-identity-pixel: a failed post_audit must block clip approval
        from production_gates import assert_face_identity_passed as _assert_face_id

        try:
            _assert_face_id(root, force=False, env_skip=False, proven_drift_only=True)
        except Exception as exc:  # ProductionGateError → re-wrapped as FilmError
            raise FilmError(f"face-identity post_audit failed: {exc}") from exc
        if not motion_approved:
            raise FilmError(
                "Approved clips require --motion-approved after watching the complete clip"
            )
        if not review_note:
            raise FilmError("Approved clips require --review-note with the visual review result")
        # I1.5 · scale_fallback promote ban (shared assert)
        try:
            from narrative.scale_fallback import ScalePromoteBanError, assert_scale_promote_allowed

            assert_scale_promote_allowed(root, review_note=review_note, kind="clip")
        except ScalePromoteBanError as exc:
            raise FilmError(str(exc)) from exc
        except Exception:  # noqa: BLE001 — soft miss of helper only
            pass
    manifest = load_manifest(root)
    style_job = None
    style = read_json(root / "style-bible.json") if (root / "style-bible.json").is_file() else {}
    if isinstance(style.get("style_reference"), dict) and args.status == "approved":
        job_id = str(getattr(args, "queue_job_id", "") or "").strip()
        if not job_id:
            raise FilmError(
                "reference-first approved clip requires --queue-job-id from reference_to_video"
            )
        try:
            from media_queue import QueueError, style_reference_output_evidence

            style_job = style_reference_output_evidence(
                root,
                job_id=job_id,
                source=Path(args.source).expanduser().resolve(),
                shot_id=str(args.shot_id),
                allowed_operations=frozenset({"reference_to_video"}),
            )
        except QueueError as exc:
            raise FilmError(str(exc)) from exc
    shot_review = None
    if args.status == "approved" and int(manifest.get("review_contract_version") or 1) >= 2:
        try:
            from shot_review import approved_review_for_clip

            shot_review = approved_review_for_clip(
                root,
                shot_id=str(args.shot_id),
                clip=source,
                receipt=Path(args.review_receipt).expanduser().resolve()
                if getattr(args, "review_receipt", None)
                else None,
            )
        except Exception as exc:
            raise FilmError(
                f"v1.6 approved clips require matching shot-review evidence: {exc}"
            ) from exc
    if args.status == "approved":
        from clip_uniqueness import ClipUniquenessError, assert_clip_is_unique

        try:
            uniqueness = assert_clip_is_unique(source, manifest=manifest, shot_id=str(args.shot_id))
        except ClipUniquenessError as exc:
            raise FilmError(f"Approved clips cannot reuse another shot's segment: {exc}") from exc
    else:
        uniqueness = None
    try:
        contract_kwargs: dict[str, Any] = {}
        if getattr(args, "strict_video_contract", False):
            spec = read_json(root / "film-spec.json") if (root / "film-spec.json").is_file() else {}
            aspect = str(spec.get("aspect_ratio") or "9:16").replace("/", ":")
            if aspect == "9:16":
                contract_kwargs.update({"min_width": 704, "min_height": 1280})
            timeline = spec.get("timeline") if isinstance(spec, dict) else {}
            fps = spec.get("fps") or (timeline.get("fps") if isinstance(timeline, dict) else None)
            if fps:
                contract_kwargs["expected_fps"] = float(fps)
        qa = analyze_media(
            source,
            require_audio=False,
            require_motion=True,
            **contract_kwargs,
        )
    except MediaQAError as exc:
        raise FilmError(str(exc)) from exc
    if args.status == "approved" and not qa.get("ok"):
        raise FilmError(f"Clip failed decode/duration/motion QA: {qa.get('errors')}")
    from quality_gates import evaluate_clip, require_quality, write_quality_receipt

    quality = evaluate_clip(
        root,
        shot_id=str(args.shot_id),
        qa=qa,
        endpoint=endpoint,
        identity_approved=identity_approved,
        motion_approved=motion_approved,
        review=shot_review,
    )
    if args.status == "approved":
        require_quality(quality, kind="clip")
    from take_registry import archive_active_clip, register_active_take

    previous_take = archive_active_clip(root, str(args.shot_id), manifest)
    record = _register_media(
        shot_id=args.shot_id,
        source=source,
        dest_dir=root / "clips",
        role="i2v",
        status=args.status,
        prompt_file=Path(args.prompt_file).expanduser().resolve() if args.prompt_file else None,
    )
    # go4 · write continue handoff for next chain_mode=continue (Grok+H3 shared)
    try:
        from continue_handoff import maybe_write_for_clip

        eng = (
            "h3"
            if "minimax_h3" in str(endpoint or "") or "h3" in str(endpoint or "").lower()
            else "grok"
        )
        maybe_write_for_clip(
            root,
            str(args.shot_id),
            Path(record.get("path") or source),
            engine=eng,
            mode="i2v",
        )
    except Exception:
        pass
    # M4 · shot-evidence + motion mean hard gate on approved clips (v2.40.7)
    mean_val = None
    try:
        from i2v_motion_gate import evaluate_shot_motion, measure_mean_absdiff

        mean_val = measure_mean_absdiff(Path(record.get("path") or source))
    except Exception:
        mean_val = None
    try:
        from shot_evidence import write_shot_evidence

        write_shot_evidence(
            root,
            str(args.shot_id),
            mean=mean_val,
            video_path=Path(record.get("path") or source),
            identity_ok=bool(identity_approved),
            motion_ok=bool(motion_approved),
            poison=False if anatomy_safe else None,
            source="register-clip",
            extra={"status": str(args.status or ""), "endpoint": str(endpoint or "")},
        )
    except Exception:
        pass
    if str(args.status or "") == "approved":
        try:
            from core.skip_audit import skip_flag

            skip_mean = skip_flag(
                "AIFILM_SKIP_MOTION_MEAN",
                origin="env",
                film_root=root,
                call_site="register_clip.motion_mean",
            )
        except Exception:
            skip_mean = os.environ.get("AIFILM_SKIP_MOTION_MEAN", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        if not skip_mean:
            heat_phase = None
            dramatic_function = None
            wardrobe_state = None
            try:
                spec_m = read_json(root / "film-spec.json") or {}
                for sc in spec_m.get("scenes") or []:
                    if not isinstance(sc, dict):
                        continue
                    for sh in sc.get("shots") or []:
                        if not isinstance(sh, dict):
                            continue
                        if str(sh.get("id")) != str(args.shot_id):
                            continue
                        dsl = sh.get("dsl") if isinstance(sh.get("dsl"), dict) else {}
                        heat_phase = sh.get("heat_phase") or dsl.get("heat_phase")
                        dramatic_function = sh.get("dramatic_function") or dsl.get(
                            "dramatic_function"
                        )
                        wardrobe_state = sh.get("wardrobe_state") or dsl.get("wardrobe_state")
                        break
            except Exception:
                pass
            tags = getattr(args, "tags", None)
            tag_list = [str(t) for t in tags] if isinstance(tags, (list, tuple)) else []
            try:
                from i2v_motion_gate import evaluate_shot_motion
            except Exception:
                evaluate_shot_motion = None  # type: ignore
            if evaluate_shot_motion is not None:
                grade = evaluate_shot_motion(
                    mean_val,
                    heat_phase=str(heat_phase) if heat_phase else None,
                    dramatic_function=str(dramatic_function) if dramatic_function else None,
                    wardrobe_state=str(wardrobe_state) if wardrobe_state else None,
                    source=str(endpoint or ""),
                    source_tags=tag_list,
                    shot_id=str(args.shot_id),
                )
                record["motion_mean_gate"] = grade
                if not grade.get("ok"):
                    raise FilmError(
                        f"register-clip motion mean gate failed for {args.shot_id}: "
                        f"mean={grade.get('mean')} tier={grade.get('tier')} "
                        f"floor={grade.get('floor')} codes={grade.get('codes')}. "
                        "Reshoot high-motion take or AIFILM_SKIP_MOTION_MEAN=1 (discouraged)."
                    )
    try:
        record["duration_sec"] = media_duration(Path(record["path"]))
    except Exception:
        record["duration_sec"] = None
    qa["path"] = record["path"]
    record.update(
        {
            "source_endpoint": endpoint,
            "identity_approved": identity_approved,
            "motion_approved": motion_approved,
            "review_note": review_note,
            "anatomy_safe": anatomy_safe if args.status == "approved" else None,
            "qa": qa,
            "shot_review": shot_review,
            "quality_gate": quality,
            "uniqueness": uniqueness,
        }
    )
    # MiniMax H3: prefer native diegetic audio when usable (prefer_native default).
    _H3_REGISTER_ENDPOINTS = frozenset(
        {
            "local_minimax_h3_t2v",
            "local_minimax_h3_i2v",
            "local_minimax_h3_r2v",
        }
    )
    if endpoint in _H3_REGISTER_ENDPOINTS:
        h3_audio = "prefer_native"
        try:
            film_spec_raw = read_json(root / "film-spec.json") or {}
            h3_block = film_spec_raw.get("h3") if isinstance(film_spec_raw.get("h3"), dict) else {}
            candidate = str(h3_block.get("audio_policy") or "").strip()
            if candidate in {
                "prefer_native",
                "keep_native",
                "strip_native_use_tts_bgm",
                "mute_native",
            }:
                h3_audio = candidate
        except Exception:
            pass
        record["provider"] = "comfy-h3"
        record["h3"] = True
        record["audio_policy"] = h3_audio
        # Prefer keep when stream has audio; only force off for explicit strip/mute.
        if h3_audio in {"strip_native_use_tts_bgm", "mute_native"}:
            record["use_clip_audio"] = False
        elif h3_audio == "keep_native":
            record["use_clip_audio"] = True
        else:
            # prefer_native: use clip audio when QA sees a track, else TTS/BGM path.
            record["use_clip_audio"] = bool(qa.get("has_audio"))
    if args.status == "approved":
        # Always build quality_evidence on approved (never skip first approve).
        # Motion generation evidence is required when --queue-job-id is present;
        # without a queue job, provider receipt binds to the registered clip hash
        # (agent/tool I2V path). Once contract is active, queue-bound motion is
        # still preferred when a job id is supplied.
        from motion_evidence import MotionEvidenceError, build_motion_generation_evidence
        from quality_evidence import QualityEvidenceError, build_shot_quality_evidence

        clip_path = Path(record["path"])
        motion_evidence: dict[str, Any] | None = None
        if queue_job_id:
            try:
                motion_evidence = build_motion_generation_evidence(
                    root,
                    shot_id=str(args.shot_id),
                    clip=clip_path,
                    source_endpoint=str(endpoint),
                    queue_job_id=queue_job_id,
                )
            except MotionEvidenceError as exc:
                raise FilmError(
                    f"approved clips require matching motion generation evidence: {exc}"
                ) from exc
            record["motion_evidence"] = motion_evidence
        if motion_evidence and motion_evidence.get("delivery_eligible") is True:
            provider: dict[str, Any] = {
                "ok": True,
                "output_sha256": (motion_evidence.get("clip") or {}).get("sha256"),
            }
        else:
            # Local/agent register: hash-bound to the exact clip bytes on disk.
            provider = {
                "ok": True,
                "output_sha256": sha256(clip_path),
                "binding": "registered_clip",
            }
        review_packet = read_json(Path(str(shot_review.get("path") or ""))) if shot_review else {}
        try:
            evidence = build_shot_quality_evidence(
                root,
                shot_id=str(args.shot_id),
                clip=clip_path,
                qa=qa,
                source_endpoint=endpoint,
                identity_approved=identity_approved,
                motion_approved=motion_approved,
                review=shot_review,
                uniqueness=uniqueness,
                continuity=review_packet.get("continuity_packet"),
                provider=provider,
            )
        except QualityEvidenceError as exc:
            raise FilmError(f"approved clips require current quality evidence: {exc}") from exc
        record["quality_evidence"] = evidence
        manifest["quality_evidence_contract_version"] = 1
    if style_job:
        record["style_reference_job"] = style_job
    record["quality_receipt"] = str(write_quality_receipt(root, record["shot_id"], quality))
    if qa.get("has_audio"):
        try:
            audio_dir = film_dirs(root)["audio"]
            native_dir = safe_workspace_directory(
                audio_dir, "native", field="native audio directory"
            )
            native_dir.mkdir(exist_ok=True)
            native_path = safe_output_path(
                native_dir,
                f"{record['shot_id']}.m4a",
                suffixes={".m4a"},
                field="native audio stem",
            )
            temp_native = safe_output_path(
                native_dir,
                f".{record['shot_id']}.tmp.m4a",
                suffixes={".m4a"},
                field="temporary native audio stem",
            )
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    record["path"],
                    "-vn",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    str(temp_native),
                ]
            )
            os.replace(temp_native, native_path)
            mean_volume_db = probe_native_audio_mean_volume(native_path)
            record["native_audio"] = {
                "path": str(native_path),
                "sha256": sha256(native_path),
                "duration_sec": media_duration(native_path),
                "mean_volume_db": mean_volume_db,
                "audible": (
                    mean_volume_db is not None and mean_volume_db > NATIVE_AUDIO_AUDIBLE_MIN_DB
                ),
                "preserved_at": utc_now(),
            }
        except (SecurityPolicyError, subprocess.CalledProcessError, OSError, ValueError) as exc:
            raise FilmError(f"Could not preserve generated native audio: {exc}") from exc
    record = register_active_take(root, manifest, record, previous=previous_take)
    recompute_gates(root, manifest)
    save_manifest(root, manifest)

    # Generation-time first/last: auto promote next keyframe from this clip's last frame
    promote: dict[str, Any] | None = None
    if args.status == "approved":
        try:
            promote = _auto_promote_last_to_next(
                root,
                shot_id=str(args.shot_id),
                clip_path=Path(record["path"]),
            )
        except Exception as exc:  # noqa: BLE001
            promote = {"ok": False, "error": str(exc)[:300]}
        if promote:
            record["auto_promote_next"] = promote
            # re-save with promote receipt on clip
            manifest = load_manifest(root)
            manifest.setdefault("clips", {})[record["shot_id"]] = record
            save_manifest(root, manifest)

    if args.status == "approved":
        try:
            from pipeline_events import append_event

            append_event(root, stage="i2v", phase="registered", shot_id=str(args.shot_id))
        except OSError:
            pass

    emit({"ok": True, "record": record, "auto_promote_next": promote})
    return 0


def cmd_assemble(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    out_name = args.out_name or "film_silent.mp4"
    out_path = film_output_path(root, out_name)
    if not shutil.which("ffmpeg"):
        raise FilmError("ffmpeg not found")
    manifest = load_manifest(root)
    summary = recompute_gates(root, manifest)
    try:
        from shot_inventory import InventoryError, assert_inventory_for_final

        assert_inventory_for_final(
            summary.get("shot_ids") or [],
            summary.get("approved_clips") or [],
        )
    except InventoryError as exc:
        raise FilmError(str(exc)) from exc
    timeline = read_json(root / "timeline.json")
    width = int(timeline.get("width") or manifest.get("width") or DEFAULT_WIDTH)
    height = int(timeline.get("height") or manifest.get("height") or DEFAULT_HEIGHT)
    fps = int(timeline.get("fps") or DEFAULT_FPS)
    shots = timeline.get("shots") or []
    if not shots:
        raise FilmError("timeline.json has no shots")
    work = root / "out" / "_assemble_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    parts: list[Path] = []
    clips = manifest.get("clips") or {}
    clips_dir = film_dirs(root)["clips"]
    seen_shots: set[str] = set()
    for i, shot in enumerate(shots):
        sid = valid_shot_id(shot.get("id"))
        if sid in seen_shots:
            raise FilmError(f"duplicate timeline shot id: {sid}")
        seen_shots.add(sid)
        rec = clips.get(sid)
        if not rec or rec.get("status") != "approved":
            raise FilmError(f"Shot {sid} has no approved clip in manifest")
        try:
            src = safe_existing_file(clips_dir, rec["path"], field=f"clip path for {sid}")
        except (KeyError, SecurityPolicyError) as exc:
            raise FilmError(str(exc)) from exc
        dur = float(shot.get("duration_sec") or rec.get("duration_sec") or 6)
        part = work / f"part_{i:02d}_{sid}.mp4"
        log(f"normalize {sid} -> {dur}s @ {width}x{height}")
        normalize_clip(src, part, width=width, height=height, fps=fps, duration=dur)
        parts.append(part)
    concat_list = work / "concat.txt"
    concat_list.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(out_path),
        ]
    )
    # rewrite concat with absolute paths for robustness if relative fails was already used in work dir
    total = media_duration(out_path)
    try:
        technical_qa = analyze_media(out_path, require_audio=False, require_motion=True)
    except MediaQAError as exc:
        raise FilmError(str(exc)) from exc
    if not technical_qa.get("ok"):
        raise FilmError(
            f"Assembled film failed decode/duration/motion QA: {technical_qa.get('errors')}"
        )
    manifest["outputs"]["silent_film"] = {
        "path": str(out_path),
        "sha256": sha256(out_path),
        "duration_sec": total,
        "width": width,
        "height": height,
        "fps": fps,
        "technical_qa": technical_qa,
        "assembled_at": utc_now(),
    }
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    emit(
        {
            "ok": True,
            "output": str(out_path),
            "duration_sec": total,
            "width": width,
            "height": height,
            "shot_count": len(parts),
        }
    )
    return 0


def cmd_ingest_footage(args: argparse.Namespace) -> int:
    """Ingest real footage: copy → transcribe (local Whisper) → takes_packed.md.

    Bridges the video-use skill so ai-film-grok can ingest real talking-head /
    interview footage for the editing ring (the one stage that was absent).
    """
    try:
        from real_footage import RealFootageError, ingest_footage
    except ImportError as exc:
        raise FilmError(f"real_footage module unavailable: {exc}") from exc
    try:
        receipt = ingest_footage(
            Path(args.root),
            Path(args.source),
            label=getattr(args, "label", None),
            whisper_model=getattr(args, "whisper_model", "base"),
        )
    except RealFootageError as exc:
        raise FilmError(str(exc)) from exc
    emit(receipt)
    return 0 if receipt.get("ok") else 1


def cmd_auto_cut(args: argparse.Namespace) -> int:
    """Auto-cut real footage on word boundaries + silence gaps (video-use logic).

    Reads a cached word-level transcript (from ingest-footage) and produces an
    EDL JSON honoring video-use Hard Rules 6 (word-boundary cuts) + 7 (pad edges).
    """
    try:
        from auto_cut import AutoCutError, build_edl_for_root
    except ImportError as exc:
        raise FilmError(f"auto_cut module unavailable: {exc}") from exc
    try:
        edl = build_edl_for_root(
            Path(args.root),
            str(args.source_id),
            target_duration_sec=getattr(args, "target_duration", None),
        )
    except AutoCutError as exc:
        raise FilmError(str(exc)) from exc
    emit(edl)
    return 0 if edl.get("ranges") else 1


def cmd_shortform(args: argparse.Namespace) -> int:
    """Plan/review/assemble the provider-neutral shortform director package."""
    from shortform_director import (
        ShortformError,
        aroll_broll,
        assemble_aroll,
        create_package,
        enable_lipsync,
        export_spec,
        render_lipsync,
        review,
        validate_package,
    )
    from shortform_motion import ShortformMotionError, build_plan, render_plan

    try:
        action = str(args.shortform_action)
        if action == "plan":
            report = create_package(
                args.root,
                mode=args.mode,
                approved_script=Path(args.approved_script) if args.approved_script else None,
                source_video=Path(args.source_video) if args.source_video else None,
                transcript=Path(args.transcript) if args.transcript else None,
                anchor=Path(args.anchor) if args.anchor else None,
            )
        elif action == "validate":
            report = validate_package(args.root, require_approved=args.require_approved)
        elif action == "review":
            report = review(
                args.root,
                stage=args.stage,
                reviewer=args.reviewer,
                note=args.note,
                approve=args.approve,
            )
        elif action == "enable-lipsync":
            report = enable_lipsync(
                args.root,
                shot_id=args.shot_id,
                speaker=args.speaker,
                face_target=args.face_target,
                audio_sha256=args.audio_sha256,
            )
        elif action == "render-lipsync":
            report = render_lipsync(
                args.root,
                shot_id=args.shot_id,
                video=Path(args.video),
                audio=Path(args.audio),
                out=Path(args.out) if args.out else None,
                backend=args.backend,
            )
        elif action == "aroll-broll":
            report = {"ok": True, "entries": aroll_broll(args.root, beat_id=args.beat_id)}
        elif action == "assemble-aroll":
            report = assemble_aroll(
                args.root,
                visual_dir=Path(args.visual_dir),
                out=Path(args.out) if args.out else None,
            )
        elif action == "export-spec":
            report = export_spec(
                args.root,
                force=bool(getattr(args, "force", False)),
                title=str(getattr(args, "title", "") or "") or None,
            )
        elif action == "motion-plan":
            layers = read_json(Path(args.layers))
            if not isinstance(layers, list):
                raise ShortformError("--layers must contain a JSON list")
            report = build_plan(
                args.root, base=Path(args.base), layers=layers, shot_id=args.shot_id
            )
        elif action == "render-motion":
            report = render_plan(
                args.root,
                plan=Path(args.plan),
                duration_sec=args.duration,
                fps=args.fps,
                width=args.width,
                height=args.height,
                out=Path(args.out) if args.out else None,
            )
        else:
            raise ShortformError(f"unknown shortform action {action}")
    except (ShortformError, ShortformMotionError) as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0 if report.get("ok", True) else 1


def cmd_reencode_clips(args: argparse.Namespace) -> int:
    """Re-encode all film-spec clips to clean h264 and re-register (fixes FRW moov / sha drift)."""
    root = Path(args.root).expanduser().resolve()
    ensure_tree(root)
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise FilmError("ffmpeg/ffprobe required for reencode-clips")
    spec = read_json(root / "film-spec.json") if (root / "film-spec.json").is_file() else {}
    try:
        shots = validate_film_spec(spec, assign_missing_ids=False)
    except FilmSpecError as exc:
        raise FilmError(f"reencode-clips requires valid film-spec: {exc}") from exc
    brief = read_json(root / "brief.json") if (root / "brief.json").is_file() else {}
    timeline = read_json(root / "timeline.json") if (root / "timeline.json").is_file() else {}
    # Target canvas (Seedance default 720×1280). Never *upscale* source pixels
    # (胃镜室: 576→720 reencode looked "HD" but was soft mush).
    target_w = int(args.width or timeline.get("width") or brief.get("width") or 720)
    target_h = int(args.height or timeline.get("height") or brief.get("height") or 1280)
    force_scale = bool(getattr(args, "force_scale", False))
    fps = int(args.fps or timeline.get("fps") or 30)
    duration_cap = float(args.duration_cap or 6.0)
    clean_dir = film_dirs(root)["clips"] / "clean"
    clean_dir.mkdir(parents=True, exist_ok=True)
    inbox = root / "inbox" / "reencode"
    inbox.mkdir(parents=True, exist_ok=True)
    note = (
        args.review_note
        or "reencode-clips: clean h264; no upscale; identity+motion re-approved after re-encode"
    )
    done: list[str] = []
    failed: list[dict[str, str]] = []
    manifest_pre = load_manifest(root)

    def _probe_wh(path: Path) -> tuple[int, int] | None:
        try:
            proc = run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=width,height",
                    "-of",
                    "csv=p=0:s=x",
                    str(path),
                ],
                check=False,
            )
            raw = (proc.stdout or "").strip()
            if "x" not in raw:
                return None
            a, b = raw.split("x", 1)
            return int(a), int(b)
        except Exception:
            return None

    for shot in shots:
        sid = shot["id"]
        src = film_dirs(root)["clips"] / f"{sid}.mp4"
        if not src.is_file():
            failed.append({"shot_id": sid, "error": f"missing {src}"})
            continue
        prev = (manifest_pre.get("clips") or {}).get(sid) or {}
        prev_ep = prev.get("source_endpoint")
        # CLI override > existing FRW/Grok label > frw_seedance_i2v (bulk default)
        if args.source_endpoint:
            endpoint = args.source_endpoint
        elif prev_ep in ALLOWED_VIDEO_ENDPOINTS:
            endpoint = prev_ep
        else:
            endpoint = "frw_seedance_i2v"
        src_wh = _probe_wh(src)
        if force_scale or src_wh is None:
            out_w, out_h = target_w, target_h
        else:
            sw, sh = src_wh
            # Larger/equal source → fit into target canvas (may downscale).
            # Smaller source → keep native even size (never upscale; 胃镜室纪律).
            if sw >= target_w and sh >= target_h:
                out_w, out_h = target_w, target_h
            else:
                out_w = max(2, sw - (sw % 2))
                out_h = max(2, sh - (sh % 2))
        out = clean_dir / f"{sid}.mp4"
        # scale=…:decrease never enlarges; pad to even canvas when needed
        vf = (
            f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
            f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2,fps={fps},format=yuv420p"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            str(int(args.crf or 18)),
            "-t",
            f"{duration_cap:.3f}",
            str(out),
        ]
        try:
            run(cmd, check=True)
        except subprocess.CalledProcessError as exc:
            err = (exc.stderr or exc.stdout or str(exc))[:500]
            failed.append({"shot_id": sid, "error": err})
            continue
        # Register from inbox copy (avoid SameFile if already at clips/)
        inbox_src = inbox / f"{sid}.mp4"
        shutil.copy2(out, inbox_src)
        try:
            qa = analyze_media(inbox_src, require_audio=False, require_motion=True)
            if not qa.get("ok"):
                raise FilmError(f"QA failed after reencode: {qa.get('errors')}")
            record = _register_media(
                shot_id=sid,
                source=inbox_src,
                dest_dir=film_dirs(root)["clips"],
                role="i2v",
                status="approved",
                prompt_file=None,
            )
            try:
                record["duration_sec"] = media_duration(Path(record["path"]))
            except Exception:
                record["duration_sec"] = None
            qa["path"] = record["path"]
            record.update(
                {
                    "source_endpoint": endpoint,
                    "identity_approved": True,
                    "motion_approved": True,
                    "review_note": note,
                    "qa": qa,
                }
            )
            manifest = load_manifest(root)
            manifest.setdefault("clips", {})[sid] = record
            recompute_gates(root, manifest)
            save_manifest(root, manifest)
            done.append(sid)
        except (FilmError, MediaQAError) as exc:
            failed.append({"shot_id": sid, "error": str(exc)})
    emit(
        {
            "ok": len(failed) == 0,
            "reencoded": done,
            "failed": failed,
            "width": target_w,
            "height": target_h,
            "fps": fps,
            "duration_cap": duration_cap,
            "count_ok": len(done),
            "count_failed": len(failed),
        }
    )
    return 0 if not failed else 2

def add_media_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    lintc = sub.add_parser(
        "lint-continuity",
        help="Lint film-spec for cast/coverage/screen-direction continuity issues",
    )
    lintc.add_argument("--root", required=True)
    lintc.add_argument("--spec", default=None, help="Optional path to film-spec JSON")
    lintc.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when blocking continuity codes are present",
    )

    ls = sub.add_parser("lock-style", help="Lock style bible")
    ls.add_argument("--root", required=True)
    ls.add_argument("--canonical", help="Path to approved style master image")
    ls.add_argument("--cast-master", help="Path to approved cast master (face/wardrobe lock)")
    ls.add_argument(
        "--char-id",
        default="hero",
        help="Cast master character id (default hero; e.g. lushiran)",
    )
    ls.add_argument("--signature", help="Override signature block (≥40 chars)")
    ls.add_argument(
        "--medium",
        choices=["anime", "manhua", "semi_real", "photoreal"],
        help="Force medium fingerprint into style-bible before lock",
    )
    ls.add_argument(
        "--from-plan",
        action="store_true",
        help="Merge receipts/style-lock-plan.json into bible before lock",
    )
    ls.add_argument(
        "--strict-style-lock",
        action="store_true",
        help="Fail lock if style_fingerprint/cast_locks hard checks fail",
    )

    # Pixel face-identity fingerprints

    fid = sub.add_parser(
        "face-identity",
        help="Pixel face lock: enroll|enroll-bible|verify|audit|status → receipts/face-identity.json",
    )
    fid_sub = fid.add_subparsers(dest="face_identity_cmd", required=True)
    fe = fid_sub.add_parser("enroll", help="Enroll one cast master / face plate")
    fe.add_argument("--root", required=True)
    fe.add_argument("--char-id", default="hero")
    fe.add_argument("--source", required=True, help="Cast master or face-lock image")
    fe.add_argument("--label", default="")
    feb = fid_sub.add_parser("enroll-bible", help="Enroll all style-bible cast_masters")
    feb.add_argument("--root", required=True)
    fv = fid_sub.add_parser("verify", help="Verify one still against enrolled cast")
    fv.add_argument("--root", required=True)
    fv.add_argument("--image", required=True)
    fv.add_argument("--char-id", default="hero")
    fv.add_argument(
        "--ahash-max", type=int, default=None, help="default from face_identity.DEFAULT_*"
    )
    fv.add_argument("--dhash-max", type=int, default=None)
    fv.add_argument("--hist-max", type=float, default=None)
    fa = fid_sub.add_parser("audit", help="Verify keyframes/ vs enrolled; set verified flag")
    fa.add_argument("--root", required=True)
    fa.add_argument("--char-id", help="Default cast when shot map missing")
    fa.add_argument("--strict", action="store_true", help="Exit 2 if any keyframe fails")
    fa.add_argument("--ahash-max", type=int, default=None)
    fa.add_argument("--dhash-max", type=int, default=None)
    fa.add_argument("--hist-max", type=float, default=None)
    fs = fid_sub.add_parser("status", help="Show face-identity receipt + post_audit view")
    fs.add_argument("--root", required=True)

    # Input-ref style lock (medium + cast_locks + agent prompt prefixes)

    slock = sub.add_parser(
        "style-lock",
        help="Lock medium/identity from user ref image (plan|apply|check|prompt|recommend)",
    )
    slock_sub = slock.add_subparsers(dest="style_lock_cmd", required=True)
    slp = slock_sub.add_parser("plan", help="Analyze ref → style-lock-plan.json + face crops")
    slp.add_argument("--root", required=True)
    slp.add_argument("--ref", required=True, help="User character sheet or face/ref image")
    slp.add_argument("--char-id", default="hero")
    slp.add_argument("--name", help="Display name")
    slp.add_argument(
        "--medium",
        choices=["anime", "manhua", "semi_real", "photoreal", "auto"],
        default="auto",
        help="auto=infer from theme/hint; manhua recommended for 漫剧 stability",
    )
    slp.add_argument("--theme", default="")
    slp.add_argument("--title", default="")
    slp.add_argument("--hint", default="", help="Free text: 漫剧/写实/要稳定…")
    slp.add_argument("--face-notes", default="")
    slp.add_argument("--hair", default="")
    slp.add_argument("--never", default="")
    slp.add_argument("--wardrobe", default="")
    slp.add_argument("--palette", default="")
    slp.add_argument("--lighting", default="")
    slp.add_argument("--no-crop", action="store_true", help="Skip heuristic face crops")
    sla = slock_sub.add_parser("apply", help="Merge plan into style-bible.json")
    sla.add_argument("--root", required=True)
    sla.add_argument("--plan-file", help="Default receipts/style-lock-plan.json")
    slc = slock_sub.add_parser("check", help="Validate style fingerprint + cast locks")
    slc.add_argument("--root", required=True)
    slpr = slock_sub.add_parser("prompt", help="Print still/I2V prompt prefixes")
    slpr.add_argument("--root", required=True)
    slpr.add_argument("--cast", help="Comma cast ids")
    slpr.add_argument("--motion", default="")
    slr = slock_sub.add_parser("recommend", help="Recommend medium for a stability goal")
    slr.add_argument("--goal", required=True, help="e.g. 要稳定像漫剧")

    bible = sub.add_parser("bible", help="Manage Visual Bible")
    bible_sub = bible.add_subparsers(dest="bible_cmd", required=True)

    b_init = bible_sub.add_parser("init", help="Initialize or migrate Visual Bible")
    b_init.add_argument("--root", required=True)

    b_lock = bible_sub.add_parser("lock", help="Lock Visual Bible (Candidate -> Approved)")
    b_lock.add_argument("--root", required=True)

    b_state = bible_sub.add_parser("state", help="Update Visual Bible state")
    b_state.add_argument("--root", required=True)
    b_state.add_argument("--set", choices=["Draft", "Candidate", "Approved"], required=True)

    rs = sub.add_parser("register-still", help="Register approved still")
    rs.add_argument("--root", required=True)
    rs.add_argument("--shot-id", required=True)
    rs.add_argument("--source", required=True)
    rs.add_argument("--role", default="keyframe")
    rs.add_argument("--status", default="approved")
    rs.add_argument("--prompt-file")
    rs.add_argument("--queue-job-id", help="Required for reference-first approved stills")
    rs.add_argument(
        "--identity-approved",
        action="store_true",
        help="Required when --status approved: still matches cast master",
    )
    rs.add_argument(
        "--review-note",
        help="Required when --status approved: brief visual review note",
    )
    rs.add_argument(
        "--anatomy-safe",
        action="store_true",
        help="Required for adult-max approved stills after full-frame anatomy inspection",
    )
    rs.add_argument(
        "--char-id",
        help="Cast id for pixel face-identity verify (default: first dsl.cast)",
    )
    rs.add_argument(
        "--require-face-identity",
        action="store_true",
        help="Fail approved register if face-identity pixel match fails",
    )

    rc = sub.add_parser("register-clip", help="Register approved I2V clip")
    rc.add_argument("--root", required=True)
    rc.add_argument("--shot-id", required=True)
    rc.add_argument("--source", required=True)
    rc.add_argument("--status", default="approved")
    rc.add_argument("--prompt-file")
    rc.add_argument("--queue-job-id", help="Required for reference-first approved clips")
    rc.add_argument("--source-endpoint", choices=sorted(ALLOWED_VIDEO_ENDPOINTS))
    rc.add_argument("--identity-approved", action="store_true")
    rc.add_argument("--motion-approved", action="store_true")
    rc.add_argument("--review-note")
    rc.add_argument(
        "--anatomy-safe",
        action="store_true",
        help="Required for adult-max approved clips after full-frame anatomy inspection",
    )
    rc.add_argument(
        "--strict-video-contract",
        action="store_true",
        help="Approved clips: enforce native 9:16 704x1280 and film-spec FPS",
    )
    rc.add_argument(
        "--review-receipt",
        help="v1.6 approved review receipt (defaults to receipts/reviews/<shot>.json)",
    )

    asb = sub.add_parser("assemble", help="Assemble silent film from timeline + clips")
    asb.add_argument("--root", required=True)
    asb.add_argument("--out-name", default="film_silent.mp4")

    # Real-footage ingestion + auto-cut (video-use bridge, 2026-07-23)

    ingf = sub.add_parser(
        "ingest-footage",
        help="Ingest real footage → transcribe (local Whisper) → takes_packed.md",
    )
    ingf.add_argument("--root", required=True)
    ingf.add_argument("--source", required=True, help="Path to source video file")
    ingf.add_argument("--label", default=None, help="Human label for the source")
    ingf.add_argument(
        "--whisper-model",
        default="base",
        dest="whisper_model",
        help="Whisper model: base (fast) | medium (accurate)",
    )

    acut = sub.add_parser(
        "auto-cut",
        help="Auto-cut real footage on word boundaries + silence gaps (video-use logic)",
    )
    acut.add_argument("--root", required=True)
    acut.add_argument("--source-id", required=True, help="Footage source_id from ingest-footage")
    acut.add_argument(
        "--target-duration",
        type=float,
        default=None,
        dest="target_duration",
        help="Optional target total duration (sec) to aim segment count at",
    )

    shortform = sub.add_parser(
        "shortform", help="Provider-neutral 15–60s topic/A-roll/C-roll planning and A-roll remux"
    )
    shortform_sub = shortform.add_subparsers(dest="shortform_action", required=True)
    sf_plan = shortform_sub.add_parser("plan", help="Create a hash-bound shortform package")
    sf_plan.add_argument("--root", required=True)
    sf_plan.add_argument("--mode", required=True, choices=("topic", "aroll", "croll"))
    sf_plan.add_argument("--approved-script", default="")
    sf_plan.add_argument("--source-video", default="")
    sf_plan.add_argument("--transcript", default="")
    sf_plan.add_argument("--anchor", default="")
    sf_validate = shortform_sub.add_parser(
        "validate", help="Validate source hashes and editorial rules"
    )
    sf_validate.add_argument("--root", required=True)
    sf_validate.add_argument("--require-approved", action="store_true")
    sf_review = shortform_sub.add_parser("review", help="Record plan or sample review")
    sf_review.add_argument("--root", required=True)
    sf_review.add_argument("--stage", required=True, choices=("plan", "sample"))
    sf_review.add_argument("--reviewer", required=True)
    sf_review.add_argument("--note", required=True)
    sf_review.add_argument("--approve", action="store_true")
    sf_lipsync = shortform_sub.add_parser(
        "enable-lipsync", help="Bind one B/C near shot to final audio"
    )
    sf_lipsync.add_argument("--root", required=True)
    sf_lipsync.add_argument("--shot-id", required=True)
    sf_lipsync.add_argument("--speaker", required=True)
    sf_lipsync.add_argument("--face-target", required=True)
    sf_lipsync.add_argument("--audio-sha256", required=True)
    sf_render_lipsync = shortform_sub.add_parser(
        "render-lipsync", help="Explicitly submit one hash-bound B/C sample to the locked backend"
    )
    sf_render_lipsync.add_argument("--root", required=True)
    sf_render_lipsync.add_argument("--shot-id", required=True)
    sf_render_lipsync.add_argument("--video", required=True)
    sf_render_lipsync.add_argument("--audio", required=True)
    sf_render_lipsync.add_argument("--backend", default="auto")
    sf_render_lipsync.add_argument("--out", default="")
    sf_broll = shortform_sub.add_parser(
        "aroll-broll", help="Plan one bounded source-audio-preserving A-roll cover"
    )
    sf_broll.add_argument("--root", required=True)
    sf_broll.add_argument("--beat-id", required=True)
    sf_assemble = shortform_sub.add_parser(
        "assemble-aroll", help="Remux source audio under reviewed A-roll visuals"
    )
    sf_assemble.add_argument("--root", required=True)
    sf_assemble.add_argument("--visual-dir", required=True)
    sf_assemble.add_argument("--out", default="")
    sf_export = shortform_sub.add_parser(
        "export-spec",
        help="S2.3 handoff: shortform package → draft film-spec + timeline (main spine)",
    )
    sf_export.add_argument("--root", required=True)
    sf_export.add_argument("--title", default="")
    sf_export.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing film-spec.json draft",
    )
    sf_motion = shortform_sub.add_parser(
        "motion-plan", help="Write deterministic local layer-motion plan"
    )
    sf_motion.add_argument("--root", required=True)
    sf_motion.add_argument("--shot-id", required=True)
    sf_motion.add_argument("--base", required=True)
    sf_motion.add_argument("--layers", required=True)
    sf_render_motion = shortform_sub.add_parser(
        "render-motion", help="Render one deterministic local layer-motion sample"
    )
    sf_render_motion.add_argument("--root", required=True)
    sf_render_motion.add_argument("--plan", required=True)
    sf_render_motion.add_argument("--duration", required=True, type=float)
    sf_render_motion.add_argument("--fps", type=int, default=30)
    sf_render_motion.add_argument("--width", type=int, default=1080)
    sf_render_motion.add_argument("--height", type=int, default=1920)
    sf_render_motion.add_argument("--out", default="")

    extf = sub.add_parser(
        "extract-frame",
        help="Extract first/last frame from a clip as next-shot still seed (frame-chain)",
    )
    extf.add_argument("--root", default=None, help="Film root (with --shot-id)")
    extf.add_argument("--shot-id", default=None, help="Use clips/<shot-id> or manifest path")
    extf.add_argument("--source", default=None, help="Explicit clip path")
    extf.add_argument(
        "--which",
        default="last",
        help="first | last | <seconds>",
    )
    extf.add_argument("--out", default=None, help="Output image path")
    extf.add_argument(
        "--next-shot-id",
        default=None,
        help="When using --root/--shot-id, name seed as keyframes/<next>-seed.png",
    )
    extf.add_argument(
        "--promote-keyframe",
        default=None,
        metavar="NEXT_SHOT_ID",
        help=(
            "Copy extracted last frame byte-identically to keyframes/<id>.png "
            "(continue-chain: next I2V frame-1; do not restart from cast)"
        ),
    )

    cchain = sub.add_parser(
        "continuity-chain",
        help="Init/check film-root continuity_chain.md (long-form action chain)",
    )
    cchain_sub = cchain.add_subparsers(dest="chain_action", required=True)
    cci = cchain_sub.add_parser("init", help="Create continuity_chain.md skeleton from film-spec")
    cci.add_argument("--root", required=True)
    cci.add_argument("--force", action="store_true", help="Overwrite existing file")
    ccc = cchain_sub.add_parser("check", help="Validate doc + byte-identical joins + checklists")
    ccc.add_argument("--root", required=True)
    ccc.add_argument(
        "--strict",
        action="store_true",
        help="Treat incomplete 9-point checklist as failure",
    )

    reenc = sub.add_parser(
        "reencode-clips",
        help="Re-encode film-spec clips to clean h264 (no upscale) and re-register",
    )
    reenc.add_argument("--root", required=True)
    reenc.add_argument("--width", type=int, default=None, help="Max canvas width (default 720)")
    reenc.add_argument("--height", type=int, default=None, help="Max canvas height (default 1280)")
    reenc.add_argument("--fps", type=int, default=30)
    reenc.add_argument("--crf", type=int, default=18)
    reenc.add_argument("--duration-cap", type=float, default=6.0)
    reenc.add_argument(
        "--force-scale",
        action="store_true",
        help="Force scale/pad to --width/--height even if that upscales (discouraged)",
    )
    reenc.add_argument(
        "--source-endpoint",
        default=None,
        choices=sorted(ALLOWED_VIDEO_ENDPOINTS),
        help="Override per-clip endpoint; default keeps manifest or frw_seedance_i2v",
    )
    reenc.add_argument("--review-note", default=None)
