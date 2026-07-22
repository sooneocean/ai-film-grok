#!/usr/bin/env python3
"""Local control plane for the ai-film-grok pipeline (no Studio required)."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure skill package root is importable before `scripts.*` (shell wrapper does not set PYTHONPATH)
_SKILL_DIR = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (_SKILL_DIR, _SCRIPTS_DIR):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from scripts.prompt_injector import PromptInjector, PromptConflictError
from scripts.visual_bible import load_bible, update_bible_state

from director_review import (
    SCORECARD_DIMENSIONS,
    DirectorReviewError,
    add_reshoot_item,
    build_notes_from_scorecard_failures,
    build_scorecard_from_cli,
    empty_director_notes,
    open_reshoot_items,
    parse_shot_id_list,
    resolve_reshoot_item,
    reshoots_clear,
    scorecard_all_pass,
    scorecard_is_complete_and_passing,
    scorecard_payload,
    validate_scorecard_for_approve,
)
from continuity import lint_continuity, lint_frame_chain
from continuity_chain import (
    check_continuity_chain,
    init_chain_doc,
    is_long_form,
    sha256_file,
    upsert_join,
)
from film_spec import FilmSpecError, validate_film_spec
from media_qa import ALLOWED_VIDEO_ENDPOINTS, MediaQAError, analyze_media, approved_clip_record
from runtime_policy import build_runtime_lock, sha256, verify_requirements_lock, verify_runtime_lock
from security_policy import (
    SecurityPolicyError,
    minimal_subprocess_env,
    reject_symlinks,
    safe_existing_file,
    safe_output_path,
    safe_subdirectory,
    safe_workspace_directory,
    validate_identifier,
)


SCHEMA_VERSION = 1
MANIFEST_NAME = "manifest.json"
DEFAULT_FPS = 30
DEFAULT_WIDTH = 720
DEFAULT_HEIGHT = 1280  # 9:16; overridden by aspect
GATE_ORDER = (
    "brief",
    "style_locked",
    "spec",
    "canonical",
    "stills_complete",
    "clips_complete",
    "assembled",
    "final_complete",
    "desktop_exported",
)
EXPORT_METADATA_FILES = (
    "brief.json",
    "style-bible.json",
    "film-spec.json",
    "timeline.json",
    "manifest.json",
    "README.md",
)


class FilmError(RuntimeError):
    """User-facing workflow error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp = Path(handle.name)
    os.replace(temp, path)


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FilmError(f"Missing JSON: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[\s_/]+", "-", text)
    text = re.sub(r"[^a-z0-9\-\u4e00-\u9fff]+", "", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "film"


def aspect_dims(aspect: str) -> tuple[int, int]:
    table = {
        "9:16": (720, 1280),
        "16:9": (1280, 720),
        "1:1": (1024, 1024),
        "3:4": (768, 1024),
        "4:3": (1024, 768),
    }
    if aspect not in table:
        raise FilmError(f"Unsupported aspect {aspect!r}; use one of {sorted(table)}")
    return table[aspect]


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=check,
        capture_output=True,
        text=True,
        env=minimal_subprocess_env(),
    )


def media_duration(path: Path) -> float:
    """Fail-loud duration probe (shared with final/compose — no silent defaults)."""
    try:
        from media_duration import MediaDurationError, probe_duration_sec
    except ImportError:
        p = Path(path)
        if not p.is_file():
            raise FilmError(f"media missing for duration probe: {p}") from None
        result = run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nokey=1:noprint_wrappers=1",
                str(path),
            ]
        )
        raw = (result.stdout or "").strip()
        if not raw:
            raise FilmError(f"unreadable duration (empty ffprobe): {path}") from None
        return float(raw)
    try:
        return probe_duration_sec(path, label="aifilm")
    except MediaDurationError as exc:
        raise FilmError(str(exc)) from exc


def emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def grok_permission_mode(config_path: Path) -> str | None:
    if not config_path.is_file():
        return None
    try:
        import tomllib

        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return "unreadable"
    for section in (config, config.get("ui") or {}, config.get("cli") or {}):
        if isinstance(section, dict) and isinstance(section.get("permission_mode"), str):
            return section["permission_mode"]
    return None


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def film_output_path(root: Path, name: str, *, field: str = "output name") -> Path:
    try:
        out_dir = safe_workspace_directory(root, "out", field="film output directory")
        return safe_output_path(out_dir, name, suffixes={".mp4"}, field=field)
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc


def valid_shot_id(value: str) -> str:
    try:
        return validate_identifier(value, field="shot id")
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc


def record_file_matches(root: Path, record: object, *, field: str) -> bool:
    if not isinstance(record, dict) or not isinstance(record.get("path"), str):
        return False
    try:
        path = safe_existing_file(root, record["path"], field=field)
    except SecurityPolicyError:
        return False
    expected = record.get("sha256")
    return isinstance(expected, str) and bool(expected) and sha256(path) == expected


def film_dirs(root: Path) -> dict[str, Path]:
    dirs = {"root": root}
    try:
        for name in ("prompts", "canonical", "keyframes", "clips", "audio", "out", "receipts"):
            dirs[name] = safe_workspace_directory(root, name, field=f"film {name} directory")
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc
    return dirs


def ensure_tree(root: Path) -> None:
    for path in film_dirs(root).values():
        path.mkdir(parents=True, exist_ok=True)


def empty_manifest(*, title: str, theme: str, aspect: str) -> dict[str, Any]:
    w, h = aspect_dims(aspect)
    return {
        "schema_version": SCHEMA_VERSION,
        "provider_default": "grok-imagine",
        "title": title,
        "theme": theme,
        "aspect_ratio": aspect,
        "width": w,
        "height": h,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "style_locked": False,
        "stills": {},
        "clips": {},
        "gates": {name: name == "brief" for name in GATE_ORDER},
        "outputs": {},
        "notes": [
            "Default motion is Grok image_to_video (frame-1 start), not first/last-frame.",
            "Use image_edit + cast master for recurring characters.",
        ],
    }


def load_manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST_NAME
    if not path.is_file():
        raise FilmError(f"No manifest at {path}; run init first")
    return read_json(path)


DIRECTOR_NOTES_NAME = "director_notes.json"


def director_notes_path(root: Path) -> Path:
    return root / DIRECTOR_NOTES_NAME


def load_director_notes(root: Path) -> dict[str, Any]:
    path = director_notes_path(root)
    if not path.is_file():
        return empty_director_notes()
    data = read_json(path)
    if not isinstance(data, dict):
        return empty_director_notes()
    return data


def save_director_notes(root: Path, notes: dict[str, Any]) -> Path:
    path = director_notes_path(root)
    write_json(path, notes)
    return path


def save_manifest(root: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = utc_now()
    write_json(root / MANIFEST_NAME, manifest)


def cmd_doctor(args: argparse.Namespace) -> int:
    skill_dir = Path(__file__).resolve().parents[1]
    edge_ok = False
    edge_err = None
    try:
        import edge_tts  # noqa: F401

        edge_ok = True
    except Exception as exc:  # pragma: no cover
        edge_err = str(exc)
    numpy_ok = False
    try:
        import numpy  # noqa: F401

        numpy_ok = True
    except Exception:
        pass
    pil_ok = False
    try:
        from PIL import Image  # noqa: F401

        pil_ok = True
    except Exception:
        pass
    tts_info: dict[str, Any] = {}
    lipsync_info: dict[str, Any] = {}
    try:
        sys.path.insert(0, str(skill_dir / "scripts"))
        from tts_backend import probe as tts_probe  # type: ignore

        tts_info = tts_probe()
    except Exception as exc:
        tts_info = {"ok": False, "error": str(exc)}
    try:
        from lipsync_backend import probe as lipsync_probe  # type: ignore

        lipsync_info = lipsync_probe()
    except Exception as exc:
        lipsync_info = {"ok": False, "error": str(exc)}
    requirements = verify_requirements_lock(skill_dir / "requirements.lock")
    runtime = verify_runtime_lock(skill_dir, skill_dir / "runtime-lock.json")
    schema_ok = False
    schema_error = None
    try:
        import jsonschema

        schema = read_json(skill_dir / "schemas" / "film-spec.schema.json")
        example = read_json(skill_dir / "templates" / "film-spec.example.json")
        jsonschema.validate(example, schema)
        schema_ok = True
    except Exception as exc:
        schema_error = str(exc)
    config_env = skill_dir / "config.env"
    config_env_mode = stat.S_IMODE(config_env.stat().st_mode) if config_env.is_file() else None
    grok_config = Path.home() / ".grok" / "config.toml"
    permission_mode = grok_permission_mode(grok_config)
    grok_log = Path.home() / ".grok" / "logs" / "unified.jsonl"
    log_mode = stat.S_IMODE(grok_log.stat().st_mode) if grok_log.is_file() else None
    warnings: list[str] = []
    if permission_mode == "always-approve":
        warnings.append("Global Grok permission_mode is always-approve; change requires explicit user approval")
    if log_mode is not None and log_mode & 0o077:
        warnings.append(f"Grok unified log is readable beyond the owner (mode {oct(log_mode)})")
    if config_env_mode is not None and config_env_mode & 0o077:
        warnings.append(f"skill config.env must be owner-only (mode {oct(config_env_mode)})")
    requested_lipsync = str(lipsync_info.get("env_backend") or "auto")
    lipsync_required_ok = requested_lipsync in {"off", "auto"} or bool(
        (lipsync_info.get("backends") or {}).get(requested_lipsync)
    )
    report = {
        "ok": True,
        "skill_dir": str(skill_dir),
        "skill_md": (skill_dir / "SKILL.md").is_file(),
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "python": sys.executable,
        "edge_tts": edge_ok,
        "edge_tts_error": edge_err,
        "tts": tts_info,
        "lipsync": lipsync_info,
        "numpy": numpy_ok,
        "pillow": pil_ok,
        "requirements_lock": requirements,
        "runtime_lock": runtime,
        "film_spec_schema": {"ok": schema_ok, "error": schema_error},
        "security_posture": {
            "config_env_mode": oct(config_env_mode) if config_env_mode is not None else None,
            "global_permission_mode": permission_mode,
            "grok_log_mode": oct(log_mode) if log_mode is not None else None,
            "warnings": warnings,
        },
        "render_final": (skill_dir / "scripts" / "render_final.py").is_file(),
        "export_composition": (skill_dir / "scripts" / "export_composition.py").is_file(),
        "compose_render": (skill_dir / "scripts" / "compose_render.py").is_file(),
        "pilot_review": (skill_dir / "scripts" / "pilot_review.py").is_file(),
        "compose_preview": (skill_dir / "scripts" / "compose_preview.py").is_file(),
        "next_actions": (skill_dir / "scripts" / "next_actions.py").is_file(),
        "preflight": (skill_dir / "scripts" / "preflight.py").is_file(),
        "npx": shutil.which("npx"),
        "lipsync_backend": (skill_dir / "scripts" / "lipsync_backend.py").is_file(),
        "tts_backend": (skill_dir / "scripts" / "tts_backend.py").is_file(),
        "provider_default": "grok-imagine",
        "tools": {
            "still_generate": "image_gen (agent tool)",
            "still_edit": "image_edit (agent tool)",
            "motion": "image_to_video (agent tool)",
            "motion_multi_ref": "reference_to_video (agent tool)",
            "vo": "MiniMax/Fish/edge or structured AIFILM_TTS_ARGV (cross-provider fallback is opt-in)",
            "lipsync": "locked MuseTalk/Wav2Lip or structured AIFILM_LIPSYNC_ARGV (optional post)",
            "bgm": "numpy procedural R&B (default) or user music file",
            "post": "render_final.py (FFmpeg + PIL subs + optional lipsync)",
            "post_designed": (
                "export-compose + compose-render (HyperFrames E2E; "
                "Remotion auto-render when node_modules ready else next_steps)"
            ),
            "post_engines": ["ffmpeg", "hyperframes", "remotion"],
        },
        "limits": {
            "motion_first_last": False,
            "video_duration_sec": [6, 10],
            "note": "For human-like VO pin a stable provider voice; cross-provider fallback is opt-in.",
        },
    }
    # Designed-post readiness (does not fail default doctor — HF is optional)
    designed: dict[str, Any] = {"ok": False, "required_for": "final --post-engine hyperframes"}
    try:
        sys.path.insert(0, str(skill_dir / "scripts"))
        from compose_render import probe_designed_post_tooling, probe_remotion_readiness

        designed = {**probe_designed_post_tooling(), "required_for": "final --post-engine hyperframes"}
        designed["ok"] = bool(designed.get("npx") and designed.get("hyperframes_ok"))
        # Soft remotion readiness when a package was exported under CWD film roots — probe empty ok
        designed["remotion"] = {
            "note": "Per-film: compose-render --engine remotion after export; needs npm install",
            "probe_fn": "probe_remotion_readiness(film_root)",
        }
        _ = probe_remotion_readiness  # keep import for doctor consumers
    except Exception as exc:  # pragma: no cover — defensive
        designed["error"] = str(exc)[:200]
    # Soft notice only — missing HyperFrames must not fail ffmpeg-only production or --strict
    if not designed.get("ok"):
        designed["soft_warning"] = (
            "designed-post not ready: "
            + str(designed.get("error") or "npx/hyperframes unavailable")
            + " — ffmpeg final still works"
        )
    report["designed_post"] = designed

    # Grok OAuth (session token from grok login) — soft probe, does not fail doctor by default
    grok_oauth: dict[str, Any] = {"ok": False}
    try:
        from grok_oauth import probe as grok_oauth_probe

        grok_oauth = grok_oauth_probe()
    except Exception as exc:  # pragma: no cover
        grok_oauth = {"ok": False, "error": str(exc)[:200]}
    report["grok_oauth"] = {
        "ok": bool(grok_oauth.get("ok")),
        "source": grok_oauth.get("source"),
        "auth_mode": grok_oauth.get("auth_mode"),
        "ttl_sec": grok_oauth.get("ttl_sec"),
        "has_imagine_image": grok_oauth.get("has_imagine_image"),
        "has_imagine_video": grok_oauth.get("has_imagine_video"),
        "error": grok_oauth.get("error"),
        "hint": grok_oauth.get("hint") or "grok login",
    }
    if not grok_oauth.get("ok"):
        warnings.append("Grok OAuth not ready (optional for API batch; in-session Imagine tools still work if logged in)")

    if not report["ffmpeg"] or not report["ffprobe"]:
        report["ok"] = False
        report["error"] = "ffmpeg/ffprobe not found on PATH"
    elif not edge_ok or not numpy_ok or not pil_ok:
        report["ok"] = False
        report["error"] = "Formal final requires edge-tts + numpy + pillow (pip install --user edge-tts numpy pillow)"
    elif (
        not tts_info.get("ok")
        or not requirements["ok"]
        or not runtime["ok"]
        or not schema_ok
        or not lipsync_required_ok
    ):
        report["ok"] = False
        report["error"] = "Runtime/schema/backend verification failed; inspect nested doctor reports"
    report["strict_ok"] = bool(report["ok"] and not warnings)
    emit(report)
    return 0 if (report["strict_ok"] if getattr(args, "strict", False) else report["ok"]) else 1


def cmd_lock_runtime(_: argparse.Namespace) -> int:
    skill_dir = Path(__file__).resolve().parents[1]
    lock_path = skill_dir / "runtime-lock.json"
    write_json(lock_path, build_runtime_lock(skill_dir))
    result = verify_runtime_lock(skill_dir, lock_path)
    emit({"ok": result["ok"], "runtime_lock": str(lock_path), "verification": result})
    return 0 if result["ok"] else 2


def _infer_medium_from_theme(theme: str, title: str) -> tuple[str, str, str]:
    """Return (medium, rendering, signature_hint) from theme/title keywords."""
    blob = f"{theme} {title}".lower()
    anime_keys = (
        "anime",
        "doujin",
        "manga",
        "漫剧",
        "同人",
        "里番",
        "二次元",
        "anime",
        "cel",
    )
    if any(k in blob for k in anime_keys):
        medium = "high-quality anime illustration"
        rendering = "clean anime linework, soft cel shading, stable character sheets"
        sig = (
            f"Vertical consistent high-quality anime short for '{title}', "
            "clean linework, coherent palette, stable cast identity and wardrobe across shots."
        )
        return medium, rendering, sig
    medium = "photoreal cinematic short"
    rendering = "photoreal, detailed skin/fabric; switch to anime only if theme requires"
    sig = (
        f"Consistent film style for '{title}': photoreal cinematic short, "
        "natural skin texture, coherent palette, stable wardrobe and identity across shots."
    )
    return medium, rendering, sig


def cmd_init(args: argparse.Namespace) -> int:
    title = args.title.strip()
    theme = args.theme.strip()
    aspect = args.aspect
    root = Path(args.root).expanduser().resolve()
    if root.exists() and any(root.iterdir()) and not args.force:
        raise FilmError(f"Root not empty: {root} (pass --force to reuse)")
    ensure_tree(root)
    (root / "canonical" / "cast").mkdir(parents=True, exist_ok=True)
    (root / "canonical" / "lookbook").mkdir(parents=True, exist_ok=True)
    w, h = aspect_dims(aspect)
    brief = {
        "title": title,
        "theme": theme,
        "aspect_ratio": aspect,
        "width": w,
        "height": h,
        "created_at": utc_now(),
        "provider": "grok-imagine",
    }
    medium, rendering, sig = _infer_medium_from_theme(theme, title)
    style = {
        "schema_version": 1,
        "locked": False,
        "title": title,
        "medium": medium,
        "palette": "to be filled from theme",
        "lighting": "motivated practicals, natural contrast",
        "lens": "contemporary digital cinema, modest depth of field",
        "rendering": rendering,
        "signature_block": sig,
        "identity_lock": "to be filled: face hair eyes wardrobe for each recurring adult cast member",
        "negative_hints": (
            "do not change face identity, do not switch medium mid-film, "
            "no underage characters, no random outfit recolor"
        ),
        "canonical_style_path": None,
        "cast_masters": {},
        "updated_at": utc_now(),
    }
    film_spec = {
        "title": title,
        "description": theme,
        "aspect_ratio": aspect,
        "scenes": [],
    }
    timeline = {
        "schema_version": 1,
        "fps": DEFAULT_FPS,
        "width": w,
        "height": h,
        "shots": [],
    }
    write_json(root / "brief.json", brief)
    write_json(root / "style-bible.json", style)
    write_json(root / "film-spec.json", film_spec)
    write_json(root / "timeline.json", timeline)
    manifest = empty_manifest(title=title, theme=theme, aspect=aspect)
    manifest["review_contract_version"] = 2
    save_manifest(root, manifest)
    (root / "README.md").write_text(
        f"# {title}\n\nTheme: {theme}\n\nProvider: Grok Imagine\nRoot: `{root}`\n",
        encoding="utf-8",
    )
    emit({"ok": True, "root": str(root), "title": title, "aspect_ratio": aspect, "width": w, "height": h})
    return 0


def recompute_gates(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    style = read_json(root / "style-bible.json") if (root / "style-bible.json").is_file() else {}
    spec = read_json(root / "film-spec.json") if (root / "film-spec.json").is_file() else {}
    spec_error = None
    try:
        shots = validate_film_spec(spec, assign_missing_ids=False)
    except FilmSpecError as exc:
        shots = []
        spec_error = str(exc)
    shot_ids = [shot["id"] for shot in shots]
    dirs = film_dirs(root)
    stills = manifest.get("stills") or {}
    clips = manifest.get("clips") or {}
    approved_stills = [
        sid
        for sid, record in stills.items()
        if isinstance(record, dict)
        and record.get("status") == "approved"
        and record_file_matches(dirs["keyframes"], record, field=f"still path for {sid}")
    ]
    review_contract = int(manifest.get("review_contract_version") or 1)
    approved_clips = [
        sid
        for sid, record in clips.items()
        if approved_clip_record(record)
        and (review_contract < 2 or isinstance(record.get("shot_review"), dict))
        and record_file_matches(dirs["clips"], record, field=f"clip path for {sid}")
    ]
    canonical = [path for path in dirs["canonical"].glob("*") if path.is_file() and not path.is_symlink()]
    out_mp4 = [path for path in dirs["out"].glob("*.mp4") if path.is_file() and not path.is_symlink()]
    outputs = manifest.get("outputs") or {}
    silent_record = outputs.get("silent_film")
    silent_qa = silent_record.get("technical_qa") if isinstance(silent_record, dict) else None
    assembled = bool(
        record_file_matches(dirs["out"], silent_record, field="silent film path")
        and isinstance(silent_qa, dict)
        and silent_qa.get("ok") is True
        and silent_qa.get("motion_ok") is True
    )
    final_record = outputs.get("final_film")
    final_qa = final_record.get("technical_qa") if isinstance(final_record, dict) else None
    final_file_ok = record_file_matches(dirs["out"], final_record, field="final film path")
    final_technical_ok = bool(
        final_file_ok
        and isinstance(final_qa, dict)
        and final_qa.get("ok") is True
        and final_qa.get("decode_ok") is True
        and final_qa.get("motion_ok") is True
        and final_qa.get("has_audio") is True
    )
    review = outputs.get("final_review")
    screening_evidence = review.get("screening_evidence") if isinstance(review, dict) else {}
    screening_evidence_ok = review_contract < 2 or (
        isinstance(screening_evidence, dict)
        and set(screening_evidence) == set(SCORECARD_DIMENSIONS)
    )
    review_ok = bool(
        isinstance(review, dict)
        and review.get("approved") is True
        and isinstance(final_record, dict)
        and review.get("output_sha256") == final_record.get("sha256")
        and isinstance(review.get("reviewer"), str)
        and review["reviewer"].strip()
        and isinstance(review.get("notes"), str)
        and review["notes"].strip()
        and isinstance(review.get("technical_qa"), dict)
        and review["technical_qa"].get("ok") is True
        and scorecard_is_complete_and_passing(review)
        and screening_evidence_ok
    )
    dnotes = load_director_notes(root)
    open_items = open_reshoot_items(dnotes)
    clips_complete = bool(shot_ids) and all(sid in approved_clips for sid in shot_ids)
    gates = {
        "brief": (root / "brief.json").is_file(),
        "style_locked": bool(style.get("locked")),
        "spec": bool(shots) and spec_error is None,
        "canonical": len(canonical) > 0,
        "stills_complete": bool(shot_ids) and all(sid in approved_stills for sid in shot_ids),
        "clips_complete": clips_complete,
        "assembled": assembled,
        "reshoots_clear": reshoots_clear(dnotes),
        "final_complete": bool(clips_complete and final_technical_ok and review_ok and reshoots_clear(dnotes)),
        "desktop_exported": bool(outputs.get("desktop_dir") and Path(outputs["desktop_dir"]).is_dir()),
    }
    manifest["gates"] = gates
    manifest["style_locked"] = gates["style_locked"]
    return {
        "shot_ids": shot_ids,
        "approved_stills": approved_stills,
        "approved_clips": approved_clips,
        "canonical_count": len(canonical),
        "outputs": [str(p) for p in out_mp4],
        "spec_error": spec_error,
        "final_technical_ok": final_technical_ok,
        "final_review_ok": review_ok,
        "open_reshoots": open_items,
        "open_reshoot_count": len(open_items),
        "director_notes_path": str(director_notes_path(root))
        if director_notes_path(root).is_file()
        else None,
        "gates": gates,
    }


def _pipeline_bundle(
    root: Path,
    *,
    gates: dict[str, Any],
    open_n: int = 0,
    persist: bool = True,
) -> tuple[list[dict[str, str]], dict[str, Any], str | None, str | None]:
    """Build next_actions + pipeline_stage; optionally persist sidecar for HUD."""
    from next_actions import (
        build_next_actions,
        detect_pipeline_stage,
        persist_pipeline_stage,
    )

    actions = build_next_actions(root, gates=gates, open_reshoot_count=open_n)
    pipeline = detect_pipeline_stage(root, gates=gates, open_reshoot_count=open_n)
    next_cmd = actions[0]["cmd"] if actions else None
    next_id = actions[0].get("id") if actions else None
    if persist:
        try:
            persist_pipeline_stage(
                root,
                pipeline,
                next_cmd=next_cmd,
                next_id=next_id,
            )
        except OSError:
            pass
    return actions, pipeline, next_cmd, next_id


def cmd_next(args: argparse.Namespace) -> int:
    """Print the single next recommended production command (lesson routing)."""
    root = Path(args.root).expanduser().resolve()
    manifest = load_manifest(root) if (root / MANIFEST_NAME).is_file() else {}
    summary = recompute_gates(root, manifest) if manifest else {"gates": {}, "open_reshoot_count": 0}
    if manifest:
        save_manifest(root, manifest)
    gates = summary.get("gates") or {}
    open_n = int(summary.get("open_reshoot_count") or 0)
    try:
        actions, pipeline, next_cmd, next_id = _pipeline_bundle(
            root, gates=gates, open_n=open_n, persist=True
        )
    except Exception as exc:
        raise FilmError(f"next_actions failed: {exc}") from exc

    print_stage = bool(getattr(args, "print_stage", False))
    print_stage_only = bool(getattr(args, "print_stage_only", False))
    print_cmd_only = bool(getattr(args, "print_cmd_only", False))

    if print_stage_only:
        from next_actions import format_stage_line

        print(format_stage_line(pipeline, compact=True))
        return 0

    if getattr(args, "all", False):
        emit(
            {
                "ok": True,
                "root": str(root),
                "pipeline_stage": pipeline,
                "stage": pipeline.get("stage"),
                "stage_label": pipeline.get("label_zh"),
                "next_actions": actions,
            }
        )
        return 0
    if not actions:
        if print_stage:
            from next_actions import format_stage_line

            print(format_stage_line(pipeline, compact=True), file=sys.stderr)
        emit(
            {
                "ok": True,
                "root": str(root),
                "pipeline_stage": pipeline,
                "stage": pipeline.get("stage"),
                "stage_label": pipeline.get("label_zh"),
                "next_cmd": None,
                "message": "no next action",
            }
        )
        return 0
    cmd = next_cmd or actions[0]["cmd"]
    if print_cmd_only and print_stage:
        # shell-friendly: stage on stderr, cmd on stdout
        from next_actions import format_stage_line

        print(format_stage_line(pipeline, compact=True), file=sys.stderr)
        print(cmd)
        return 0
    if print_cmd_only:
        print(cmd)
        return 0
    if print_stage:
        from next_actions import format_stage_line

        # human mode: one-line stage then full JSON (stage also in payload)
        print(format_stage_line(pipeline, compact=False), file=sys.stderr)
    emit(
        {
            "ok": True,
            "root": str(root),
            "pipeline_stage": pipeline,
            "stage": pipeline.get("stage"),
            "stage_label": pipeline.get("label_zh"),
            "next_cmd": cmd,
            "why": actions[0].get("why"),
            "id": next_id or actions[0].get("id"),
            "next_actions": actions,
        }
    )
    return 0


def cmd_stage(args: argparse.Namespace) -> int:
    """Print / refresh current pipeline stage (product spine layer)."""
    root = Path(args.root).expanduser().resolve()
    manifest = load_manifest(root) if (root / MANIFEST_NAME).is_file() else {}
    summary = recompute_gates(root, manifest) if manifest else {"gates": {}, "open_reshoot_count": 0}
    if manifest:
        save_manifest(root, manifest)
    gates = summary.get("gates") or {}
    open_n = int(summary.get("open_reshoot_count") or 0)
    try:
        actions, pipeline, next_cmd, next_id = _pipeline_bundle(
            root, gates=gates, open_n=open_n, persist=not bool(getattr(args, "no_persist", False))
        )
    except Exception as exc:
        raise FilmError(f"stage detect failed: {exc}") from exc
    from next_actions import format_stage_line

    line = format_stage_line(pipeline, compact=not bool(getattr(args, "full", False)))
    if getattr(args, "json", False) or getattr(args, "as_json", False):
        emit(
            {
                "ok": True,
                "root": str(root),
                "pipeline_stage": pipeline,
                "stage": pipeline.get("stage"),
                "stage_label": pipeline.get("label_zh"),
                "line": line,
                "next_cmd": next_cmd,
                "next_id": next_id,
                "next_actions": actions[:3] if actions else [],
            }
        )
        return 0
    if getattr(args, "full", False):
        print(line)
        if next_cmd:
            print(f"next: {next_cmd}")
        return 0
    print(line)
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    """Lesson-based hard/soft gate check before bulk or final."""
    skill_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from preflight import PreflightError, run_preflight
    except ImportError as exc:
        raise FilmError(f"Cannot import preflight: {exc}") from exc
    root = Path(args.root).expanduser().resolve()
    try:
        report = run_preflight(root)
    except PreflightError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    if not report.get("hard_ok"):
        return 2
    if getattr(args, "strict", False) and not report.get("soft_ok"):
        return 3
    return 0


def cmd_state_index(args: argparse.Namespace) -> int:
    """Checkpoint: state photos + keyframes + promote plan for fluid transitions."""
    skill_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from state_index_gate import run_state_index_check, write_state_index_receipt
    except ImportError as exc:
        raise FilmError(f"Cannot import state_index_gate: {exc}") from exc
    root = Path(args.root).expanduser().resolve()
    report = run_state_index_check(root)
    path = write_state_index_receipt(root, report)
    report["receipt_path"] = str(path)
    action = getattr(args, "state_index_action", None) or "check"
    if action == "plan":
        # plan = full report + human-readable generate_plan first
        plan_view = {
            "ok": report.get("ok"),
            "kind": "state-index-plan",
            "purpose": report.get("purpose"),
            "generate_plan": report.get("generate_plan") or [],
            "agent_do": report.get("agent_do") or [],
            "hard": report.get("hard") or [],
            "soft": report.get("soft") or [],
            "fluency_issues": report.get("fluency_issues") or [],
            "undress_anchor": report.get("undress_anchor"),
            "missing_state_photos": report.get("missing_state_photos"),
            "missing_keyframes": report.get("missing_keyframes"),
            "receipt_path": str(path),
            "ref": report.get("ref"),
            "note": (
                "Execute generate_plan in order, then re-run: "
                f'aifilm state-index check --root "{root}"'
            ),
        }
        emit(plan_view)
    else:
        emit(report)
    if not report.get("ok"):
        return 2
    if getattr(args, "strict", False) and (report.get("generate_plan") or report.get("soft")):
        return 3
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    manifest = load_manifest(root)
    summary = recompute_gates(root, manifest)
    save_manifest(root, manifest)
    next_gate = None
    for name in GATE_ORDER:
        if not summary["gates"].get(name):
            next_gate = name
            break
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    final_rec = outputs.get("final_film") if isinstance(outputs.get("final_film"), dict) else {}
    compose_pkg = root / "compose" / "package.json"
    compose_hf = root / "compose" / "hyperframes" / "index.html"
    compose_preview_meta = root / "compose" / "preview.json"
    pilot_path = root / "receipts" / "pilot-approval.json"
    pilot_score_path = root / "receipts" / "pilot-scorecard.json"
    pilot_data = read_json(pilot_path) if pilot_path.is_file() else {}
    try:
        from production_gates import pilot_is_user_approved as _pilot_ok
        pilot_ok = _pilot_ok(pilot_data) if pilot_data else False
    except Exception:
        pilot_ok = False
    gates = summary.get("gates") or {}
    open_n = int(summary.get("open_reshoot_count") or 0)
    try:
        next_actions, pipeline_stage, next_cmd, _next_id = _pipeline_bundle(
            root, gates=gates, open_n=open_n, persist=True
        )
    except Exception:
        next_actions = []
        pipeline_stage = {"stage": "unknown", "label_zh": "未知", "error": "detect_failed"}
        next_cmd = None
    emit(
        {
            "ok": True,
            "root": str(root),
            "title": manifest.get("title"),
            "provider_default": manifest.get("provider_default"),
            "pipeline_stage": pipeline_stage,
            "stage": pipeline_stage.get("stage") if isinstance(pipeline_stage, dict) else None,
            "stage_label": pipeline_stage.get("label_zh") if isinstance(pipeline_stage, dict) else None,
            "next_gate": next_gate,
            "next_actions": next_actions,
            "next_cmd": next_cmd or (next_actions[0]["cmd"] if next_actions else None),
            "post_engine": final_rec.get("post_engine") or "none",
            "final_film": {
                "path": final_rec.get("path"),
                "sha256": (final_rec.get("sha256") or "")[:16] or None,
                "duration_sec": final_rec.get("duration_sec"),
                "post_engine": final_rec.get("post_engine"),
            }
            if final_rec
            else None,
            "pilot": {
                "user_approved": pilot_ok,
                "approval_present": pilot_path.is_file(),
                "scorecard_present": pilot_score_path.is_file(),
            },
            "audio": _status_audio_summary(root),
            "inventory": _status_inventory(root, summary),
            "evidence": _status_evidence(root),
            "compose": {
                "export_present": compose_pkg.is_file(),
                "hyperframes_index": compose_hf.is_file(),
                "remotion_package": (root / "compose" / "remotion" / "package.json").is_file(),
                "remotion": _status_remotion_probe(root),
                "preview_meta": str(compose_preview_meta) if compose_preview_meta.is_file() else None,
                "preview_receipt": str(root / "receipts" / "compose-preview.json")
                if (root / "receipts" / "compose-preview.json").is_file()
                else None,
                "export_meta": outputs.get("compose_export"),
            },
            **summary,
            "manifest": str(root / MANIFEST_NAME),
        }
    )
    return 0


def _status_inventory(root: Path, summary: dict[str, Any]) -> dict[str, Any]:
    """Shot inventory consistency for status (fail-closed signal, not silent partial)."""
    try:
        from shot_inventory import check_shot_inventory, discover_vo_stem_ids

        shot_ids = summary.get("shot_ids") or []
        approved = summary.get("approved_clips") or []
        vo_ids = discover_vo_stem_ids(root)
        report = check_shot_inventory(
            shot_ids,
            approved,
            vo_stem_ids=vo_ids if vo_ids else None,
            require_vo=bool(vo_ids),
        )
        return report
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _status_evidence(root: Path) -> dict[str, Any]:
    """intent vs executed vs human_review — plan cannot impersonate delivery."""
    try:
        from evidence_status import classify_evidence

        return classify_evidence(root)
    except Exception as exc:
        return {"error": str(exc)[:200]}


def _status_audio_summary(root: Path) -> dict[str, Any]:
    """Phase F: surface TTS / sound_plan / mix_report for agent routing."""
    out: dict[str, Any] = {
        "tts_backend": None,
        "vo_voice": None,
        "sound_plan_mood": None,
        "auto_sfx": None,
        "sidechain": None,
        "mix_report": None,
        "loudness": None,
    }
    spec_path = root / "film-spec.json"
    if spec_path.is_file():
        try:
            spec = read_json(spec_path)
            out["tts_backend"] = spec.get("tts_backend")
            out["vo_voice"] = spec.get("vo_voice")
            sp = spec.get("sound_plan") if isinstance(spec.get("sound_plan"), dict) else {}
            out["sound_plan_mood"] = sp.get("mood")
            out["auto_sfx"] = sp.get("auto_sfx")
            out["sidechain"] = sp.get("sidechain")
            if spec.get("_tts_notes"):
                out["tts_notes"] = spec.get("_tts_notes")
        except Exception as exc:
            out["spec_error"] = str(exc)[:160]
    mix_path = root / "audio" / "mix_report.json"
    if mix_path.is_file():
        try:
            mix = read_json(mix_path)
            out["mix_report"] = str(mix_path)
            out["sfx_overlay_count"] = mix.get("sfx_overlay_count")
            out["sidechain_applied"] = mix.get("sidechain_applied")
            if isinstance(mix.get("sidechain"), dict):
                out["sidechain"] = mix.get("sidechain")
            out["loudness"] = mix.get("loudness")
            out["loudness_before"] = mix.get("loudness_before")
            out["loudnorm_applied"] = mix.get("loudnorm_applied")
            out["loudnorm_decision"] = mix.get("loudnorm_decision")
            out["loudnorm_policy"] = mix.get("loudnorm_policy")
            out["bed_source"] = mix.get("bed_source")
            out["music_template"] = mix.get("music_template")
        except Exception as exc:
            out["mix_error"] = str(exc)[:160]
    # Also surface whether a local template file exists (pre-final)
    try:
        from sound_plan import resolve_music_template

        mt = resolve_music_template(
            root,
            mood=out.get("sound_plan_mood") or "rnb",
            plan=None,
            music_arg=None,
            mode="auto",
        )
        out["local_music_available"] = bool(mt)
        if mt:
            out["local_music_path"] = mt.get("relative") or mt.get("path")
    except Exception:
        out["local_music_available"] = False
    return out


def _status_remotion_probe(root: Path) -> dict[str, Any]:
    """Best-effort remotion readiness for status JSON (never raises)."""
    try:
        from compose_render import probe_remotion_readiness

        info = probe_remotion_readiness(root)
        return {
            "ready": bool(info.get("ready")),
            "missing": info.get("missing") or [],
            "package_json": bool(info.get("package_json")),
            "node_modules": bool(info.get("node_modules")),
        }
    except Exception as exc:
        return {"ready": False, "error": str(exc)[:200]}


def cmd_write_spec(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    ensure_tree(root)
    try:
        from narrative_control import assert_projection_ready, NarrativeControlError

        assert_projection_ready(root, require_locked=True)
    except NarrativeControlError as exc:
        raise FilmError(f"{exc.code}: {exc}") from exc
    default_spec = root / "film-spec.json"
    if args.spec:
        spec_path = Path(args.spec).expanduser().resolve()
    else:
        spec_path = default_spec
    spec = read_json(spec_path)
    try:
        shots = validate_film_spec(spec, assign_missing_ids=True, film_root=root)
    except FilmSpecError as exc:
        raise FilmError(str(exc)) from exc

    # --- New Visual Bible Prompt Injector Logic ---
    bible = load_bible(root)
    injector = PromptInjector(bible)
    conflict_errors = []
    for shot in shots:
        try:
            injector.assemble(shot, root)
        except PromptConflictError as e:
            conflict_errors.append(str(e))

    if conflict_errors:
        err_msg = "Prompt conflicts detected:\n- " + "\n- ".join(conflict_errors)
        raise FilmError(err_msg)

    # Wardrobe State Linting (shot-level continuity write-back preferred)
    wardrobe_variants = bible.get("wardrobe_variants", {})
    wardrobe_errors = []
    for shot in shots:
        w_state = shot.get("wardrobe_state") or (shot.get("dsl") or {}).get(
            "wardrobe_state"
        )
        if w_state and w_state != "default":
            heroines = shot.get("heroine_ids", ["hero"])
            # also honor dsl.cast when heroine_ids default
            cast = (shot.get("dsl") or {}).get("cast")
            if isinstance(cast, list) and cast and heroines == ["hero"]:
                heroines = [str(c) for c in cast if c]
            for h in heroines:
                variants = wardrobe_variants.get(h) or wardrobe_variants.get("hero") or {}
                if w_state not in variants:
                    wardrobe_errors.append(
                        f"Shot {shot.get('id', '?')} requests wardrobe '{w_state}' for '{h}', "
                        f"but it is not defined in the Visual Bible."
                    )

    if wardrobe_errors:
        err_msg = "Wardrobe Linting Failed:\n- " + "\n- ".join(wardrobe_errors)
        raise FilmError(err_msg)
    # ---------------------------------------------

    # Long-form: ensure continuity_chain.md skeleton exists (never overwrite without force)
    chain_path = None
    if is_long_form(spec, shots):
        chain_path = init_chain_doc(root, spec, force=False)
        spec["_continuity_chain"] = {
            "long_form": True,
            "doc": str(chain_path),
            "required": True,
            "note": (
                "Long-form: maintain continuity_chain.md; continue joins byte-reuse last frame "
                "as next keyframe (extract-frame --promote-keyframe). "
                "See references/continuity_chain.md"
            ),
        }
    else:
        spec["_continuity_chain"] = {
            "long_form": False,
            "required": False,
            "note": "Short form: continue joins still should promote last frame; doc optional",
        }
    write_json(root / "film-spec.json", spec)
    manifest = load_manifest(root)
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    # seed timeline placeholders
    timeline = {
        "schema_version": 1,
        "fps": DEFAULT_FPS,
        "width": manifest.get("width", DEFAULT_WIDTH),
        "height": manifest.get("height", DEFAULT_HEIGHT),
        "shots": [
            {
                "id": shot["id"],
                "duration_sec": float(shot.get("duration_sec") or 6),
                "title": shot.get("title") or shot["id"],
            }
            for shot in shots
        ],
    }
    write_json(root / "timeline.json", timeline)
    cont = spec.get("_continuity_lint") or lint_continuity(shots)
    write_json(root / "continuity_lint.json", cont)
    emit(
        {
            "ok": True,
            "root": str(root),
            "shot_count": len(shots),
            "timeline": str(root / "timeline.json"),
            "continuity": cont,
            "framing_lint": spec.get("_framing_lint"),
            "continuity_chain_doc": str(chain_path) if chain_path else None,
            "long_form": is_long_form(spec, shots),
            "transition_intents": spec.get("transition_intents"),
            "sound_plan": spec.get("sound_plan"),
        }
    )
    return 0


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
    intents = spec.get("transition_intents") if isinstance(spec.get("transition_intents"), list) else None
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
        raise FilmError(
            "continuity lint failed: " + ",".join(report.get("codes") or [])
        )
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
        manifest = (
            read_json(root / "manifest.json") if (root / "manifest.json").is_file() else {}
        )
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
        subprocess.run(cmd, capture_output=True, text=True, check=True)
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
        raise FilmError(
            "continuity-chain check failed: " + ",".join(report.get("codes") or [])
        )
    return 0 if report["ok"] else 2


def cmd_lock_style(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    style = load_bible(root)
    if args.signature:
        style["signature_block"] = args.signature.strip()
    if args.canonical:
        src = Path(args.canonical).expanduser().resolve()
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
    cast_master = getattr(args, "cast_master", None)
    if cast_master:
        csrc = Path(cast_master).expanduser().resolve()
        if not csrc.is_file():
            raise FilmError(f"Cast master image missing: {csrc}")
        cast_dir = film_dirs(root)["canonical"] / "cast"
        cast_dir.mkdir(parents=True, exist_ok=True)
        try:
            cdest = safe_output_path(
                cast_dir,
                f"hero-v1{csrc.suffix.lower() or '.png'}",
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
        style["cast_masters"]["hero"] = str(cdest)
        style["cast_master_sha256"] = sha256(cdest)

    # Consistency gates before lock (prevent empty/placeholder bibles)
    sig = str(style.get("signature_block") or "").strip()
    if len(sig) < 40:
        raise FilmError(
            "lock-style requires signature_block ≥40 chars "
            "(pass --signature or edit style-bible.json first)"
        )
    palette = str(style.get("palette") or "").strip().lower()
    if not palette or "to be filled" in palette:
        raise FilmError(
            "lock-style requires a concrete palette in style-bible.json "
            "(not 'to be filled…')"
        )
    identity = str(style.get("identity_lock") or "").strip().lower()
    if identity and "to be filled" in identity:
        raise FilmError(
            "lock-style requires identity_lock filled with face/hair/eyes/wardrobe "
            "(edit style-bible.json before locking)"
        )
    if not style.get("canonical_style_path"):
        raise FilmError("lock-style requires --canonical style master image")

    style["locked"] = True
    style["state"] = "Approved"
    from scripts.visual_bible import save_bible
    save_bible(root, style)
    manifest = load_manifest(root)
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    emit(
        {
            "ok": True,
            "style_locked": True,
            "canonical_style_path": style.get("canonical_style_path"),
            "cast_masters": style.get("cast_masters") or {},
        }
    )
    return 0


def _register_media(
    *,
    shot_id: str,
    source: Path,
    dest_dir: Path,
    role: str,
    status: str,
    prompt_file: Path | None,
) -> dict[str, Any]:
    shot_id = valid_shot_id(shot_id)
    if not source.is_file():
        raise FilmError(f"Source missing: {source}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        dest = safe_output_path(
            dest_dir,
            f"{shot_id}{source.suffix.lower()}",
            suffixes={source.suffix.lower()},
            field="registered media filename",
        )
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc
    # Same-path short-circuit (source already at keyframes/shotXX or clips/shotXX)
    if source.resolve() != dest.resolve():
        shutil.copy2(source, dest)
    record = {
        "shot_id": shot_id,
        "role": role,
        "status": status,
        "path": str(dest),
        "sha256": sha256(dest),
        "bytes": dest.stat().st_size,
        "registered_at": utc_now(),
        "provider": "grok-imagine",
    }
    if prompt_file and prompt_file.is_file():
        record["prompt_file"] = str(prompt_file)
        record["prompt_sha256"] = sha256(prompt_file)
    return record


def cmd_register_still(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    ensure_tree(root)
    identity_approved = getattr(args, "identity_approved", False) is True
    review_note = str(getattr(args, "review_note", "") or "").strip()
    source = Path(args.source).expanduser().resolve()
    # Lesson 2026-07-22: compressed/wrong-aspect still → mushy I2V (vivian-ep01)
    aspect = "9:16"
    try:
        spec = read_json(root / "film-spec.json") if (root / "film-spec.json").is_file() else {}
        aspect = str(spec.get("aspect_ratio") or aspect)
    except Exception:
        pass
    from media_qa import analyze_still_geometry

    geo = analyze_still_geometry(source, aspect_ratio=aspect)
    if args.status == "approved" and not geo.get("ok"):
        raise FilmError(
            "Approved still failed geometry gate (keyframe no-compress): "
            + "; ".join(geo.get("errors") or ["unknown"])
            + " — re-export ≥720×1280 9:16 (or film aspect) full-res; "
            "never I2V from thumbnail/landscape compress. "
            "See references/lessons-2026-07-22-keyframe-no-compress.md"
        )
    if args.status == "approved":
        if not identity_approved:
            raise FilmError(
                "Approved stills require --identity-approved after comparing to cast master"
            )
        if not review_note:
            raise FilmError(
                "Approved stills require --review-note "
                "(e.g. 'id-ok face/hair/outfit; medium matches style-v1')"
            )
    record = _register_media(
        shot_id=args.shot_id,
        source=source,
        dest_dir=root / "keyframes",
        role=args.role,
        status=args.status,
        prompt_file=Path(args.prompt_file).expanduser().resolve() if args.prompt_file else None,
    )
    record["geometry_qa"] = geo
    if args.status == "approved":
        record["identity_approved"] = True
        record["review_note"] = review_note
    manifest = load_manifest(root)
    manifest.setdefault("stills", {})[record["shot_id"]] = record
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    emit({"ok": True, "record": record, "geometry_qa": geo})
    return 0


def _auto_promote_last_to_next(
    root: Path,
    *,
    shot_id: str,
    clip_path: Path,
) -> dict[str, Any] | None:
    """After I2V register: promote last frame → next shot first keyframe when story serial.

    Lesson 2026-07-21: generation must follow actual last→first frames (wardrobe/pose),
    never re-open next still from full cast master on continue/undress chains.
    """
    try:
        from continuity_chain import (
            flatten_shots,
            next_shot_after,
            should_auto_promote_next,
            upsert_join,
            sha256_file as chain_sha,
        )
    except Exception:
        return None
    spec_path = root / "film-spec.json"
    if not spec_path.is_file() or not clip_path.is_file():
        return None
    try:
        spec = read_json(spec_path)
    except Exception:
        return None
    shots = flatten_shots(spec)
    prev = next((s for s in shots if str(s.get("id")) == str(shot_id)), None)
    nxt = next_shot_after(spec, shot_id)
    if not nxt:
        return {"ok": True, "skipped": True, "reason": "last shot — no promote"}
    next_id = str(nxt.get("id") or "")
    heat = str(spec.get("heat_scale") or "")
    do, why = should_auto_promote_next(prev, nxt, heat_scale=heat)
    # allow force off
    if spec.get("auto_promote_next") is False:
        return {"ok": True, "skipped": True, "reason": "auto_promote_next:false"}
    if not do:
        return {"ok": True, "skipped": True, "reason": why}
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        return {"ok": False, "error": "ffmpeg/ffprobe required for auto promote"}
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
                str(clip_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        duration = float((probe.stdout or "0").strip() or "0")
    except (subprocess.CalledProcessError, ValueError) as exc:
        return {"ok": False, "error": f"ffprobe: {exc}"}
    t = max(0.0, duration - 0.05) if duration > 0.1 else 0.0
    kf_dir = root / "keyframes"
    kf_dir.mkdir(parents=True, exist_ok=True)
    last_path = kf_dir / f"_last_{shot_id}.png"
    next_kf = kf_dir / f"{next_id}.png"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{t:.4f}",
                "-i",
                str(clip_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(last_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        return {
            "ok": False,
            "error": f"ffmpeg extract last failed: {(exc.stderr or '')[-300:]}",
        }
    if not last_path.is_file() or last_path.stat().st_size < 32:
        return {"ok": False, "error": "empty last frame"}
    shutil.copy2(last_path, next_kf)
    seed = kf_dir / f"{next_id}-seed.png"
    shutil.copy2(last_path, seed)
    last_sha = chain_sha(last_path)
    first_sha = chain_sha(next_kf)
    join = upsert_join(
        root,
        from_id=str(shot_id),
        to_id=next_id,
        mode="continue",
        last_sha=last_sha,
        first_sha=first_sha,
        last_path=str(last_path),
        first_path=str(next_kf),
        checklist={
            "wardrobe": "carry last-frame costume (no re-dress)",
            "pose": "start from actual last frame pose",
            "note": why,
        },
    )
    # Register still seed as approved frame-chain input (not final art yet)
    try:
        manifest = load_manifest(root)
        stills = manifest.setdefault("stills", {})
        stills[next_id] = {
            "shot_id": next_id,
            "role": "keyframe",
            "status": "frame_chain_seed",
            "path": str(next_kf),
            "sha256": first_sha,
            "bytes": next_kf.stat().st_size,
            "registered_at": utc_now(),
            "provider": "frame-chain-promote",
            "identity_approved": True,
            "review_note": (
                f"AUTO promote last frame of {shot_id} → first of {next_id}; "
                f"{why}; do NOT regenerate from full cast; I2V input={next_kf}"
            ),
            "promoted_from": str(shot_id),
            "byte_identical_to_prev_last": True,
        }
        save_manifest(root, manifest)
    except Exception:
        pass
    return {
        "ok": True,
        "skipped": False,
        "reason": why,
        "from": shot_id,
        "to": next_id,
        "last_frame": str(last_path),
        "next_keyframe": str(next_kf),
        "byte_identical": last_sha == first_sha,
        "join": join,
        "agent_next": (
            f"I2V {next_id} MUST use image={next_kf} (actual last frame of {shot_id}). "
            "Forbidden: image_edit from full cast master (causes re-dress / pose break). "
            "Only image_edit the promoted frame for micro pose if cut required — keep wardrobe."
        ),
    }


def cmd_register_clip(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    ensure_tree(root)
    source = Path(args.source).expanduser().resolve()
    endpoint = getattr(args, "source_endpoint", None)
    identity_approved = getattr(args, "identity_approved", False) is True
    motion_approved = getattr(args, "motion_approved", False) is True
    review_note = str(getattr(args, "review_note", "") or "").strip()
    if args.status == "approved":
        if endpoint not in ALLOWED_VIDEO_ENDPOINTS:
            raise FilmError(
                f"Approved clips require --source-endpoint in {sorted(ALLOWED_VIDEO_ENDPOINTS)}"
            )
        if not identity_approved:
            raise FilmError("Approved clips require --identity-approved after canonical identity review")
        if not motion_approved:
            raise FilmError("Approved clips require --motion-approved after watching the complete clip")
        if not review_note:
            raise FilmError("Approved clips require --review-note with the visual review result")
    manifest = load_manifest(root)
    shot_review = None
    if args.status == "approved" and int(manifest.get("review_contract_version") or 1) >= 2:
        try:
            from shot_review import approved_review_for_clip

            shot_review = approved_review_for_clip(
                root,
                shot_id=str(args.shot_id),
                clip=source,
                receipt=Path(args.review_receipt).expanduser().resolve() if getattr(args, "review_receipt", None) else None,
            )
        except Exception as exc:
            raise FilmError(f"v1.6 approved clips require matching shot-review evidence: {exc}") from exc
    try:
        qa = analyze_media(source, require_audio=False, require_motion=True)
    except MediaQAError as exc:
        raise FilmError(str(exc)) from exc
    if args.status == "approved" and not qa.get("ok"):
        raise FilmError(f"Clip failed decode/duration/motion QA: {qa.get('errors')}")
    record = _register_media(
        shot_id=args.shot_id,
        source=source,
        dest_dir=root / "clips",
        role="i2v",
        status=args.status,
        prompt_file=Path(args.prompt_file).expanduser().resolve() if args.prompt_file else None,
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
            "qa": qa,
            "shot_review": shot_review,
        }
    )
    if qa.get("has_audio"):
        try:
            audio_dir = film_dirs(root)["audio"]
            native_dir = safe_workspace_directory(audio_dir, "native", field="native audio directory")
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
            record["native_audio"] = {
                "path": str(native_path),
                "sha256": sha256(native_path),
                "duration_sec": media_duration(native_path),
                "preserved_at": utc_now(),
            }
        except (SecurityPolicyError, subprocess.CalledProcessError, OSError, ValueError) as exc:
            raise FilmError(f"Could not preserve generated native audio: {exc}") from exc
    manifest.setdefault("clips", {})[record["shot_id"]] = record
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

    emit({"ok": True, "record": record, "auto_promote_next": promote})
    return 0


def normalize_clip(src: Path, dest: Path, *, width: int, height: int, fps: int, duration: float | None) -> None:
    """Re-encode to a common profile for safe concat."""
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps},format=yuv420p,setpts=PTS-STARTPTS"
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
        "20",
    ]
    if duration is not None and duration > 0:
        # If source shorter, slow slightly up to 1.33x then freeze-pad via tpad if needed.
        try:
            src_dur = media_duration(src)
        except Exception:
            src_dur = duration
        if src_dur > 0 and duration > src_dur * 1.001:
            factor = min(duration / src_dur, 1.34)
            # Apply setpts slowdown then trim/pad
            vf2 = (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps={fps},format=yuv420p,"
                f"setpts={factor}*PTS,tpad=stop_mode=clone:stop_duration={max(0.0, duration - src_dur * factor)}"
            )
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-vf",
                vf2,
                "-an",
                "-t",
                str(duration),
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "20",
                str(dest),
            ]
            run(cmd)
            return
        cmd.extend(["-t", str(duration)])
    cmd.append(str(dest))
    run(cmd)


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
        raise FilmError(f"Assembled film failed decode/duration/motion QA: {technical_qa.get('errors')}")
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
            "width": width,
            "height": height,
            "fps": fps,
            "duration_cap": duration_cap,
            "count_ok": len(done),
            "count_failed": len(failed),
        }
    )
    return 0 if not failed else 2


def cmd_final(args: argparse.Namespace) -> int:
    """FFmpeg final, optionally followed by HyperFrames/Remotion designed-post compose-render."""
    skill_dir = Path(__file__).resolve().parents[1]
    script = skill_dir / "scripts" / "render_final.py"
    if not script.is_file():
        raise FilmError(f"Missing {script}")
    root = Path(args.root).expanduser().resolve()
    post_engine = str(getattr(args, "post_engine", "ffmpeg") or "ffmpeg").strip().lower()
    if post_engine not in {"ffmpeg", "hyperframes", "remotion"}:
        raise FilmError("--post-engine must be ffmpeg|hyperframes|remotion")

    # Lesson preflight (default on): hard blocks; soft logs; --skip-preflight escapes
    preflight_report: dict[str, Any] | None = None
    if not bool(getattr(args, "skip_preflight", False)):
        sys.path.insert(0, str(skill_dir / "scripts"))
        try:
            from preflight import PreflightError, run_preflight
        except ImportError as exc:
            raise FilmError(f"Cannot import preflight: {exc}") from exc
        try:
            preflight_report = run_preflight(root)
        except PreflightError as exc:
            raise FilmError(str(exc)) from exc
        hard = preflight_report.get("hard") or []
        soft = preflight_report.get("soft") or []
        if hard:
            codes = ", ".join(str(i.get("code")) for i in hard if isinstance(i, dict))
            msgs = "; ".join(str(i.get("message")) for i in hard if isinstance(i, dict))
            raise FilmError(
                f"final blocked by preflight hard gates [{codes}]: {msgs}. "
                f'Run aifilm preflight --root "{root}" then fix, or --skip-preflight (not recommended).'
            )
        if soft:
            for item in soft:
                if not isinstance(item, dict):
                    continue
                log(
                    f"preflight soft [{item.get('code')}]: {item.get('message')} "
                    f"| fix: {item.get('fix') or '—'}"
                )
        if bool(getattr(args, "preflight_strict", False)) and soft:
            codes = ", ".join(str(i.get("code")) for i in soft if isinstance(i, dict))
            raise FilmError(
                f"final blocked by preflight --preflight-strict soft gates [{codes}]. "
                f'Run aifilm preflight --root "{root}" or drop --preflight-strict.'
            )
        log(
            f"preflight ok (hard=0 soft={len(soft)}) "
            f"→ post_engine={post_engine}"
        )

    # Fail early before TTS if loop-risk VO would force boring stream_loop.
    # When receipts/tts-rehearsal.json present, measured_duration_sec preferred over estimate.
    from production_gates import ProductionGateError, assert_no_loop_risk

    try:
        assert_no_loop_risk(
            root,
            force=bool(getattr(args, "allow_loop_risk", False)),
            strict_tts_rehearsal=bool(getattr(args, "strict_tts_rehearsal", False)),
        )
    except ProductionGateError as exc:
        raise FilmError(str(exc)) from exc

    # Shot inventory must be complete before final (no indexing past missing clips)
    try:
        man_inv = load_manifest(root)
        sum_inv = recompute_gates(root, man_inv)
        from shot_inventory import InventoryError, assert_inventory_for_final

        assert_inventory_for_final(
            sum_inv.get("shot_ids") or [],
            sum_inv.get("approved_clips") or [],
        )
    except InventoryError as exc:
        raise FilmError(str(exc)) from exc

    if args.out_name:
        film_output_path(root, args.out_name)

    # Designed-post path:
    # - SRT only on FFmpeg plate (subs off) so designed captions don't double-burn
    # - blank plate title/end glyphs so designed cards don't double-burn titles
    #   (pad duration kept for VO/SRT clock)
    subs_mode = str(getattr(args, "subs", None) or "").strip().lower()
    if not subs_mode:
        subs_mode = "off" if post_engine in {"hyperframes", "remotion"} else "burn"
    plate_cards = str(getattr(args, "plate_cards", None) or "auto").strip().lower()
    if plate_cards in {"", "auto"}:
        plate_cards = "blank" if post_engine in {"hyperframes", "remotion"} else "text"
    if plate_cards not in {"text", "blank"}:
        raise FilmError("--plate-cards must be auto|text|blank")

    cmd = [sys.executable, str(script), "--root", str(root)]
    if args.out_name:
        cmd += ["--out-name", args.out_name]
    if args.voice:
        cmd += ["--voice", args.voice]
    if getattr(args, "tts_backend", None):
        cmd += ["--tts-backend", args.tts_backend]
    # Use --flag=value so values starting with '-' (e.g. -5%) are not eaten as flags
    if getattr(args, "vo_rate", None):
        cmd += [f"--vo-rate={args.vo_rate}"]
    if getattr(args, "vo_pitch", None):
        cmd += [f"--vo-pitch={args.vo_pitch}"]
    if getattr(args, "vo_gain", None) is not None:
        cmd += [f"--vo-gain={args.vo_gain}"]
    if getattr(args, "vocal_color_gain", None) is not None:
        cmd += ["--vocal-color-gain", str(args.vocal_color_gain)]
    if args.title:
        cmd += ["--title", args.title]
    if args.end_title:
        cmd += ["--end-title", args.end_title]
    if args.music:
        cmd += ["--music", args.music]
    if args.music_license:
        cmd += ["--music-license", args.music_license]
    if getattr(args, "music_template", None):
        cmd += ["--music-template", str(args.music_template)]
    if args.music_volume is not None:
        cmd += ["--music-volume", str(args.music_volume)]
    if getattr(args, "transition_sec", None) is not None:
        cmd += ["--transition-sec", str(args.transition_sec)]
    if getattr(args, "native_audio_volume", None) is not None:
        cmd += ["--native-audio-volume", str(args.native_audio_volume)]
    if args.music_mood:
        cmd += ["--music-mood", args.music_mood]
    if getattr(args, "music_seed", None) is not None:
        cmd += ["--music-seed", str(int(args.music_seed))]
    if getattr(args, "sidechain_threshold", None) is not None:
        cmd += ["--sidechain-threshold", str(args.sidechain_threshold)]
    if getattr(args, "sidechain_ratio", None) is not None:
        cmd += ["--sidechain-ratio", str(args.sidechain_ratio)]
    if getattr(args, "sidechain_attack", None) is not None:
        cmd += ["--sidechain-attack", str(args.sidechain_attack)]
    if getattr(args, "sidechain_release", None) is not None:
        cmd += ["--sidechain-release", str(args.sidechain_release)]
    if getattr(args, "loudnorm", None):
        cmd += ["--loudnorm", str(args.loudnorm)]
    if getattr(args, "target_lufs", None) is not None:
        cmd += ["--target-lufs", str(args.target_lufs)]
    if getattr(args, "lipsync", None):
        cmd += ["--lipsync", args.lipsync]
    if getattr(args, "sub_lead", None) is not None:
        cmd += ["--sub-lead", str(args.sub_lead)]
    if getattr(args, "sub_max_unit", None) is not None:
        cmd += ["--sub-max-unit", str(args.sub_max_unit)]
    if getattr(args, "sub_max_chars", None) is not None:
        cmd += ["--sub-max-chars", str(args.sub_max_chars)]
    if getattr(args, "title_dur", None) is not None:
        cmd += ["--title-dur", str(args.title_dur)]
    if getattr(args, "end_dur", None) is not None:
        cmd += ["--end-dur", str(args.end_dur)]
    if getattr(args, "allow_loop_risk", False):
        cmd += ["--allow-loop-risk"]
    if getattr(args, "vo_fit", None):
        cmd += ["--vo-fit", str(args.vo_fit)]
    cmd += ["--subs", subs_mode]
    cmd += ["--plate-cards", plate_cards]
    log(
        f"running render_final.py (post_engine={post_engine}, "
        f"subs={subs_mode}, plate_cards={plate_cards}) ..."
    )
    proc = run(cmd, check=False)
    sys.stderr.write(proc.stderr or "")
    ffmpeg_result: dict[str, Any] | None = None
    if proc.stdout:
        try:
            ffmpeg_result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            # keep raw for ffmpeg-only path
            if post_engine == "ffmpeg":
                print(proc.stdout)
    if proc.returncode != 0:
        if post_engine == "ffmpeg" and not proc.stdout:
            pass
        elif post_engine != "ffmpeg":
            emit(
                {
                    "ok": False,
                    "post_engine": post_engine,
                    "stage": "ffmpeg",
                    "error": (proc.stderr or proc.stdout or "render_final failed")[:2000],
                    "ffmpeg": ffmpeg_result,
                }
            )
        return proc.returncode

    if post_engine == "ffmpeg":
        if ffmpeg_result is not None:
            out_obj = {**ffmpeg_result, "post_engine": "ffmpeg"}
            if preflight_report is not None:
                out_obj["preflight"] = {
                    "hard_ok": preflight_report.get("hard_ok"),
                    "soft_count": len(preflight_report.get("soft") or []),
                    "soft_codes": [
                        i.get("code")
                        for i in (preflight_report.get("soft") or [])
                        if isinstance(i, dict)
                    ],
                }
            emit(out_obj)
        elif proc.stdout:
            print(proc.stdout)
        return 0

    # Designed-post: HyperFrames or Remotion after FFmpeg plate (subs off)
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from compose_render import (
            ComposeRenderError,
            compose_render,
            probe_designed_post_tooling,
            probe_remotion_readiness,
        )
    except ImportError as exc:
        raise FilmError(f"Cannot import compose_render: {exc}") from exc

    if post_engine == "hyperframes":
        tooling = probe_designed_post_tooling()
        if not tooling.get("npx") or not tooling.get("hyperframes_ok"):
            raise FilmError(
                "post-engine=hyperframes 需要 Node/npx + hyperframes；"
                f"tooling={tooling}。可改用 --post-engine ffmpeg，"
                "或安装 Node 22+ 后重试。"
            )
        log("post-engine=hyperframes → compose-render ...")
        try:
            result = compose_render(
                root,
                engine="hyperframes",
                export_first=True,
                force_export=True,
                layout="underlay",
                compose_preset=str(getattr(args, "compose_preset", "auto") or "auto"),
                quality=str(getattr(args, "compose_quality", "standard") or "standard"),
                out_name=str(args.out_name or "film_final.mp4"),
                register=True,
                skip_check=bool(getattr(args, "skip_compose_check", False)),
                keep_raw=bool(getattr(args, "keep_compose_raw", False)),
                require_preview=bool(getattr(args, "require_preview", False)),
                title_dur=float(getattr(args, "title_dur", 1.5) or 1.5),
                end_dur=1.5,
                allow_burned_underlay=bool(getattr(args, "allow_burned_underlay", False)),
                title_sequence=getattr(args, "title_sequence", None),
                end_roll=getattr(args, "end_roll", None),
            )
        except ComposeRenderError as exc:
            raise FilmError(str(exc)) from exc
        out_obj: dict[str, Any] = {
            "ok": True,
            "post_engine": "hyperframes",
            "ffmpeg": ffmpeg_result,
            "compose": result,
            "output": result.get("output"),
            "output_sha256": result.get("output_sha256"),
            "final_complete": False,
            "next": result.get("next"),
        }
    else:
        # remotion
        if not which_npx_safe():
            raise FilmError(
                "post-engine=remotion 需要 Node/npx。"
                "安装 Node 22+ 后重试，或 --post-engine hyperframes|ffmpeg。"
            )
        npm_install = bool(getattr(args, "npm_install", False))
        readiness = probe_remotion_readiness(root)
        log(
            f"post-engine=remotion → compose-render "
            f"(npm_install={npm_install}, prior_ready={readiness.get('ready')}) ..."
        )
        try:
            result = compose_render(
                root,
                engine="remotion",
                export_first=True,
                force_export=True,
                layout="underlay",
                compose_preset=str(getattr(args, "compose_preset", "auto") or "auto"),
                out_name=str(args.out_name or "film_final.mp4"),
                register=True,
                keep_raw=bool(getattr(args, "keep_compose_raw", False)),
                require_preview=bool(getattr(args, "require_preview", False)),
                npm_install=npm_install,
                npm_install_timeout=int(getattr(args, "npm_install_timeout", 900) or 900),
                title_dur=float(getattr(args, "title_dur", 1.5) or 1.5),
                end_dur=1.5,
                allow_burned_underlay=bool(getattr(args, "allow_burned_underlay", False)),
                title_sequence=getattr(args, "title_sequence", None),
                end_roll=getattr(args, "end_roll", None),
            )
        except ComposeRenderError as exc:
            raise FilmError(str(exc)) from exc
        # compose_render may return ok=False when not ready (no raise)
        out_obj = {
            "ok": bool(result.get("ok")),
            "post_engine": "remotion" if result.get("rendered") else None,
            "rendered": result.get("rendered"),
            "ffmpeg": ffmpeg_result,
            "compose": result,
            "output": result.get("output"),
            "output_sha256": result.get("output_sha256"),
            "final_complete": False,
            "next": result.get("next") or result.get("next_steps"),
            "error": result.get("error"),
            "message": result.get("message"),
        }
        if preflight_report is not None:
            out_obj["preflight"] = {
                "hard_ok": preflight_report.get("hard_ok"),
                "soft_count": len(preflight_report.get("soft") or []),
                "soft_codes": [
                    i.get("code")
                    for i in (preflight_report.get("soft") or [])
                    if isinstance(i, dict)
                ],
            }
        emit(out_obj)
        return 0 if out_obj.get("ok") else 2

    if preflight_report is not None:
        out_obj["preflight"] = {
            "hard_ok": preflight_report.get("hard_ok"),
            "soft_count": len(preflight_report.get("soft") or []),
            "soft_codes": [
                i.get("code")
                for i in (preflight_report.get("soft") or [])
                if isinstance(i, dict)
            ],
        }
    emit(out_obj)
    return 0


def which_npx_safe() -> str | None:
    import shutil

    return shutil.which("npx")


def cmd_review_final(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    manifest = load_manifest(root)
    summary = recompute_gates(root, manifest)
    if not summary["gates"]["clips_complete"]:
        raise FilmError("Cannot approve final: not every planned clip has endpoint, identity, motion, and decode QA")
    final_record = (manifest.get("outputs") or {}).get("final_film")
    out_dir = film_dirs(root)["out"]
    if not record_file_matches(out_dir, final_record, field="final film path"):
        raise FilmError("Cannot approve final: final film is missing or its SHA-256 no longer matches")
    final_path = safe_existing_file(out_dir, final_record["path"], field="final film path")
    try:
        technical_qa = analyze_media(final_path, require_audio=True, require_motion=True)
    except (MediaQAError, SecurityPolicyError) as exc:
        raise FilmError(str(exc)) from exc
    if not technical_qa.get("ok"):
        raise FilmError(f"Cannot approve final: technical QA failed: {technical_qa.get('errors')}")
    reviewer = str(args.reviewer or "").strip()
    notes = str(args.notes or "").strip()
    if not args.approve:
        raise FilmError("Full-film review requires explicit --approve after watching the entire film")
    if not reviewer or not notes:
        raise FilmError("Full-film review requires non-empty --reviewer and --notes")
    try:
        card = build_scorecard_from_cli(args)
    except DirectorReviewError as exc:
        raise FilmError(str(exc)) from exc
    manifest_contract = int(manifest.get("review_contract_version") or 1)
    screening_evidence: dict[str, Any] = {}
    if manifest_contract >= 2:
        try:
            from director_review import parse_timestamp_evidence

            screening_evidence = parse_timestamp_evidence(
                list(getattr(args, "screening_evidence", None) or []),
                required=SCORECARD_DIMENSIONS,
                duration_sec=float(technical_qa.get("duration_sec") or 0.0),
            )
        except DirectorReviewError as exc:
            raise FilmError(str(exc)) from exc

    # Scorecard fail → write director_notes reshoot list, do not approve
    if not scorecard_all_pass(card):
        shot_ids = parse_shot_id_list(getattr(args, "reshoot_shots", None))
        existing = load_director_notes(root)
        package = build_notes_from_scorecard_failures(
            card,
            notes_text=notes,
            output_sha256=str(final_record.get("sha256") or ""),
            shot_ids=shot_ids,
            existing=existing,
        )
        notes_path = save_director_notes(root, package)
        open_items = open_reshoot_items(package)
        # Persist failed attempt for audit (not approved)
        failed_review = {
            "approved": False,
            "reviewed_at": utc_now(),
            "reviewer": reviewer,
            "notes": notes,
            "output_sha256": final_record["sha256"],
            "technical_qa": technical_qa,
            "scorecard": scorecard_payload(card),
            "screening_evidence": screening_evidence,
            "director_notes_path": str(notes_path),
            "open_reshoot_ids": [it.get("id") for it in open_items],
        }
        write_json(out_dir / "final-review-failed.json", failed_review)
        recompute_gates(root, manifest)
        save_manifest(root, manifest)
        fails = ",".join(scorecard_payload(card)["failures"])
        raise FilmError(
            f"scorecard fail [{fails}] — wrote {len(open_items)} open reshoot item(s) to "
            f"{notes_path}; resolve with director-notes then re-run review-final with all pass"
        )

    try:
        scorecard = validate_scorecard_for_approve(card)
    except DirectorReviewError as exc:
        raise FilmError(str(exc)) from exc
    review = {
        "approved": True,
        "reviewed_at": utc_now(),
        "reviewer": reviewer,
        "notes": notes,
        "output_sha256": final_record["sha256"],
        "technical_qa": technical_qa,
        "scorecard": scorecard,
        "screening": {"path": str(final_path), "sha256": final_record["sha256"], "duration_sec": technical_qa.get("duration_sec")},
        "screening_evidence": screening_evidence,
    }
    review_path = out_dir / "final-review.json"
    write_json(review_path, review)
    review["path"] = str(review_path)
    manifest.setdefault("outputs", {})["final_review"] = review
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    emit({"ok": True, "final_complete": manifest["gates"]["final_complete"], "review": review})
    return 0


def cmd_review_shot(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    ensure_tree(root)
    try:
        from shot_review import REVIEW_DIMENSIONS, ShotReviewError, create_shot_review

        scores = {dim: getattr(args, f"score_{dim}") for dim in REVIEW_DIMENSIONS}
        report = create_shot_review(
            root,
            shot_id=str(args.shot_id),
            source=Path(args.source),
            reviewer=str(args.reviewer),
            notes=str(args.notes),
            scores=scores,
            evidence_values=list(args.evidence or []),
            references=[Path(item) for item in (args.reference or [])],
            approve=bool(args.approve),
        )
    except (ShotReviewError, MediaQAError, ValueError) as exc:
        raise FilmError(str(exc)) from exc
    emit({"ok": True, "approved": report["approved"], "review": report})
    return 0


def cmd_review_contract(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    manifest = load_manifest(root)
    if args.review_contract_action != "migrate":
        raise FilmError(f"unknown review-contract action: {args.review_contract_action}")
    legacy = [sid for sid, record in (manifest.get("clips") or {}).items() if isinstance(record, dict) and record.get("status") == "approved" and not isinstance(record.get("shot_review"), dict)]
    manifest["review_contract_version"] = 2
    manifest["review_contract_migrated_at"] = utc_now()
    manifest["review_contract_pending_shots"] = legacy
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    emit({"ok": True, "review_contract_version": 2, "pending_shot_reviews": legacy, "note": "existing approvals remain historical records; review each listed clip before it can satisfy v1.6 delivery gates"})
    return 0


def cmd_director_notes(args: argparse.Namespace) -> int:
    """List / add / resolve director reshoot notes (B3 closed loop)."""
    root = Path(args.root).expanduser().resolve()
    load_manifest(root)  # ensures project exists
    action = args.notes_cmd
    package = load_director_notes(root)

    if action == "list":
        open_items = open_reshoot_items(package)
        emit(
            {
                "ok": True,
                "path": str(director_notes_path(root))
                if director_notes_path(root).is_file()
                else None,
                "open_reshoot_count": len(open_items),
                "open_reshoots": open_items,
                "items": package.get("items") or [],
                "reshoots_clear": reshoots_clear(package),
                "scorecard": package.get("scorecard"),
            }
        )
        return 0

    if action == "add":
        try:
            item = add_reshoot_item(
                package,
                action=str(args.action),
                reason_code=str(args.reason),
                note=str(args.note or ""),
                shot_id=(str(args.shot_id).strip() if args.shot_id else None),
                source="manual",
            )
        except DirectorReviewError as exc:
            raise FilmError(str(exc)) from exc
        path = save_director_notes(root, package)
        manifest = load_manifest(root)
        recompute_gates(root, manifest)
        save_manifest(root, manifest)
        emit(
            {
                "ok": True,
                "path": str(path),
                "item": item,
                "open_reshoot_count": len(open_reshoot_items(package)),
            }
        )
        return 0

    if action == "resolve":
        try:
            resolved = resolve_reshoot_item(
                package,
                item_id=(str(args.item_id).strip() if args.item_id else None),
                shot_id=(str(args.shot_id).strip() if args.shot_id else None),
                resolve_note=str(args.note or ""),
            )
        except DirectorReviewError as exc:
            raise FilmError(str(exc)) from exc
        path = save_director_notes(root, package)
        manifest = load_manifest(root)
        recompute_gates(root, manifest)
        save_manifest(root, manifest)
        emit(
            {
                "ok": True,
                "path": str(path),
                "resolved": resolved,
                "open_reshoot_count": len(open_reshoot_items(package)),
                "reshoots_clear": reshoots_clear(package),
            }
        )
        return 0

    raise FilmError(f"Unknown director-notes action: {action}")


def cmd_pilot(args: argparse.Namespace) -> int:
    """Pilot three-shot scorecard assist (pick/report/score/approve)."""
    skill_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from pilot_review import (
            PilotReviewError,
            build_pilot_approval,
            build_pilot_scorecard,
            load_pilot_scorecard,
            pick_pilot_shots,
            pilot_report,
            read_json,
            write_pilot_approval,
            write_pilot_scorecard,
        )
        from production_gates import pilot_is_user_approved
    except ImportError as exc:
        raise FilmError(f"Cannot import pilot_review: {exc}") from exc

    root = Path(args.root).expanduser().resolve()
    action = str(getattr(args, "pilot_action", "") or "")
    try:
        if action == "pick":
            spec = read_json(root / "film-spec.json")
            if not spec:
                raise FilmError("film-spec.json missing")
            shots = pick_pilot_shots(spec, n=int(getattr(args, "n", 3) or 3))
            emit({"ok": True, "shots": shots, "n": len(shots)})
            return 0
        if action == "report":
            shots_raw = str(getattr(args, "shots", "") or "")
            shots = [s.strip() for s in shots_raw.split(",") if s.strip()] or None
            emit(pilot_report(root, shots=shots))
            return 0
        if action == "score":
            from pilot_review import fail_scorecard_to_director_notes

            shots = [s.strip() for s in str(args.shots).split(",") if s.strip()]
            scores = {
                "identity": args.score_identity,
                "style": args.score_style,
                "motion": args.score_motion,
            }
            card = build_pilot_scorecard(
                shots=shots,
                scores=scores,
                reviewer=str(args.reviewer),
                notes=str(args.notes),
            )
            path = write_pilot_scorecard(root, card)
            notes_items = fail_scorecard_to_director_notes(
                root,
                card,
                enabled=not bool(getattr(args, "no_notes_on_fail", False)),
            )
            emit(
                {
                    "ok": True,
                    "path": str(path),
                    "scorecard": card,
                    "director_notes_items": notes_items,
                }
            )
            return 0
        if action == "approve":
            scorecard = load_pilot_scorecard(root)
            shots = [s.strip() for s in str(getattr(args, "shots", "") or "").split(",") if s.strip()]
            if not shots and isinstance(scorecard.get("shots"), list):
                shots = [str(x) for x in scorecard["shots"]]
            if not shots:
                spec = read_json(root / "film-spec.json")
                shots = pick_pilot_shots(spec) if spec else []
            approval = build_pilot_approval(
                shots=shots,
                user_phrase=str(args.user_phrase),
                notes=str(getattr(args, "notes", "") or ""),
                compared_to_cast=getattr(args, "compared_to_cast", None),
                scorecard=scorecard or None,
                require_scorecard=not bool(getattr(args, "no_require_scorecard", False)),
            )
            path = write_pilot_approval(root, approval)
            emit(
                {
                    "ok": True,
                    "path": str(path),
                    "approval": approval,
                    "user_approved": pilot_is_user_approved(approval),
                }
            )
            return 0
        raise FilmError(f"Unknown pilot action: {action}")
    except PilotReviewError as exc:
        raise FilmError(str(exc)) from exc


def cmd_compose_preview(args: argparse.Namespace) -> int:
    """Open HyperFrames or Remotion Studio and return URL + receipt."""
    skill_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from compose_preview import (
            ComposePreviewError,
            compose_preview,
            load_preview_receipt,
            preview_status,
            preview_stop,
        )
    except ImportError as exc:
        raise FilmError(f"Cannot import compose_preview: {exc}") from exc

    root = Path(args.root).expanduser().resolve()
    engine = str(getattr(args, "engine", "hyperframes") or "hyperframes").strip().lower()
    default_port = 3003 if engine == "remotion" else 3002
    port = getattr(args, "port", None)
    port_i = int(port) if port is not None else default_port
    hf_dir = root / "compose" / "hyperframes"
    try:
        if getattr(args, "stop", False):
            if engine == "remotion":
                emit(
                    {
                        "ok": False,
                        "engine": "remotion",
                        "error": "Remotion Studio stop is manual (kill studio process)",
                    }
                )
                return 2
            if not hf_dir.is_dir():
                raise FilmError("compose/hyperframes missing")
            emit(preview_stop(hf_dir))
            return 0
        if getattr(args, "status_only", False):
            if engine == "remotion":
                rem = root / "compose" / "remotion"
                emit(
                    {
                        "ok": True,
                        "engine": "remotion",
                        "dir": str(rem),
                        "package": (rem / "package.json").is_file(),
                        "node_modules": (rem / "node_modules" / "remotion").is_dir(),
                        "receipt": load_preview_receipt(root),
                    }
                )
                return 0
            if not hf_dir.is_dir():
                raise FilmError("compose/hyperframes missing")
            emit({"ok": True, **preview_status(hf_dir)})
            return 0
        result = compose_preview(
            root,
            engine=engine,
            port=port_i,
            open_browser=not bool(getattr(args, "no_open", False)),
            export_if_missing=not bool(getattr(args, "no_export", False)),
            background=not bool(getattr(args, "foreground", False)),
            force_new=bool(getattr(args, "force_new", False)),
        )
    except ComposePreviewError as exc:
        raise FilmError(str(exc)) from exc
    emit(result)
    return 0 if result.get("ok") is not False else 2


def cmd_export_compose(args: argparse.Namespace) -> int:
    """Export approved clips + film-spec timeline into HyperFrames/Remotion packages.

    Designed-post bridge only — does not replace Grok I2V or default FFmpeg final.
    """
    skill_dir = Path(__file__).resolve().parents[1]
    script = skill_dir / "scripts" / "export_composition.py"
    if not script.is_file():
        raise FilmError(f"Missing {script}")
    # Import sibling module for in-process export (tests + consistent errors)
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from export_composition import ComposeExportError, export_composition
    except ImportError as exc:
        raise FilmError(f"Cannot import export_composition: {exc}") from exc

    root = Path(args.root).expanduser().resolve()
    manifest = load_manifest(root)
    summary = recompute_gates(root, manifest)
    if not summary["gates"].get("clips_complete"):
        raise FilmError(
            "export-compose requires clips_complete "
            "(every planned shot has approved register-clip)"
        )
    try:
        result = export_composition(
            root,
            engine=str(getattr(args, "engine", "both") or "both"),
            title_dur=float(getattr(args, "title_dur", 1.5) or 1.5),
            end_dur=float(getattr(args, "end_dur", 1.5) or 1.5),
            force=bool(getattr(args, "force", False)),
            layout=str(getattr(args, "layout", "auto") or "auto"),
            compose_preset=str(getattr(args, "compose_preset", "auto") or "auto"),
            title_sequence=getattr(args, "title_sequence", None),
            end_roll=getattr(args, "end_roll", None),
        )
    except ComposeExportError as exc:
        raise FilmError(str(exc)) from exc
    emit(result)
    return 0


def cmd_compose_render(args: argparse.Namespace) -> int:
    """HyperFrames check+render+audio mux+register final (designed post)."""
    skill_dir = Path(__file__).resolve().parents[1]
    if not (skill_dir / "scripts" / "compose_render.py").is_file():
        raise FilmError("Missing compose_render.py")
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from compose_render import ComposeRenderError, compose_render, register_final_film
    except ImportError as exc:
        raise FilmError(f"Cannot import compose_render: {exc}") from exc

    root = Path(args.root).expanduser().resolve()
    if getattr(args, "register_only", None):
        try:
            result = register_final_film(
                root,
                Path(args.register_only),
                out_name=str(getattr(args, "out_name", None) or "film_final.mp4"),
                post_engine=str(getattr(args, "post_engine", None) or "external"),
                force=True,
            )
        except ComposeRenderError as exc:
            raise FilmError(str(exc)) from exc
        emit(result)
        return 0

    manifest = load_manifest(root)
    summary = recompute_gates(root, manifest)
    if not summary["gates"].get("clips_complete"):
        raise FilmError("compose-render requires clips_complete")
    try:
        result = compose_render(
            root,
            engine=str(getattr(args, "engine", "hyperframes") or "hyperframes"),
            export_first=not bool(getattr(args, "no_export", False)),
            force_export=not bool(getattr(args, "no_force_export", False)),
            layout=str(getattr(args, "layout", "auto") or "auto"),
            compose_preset=str(getattr(args, "compose_preset", "auto") or "auto"),
            quality=str(getattr(args, "quality", "standard") or "standard"),
            out_name=str(getattr(args, "out_name", None) or "film_final.mp4"),
            register=not bool(getattr(args, "no_register", False)),
            skip_check=bool(getattr(args, "skip_check", False)),
            keep_raw=bool(getattr(args, "keep_raw", False)),
            require_preview=bool(getattr(args, "require_preview", False)),
            npm_install=bool(getattr(args, "npm_install", False)),
            npm_install_timeout=int(getattr(args, "npm_install_timeout", 900) or 900),
            title_dur=float(getattr(args, "title_dur", 1.5) or 1.5),
            end_dur=float(getattr(args, "end_dur", 1.5) or 1.5),
            allow_burned_underlay=bool(getattr(args, "allow_burned_underlay", False)),
            title_sequence=getattr(args, "title_sequence", None),
            end_roll=getattr(args, "end_roll", None),
        )
    except ComposeRenderError as exc:
        raise FilmError(str(exc)) from exc
    emit(result)
    return 0


def cmd_register_final(args: argparse.Namespace) -> int:
    """Register an external/composed MP4 as formal final_film candidate."""
    skill_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from compose_render import ComposeRenderError, register_final_film
    except ImportError as exc:
        raise FilmError(f"Cannot import compose_render: {exc}") from exc
    root = Path(args.root).expanduser().resolve()
    try:
        result = register_final_film(
            root,
            Path(args.source),
            out_name=str(getattr(args, "out_name", None) or "film_final.mp4"),
            post_engine=str(getattr(args, "post_engine", None) or "external"),
            require_motion=not bool(getattr(args, "allow_static", False)),
            force=True,
        )
    except ComposeRenderError as exc:
        raise FilmError(str(exc)) from exc
    emit(result)
    return 0


def cmd_frw(args: argparse.Namespace) -> int:
    """Proxy to local frwclaw-pro dispatch (bulk 2V preferred path).

    Special: ``frw canary`` → scripts/frw_canary.py (key capability receipt).
    """
    launcher = Path(__file__).resolve().parent / "frw_dispatch.py"
    if not launcher.is_file():
        raise FilmError(f"missing FRW launcher: {launcher}")
    argv = list(getattr(args, "frw_argv", None) or [])
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        argv = ["help"]
    # Do not capture stdout — FRW protocol is one-line JSON for the agent.
    return int(subprocess.call([sys.executable, str(launcher), *argv]))


def cmd_export_desktop(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    desktop = Path.home() / "Desktop"
    if not desktop.is_dir():
        raise FilmError(f"Desktop not found: {desktop}")
    name = args.name.strip() or (load_manifest(root).get("title") or "GrokFilm")
    try:
        dest = safe_subdirectory(desktop, name, field="Desktop export name")
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc
    if dest.exists() and not args.force:
        raise FilmError(f"Desktop export already exists: {dest} (pass --force to update it)")
    manifest = load_manifest(root)
    recompute_gates(root, manifest)
    if not manifest["gates"]["final_complete"]:
        raise FilmError("Desktop export requires completed technical QA and explicit full-film final review")
    dirs = film_dirs(root)
    try:
        reject_symlinks(dest, field="Desktop export destination")
        for key in ("out", "audio", "keyframes", "clips", "canonical"):
            reject_symlinks(dirs[key], field=f"film {key} export source")
        for meta in EXPORT_METADATA_FILES:
            if (root / meta).is_symlink():
                raise SecurityPolicyError(f"Invalid export source: symbolic links are not allowed: {root / meta}")
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc
    for sub in ("成片", "关键帧", "镜头片段", "定妆与场景", "简报", "项目状态"):
        try:
            safe_workspace_directory(dest, sub, field=f"Desktop {sub} directory").mkdir(
                parents=True, exist_ok=True
            )
        except SecurityPolicyError as exc:
            raise FilmError(str(exc)) from exc

    # films: only ship clean deliverables (skip film_final_pre_*, dual intermediates)
    out_dir = dirs["out"]
    prefer = ["film_final.mp4", "film_silent.mp4"]
    copied_any = False
    for name in prefer:
        src = out_dir / name
        if src.is_file():
            shutil.copy2(src, dest / "成片" / name)
            copied_any = True
    if not copied_any:
        for mp4 in sorted(out_dir.glob("*.mp4")):
            if mp4.name.startswith("_") or "pre_" in mp4.name or "_work" in mp4.name:
                continue
            shutil.copy2(mp4, dest / "成片" / mp4.name)
    for side in ("final.srt", "final-delivery.json"):
        src = out_dir / side
        if src.is_file():
            shutil.copy2(src, dest / "成片" / side)
    # clean stale intermediate copies from previous exports
    for stale in (dest / "成片").glob("*.mp4"):
        if stale.name not in ("film_final.mp4", "film_silent.mp4") and (
            "pre_" in stale.name or stale.name.endswith("_dual.mp4") or "里番" in stale.name
        ):
            try:
                stale.unlink()
            except OSError:
                pass
    # audio stems
    try:
        audio_export = safe_workspace_directory(dest, "音频", field="Desktop audio directory")
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc
    audio_export.mkdir(exist_ok=True)
    for audio in dirs["audio"].glob("*"):
        if audio.is_file():
            shutil.copy2(audio, audio_export / audio.name)
    for img in sorted(dirs["keyframes"].glob("*")):
        if img.is_file():
            shutil.copy2(img, dest / "关键帧" / img.name)
    for clip in sorted(dirs["clips"].glob("*")):
        if clip.is_file():
            shutil.copy2(clip, dest / "镜头片段" / clip.name)
    for can in sorted(dirs["canonical"].glob("*")):
        if can.is_file():
            shutil.copy2(can, dest / "定妆与场景" / can.name)
    for meta in EXPORT_METADATA_FILES:
        src = root / meta
        if src.is_file():
            shutil.copy2(src, dest / "简报" / meta)
    # pilot + compose pointers
    for pilot_name in ("pilot-approval.json", "pilot-scorecard.json"):
        src = root / "receipts" / pilot_name
        if src.is_file():
            shutil.copy2(src, dest / "项目状态" / pilot_name)
    for side in ("director_notes.json",):
        src = root / side
        if src.is_file():
            shutil.copy2(src, dest / "项目状态" / side)
    compose_preview = root / "compose" / "preview.json"
    if compose_preview.is_file():
        shutil.copy2(compose_preview, dest / "项目状态" / "compose-preview.json")
    shutil.copy2(root / MANIFEST_NAME, dest / "项目状态" / MANIFEST_NAME)

    readme = dest / "README.txt"
    silent = (manifest.get("outputs") or {}).get("silent_film") or {}
    final = (manifest.get("outputs") or {}).get("final_film") or {}
    readme.write_text(
        "\n".join(
            [
                f"{manifest.get('title', name)} · Grok Imagine 输出",
                "=" * 40,
                "",
                "【成片】先看这里（正式版优先）",
                f"  主文件目录: {dest / '成片'}",
                f"  final:  {final.get('path', '(尚未 final — 跑 aifilm_grok.py final)')}",
                f"  silent: {silent.get('path', '(尚未 assemble)')}",
                "",
                "【关键帧】keyframes",
                "【镜头片段】image_to_video clips",
                "【定妆与场景】canonical masters",
                "【音频】edge-tts 口白 + 配乐",
                "【简报】style-bible / film-spec / timeline / final-delivery.json",
                "",
                f"项目根: {root}",
                f"导出时间: {utc_now()}",
                "说明: motion 为 frame-1 I2V，非 first/last-frame；正式版含口白/字幕/BGM。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    manifest.setdefault("outputs", {})["desktop_dir"] = str(dest)
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    emit({"ok": True, "desktop_dir": str(dest), "main_film_dir": str(dest / "成片")})
    return 0


def cmd_frw_lipsync(args: argparse.Namespace) -> int:
    """FRW cloud lipsync (ltx/wan/seedance) — probe or run face+audio."""
    from frw_lipsync import FrwLipsyncError, probe_lipsync_models, run_frw_lipsync

    action = str(getattr(args, "frw_ls_action", None) or "probe")
    try:
        if action == "probe":
            rep = probe_lipsync_models()
            emit(rep)
            return 0 if rep.get("ok") else 1
        face = getattr(args, "face", None)
        audio = getattr(args, "audio", None)
        if not face or not audio:
            raise FilmError("frw-lipsync run requires --face and --audio")
        rep = run_frw_lipsync(
            face=Path(face),
            audio=Path(audio),
            out=Path(args.out) if getattr(args, "out", None) else None,
            root=Path(args.root) if getattr(args, "root", None) else None,
            shot_id=getattr(args, "shot_id", None),
            model=str(getattr(args, "model", None) or "auto"),
            prompt=str(getattr(args, "prompt", None) or ""),
            wait=not bool(getattr(args, "no_wait", False)),
            register=bool(getattr(args, "register", False)),
            poll_timeout=float(getattr(args, "poll_timeout", None) or 300),
        )
        emit(rep)
        return 0 if rep.get("ok") else 1
    except FrwLipsyncError as exc:
        raise FilmError(str(exc)) from exc


def cmd_env_plate(args: argparse.Namespace) -> int:
    """FRW LTX T2V env/no-face plate (+ first frame keyframe)."""
    from env_plate import EnvPlateError, run_env_plate

    try:
        rep = run_env_plate(
            prompt=str(args.prompt),
            root=Path(args.root).expanduser().resolve() if getattr(args, "root", None) else None,
            shot_id=getattr(args, "shot_id", None),
            wait=not bool(getattr(args, "no_wait", False)),
            width=str(getattr(args, "width", None) or "720"),
            height=str(getattr(args, "height", None) or "1280"),
            duration=str(getattr(args, "duration", None) or "5"),
            fps=str(getattr(args, "fps", None) or "24"),
            register=not bool(getattr(args, "no_register", False)),
            extract_keyframe=not bool(getattr(args, "no_keyframe", False)),
            out_dir=Path(args.out_dir) if getattr(args, "out_dir", None) else None,
            poll_timeout=float(getattr(args, "poll_timeout", None) or 240),
        )
    except EnvPlateError as exc:
        raise FilmError(str(exc)) from exc
    emit(rep)
    return 0 if rep.get("ok") else 1


def cmd_grok_oauth(args: argparse.Namespace) -> int:
    """Grok OAuth pack (chat/image/edit/video/tts) via ~/.grok/auth.json."""
    from grok_oauth import (
        GrokOAuthError,
        chat_completion,
        get_access_token,
        images_edit,
        images_generate,
        probe,
        tts_list_voices,
        tts_speak,
        video_generate,
        video_status,
        video_submit,
        video_wait,
    )

    action = str(getattr(args, "oauth_action", None) or "doctor")
    try:
        if action == "doctor":
            rep = probe(deep=bool(getattr(args, "deep", False)))
            emit(rep)
            return 0 if rep.get("ok") else 1
        if action == "refresh":
            tok = get_access_token(force_refresh=True, persist=True)
            emit(
                {
                    "ok": True,
                    "refreshed": tok.get("refreshed"),
                    "ttl_sec": tok.get("ttl_sec"),
                    "expires_at": tok.get("expires_at"),
                    "source": tok.get("source"),
                    "email": tok.get("email"),
                }
            )
            return 0
        if action == "chat":
            prompt = getattr(args, "prompt", None)
            if not prompt:
                raise FilmError("grok-oauth chat requires --prompt")
            emit(
                chat_completion(
                    str(prompt),
                    model=getattr(args, "model", None),
                    system=getattr(args, "system", None),
                    json_mode=bool(getattr(args, "json_mode", False)),
                )
            )
            return 0
        if action == "image":
            prompt = getattr(args, "prompt", None)
            out = getattr(args, "out", None)
            if not prompt or not out:
                raise FilmError("grok-oauth image requires --prompt and --out")
            emit(
                images_generate(
                    str(prompt),
                    out=Path(out),
                    model=getattr(args, "model", None),
                    aspect_ratio=getattr(args, "aspect", None) or "9:16",
                    resolution=getattr(args, "resolution", None),
                )
            )
            return 0
        if action == "image-edit":
            prompt = getattr(args, "prompt", None)
            image = getattr(args, "image", None)
            out = getattr(args, "out", None)
            if not prompt or not image or not out:
                raise FilmError("grok-oauth image-edit requires --image --prompt --out")
            refs = list(getattr(args, "ref", None) or []) or None
            emit(
                images_edit(
                    str(prompt),
                    image=str(image),
                    out=Path(out),
                    model=getattr(args, "model", None),
                    aspect_ratio=getattr(args, "aspect", None),
                    extra_images=refs,
                )
            )
            return 0
        if action == "video":
            prompt = getattr(args, "prompt", None)
            image = getattr(args, "image", None)
            out = getattr(args, "out", None)
            refs = list(getattr(args, "ref", None) or []) or None
            if getattr(args, "wait", False):
                if not out:
                    raise FilmError("grok-oauth video --wait requires --out")
                emit(
                    video_generate(
                        str(prompt) if prompt else None,
                        image=str(image) if image else None,
                        out=Path(out),
                        model=getattr(args, "model", None),
                        duration=int(getattr(args, "duration", 6) or 6),
                        aspect_ratio=getattr(args, "aspect", None) or "9:16",
                        resolution=getattr(args, "resolution", None) or "720p",
                        reference_images=refs,
                        timeout_sec=float(getattr(args, "timeout", 600) or 600),
                    )
                )
            else:
                emit(
                    video_submit(
                        str(prompt) if prompt else None,
                        image=str(image) if image else None,
                        model=getattr(args, "model", None),
                        duration=int(getattr(args, "duration", 6) or 6),
                        aspect_ratio=getattr(args, "aspect", None) or "9:16",
                        resolution=getattr(args, "resolution", None) or "720p",
                        reference_images=refs,
                    )
                )
            return 0
        if action == "video-status":
            rid = getattr(args, "request_id", None)
            if not rid:
                raise FilmError("grok-oauth video-status requires --request-id")
            out = getattr(args, "out", None)
            if getattr(args, "wait", False) or out:
                emit(
                    video_wait(
                        str(rid),
                        out=Path(out) if out else None,
                        timeout_sec=float(getattr(args, "timeout", 600) or 600),
                    )
                )
            else:
                emit(video_status(str(rid)))
            return 0
        if action == "tts":
            text = getattr(args, "text", None)
            text_file = getattr(args, "text_file", None)
            out = getattr(args, "out", None)
            if text_file:
                text = Path(str(text_file)).expanduser().read_text(encoding="utf-8")
            if not text or not out:
                raise FilmError("grok-oauth tts requires --text/--text-file and --out")
            emit(
                tts_speak(
                    str(text),
                    out=Path(out),
                    voice_id=getattr(args, "voice", None),
                    language=getattr(args, "language", None),
                    speed=getattr(args, "speed", None),
                    with_timestamps=bool(getattr(args, "timestamps", False)),
                )
            )
            return 0
        if action == "voices":
            emit(tts_list_voices())
            return 0
    except GrokOAuthError as exc:
        raise FilmError(str(exc)) from exc
    raise FilmError(f"unknown grok-oauth action {action!r}")


def cmd_graph(args: argparse.Namespace) -> int:
    """Vertical Drama Graph: legacy derive/import + canonical project/validate/status."""
    root = Path(args.root).expanduser().resolve()
    from drama_graph import derive_graph, graph_path, graph_status, validate_graph
    from narrative_control import (
        GRAPH_SCHEMA_VERSION,
        control_status,
        graph_content_sha256,
        graph_locked_for_projection,
        projection_status,
        draft_director_board,
    )
    action = str(getattr(args, "graph_action", "") or "")
    if action == "derive":
        existing = json.loads(graph_path(root).read_text(encoding="utf-8")) if graph_path(root).is_file() else {}
        if int(existing.get("schema_version") or 0) >= GRAPH_SCHEMA_VERSION:
            raise FilmError("canonical drama-graph exists; use aifilm graph project or plan edit, not graph derive")
        graph = derive_graph(root, write=not bool(getattr(args, "no_write", False)))
        v = validate_graph(graph)
        emit(
            {
                "ok": bool(v.get("ok")),
                "action": "derive",
                "path": str(graph_path(root)),
                "shot_count": v.get("shot_count"),
                "warnings": (graph.get("warnings") or []) + (v.get("warnings") or []),
                "errors": v.get("errors") or [],
                "project": graph.get("project"),
                "episode_count": len(graph.get("episodes") or []),
            }
        )
        return 0 if v.get("ok") else 1
    if action == "import":
        existing = (
            json.loads(graph_path(root).read_text(encoding="utf-8"))
            if graph_path(root).is_file()
            else {}
        )
        if int(existing.get("schema_version") or 0) >= GRAPH_SCHEMA_VERSION:
            raise FilmError("canonical drama-graph already exists; refusing legacy import overwrite")
        graph = derive_graph(root, write=False)
        spec = json.loads((root / "film-spec.json").read_text(encoding="utf-8")) if (root / "film-spec.json").is_file() else {}
        di = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
        graph["schema_version"] = GRAPH_SCHEMA_VERSION
        graph["derived_from"] = {**(graph.get("derived_from") or {}), "mode": "legacy-import", "imported_at": utc_now()}
        graph["story"] = {
            "premise": str(spec.get("description") or di.get("logline") or ""),
            "logline": str(di.get("logline") or spec.get("description") or ""),
            "theme": str(di.get("theme") or ""),
            "protagonist_ids": list(di.get("cast") or spec.get("cast_ids") or []),
            "protagonist_goal": str(di.get("protagonist_goal") or ""),
            "opposition": str(di.get("opposition") or ""),
            "stakes": str(di.get("stakes") or ""),
            "climax_choice": str(di.get("climax_choice") or ""),
            "ending_hook": str(di.get("ending_hook") or ""),
            "emotional_arc": list(di.get("emotional_arc") or []),
            "pace_chart": list(di.get("pace_chart") or []),
            "constraints": list(di.get("taboos") or []),
            "status": "needs_authoring",
        }
        for ep in graph.get("episodes") or []:
            for scene in ep.get("scenes") or []:
                for beat in scene.get("beats") or []:
                    if not isinstance(beat, dict):
                        continue
                    beat.setdefault("objective", "needs_authoring")
                    beat.setdefault("obstacle", "needs_authoring")
                    beat.setdefault("tactic", "needs_authoring")
                    beat.setdefault("turn", "needs_authoring")
                    beat.setdefault("outcome", "needs_authoring")
                    beat.setdefault("state_delta", "needs_authoring")
                    beat.setdefault("director_board", draft_director_board())
        from narrative_control import ensure_graph_controls
        ensure_graph_controls(graph)
        write_json(graph_path(root), graph)
        migration = {
            "schema_version": 1,
            "kind": "drama-graph-migration",
            "at": utc_now(),
            "source": "film-spec.json",
            "target": "drama-graph.json",
            "target_schema_version": GRAPH_SCHEMA_VERSION,
            "content_sha256": graph_content_sha256(graph),
            "note": "legacy import is draft-only; complete director_board and lock scopes before projection",
        }
        write_json(root / "receipts" / "graph-migration.json", migration)
        emit({"ok": True, "action": "import", "path": str(graph_path(root)), "receipt": str(root / "receipts" / "graph-migration.json"), "state": graph.get("state"), "content_sha256": graph_content_sha256(graph)})
        return 0
    if action == "project":
        graph = json.loads(graph_path(root).read_text(encoding="utf-8")) if graph_path(root).is_file() else {}
        if int(graph.get("schema_version") or 0) < GRAPH_SCHEMA_VERSION:
            raise FilmError("graph project requires canonical graph v2; run aifilm graph import first")
        ready = graph_locked_for_projection(graph)
        if not ready.get("ok"):
            raise FilmError("graph is not ready for projection: " + ", ".join(ready.get("missing_scopes") or [i.get("code", "NARRATIVE") for i in (ready.get("semantic") or {}).get("errors", [])]))
        from story_plan import project_graph_to_film_spec
        existing = json.loads((root / "film-spec.json").read_text(encoding="utf-8")) if (root / "film-spec.json").is_file() else {}
        has_shots = any(isinstance(sc, dict) and sc.get("shots") for sc in (existing.get("scenes") or []))
        if has_shots and not bool(getattr(args, "force", False)):
            raise FilmError("film-spec already has shots; pass --force to overwrite projection")
        norm_path = root / "receipts" / "story-normalize.json"
        norm = json.loads(norm_path.read_text(encoding="utf-8")) if norm_path.is_file() else None
        spec = project_graph_to_film_spec(graph, base_spec=existing, normalized=norm)
        write_json(root / "film-spec.json", spec)
        emit({"ok": True, "action": "project", "path": str(root / "film-spec.json"), "source_revision": graph.get("revision"), "source_sha256": graph_content_sha256(graph)})
        return 0
    if action == "validate":
        if bool(getattr(args, "derive_if_missing", False)) and not graph_path(root).is_file():
            derive_graph(root, write=True)
        report = validate_graph(root=root)
        report["narrative"] = control_status(root)
        report["action"] = "validate"
        report["path"] = str(graph_path(root))
        emit(report)
        return 0 if report.get("ok") else 1
    if action == "status":
        auto = bool(getattr(args, "derive_if_missing", True)) and not bool(
            getattr(args, "no_derive", False)
        )
        st = graph_status(root, auto_derive=auto)
        if bool(getattr(args, "with_jobs", False)):
            from drama_graph import build_jobs_summary

            st["jobs_summary"] = build_jobs_summary(root)
        st["control"] = control_status(root)
        st["projection"] = projection_status(root)
        emit(st)
        return 0 if st.get("ok") else 1
    raise FilmError(f"unknown graph action {action!r}")


def cmd_skill(args: argparse.Namespace) -> int:
    """Skill Registry: list | show (Phase 2 shell)."""
    from skill_registry import list_skills, show_skill

    action = str(getattr(args, "skill_action", "") or "")
    if action == "list":
        tag = getattr(args, "tag", None)
        phase = getattr(args, "phase", None)
        report = list_skills(tag=tag, phase=str(phase) if phase is not None else None)
        emit(report)
        return 0 if report.get("ok") else 1
    if action == "show":
        sid = getattr(args, "id", None) or getattr(args, "skill_id", None)
        if not sid:
            raise FilmError("skill show requires --id")
        report = show_skill(str(sid))
        emit(report)
        return 0 if report.get("ok") else 1
    raise FilmError(f"unknown skill action {action!r}")


def cmd_assets(args: argparse.Namespace) -> int:
    """Phase 4: structured Character/Location/Prop + CharacterState ↔ state-index."""
    from asset_registry import assets_check, assets_status, sync_assets

    action = str(getattr(args, "assets_action", "") or "")
    root_s = getattr(args, "root", None)
    if not root_s:
        raise FilmError("assets requires --root")
    root = Path(root_s).expanduser().resolve()

    if action == "sync":
        report = sync_assets(
            root,
            write=not bool(getattr(args, "no_write", False)),
            force=bool(getattr(args, "force", False)),
            update_graph=not bool(getattr(args, "no_graph", False)),
        )
        emit(report)
        return 0 if report.get("ok") else 1
    if action == "status":
        report = assets_status(root, auto_sync=bool(getattr(args, "sync", False)))
        emit(report)
        return 0 if report.get("ok") else 1
    if action == "check":
        report = assets_check(
            root,
            sync_first=not bool(getattr(args, "no_sync", False)),
        )
        emit(report)
        return 0 if report.get("ok") else 1
    raise FilmError(f"unknown assets action {action!r}")


def cmd_plan(args: argparse.Namespace) -> int:
    """Phase 3: story.normalize → beat/shot plan → drama-graph (+ film-spec seed)."""
    from story_plan import (
        normalize_story,
        plan_status,
        project_graph_to_film_spec,
        run_plan,
    )
    from drama_graph import GRAPH_NAME, validate_graph
    from narrative_control import (
        NarrativeControlError,
        control_status,
        edit_node,
        graph_locked_for_projection,
        mark_replan,
        unlock_scope,
        lock_scope,
        write_revision_receipt,
        validate_narrative_graph,
    )
    from util import read_json, write_json

    action = str(getattr(args, "plan_action", "") or "")

    def _load_text() -> str:
        text = getattr(args, "text", None)
        file_p = getattr(args, "file", None)
        if file_p:
            p = Path(str(file_p)).expanduser().resolve()
            if not p.is_file():
                raise FilmError(f"plan source file not found: {p}")
            return p.read_text(encoding="utf-8")
        if text is not None and str(text).strip():
            return str(text)
        raise FilmError("plan requires --text or --file")

    if action == "normalize":
        raw = _load_text()
        root_s = getattr(args, "root", None)
        norm = normalize_story(
            raw,
            title_hint=getattr(args, "title", None),
            source_path=str(getattr(args, "file", None) or ""),
        )
        if root_s:
            root = Path(root_s).expanduser().resolve()
            root.mkdir(parents=True, exist_ok=True)
            (root / "receipts").mkdir(parents=True, exist_ok=True)
            out = root / "receipts" / "story-normalize.json"
            write_json(out, norm)
            emit({"ok": True, "action": "normalize", "path": str(out), "story": norm})
        else:
            emit({"ok": True, "action": "normalize", "story": norm})
        return 0

    if action == "run":
        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan run requires --root")
        root = Path(root_s).expanduser().resolve()
        raw = _load_text()
        report = run_plan(
            root,
            raw,
            title=getattr(args, "title", None),
            target_duration=float(getattr(args, "target_duration", 45) or 45),
            apply_film_spec=bool(getattr(args, "apply_film_spec", False)) and not bool(getattr(args, "no_film_spec", False)),
            force=bool(getattr(args, "force", False)),
            source_path=str(getattr(args, "file", None) or ""),
            seed_bible=not bool(getattr(args, "no_bible", False)),
        )
        emit(report)
        return 0 if report.get("ok") else 1

    if action == "validate":
        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan validate requires --root")
        root = Path(root_s).expanduser().resolve()
        status = control_status(root)
        # Copy the semantic summary before attaching the full control status;
        # otherwise report['control']['semantic'] points back into report and
        # json.dumps() fails with a circular-reference error.
        strict_requested = bool(getattr(args, "strict", False))
        if strict_requested and (root / GRAPH_NAME).is_file():
            report = validate_narrative_graph(read_json(root / GRAPH_NAME), strict=True)
        else:
            report = dict(status.get("semantic") or {"ok": False, "issues": [{"code": "GRAPH_MISSING"}]})
        report["strict_requested"] = strict_requested
        report.update({"action": "validate", "root": str(root), "control": status})
        emit(report)
        return 0 if report.get("ok") else 1

    if action in {"edit", "lock", "unlock", "replan"}:
        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError(f"plan {action} requires --root")
        root = Path(root_s).expanduser().resolve()
        graph_path = root / GRAPH_NAME
        graph = read_json(graph_path)
        if not graph:
            raise FilmError(f"missing {graph_path} — run: aifilm plan run --root …")
        try:
            if action == "edit":
                changes: dict[str, Any] = {}
                for item in list(getattr(args, "set", None) or []):
                    if "=" not in item:
                        raise NarrativeControlError(f"--set requires field=value: {item}", code="INVALID_FIELD")
                    field, raw_value = item.split("=", 1)
                    try:
                        value: Any = json.loads(raw_value)
                    except json.JSONDecodeError:
                        value = raw_value
                    if str(getattr(args, "node", "")) == "story" and field.startswith("story."):
                        field = field.split(".", 1)[1]
                    changes[field] = value
                graph, affected = edit_node(graph, str(args.node), changes)
                write_json(graph_path, graph)
                receipt = write_revision_receipt(root, graph, action="edit", node_ref=str(args.node), affected=affected)
                emit({"ok": True, "action": action, "revision": graph.get("revision"), "affected_nodes": affected, "receipt_path": str(receipt)})
                return 0
            if action == "lock":
                graph = lock_scope(graph, str(args.scope), user_phrase=str(args.user_phrase))
                write_json(graph_path, graph)
                receipt = write_revision_receipt(root, graph, action="lock", reason=str(args.user_phrase))
                emit({"ok": True, "action": action, "scope": args.scope, "revision": graph.get("revision"), "receipt_path": str(receipt)})
                return 0
            if action == "unlock":
                graph = unlock_scope(graph, str(args.scope), reason=str(args.reason))
                write_json(graph_path, graph)
                receipt = write_revision_receipt(root, graph, action="unlock", reason=str(args.reason))
                emit({"ok": True, "action": action, "scope": args.scope, "revision": graph.get("revision"), "receipt_path": str(receipt)})
                return 0
            if not bool(getattr(args, "descendants", False)):
                raise NarrativeControlError("replan requires --descendants to confirm subtree invalidation", code="DESCENDANTS_CONFIRM_REQUIRED")
            affected = mark_replan(graph, str(args.node))
            write_json(graph_path, graph)
            receipt = write_revision_receipt(root, graph, action="replan", node_ref=str(args.node), affected=affected)
            emit({"ok": True, "action": action, "revision": graph.get("revision"), "affected_nodes": affected, "receipt_path": str(receipt)})
            return 0
        except NarrativeControlError as exc:
            raise FilmError(f"{exc.code}: {exc}") from exc

    if action == "project":
        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan project requires --root")
        root = Path(root_s).expanduser().resolve()
        gpath = root / GRAPH_NAME
        graph = read_json(gpath)
        if not graph:
            raise FilmError(f"missing {gpath} — run: aifilm plan run --root …")
        force = bool(getattr(args, "force", False))
        existing = read_json(root / "film-spec.json") or {}
        has_shots = any(
            isinstance(sc, dict) and sc.get("shots")
            for sc in (existing.get("scenes") or [])
        )
        if has_shots and not force:
            emit(
                {
                    "ok": False,
                    "error": "film-spec already has shots; pass --force to overwrite",
                }
            )
            return 1
        norm = read_json(root / "receipts" / "story-normalize.json")
        ready = graph_locked_for_projection(graph)
        if not ready.get("ok"):
            emit({"ok": False, "action": "project", "error": "graph is not ready for projection", "missing_scopes": ready.get("missing_scopes"), "semantic": ready.get("semantic")})
            return 1
        spec = project_graph_to_film_spec(graph, base_spec=existing, normalized=norm)
        write_json(root / "film-spec.json", spec)
        v = validate_graph(graph)
        emit(
            {
                "ok": True,
                "action": "project",
                "path": str(root / "film-spec.json"),
                "graph_ok": bool(v.get("ok")),
                "shot_count": v.get("shot_count"),
                "next": f'aifilm write-spec --root "{root}"',
            }
        )
        return 0

    if action == "status":
        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan status requires --root")
        emit(plan_status(Path(root_s)))
        return 0

    raise FilmError(f"unknown plan action {action!r}")


def cmd_dispatch(args: argparse.Namespace) -> int:
    """Auto-orchestrate: craft + capability + next → single agent packet."""
    root = Path(args.root).expanduser().resolve()
    from dispatch import build_dispatch

    gates: dict[str, Any] = {}
    open_n = 0
    if (root / MANIFEST_NAME).is_file():
        man = load_manifest(root)
        summary = recompute_gates(root, man)
        gates = summary.get("gates") or {}
        open_n = int(summary.get("open_reshoot_count") or 0)
        save_manifest(root, man)

    packet = build_dispatch(
        root,
        gates=gates,
        open_reshoot_count=open_n,
        include_capability=not bool(getattr(args, "no_capability", False)),
        write_receipt=not bool(getattr(args, "no_write", False)),
    )

    # Keep pipeline HUD in sync
    try:
        from next_actions import detect_pipeline_stage, persist_pipeline_stage

        pipeline = detect_pipeline_stage(root, gates=gates, open_reshoot_count=open_n)
        persist_pipeline_stage(
            root,
            pipeline,
            next_cmd=packet.get("next_cmd"),
            next_id=packet.get("next_id"),
        )
    except Exception:
        pass

    if bool(getattr(args, "print_cmd_only", False)):
        print(packet.get("next_cmd") or "")
        return 0 if packet.get("next_cmd") else 1
    if bool(getattr(args, "print_instruction", False)):
        print(packet.get("agent_instruction") or "")
        return 0

    emit(packet)
    return 0 if packet.get("ok") else 1


def cmd_craft(args: argparse.Namespace) -> int:
    """Craft spine status (idea→verified)."""
    root_s = getattr(args, "root", None)
    if not root_s:
        raise FilmError("craft requires --root")
    root = Path(root_s).expanduser().resolve()
    from craft_spine import craft_status_report

    gates: dict[str, Any] = {}
    if (root / MANIFEST_NAME).is_file():
        man = load_manifest(root)
        summary = recompute_gates(root, man)
        gates = summary.get("gates") or {}
    report = craft_status_report(root, gates=gates)
    emit(report)
    return 0


def cmd_selects(args: argparse.Namespace) -> int:
    root_s = getattr(args, "root", None)
    if not root_s:
        raise FilmError("selects requires --root")
    root = Path(root_s).expanduser().resolve()
    from selects_report import build_selects_report

    report = build_selects_report(root, write_receipt=not bool(getattr(args, "no_write", False)))
    emit(report)
    return 0 if report.get("ok") or report.get("planned") == 0 else 1


def cmd_audio_plan(args: argparse.Namespace) -> int:
    from audio_plan import build_audio_plan

    root = Path(args.root).expanduser().resolve()
    emit(build_audio_plan(root))
    return 0


def cmd_lipsync_canary(args: argparse.Namespace) -> int:
    from lipsync_canary import LipsyncCanaryError, run_lipsync_canary

    root = Path(args.root).expanduser().resolve()
    try:
        report = run_lipsync_canary(
            root,
            shot_id=str(args.shot_id),
            backend=str(getattr(args, "backend", None) or "auto"),
            video=Path(args.video).expanduser() if getattr(args, "video", None) else None,
            audio=Path(args.audio).expanduser() if getattr(args, "audio", None) else None,
        )
    except LipsyncCanaryError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    # not ready unlock path is soft fail (exit 1) but not crash
    return 0 if report.get("ok") else 1


def cmd_capability(args: argparse.Namespace) -> int:
    """One-page readiness: TTS / FRW canary summary / optional i2v suggest+apply."""
    from capability_report import CapabilityError, build_capability_report

    root = None
    if getattr(args, "root", None):
        root = Path(args.root).expanduser().resolve()
    try:
        report = build_capability_report(
            root=root,
            run_canary=bool(getattr(args, "run_canary", False)),
            suggest_i2v=bool(getattr(args, "suggest_i2v", False))
            or bool(getattr(args, "apply", False)),
            apply=bool(getattr(args, "apply", False)),
            canary_wait=bool(getattr(args, "canary_wait", False)),
            canary_full=bool(getattr(args, "canary_full", False)),
        )
    except CapabilityError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0 if report.get("ok") else 1


def cmd_tts_ab(args: argparse.Namespace) -> int:
    """A/B TTS for one shot → receipts/tts-ab/ (does not change film-spec)."""
    from tts_ab import TTSAbError, run_tts_ab

    backends = [b.strip() for b in str(getattr(args, "backends", "edge,voicebox")).split(",") if b.strip()]
    try:
        man = run_tts_ab(
            Path(args.root).expanduser().resolve(),
            shot_id=str(args.shot_id),
            backends=backends,
            voice=getattr(args, "voice", None),
            text=getattr(args, "text", None),
            spec_path=Path(args.spec).expanduser().resolve() if getattr(args, "spec", None) else None,
        )
    except TTSAbError as exc:
        raise FilmError(str(exc)) from exc
    emit(man)
    return 0 if man.get("ok") else 1


def cmd_tts_rehearse(args: argparse.Namespace) -> int:
    """Probe real VO durations into receipts/tts-rehearsal.json (before bulk or final)."""
    root = Path(args.root).expanduser().resolve()
    try:
        from tts_rehearsal import TTSRehearsalError, register_measured_durations, run_rehearsal
    except ImportError as exc:
        raise FilmError(f"tts_rehearsal unavailable: {exc}") from exc

    try:
        if getattr(args, "register_json", None):
            reg_path = Path(args.register_json).expanduser().resolve()
            data = read_json(reg_path)
            if isinstance(data, dict) and isinstance(data.get("shots"), list):
                items = data["shots"]
            elif isinstance(data, list):
                items = data
            else:
                # read_json always returns dict for non-list files; support raw list
                raw = json.loads(reg_path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    items = raw
                elif isinstance(raw, dict) and isinstance(raw.get("shots"), list):
                    items = raw["shots"]
                else:
                    raise FilmError("register-json must be a list or {shots: [...]}")
            # path map vs pure duration register
            if items and all(isinstance(x, dict) and x.get("path") for x in items):
                register_map = {
                    str(x["shot_id"]): Path(str(x["path"])) for x in items if isinstance(x, dict)
                }
                receipt = run_rehearsal(
                    root,
                    spec_path=Path(args.spec).expanduser().resolve() if args.spec else None,
                    backend=getattr(args, "tts_backend", None) or getattr(args, "backend", None),
                    voice=str(getattr(args, "voice", None) or "zh-CN-XiaoxiaoNeural"),
                    register_map=register_map,
                    synthesize=False,
                )
            else:
                receipt = register_measured_durations(
                    root,
                    items,
                    source="register",
                    backend=getattr(args, "tts_backend", None) or getattr(args, "backend", None),
                )
        else:
            if bool(getattr(args, "no_synthesize", False)):
                raise FilmError("--no-synthesize requires --register-json")
            receipt = run_rehearsal(
                root,
                spec_path=Path(args.spec).expanduser().resolve() if args.spec else None,
                backend=getattr(args, "tts_backend", None) or getattr(args, "backend", None),
                voice=str(getattr(args, "voice", None) or "zh-CN-XiaoxiaoNeural"),
                synthesize=True,
            )
    except TTSRehearsalError as exc:
        raise FilmError(str(exc)) from exc

    emit(receipt)
    return 0 if receipt.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aifilm_grok", description="ai-film-grok local control plane")
    sub = p.add_subparsers(dest="cmd", required=True)

    doctor = sub.add_parser("doctor", help="Check tooling, locks, schema, backends, and security posture")
    doctor.add_argument("--strict", action="store_true", help="Also fail on global security warnings")
    sub.add_parser("lock-runtime", help="Fingerprint the current verified Python/FFmpeg/script runtime")

    fls = sub.add_parser(
        "frw-lipsync",
        help="FRW cloud lipsync (ltx/wan/seedance 音画同步); probe first — often 403/502",
    )
    fls.add_argument(
        "frw_ls_action",
        nargs="?",
        default="probe",
        choices=["probe", "run"],
        help="probe (default) or run",
    )
    fls.add_argument("--face", default=None, help="Face/still image path")
    fls.add_argument("--audio", default=None, help="VO wav/mp3 path")
    fls.add_argument("--out", default=None)
    fls.add_argument("--root", default=None)
    fls.add_argument("--shot-id", default=None)
    fls.add_argument(
        "--model",
        default="auto",
        choices=["auto", "ltx-lipsync", "wan-lipsync", "seedance-2-pro-lipsync"],
    )
    fls.add_argument("--prompt", default="")
    fls.add_argument("--no-wait", action="store_true")
    fls.add_argument("--register", action="store_true")
    fls.add_argument("--poll-timeout", type=float, default=300)

    envp = sub.add_parser(
        "env-plate",
        help="FRW LTX T2V env/no-face plate (unlimited FRW) → clip + first keyframe",
    )
    envp.add_argument("--prompt", required=True)
    envp.add_argument("--root", default=None, help="Film root (optional register/receipts)")
    envp.add_argument("--shot-id", default=None)
    envp.add_argument("--no-wait", action="store_true")
    envp.add_argument("--width", default="720")
    envp.add_argument("--height", default="1280")
    envp.add_argument("--duration", default="5")
    envp.add_argument("--fps", default="24")
    envp.add_argument("--no-register", action="store_true")
    envp.add_argument("--no-keyframe", action="store_true")
    envp.add_argument("--out-dir", default=None)
    envp.add_argument("--poll-timeout", type=float, default=240)

    goauth = sub.add_parser(
        "grok-oauth",
        help=(
            "Grok OAuth pack (auth.json): doctor|refresh|chat|image|image-edit|"
            "video|video-status|tts|voices"
        ),
    )
    goauth.add_argument(
        "oauth_action",
        nargs="?",
        default="doctor",
        choices=[
            "doctor",
            "refresh",
            "chat",
            "image",
            "image-edit",
            "video",
            "video-status",
            "tts",
            "voices",
        ],
    )
    goauth.add_argument("--prompt", default=None)
    goauth.add_argument("--out", default=None, help="output path (image/video/tts)")
    goauth.add_argument("--model", default=None)
    goauth.add_argument("--system", default=None)
    goauth.add_argument("--aspect", default="9:16")
    goauth.add_argument("--deep", action="store_true", help="doctor: also probe TTS voices")
    goauth.add_argument("--json", action="store_true", dest="json_mode", help="chat: JSON mode")
    goauth.add_argument("--image", default=None, help="input still for image-edit / video I2V")
    goauth.add_argument("--ref", action="append", default=[], help="extra reference image(s)")
    goauth.add_argument("--duration", type=int, default=6, help="video duration seconds")
    goauth.add_argument(
        "--resolution",
        default=None,
        help="video: 480p|720p|1080p; image: 1k|2k",
    )
    goauth.add_argument("--wait", action="store_true", help="video: poll until done")
    goauth.add_argument("--timeout", type=float, default=600.0, help="video poll timeout sec")
    goauth.add_argument("--request-id", default=None, dest="request_id")
    goauth.add_argument("--text", default=None, help="tts text")
    goauth.add_argument("--text-file", default=None, dest="text_file")
    goauth.add_argument("--voice", default=None, help="tts voice_id (default eve)")
    goauth.add_argument("--language", default=None, help="tts language (default zh)")
    goauth.add_argument("--speed", type=float, default=None, help="tts speed 0.7–1.5")
    goauth.add_argument("--timestamps", action="store_true", help="tts character timestamps")
    disp = sub.add_parser(
        "dispatch",
        help="AUTO orchestrate: craft ring + capability + next_cmd (agent primary entry)",
    )
    disp.add_argument("--root", required=True)
    disp.add_argument("--print-cmd-only", action="store_true", help="Only print next shell command")
    disp.add_argument(
        "--print-instruction",
        action="store_true",
        help="Only print agent_instruction checklist",
    )
    disp.add_argument("--no-capability", action="store_true", help="Skip capability probe (faster)")
    disp.add_argument("--no-write", action="store_true", help="Do not write receipts/dispatch.json")

    craft_p = sub.add_parser(
        "craft",
        help="Craft spine status (idea→story→beats→shots→media→selects→rough→verified)",
    )
    craft_p.add_argument("--root", required=True)
    craft_p.add_argument(
        "craft_action",
        nargs="?",
        default="status",
        choices=["status"],
        help="status (default)",
    )

    sel_p = sub.add_parser("selects", help="Selects ring: planned shots vs approved clips")
    sel_p.add_argument("--root", required=True)
    sel_p.add_argument(
        "selects_action",
        nargs="?",
        default="report",
        choices=["report"],
        help="report (default)",
    )
    sel_p.add_argument("--no-write", action="store_true", help="Do not write selects-report.json")

    ap = sub.add_parser("audio-plan", help="Dry-run TTS/BGM/lipsync plan (no render)")
    ap.add_argument("--root", required=True)

    lsc = sub.add_parser(
        "lipsync-canary",
        help="Single-shot lipsync probe → receipts/lipsync-canary/ (default final still lipsync off)",
    )
    lsc.add_argument("--root", required=True)
    lsc.add_argument("--shot", "--shot-id", dest="shot_id", required=True)
    lsc.add_argument("--backend", default="auto")
    lsc.add_argument("--video", default=None)
    lsc.add_argument("--audio", default=None)

    cap = sub.add_parser(
        "capability",
        help="One-page readiness (TTS/BGM/lipsync/tools + optional FRW canary / i2v suggest)",
    )
    cap.add_argument("--root", default=None, help="Film root (reads frw canary receipt + film-spec)")
    cap.add_argument(
        "--run-canary",
        action="store_true",
        help="Hit FRW API canary and write receipts/frw-key-capability.json (costs credits)",
    )
    cap.add_argument("--canary-wait", action="store_true", help="With --run-canary: poll ltx-t2v")
    cap.add_argument("--canary-full", action="store_true", help="With --run-canary: full template probes")
    cap.add_argument(
        "--suggest-i2v",
        action="store_true",
        help="From canary receipt, suggest i2v_provider / frw_* patch (no write unless --apply)",
    )
    cap.add_argument(
        "--apply",
        action="store_true",
        help="Opt-in: write suggested i2v fields into film-spec.json (then re-run write-spec)",
    )

    tab = sub.add_parser(
        "tts-ab",
        help="A/B TTS same nar through multiple backends → receipts/tts-ab/ (no film-spec change)",
    )
    tab.add_argument("--root", required=True)
    tab.add_argument("--shot", "--shot-id", dest="shot_id", required=True)
    tab.add_argument(
        "--backends",
        default="edge,voicebox",
        help="Comma-separated backends (default: edge,voicebox)",
    )
    tab.add_argument("--voice", default=None)
    tab.add_argument("--text", default=None, help="Override shot nar")
    tab.add_argument("--spec", default=None)

    init_p = sub.add_parser("init", help="Create film root")
    init_p.add_argument("--theme", required=True)
    init_p.add_argument("--title", required=True)
    init_p.add_argument("--root", required=True)
    init_p.add_argument("--aspect", default="9:16")
    init_p.add_argument("--force", action="store_true")

    st = sub.add_parser("status", help="Gate status")
    st.add_argument("--root", required=True)

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

    ws = sub.add_parser("write-spec", help="Validate and write film-spec + seed timeline")
    ws.add_argument("--root", required=True)
    ws.add_argument("--spec", help="Path to film-spec JSON (default root/film-spec.json)")

    ls = sub.add_parser("lock-style", help="Lock style bible")
    ls.add_argument("--root", required=True)
    ls.add_argument("--canonical", help="Path to approved style master image")
    ls.add_argument("--cast-master", help="Path to approved cast master (face/wardrobe lock)")
    ls.add_argument("--signature", help="Override signature block (≥40 chars)")

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
    rs.add_argument(
        "--identity-approved",
        action="store_true",
        help="Required when --status approved: still matches cast master",
    )
    rs.add_argument(
        "--review-note",
        help="Required when --status approved: brief visual review note",
    )

    rc = sub.add_parser("register-clip", help="Register approved I2V clip")
    rc.add_argument("--root", required=True)
    rc.add_argument("--shot-id", required=True)
    rc.add_argument("--source", required=True)
    rc.add_argument("--status", default="approved")
    rc.add_argument("--prompt-file")
    rc.add_argument("--source-endpoint", choices=sorted(ALLOWED_VIDEO_ENDPOINTS))
    rc.add_argument("--identity-approved", action="store_true")
    rc.add_argument("--motion-approved", action="store_true")
    rc.add_argument("--review-note")
    rc.add_argument("--review-receipt", help="v1.6 approved review receipt (defaults to receipts/reviews/<shot>.json)")

    shot_review = sub.add_parser("review-shot", help="Create evidence-backed first/middle/last-frame director review for one clip")
    shot_review.add_argument("--root", required=True)
    shot_review.add_argument("--shot-id", required=True)
    shot_review.add_argument("--source", required=True)
    shot_review.add_argument("--approve", action="store_true", help="Approve only if QA, 1–5 scores, and timestamp evidence all pass")
    shot_review.add_argument("--reviewer", required=True)
    shot_review.add_argument("--notes", required=True)
    for dim in ("identity", "continuity", "composition", "motion", "narrative"):
        shot_review.add_argument(f"--score-{dim}", type=int, choices=range(1, 6), required=True, dest=f"score_{dim}")
    shot_review.add_argument("--evidence", action="append", default=[], help="Repeat dimension@seconds:note for every review dimension")
    shot_review.add_argument("--reference", action="append", default=[], help="Optional reference asset path; repeatable")

    review_contract = sub.add_parser("review-contract", help="Explicitly migrate a legacy film root to v1.6 review evidence gates")
    review_contract_sub = review_contract.add_subparsers(dest="review_contract_action", required=True)
    review_contract_migrate = review_contract_sub.add_parser("migrate", help="Require real shot reviews for historical approved clips")
    review_contract_migrate.add_argument("--root", required=True)

    asb = sub.add_parser("assemble", help="Assemble silent film from timeline + clips")
    asb.add_argument("--root", required=True)
    asb.add_argument("--out-name", default="film_silent.mp4")

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

    fin = sub.add_parser("final", help="Render formal final: edge-tts VO + BGM + burned Chinese subs")
    fin.add_argument("--root", required=True)
    fin.add_argument("--out-name", default="film_final.mp4")
    fin.add_argument("--transition-sec", type=float, default=None, help="Inter-shot xfade seconds")
    fin.add_argument(
        "--allow-loop-risk",
        action="store_true",
        help="Allow final when VO would stream_loop short plates (discouraged); does NOT skip measured over-plate",
    )
    fin.add_argument(
        "--strict-tts-rehearsal",
        action="store_true",
        help="Require receipts/tts-rehearsal.json before final; measured VO preferred for pacing",
    )
    fin.add_argument(
        "--vo-fit",
        default=None,
        choices=["atempo", "legacy"],
        help="slot mode: atempo=VO speed to plate (default three-axis); legacy=old pad/stretch",
    )
    fin.add_argument("--voice", default=None, help="edge voice or provider voice id; default comes from film-spec")
    fin.add_argument(
        "--tts-backend",
        default=None,
        choices=["auto", "minimax", "fish", "edge", "external"],
        help="auto: external > MiniMax > pinned Fish > edge",
    )
    fin.add_argument("--vo-rate", default=None)
    fin.add_argument("--vo-pitch", default=None)
    fin.add_argument("--vo-gain", type=float, default=None)
    fin.add_argument(
        "--vocal-color-gain",
        type=float,
        default=None,
        help="Independent 娇喘/语助词 track gain (0..1.5; film-spec voice_tracks.vocal_color_gain)",
    )
    fin.add_argument("--title")
    fin.add_argument("--end-title")
    fin.add_argument("--music", help="External BGM file (overrides audio/bgm.wav templates)")
    fin.add_argument(
        "--music-license",
        help="License note; or place audio/*.license.txt beside the file",
    )
    fin.add_argument(
        "--music-template",
        default=None,
        choices=["off", "auto", "on"],
        help="Local BGM: auto=use audio/bgm.wav or audio/templates/{mood}.* if present; on=require; off=procedural",
    )
    fin.add_argument(
        "--music-volume",
        type=float,
        default=0.52,
        help="BGM mix gain once; ~0.45-0.58 dual-track (VO clear + BGM audible)",
    )
    fin.add_argument(
        "--native-audio-volume",
        type=float,
        default=None,
        help="Mix gain for generated clip audio preserved as native stems (default from film-spec or 0.16)",
    )
    fin.add_argument(
        "--music-mood",
        default="rnb",
        help="playful|dark|warm|rnb|sensual|soul — 色气默认 rnb (seductive R&B/Soul；勿对里番用 dark)",
    )
    fin.add_argument(
        "--music-seed",
        type=int,
        default=None,
        help="Procedural BGM seed (change for a new anti-fatigue take; default = hash of title)",
    )
    fin.add_argument(
        "--sidechain-threshold",
        type=float,
        default=None,
        help="VO→BGM sidechain threshold (rnb default 0.07)",
    )
    fin.add_argument(
        "--sidechain-ratio",
        type=float,
        default=None,
        help="VO→BGM sidechain ratio (rnb default 3.2)",
    )
    fin.add_argument(
        "--sidechain-attack",
        type=float,
        default=None,
        help="Sidechain attack ms (rnb default 15)",
    )
    fin.add_argument(
        "--sidechain-release",
        type=float,
        default=None,
        help="Sidechain release ms — higher = BGM returns slower in VO pauses (rnb default 720)",
    )
    fin.add_argument(
        "--loudnorm",
        default=None,
        choices=["off", "auto", "on"],
        help="Mix loudness: auto (default, only if too loud/quiet) | on | off",
    )
    fin.add_argument(
        "--target-lufs",
        type=float,
        default=None,
        help="loudnorm target LUFS (default -16 shortform)",
    )
    fin.add_argument(
        "--lipsync",
        default="off",
        choices=["auto", "off", "require", "external", "musetalk", "wav2lip"],
        help="Lip-sync OFF by default (Wav2Lip often warps faces). Use auto only when quality is acceptable.",
    )
    fin.add_argument("--sub-lead", type=float, default=0.08, help="Show subtitles early (seconds)")
    fin.add_argument("--sub-max-unit", type=float, default=1.75, help="Max seconds per subtitle line")
    fin.add_argument("--sub-max-chars", type=int, default=14, help="Max Chinese chars per line")
    fin.add_argument(
        "--title-dur",
        type=float,
        default=1.5,
        help="Title pad seconds (designed-post keeps pad; glyphs only if --plate-cards text)",
    )
    fin.add_argument(
        "--end-dur",
        type=float,
        default=None,
        help="End card pad seconds (default: render_final 1.6; designed-post still draws 完)",
    )
    fin.add_argument(
        "--plate-cards",
        choices=["text", "blank", "auto"],
        default="auto",
        help="auto: blank under hyperframes/remotion, text under ffmpeg; blank=pad only no glyphs",
    )
    fin.add_argument(
        "--post-engine",
        default="ffmpeg",
        choices=["ffmpeg", "hyperframes", "remotion"],
        help=(
            "ffmpeg=default burn delivery; hyperframes|remotion=FFmpeg VO/BGM "
            "(subs off) then designed captions render+register"
        ),
    )
    fin.add_argument(
        "--subs",
        default=None,
        choices=["burn", "off"],
        help="burn|off (default: burn for ffmpeg, off for hyperframes|remotion post-engine)",
    )
    fin.add_argument(
        "--compose-quality",
        default="standard",
        choices=["draft", "standard", "high"],
        help="HyperFrames render quality when --post-engine hyperframes",
    )
    fin.add_argument(
        "--compose-preset",
        default="auto",
        choices=["auto", "ecchi-rnb", "minimal"],
        help="Designed-post title/caption look: auto (from mood/tone) | ecchi-rnb | minimal",
    )
    fin.add_argument(
        "--title-sequence",
        default=None,
        choices=["auto", "none"],
        help="Override film-spec title_sequence mode (auto=spec/default, none=suppress)",
    )
    fin.add_argument(
        "--end-roll",
        default=None,
        choices=["auto", "none", "cast_only", "full"],
        help="Override film-spec end_roll mode (auto=spec/default, none=suppress)",
    )
    fin.add_argument(
        "--require-preview",
        action="store_true",
        help="With designed-post: require receipts/compose-preview.json first",
    )
    fin.add_argument(
        "--npm-install",
        action="store_true",
        help="With --post-engine remotion: run npm install once before render (network)",
    )
    fin.add_argument(
        "--npm-install-timeout",
        type=int,
        default=900,
        help="Seconds for remotion --npm-install (default 900)",
    )
    fin.add_argument(
        "--allow-burned-underlay",
        action="store_true",
        help="Allow underlay when plate already has burned-in captions (double-burn risk)",
    )
    fin.add_argument(
        "--skip-compose-check",
        action="store_true",
        help="Skip hyperframes check before render (not recommended)",
    )
    fin.add_argument(
        "--keep-compose-raw",
        action="store_true",
        help="Keep out/film_*_raw.mp4 when using designed-post engines",
    )
    fin.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip lesson preflight hard gates before final (not recommended)",
    )
    fin.add_argument(
        "--preflight-strict",
        action="store_true",
        help="Also block final on preflight soft warnings",
    )

    review = sub.add_parser(
        "review-final",
        help="Record explicit end-to-end final-film approval with director scorecard",
    )
    review.add_argument("--root", required=True)
    review.add_argument("--approve", action="store_true")
    review.add_argument("--reviewer", required=True)
    review.add_argument("--notes", required=True)
    for dim in SCORECARD_DIMENSIONS:
        flag = f"--score-{dim.replace('_', '-')}"
        review.add_argument(
            flag,
            choices=["pass", "fail"],
            default=None,
            dest=f"score_{dim}",
            help=f"Director scorecard dimension '{dim}' (required with --approve)",
        )
    review.add_argument(
        "--reshoot-shots",
        default="",
        help="Comma-separated shot ids to attach to identity/style/motion/escalation fails (writes director_notes)",
    )
    review.add_argument("--screening-evidence", action="append", default=[], help="v1.6: repeat dimension@seconds:note for each final scorecard dimension")

    dn = sub.add_parser(
        "director-notes",
        help="List/add/resolve director reshoot notes (scorecard fail loop)",
    )
    dn_sub = dn.add_subparsers(dest="notes_cmd", required=True)
    dn_list = dn_sub.add_parser("list", help="Show open and all reshoot items")
    dn_list.add_argument("--root", required=True)
    dn_add = dn_sub.add_parser("add", help="Add a reshoot/recut item")
    dn_add.add_argument("--root", required=True)
    dn_add.add_argument("--action", required=True, choices=["keep", "reshoot", "recut"])
    dn_add.add_argument(
        "--reason",
        required=True,
        choices=[
            "identity",
            "style",
            "motion",
            "escalation",
            "audio",
            "subs",
            "dead_air",
            "other",
            "continuity",
            "performance",
        ],
    )
    dn_add.add_argument("--shot-id", default=None)
    dn_add.add_argument("--note", default="")
    dn_res = dn_sub.add_parser("resolve", help="Mark open item(s) resolved")
    dn_res.add_argument("--root", required=True)
    dn_res.add_argument("--item-id", default=None)
    dn_res.add_argument("--shot-id", default=None)
    dn_res.add_argument("--note", default="")

    nxt = sub.add_parser("next", help="Print next recommended production command")
    nxt.add_argument("--root", required=True)
    nxt.add_argument("--all", action="store_true", help="List full next_actions")
    nxt.add_argument(
        "--print-cmd-only",
        action="store_true",
        help="Stdout only the command string (for shell eval)",
    )
    nxt.add_argument(
        "--print-stage",
        action="store_true",
        help="Also print pipeline stage line on stderr (or with --print-cmd-only)",
    )
    nxt.add_argument(
        "--print-stage-only",
        action="store_true",
        help="Stdout only compact stage line (片 2/7 语音·tts-rehearse); still persists sidecar",
    )

    stg = sub.add_parser(
        "stage",
        help="Show current pipeline layer (agent/visual/voice/design/post/…)",
    )
    stg.add_argument("--root", required=True)
    stg.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit full pipeline_stage JSON",
    )
    stg.add_argument(
        "--full",
        action="store_true",
        help="Long label + next_cmd line",
    )
    stg.add_argument(
        "--no-persist",
        action="store_true",
        help="Do not write receipts/pipeline_stage.json or HUD sidecar",
    )

    pf = sub.add_parser(
        "preflight",
        help="Lesson-based health check before bulk/final (hard+soft)",
    )
    pf.add_argument("--root", required=True)
    pf.add_argument("--strict", action="store_true", help="Also fail on soft warnings")

    si = sub.add_parser(
        "state-index",
        help="Checkpoint: state photos + keyframes + promote plan (fluid camera/joins)",
    )
    si_sub = si.add_subparsers(dest="state_index_action", required=True)
    sic = si_sub.add_parser(
        "check",
        help="Run state-index gate; write receipts/state-index.json",
    )
    sic.add_argument("--root", required=True)
    sic.add_argument(
        "--strict",
        action="store_true",
        help="Also fail if generate_plan or soft gaps non-empty",
    )
    sip = si_sub.add_parser(
        "plan",
        help="Print regenerate plan (state photos / keyframes / promote) for this stage",
    )
    sip.add_argument("--root", required=True)
    sip.add_argument("--strict", action="store_true")

    pilot = sub.add_parser(
        "pilot",
        help="Pilot three-shot scorecard assist (pick/report/score/approve)",
    )
    pilot_sub = pilot.add_subparsers(dest="pilot_action", required=True)
    pp = pilot_sub.add_parser("pick", help="Suggest pilot shot ids from film-spec beats")
    pp.add_argument("--root", required=True)
    pp.add_argument("--n", type=int, default=3)
    pr = pilot_sub.add_parser("report", help="Media + scorecard + approval status for pilot shots")
    pr.add_argument("--root", required=True)
    pr.add_argument("--shots", default="", help="Comma shot ids (default auto-pick)")
    ps = pilot_sub.add_parser("score", help="Write receipts/pilot-scorecard.json (identity/style/motion)")
    ps.add_argument("--root", required=True)
    ps.add_argument("--shots", required=True)
    ps.add_argument("--reviewer", required=True)
    ps.add_argument("--notes", required=True)
    ps.add_argument("--score-identity", required=True, choices=["pass", "fail"])
    ps.add_argument("--score-style", required=True, choices=["pass", "fail"])
    ps.add_argument("--score-motion", required=True, choices=["pass", "fail"])
    ps.add_argument(
        "--no-notes-on-fail",
        action="store_true",
        help="Do not open director_notes when pilot score fails",
    )
    pa = pilot_sub.add_parser("approve", help="Write user pilot-approval.json (needs user phrase)")
    pa.add_argument("--root", required=True)
    pa.add_argument("--shots", default="")
    pa.add_argument("--user-phrase", required=True, help='User words e.g. "pilot 过"')
    pa.add_argument("--notes", default="")
    pa.add_argument("--compared-to-cast", default=None)
    pa.add_argument(
        "--no-require-scorecard",
        action="store_true",
        help="Allow without pilot-scorecard all-pass (not recommended)",
    )

    cpv = sub.add_parser(
        "compose-preview",
        help="Start HyperFrames or Remotion Studio; write receipts/compose-preview.json",
    )
    cpv.add_argument("--root", required=True)
    cpv.add_argument(
        "--engine",
        default="hyperframes",
        choices=["hyperframes", "remotion"],
        help="hyperframes (default) | remotion (needs npm install in compose/remotion)",
    )
    cpv.add_argument(
        "--port",
        type=int,
        default=None,
        help="Studio port (default 3002 HF / 3003 Remotion)",
    )
    cpv.add_argument("--no-open", action="store_true", help="Print URL only; do not open browser")
    cpv.add_argument("--no-export", action="store_true", help="Do not auto export-compose if missing")
    cpv.add_argument("--foreground", action="store_true", help="Block instead of background server")
    cpv.add_argument("--force-new", action="store_true")
    cpv.add_argument("--stop", action="store_true", help="Stop background Studio (HF only)")
    cpv.add_argument(
        "--status",
        action="store_true",
        dest="status_only",
        help="Show running Studio URL without starting",
    )

    ec = sub.add_parser(
        "export-compose",
        help="Export approved clips to HyperFrames/Remotion designed-post packages",
    )
    ec.add_argument("--root", required=True)
    ec.add_argument(
        "--engine",
        default="both",
        choices=["hyperframes", "remotion", "both"],
        help="hyperframes (HTML Studio, default primary) | remotion | both",
    )
    ec.add_argument(
        "--layout",
        default="auto",
        choices=["auto", "multiclip", "underlay"],
        help="auto: underlay when film_final exists",
    )
    ec.add_argument(
        "--compose-preset",
        default="auto",
        choices=["auto", "ecchi-rnb", "minimal"],
        help="Title/caption preset: auto|ecchi-rnb|minimal",
    )
    ec.add_argument("--title-dur", type=float, default=1.5)
    ec.add_argument("--end-dur", type=float, default=1.5)
    ec.add_argument(
        "--title-sequence",
        default=None,
        choices=["auto", "none"],
        help="Override film-spec title_sequence mode (auto=spec/default, none=suppress)",
    )
    ec.add_argument(
        "--end-roll",
        default=None,
        choices=["auto", "none", "cast_only", "full"],
        help="Override film-spec end_roll mode (auto=spec/default, none=suppress)",
    )
    ec.add_argument("--force", action="store_true", help="Overwrite existing compose/")

    cr = sub.add_parser(
        "compose-render",
        help="HyperFrames check+render+audio+register final (designed post)",
    )
    cr.add_argument("--root", required=True)
    cr.add_argument(
        "--engine",
        default="hyperframes",
        choices=["hyperframes", "remotion", "both"],
    )
    cr.add_argument("--layout", default="auto", choices=["auto", "multiclip", "underlay"])
    cr.add_argument(
        "--compose-preset",
        default="auto",
        choices=["auto", "ecchi-rnb", "minimal"],
        help="Title/caption preset: auto|ecchi-rnb|minimal",
    )
    cr.add_argument(
        "--require-preview",
        action="store_true",
        help="Require receipts/compose-preview.json before HyperFrames render",
    )
    cr.add_argument(
        "--npm-install",
        action="store_true",
        help="Remotion: run npm install in compose/remotion before auto-render (network)",
    )
    cr.add_argument(
        "--npm-install-timeout",
        type=int,
        default=900,
        help="Timeout seconds for --npm-install (default 900)",
    )
    cr.add_argument("--quality", default="standard", choices=["draft", "standard", "high"])
    cr.add_argument("--out-name", default="film_final.mp4")
    cr.add_argument("--no-export", action="store_true")
    cr.add_argument("--no-force-export", action="store_true")
    cr.add_argument("--no-register", action="store_true")
    cr.add_argument("--skip-check", action="store_true")
    cr.add_argument(
        "--keep-raw",
        action="store_true",
        help="Keep out/film_hyperframes_raw.mp4 after audio mux",
    )
    cr.add_argument("--title-dur", type=float, default=1.5)
    cr.add_argument("--end-dur", type=float, default=1.5)
    cr.add_argument(
        "--title-sequence",
        default=None,
        choices=["auto", "none"],
        help="Override film-spec title_sequence mode (auto=spec/default, none=suppress)",
    )
    cr.add_argument(
        "--end-roll",
        default=None,
        choices=["auto", "none", "cast_only", "full"],
        help="Override film-spec end_roll mode (auto=spec/default, none=suppress)",
    )
    cr.add_argument(
        "--allow-burned-underlay",
        action="store_true",
        help="Allow underlay when plate already has burned-in captions (double-burn risk)",
    )
    cr.add_argument(
        "--register-only",
        default=None,
        help="Only register existing MP4 as final_film",
    )
    cr.add_argument("--post-engine", default="external")

    rf = sub.add_parser(
        "register-final",
        help="Register external/composed MP4 as formal final_film candidate",
    )
    rf.add_argument("--root", required=True)
    rf.add_argument("--source", required=True)
    rf.add_argument("--out-name", default="film_final.mp4")
    rf.add_argument(
        "--post-engine",
        default="external",
        help="Label: external|hyperframes|remotion|ffmpeg",
    )
    rf.add_argument(
        "--allow-static",
        action="store_true",
        help="Allow motion QA soft path (title-only tests; production leave off)",
    )

    ex = sub.add_parser("export-desktop", help="Copy deliverables to ~/Desktop/<name>")
    ex.add_argument("--root", required=True)
    ex.add_argument("--name", required=True)
    ex.add_argument("--force", action="store_true")

    treh = sub.add_parser(
        "tts-rehearse",
        help="Probe/register real VO durations into receipts/tts-rehearsal.json before bulk/final",
    )
    treh.add_argument("--root", required=True)
    treh.add_argument("--spec", default=None, help="Optional film-spec path")
    treh.add_argument("--backend", "--tts-backend", dest="tts_backend", default=None)
    treh.add_argument("--voice", default="zh-CN-XiaoxiaoNeural")
    treh.add_argument(
        "--register-json",
        default=None,
        help="JSON list of {shot_id, path|measured_duration_sec} (offline / no network)",
    )
    treh.add_argument(
        "--no-synthesize",
        action="store_true",
        help="Only register mode; requires --register-json",
    )

    frw = sub.add_parser(
        "frw",
        help=(
            "Proxy to FRW img-video-frw dispatch. "
            "Use: frw canary [--root ROOT] [--wait] [--full] | "
            "frw newvideo --model seedance-2-fast-i2v …"
        ),
    )
    frw.add_argument(
        "frw_argv",
        nargs=argparse.REMAINDER,
        help=(
            "Args passed to frw_dispatch.py. "
            "Examples: canary --root <film> ; "
            "newvideo --model seedance-2-fast-i2v --img-url … --wait"
        ),
    )

    # Phase 1: Vertical Drama Graph
    graph_p = sub.add_parser(
        "graph",
        help="Vertical Drama Graph: derive|validate|status (from film-spec; Phase 1)",
    )
    graph_sub = graph_p.add_subparsers(dest="graph_action", required=True)
    g_der = graph_sub.add_parser(
        "derive", help="Derive drama-graph.json from film-spec (read-only projection)"
    )
    g_der.add_argument("--root", required=True, help="Film root")
    g_der.add_argument("--no-write", action="store_true", help="Do not write drama-graph.json")
    g_imp = graph_sub.add_parser("import", help="Explicitly import legacy film-spec into canonical drama-graph v2")
    g_imp.add_argument("--root", required=True, help="Film root")
    g_proj = graph_sub.add_parser("project", help="Project locked canonical drama-graph into film-spec")
    g_proj.add_argument("--root", required=True, help="Film root")
    g_proj.add_argument("--force", action="store_true", help="Overwrite existing film-spec shots")
    g_val = graph_sub.add_parser("validate", help="Validate drama-graph.json structure")
    g_val.add_argument("--root", required=True, help="Film root")
    g_val.add_argument(
        "--derive-if-missing",
        action="store_true",
        help="Derive graph first if missing",
    )
    g_st = graph_sub.add_parser("status", help="Graph counts + validate summary")
    g_st.add_argument("--root", required=True, help="Film root")
    g_st.add_argument(
        "--no-derive",
        action="store_true",
        help="Do not auto-derive if graph missing",
    )
    g_st.add_argument("--with-jobs", action="store_true", help="Include execution jobs_summary")

    # Phase 2: Skill Registry shell
    skill_p = sub.add_parser("skill", help="Skill Registry: list|show (Phase 2 shell)")
    skill_sub = skill_p.add_subparsers(dest="skill_action", required=True)
    sk_list = skill_sub.add_parser("list", help="List registered skills")
    sk_list.add_argument("--tag", default=None, help="Filter by tag")
    sk_list.add_argument("--phase", default=None, help="Filter by phase id (e.g. 1, 2)")
    sk_show = skill_sub.add_parser("show", help="Show one skill + contracts")
    sk_show.add_argument("--id", dest="id", required=True, help="skill_id e.g. image.animate")

    # Phase 3: story → beat/shot planning
    plan_p = sub.add_parser(
        "plan",
        help="Story plan: normalize|run|validate|edit|lock|unlock|replan|project|status",
    )
    plan_sub = plan_p.add_subparsers(dest="plan_action", required=True)
    p_norm = plan_sub.add_parser("normalize", help="story.normalize → receipts/story-normalize.json")
    p_norm.add_argument("--root", default=None, help="Optional film root to write receipt")
    p_norm.add_argument("--text", default=None, help="Raw story / brief text")
    p_norm.add_argument("--file", default=None, help="Path to .txt/.md story")
    p_norm.add_argument("--title", default=None, help="Title override")
    p_run = plan_sub.add_parser(
        "run",
        help="Create draft plan: normalize→episode→scene→beat→shot→canonical drama-graph",
    )
    p_run.add_argument("--root", required=True, help="Film root")
    p_run.add_argument("--text", default=None, help="Raw story / one-liner idea")
    p_run.add_argument("--file", default=None, help="Path to story file")
    p_run.add_argument("--title", default=None, help="Title override")
    p_run.add_argument(
        "--target-duration",
        type=float,
        default=45.0,
        help="Target episode duration seconds (default 45)",
    )
    p_run.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing film-spec shots / locked bible seed",
    )
    p_run.add_argument("--apply-film-spec", action="store_true", help="Also write a draft film-spec projection")
    p_run.add_argument("--no-film-spec", action="store_true", help="Do not write film-spec (compatibility alias)")
    p_run.add_argument(
        "--no-bible",
        action="store_true",
        help="Do not seed style-bible characters/locations",
    )
    p_proj = plan_sub.add_parser(
        "project", help="Project drama-graph → film-spec (when graph already planned)"
    )
    p_proj.add_argument("--root", required=True)
    p_proj.add_argument("--force", action="store_true", help="Overwrite existing shots")
    p_val = plan_sub.add_parser("validate", help="Validate story/beat/shot semantics and projection state")
    p_val.add_argument("--root", required=True)
    p_val.add_argument("--strict", action="store_true")
    p_edit = plan_sub.add_parser("edit", help="Edit one unlocked narrative node")
    p_edit.add_argument("--root", required=True)
    p_edit.add_argument("--node", required=True, help="Node id/ref, e.g. story or ep01_sc01_bt03")
    p_edit.add_argument("--set", action="append", required=True, help="field=value; repeatable")
    p_lock = plan_sub.add_parser("lock", help="Lock one narrative scope after semantic validation")
    p_lock.add_argument("--root", required=True)
    p_lock.add_argument("--scope", choices=("story", "beats", "shots", "panels"), required=True)
    p_lock.add_argument("--user-phrase", required=True)
    p_unlock = plan_sub.add_parser("unlock", help="Unlock one narrative scope with an audit reason")
    p_unlock.add_argument("--root", required=True)
    p_unlock.add_argument("--scope", choices=("story", "beats", "shots", "panels"), required=True)
    p_unlock.add_argument("--reason", required=True)
    p_replan = plan_sub.add_parser("replan", help="Mark a node and descendants stale without deleting media")
    p_replan.add_argument("--root", required=True)
    p_replan.add_argument("--node", required=True)
    p_replan.add_argument("--descendants", action="store_true", help="Required explicit confirmation flag")
    p_st = plan_sub.add_parser("status", help="Plan + graph status for film root")
    p_st.add_argument("--root", required=True)

    # Phase 4: asset registry (character/location/prop/state)
    assets_p = sub.add_parser(
        "assets",
        help="Asset registry: sync|status|check (Phase 4 Character/Location/Prop/State)",
    )
    assets_sub = assets_p.add_subparsers(dest="assets_action", required=True)
    a_sync = assets_sub.add_parser(
        "sync",
        help="Structure bible locations/props + wardrobe variants + cast-state slots + timeline",
    )
    a_sync.add_argument("--root", required=True)
    a_sync.add_argument("--force", action="store_true", help="Re-structure locations/props objects")
    a_sync.add_argument("--no-write", action="store_true")
    a_sync.add_argument("--no-graph", action="store_true", help="Do not patch drama-graph")
    a_st = assets_sub.add_parser("status", help="Show assets-registry summary")
    a_st.add_argument("--root", required=True)
    a_st.add_argument("--sync", action="store_true", help="Sync if missing")
    a_ck = assets_sub.add_parser(
        "check",
        help="Align assets-registry with state-index + wardrobe re-dress risks",
    )
    a_ck.add_argument("--root", required=True)
    a_ck.add_argument("--no-sync", action="store_true", help="Do not re-sync before check")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == "doctor":
            return cmd_doctor(args)
        if args.cmd == "lock-runtime":
            return cmd_lock_runtime(args)
        if args.cmd == "review-shot":
            return cmd_review_shot(args)
        if args.cmd == "review-contract":
            return cmd_review_contract(args)
        if args.cmd == "frw-lipsync":
            return cmd_frw_lipsync(args)
        if args.cmd == "env-plate":
            return cmd_env_plate(args)
        if args.cmd == "grok-oauth":
            return cmd_grok_oauth(args)
        if args.cmd == "dispatch":
            return cmd_dispatch(args)
        if args.cmd == "craft":
            return cmd_craft(args)
        if args.cmd == "selects":
            return cmd_selects(args)
        if args.cmd == "audio-plan":
            return cmd_audio_plan(args)
        if args.cmd == "lipsync-canary":
            return cmd_lipsync_canary(args)
        if args.cmd == "capability":
            return cmd_capability(args)
        if args.cmd == "tts-ab":
            return cmd_tts_ab(args)
        if args.cmd == "init":
            return cmd_init(args)
        if args.cmd == "status":
            return cmd_status(args)
        if args.cmd == "stage":
            return cmd_stage(args)
        if args.cmd == "write-spec":
            return cmd_write_spec(args)
        if args.cmd == "lint-continuity":
            return cmd_lint_continuity(args)
        if args.cmd == "extract-frame":
            return cmd_extract_frame(args)
        if args.cmd == "continuity-chain":
            return cmd_continuity_chain(args)
        if args.cmd == "lock-style":
            return cmd_lock_style(args)
        if args.cmd == "bible":
            root = Path(args.root).expanduser().resolve()
            if args.bible_cmd == "init":
                from scripts.visual_bible import load_bible, save_bible
                bible = load_bible(root)
                save_bible(root, bible)
                emit({"ok": True, "msg": "Visual Bible initialized/migrated to v2"})
            elif args.bible_cmd == "lock":
                from scripts.visual_bible import update_bible_state
                update_bible_state(root, "Approved")
                emit({"ok": True, "msg": "Visual Bible locked (Approved)"})
            elif args.bible_cmd == "state":
                from scripts.visual_bible import update_bible_state
                update_bible_state(root, args.set)
                emit({"ok": True, "msg": f"Visual Bible state updated to {args.set}"})
            return 0
        if args.cmd == "register-still":
            return cmd_register_still(args)
        if args.cmd == "tts-rehearse":
            return cmd_tts_rehearse(args)
        if args.cmd == "register-clip":
            return cmd_register_clip(args)
        if args.cmd == "assemble":
            return cmd_assemble(args)
        if args.cmd == "reencode-clips":
            return cmd_reencode_clips(args)
        if args.cmd == "final":
            return cmd_final(args)
        if args.cmd == "review-final":
            return cmd_review_final(args)
        if args.cmd == "director-notes":
            return cmd_director_notes(args)
        if args.cmd == "next":
            return cmd_next(args)
        if args.cmd == "preflight":
            return cmd_preflight(args)
        if args.cmd == "state-index":
            return cmd_state_index(args)
        if args.cmd == "pilot":
            return cmd_pilot(args)
        if args.cmd == "compose-preview":
            return cmd_compose_preview(args)
        if args.cmd == "export-compose":
            return cmd_export_compose(args)
        if args.cmd == "compose-render":
            return cmd_compose_render(args)
        if args.cmd == "register-final":
            return cmd_register_final(args)
        if args.cmd == "export-desktop":
            return cmd_export_desktop(args)
        if args.cmd == "frw":
            return cmd_frw(args)
        if args.cmd == "graph":
            # allow --no-derive to flip auto_derive off for status
            if getattr(args, "graph_action", None) == "status" and bool(
                getattr(args, "no_derive", False)
            ):
                args.derive_if_missing = False
            return cmd_graph(args)
        if args.cmd == "skill":
            return cmd_skill(args)
        if args.cmd == "plan":
            return cmd_plan(args)
        if args.cmd == "assets":
            return cmd_assets(args)
        raise FilmError(f"Unknown command {args.cmd}")
    except FilmError as exc:
        emit({"ok": False, "error": str(exc)})
        return 2
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        emit({"ok": False, "error": f"Command failed: {err[:2000]}"})
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
