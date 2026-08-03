#!/usr/bin/env python3
"""Local control plane for the ai-film-grok pipeline (no Studio required)."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from logger import log

# Ensure skill package root is importable before `scripts.*` (shell wrapper does not set PYTHONPATH)
_SKILL_DIR = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (_SKILL_DIR, _SCRIPTS_DIR):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from continuity import lint_continuity, lint_frame_chain
from continuity_chain import (
    check_continuity_chain,
    init_chain_doc,
    is_long_form,
    upsert_join,
)
from director_review import (
    SCORECARD_DIMENSIONS,
    DirectorReviewError,
    add_reshoot_item,
    build_grades_from_cli,
    build_notes_from_scorecard_failures,
    build_scorecard_from_cli,
    empty_director_notes,
    open_reshoot_items,
    parse_fail_reasons,
    parse_shot_id_list,
    reshoots_clear,
    resolve_reshoot_item,
    scorecard_all_pass,
    scorecard_is_complete_and_passing,
    scorecard_payload,
    validate_scorecard_for_approve,
)
from film_spec import FilmSpecError, validate_film_spec
from media_qa import ALLOWED_VIDEO_ENDPOINTS, MediaQAError, analyze_media, approved_clip_record
from prompt_injector import PromptConflictError, PromptInjector
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
from util import read_json as _util_read_json
from util import sha256_file, utc_now, write_json
from util.errors import FilmError  # noqa: E402 — re-exported for backward compat
from visual_bible import load_bible

SCHEMA_VERSION = 2
MANIFEST_NAME = "manifest.json"
DEFAULT_FPS = 30
DEFAULT_WIDTH = 720
DEFAULT_HEIGHT = 1280  # 9:16; overridden by aspect
NATIVE_AUDIO_AUDIBLE_MIN_DB = -42.0
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
    "post-plan.json",
)


def read_json(path: Path) -> dict[str, Any]:
    """Strict JSON read — delegates to ``util.require_json``."""
    from util import require_json

    return require_json(path)


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


def run(
    cmd: list[str],
    *,
    check: bool = True,
    timeout: int | float | None = 60,
) -> subprocess.CompletedProcess[str]:
    """Subprocess helper. Default 60s; pass timeout=None or large value for long renders (final)."""
    return subprocess.run(
        cmd,
        timeout=timeout,
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


def probe_native_audio_mean_volume(path: Path) -> float | None:
    """Return native I2V stem mean volume, or None when ffmpeg cannot measure it."""
    try:
        result = run(
            ["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(
        r"mean_volume:\s*(-?\d+(?:\.\d+)?)\s*dB", (result.stderr or "") + (result.stdout or "")
    )
    return float(match.group(1)) if match else None


def emit(obj: dict[str, Any]) -> None:
    # Agent/pipe consumers do not benefit from whitespace; keep TTY output
    # readable while reducing captured CLI context substantially.
    if sys.stdout.isatty() or os.environ.get("AIFILM_PRETTY_JSON", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


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
        "truth_contract": {
            "source_of_truth": "local-contract-and-receipts",
            "contract_sha256": "",
            "graph_sha256": "",
            "spec_sha256": "",
            "timeline_sha256": "",
        },
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


def _classify_doctor_readiness(
    *,
    core_checks: dict[str, bool],
    optional_capabilities: dict[str, Any],
    environment_warnings: list[str],
) -> dict[str, Any]:
    """Separate production requirements from optional tools and host advisories."""
    failed_checks = [name for name, ready in core_checks.items() if not ready]
    core_readiness = {
        "ok": not failed_checks,
        "checks": core_checks,
        "failed_checks": failed_checks,
    }
    environment_advisories = {
        "ok": not environment_warnings,
        "warnings": list(environment_warnings),
        "severity": "advisory" if environment_warnings else "none",
        "blocks_core": False,
    }
    strict_blocking = bool(failed_checks)
    strict_status = (
        "blocked" if strict_blocking else "advisory_only" if environment_warnings else "pass"
    )
    return {
        "core_readiness": core_readiness,
        "optional_capabilities": optional_capabilities,
        "environment_advisories": environment_advisories,
        "ok": core_readiness["ok"],
        "strict_ok": bool(core_readiness["ok"] and environment_advisories["ok"]),
        "strict_status": strict_status,
        "strict_blocking": strict_blocking,
    }


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
    requirements = verify_requirements_lock(skill_dir / "requirements.lock", skill_dir)
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
    environment_warnings: list[str] = []
    if permission_mode == "always-approve":
        environment_warnings.append(
            "Global Grok permission_mode is always-approve; change requires explicit user approval"
        )
    if log_mode is not None and log_mode & 0o077:
        environment_warnings.append(
            f"Grok unified log is readable beyond the owner (mode {oct(log_mode)}); "
            f"fix: chmod 600 {grok_log}"
        )
    if config_env_mode is not None and config_env_mode & 0o077:
        environment_warnings.append(
            f"skill config.env must be owner-only (mode {oct(config_env_mode)})"
        )
    requested_lipsync = str(lipsync_info.get("env_backend") or "auto")
    ready_lipsync_backends = list(lipsync_info.get("ready") or [])
    if requested_lipsync == "require":
        lipsync_required_ok = bool(ready_lipsync_backends)
    else:
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
            "warnings": environment_warnings,
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
            "motion": "FRW LTX 2.3 → FRW API I2V → Grok Video 1.5",
            "motion_multi_ref": "reference_to_video (agent tool)",
            "vo": "MiMo (default; limited-time free), MiniMax/Fish/edge, or structured AIFILM_TTS_ARGV (cross-provider fallback is opt-in)",
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

        designed = {
            **probe_designed_post_tooling(),
            "required_for": "final --post-engine hyperframes",
        }
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

    # Soft Comfy tunnel probe (C2) — advisory only; missing tunnel must not fail core doctor
    tunnel: dict[str, Any] = {"ok": None, "required_for": "5090 comfy bulk"}
    try:
        from workflow_pack import tunnel_probe

        tunnel = {
            **tunnel_probe(port=int(os.environ.get("AIFILM_COMFY_TUNNEL_PORT") or 18188)),
            "required_for": "5090 comfy bulk",
            "advisory": True,
        }
    except Exception as exc:  # pragma: no cover
        tunnel = {"ok": None, "skipped": True, "error": str(exc)[:160], "advisory": True}
    report["comfy_tunnel"] = tunnel

    # video-use skill readiness (real-footage editing ring, 2026-07-23) — soft probe
    video_use: dict[str, Any] = {"ok": False, "required_for": "ingest-footage / auto-cut"}
    try:
        sys.path.insert(0, str(skill_dir / "scripts"))
        from real_footage import video_use_dir

        vu = video_use_dir()
        video_use = {
            "ok": True,
            "path": str(vu),
            "has_transcribe": (vu / "helpers" / "transcribe.py").is_file(),
            "has_pack": (vu / "helpers" / "pack_transcripts.py").is_file(),
            "has_render": (vu / "helpers" / "render.py").is_file(),
            "has_grade": (vu / "helpers" / "grade.py").is_file(),
            "required_for": "ingest-footage / auto-cut",
        }
    except Exception as exc:  # noqa: BLE001 — soft probe
        video_use["error"] = str(exc)[:200]
        video_use["soft_warning"] = (
            "video-use not installed — install/ symlink the skill for real-footage editing"
        )
    report["video_use"] = video_use

    # I2V provider registry summary (grok + seedance) — soft probe
    i2v_providers: dict[str, Any] = {"ok": False}
    try:
        sys.path.insert(0, str(skill_dir / "scripts"))
        from i2v_provider import preferred, registry_report

        active = preferred()
        reg = registry_report()
        i2v_providers = {
            "ok": True,
            "active": active.name,
            "providers": reg["providers"],
        }
    except Exception as exc:  # noqa: BLE001 — soft probe
        i2v_providers = {"ok": False, "error": str(exc)[:200]}
    report["i2v_providers"] = i2v_providers

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
    optional_warnings: list[str] = []
    if not grok_oauth.get("ok"):
        optional_warnings.append(
            "Grok OAuth not ready (optional for API batch; in-session Imagine tools still work if logged in)"
        )

    if not report["ffmpeg"] or not report["ffprobe"]:
        report["ok"] = False
        report["error"] = "ffmpeg/ffprobe not found on PATH"
    elif not edge_ok or not numpy_ok or not pil_ok:
        report["ok"] = False
        report["error"] = (
            "Formal final requires edge-tts + numpy + pillow (pip install --user edge-tts numpy pillow)"
        )
    elif (
        not tts_info.get("ok")
        or not requirements["ok"]
        or not runtime["ok"]
        or not schema_ok
        or not lipsync_required_ok
    ):
        report["ok"] = False
        report["error"] = (
            "Runtime/schema/backend verification failed; inspect nested doctor reports"
        )
    core_checks = {
        "skill_spine": bool(report["skill_md"]),
        "ffmpeg": bool(report["ffmpeg"]),
        "ffprobe": bool(report["ffprobe"]),
        "edge_tts": edge_ok,
        "numpy": numpy_ok,
        "pillow": pil_ok,
        "tts_backend": bool(tts_info.get("ok")),
        "requirements_lock": bool(requirements.get("ok")),
        "runtime_lock": bool(runtime.get("ok")),
        "film_spec_schema": schema_ok,
        "requested_lipsync_backend": lipsync_required_ok,
    }
    optional_capabilities = {
        "lipsync": {
            "enabled": requested_lipsync not in {"off", "auto"},
            "requested_backend": requested_lipsync,
            "ready": bool(ready_lipsync_backends),
            "ready_backends": ready_lipsync_backends,
            "required_request_satisfied": lipsync_required_ok,
        },
        "designed_post": {
            "ready": bool(designed.get("ok")),
            "required_for": designed.get("required_for"),
        },
        "grok_oauth": {
            "ready": bool(grok_oauth.get("ok")),
            "required_for": "API batch generation",
        },
        "warnings": optional_warnings,
    }
    readiness = _classify_doctor_readiness(
        core_checks=core_checks,
        optional_capabilities=optional_capabilities,
        environment_warnings=environment_warnings,
    )
    report.update(readiness)
    if not report["ok"] and "error" not in report:
        report["error"] = "Core readiness failed; inspect core_readiness.failed_checks"

    # P4-3: art check — run director methodology verification
    if getattr(args, "art_check", False):
        art_report: dict[str, Any] = {"ok": True, "checks": {}}
        film_root = Path(getattr(args, "art_root", ".")).expanduser().resolve()
        if (film_root / "film-spec.json").is_file():
            try:
                from director_cli import verify as director_verify

                result = director_verify(film_root)
                art_report["checks"][str(film_root)] = result
                if not result.get("ok"):
                    art_report["ok"] = False
            except Exception as exc:  # noqa: BLE001
                art_report["checks"][str(film_root)] = {"ok": False, "error": str(exc)[:200]}
        report["art_check"] = art_report

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


def _cmd_init_in_place(args: argparse.Namespace) -> int:
    title = args.title.strip()
    theme = args.theme.strip()
    aspect = args.aspect
    root = Path(args.root).expanduser().resolve()
    root_has_content = root.exists() and any(root.iterdir())
    if root_has_content and not args.force:
        raise FilmError(f"Root not empty: {root} (pass --force to reuse)")
    if root_has_content and args.force and not (root / "production-book.json").is_file():
        raise FilmError(
            "legacy root has no production-book.json; run "
            f'aifilm director migrate-audit --root "{root}" before any explicit migration'
        )
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
    try:
        from bgm_library import BGMLibraryError, default_library_root, library_status

        if library_status(default_library_root()).get("ready_for_default"):
            film_spec["audio_policy"] = {
                "mode": "auto",
                "bed_source": "approved_library",
            }
    except (BGMLibraryError, OSError, ValueError):
        # A missing or corrupt optional shared library cannot make init unusable.
        pass
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
    # Existing projects and clients remain on v2 until they explicitly opt in
    # to v3; v3 changes the review input contract and must not be silent.
    manifest["review_contract_version"] = 2
    manifest["truth_contract"]["contract_sha256"] = sha256_file(root / "film-spec.json")
    save_manifest(root, manifest)
    from production_book import init_production_book

    init_production_book(
        root,
        title=title,
        rigor="professional",
        format_pack="vertical-short",
        genre_pack="drama",
        quality_target="standard",
    )
    try:
        from pipeline_events import append_event

        append_event(root, stage="init", phase="completed")
    except OSError:
        pass
    (root / "README.md").write_text(
        f"# {title}\n\nTheme: {theme}\n\nProvider: Grok Imagine\nRoot: `{root}`\n",
        encoding="utf-8",
    )
    emit(
        {
            "ok": True,
            "root": str(root),
            "title": title,
            "aspect_ratio": aspect,
            "width": w,
            "height": h,
            "workflow": {
                "entry": "/ai-film-grok",
                "mode": "professional",
                "internal_stage_model": "professional-director-11",
            },
        }
    )
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Build a new root off-path, then publish the complete Professional project."""
    destination = Path(args.root).expanduser().resolve()
    if destination.exists() and any(destination.iterdir()):
        return _cmd_init_in_place(args)
    if destination.is_symlink():
        raise FilmError(f"Refusing to initialize a symlink root: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.aifilm-init-", dir=destination.parent)
    )
    staged_args = argparse.Namespace(**vars(args))
    staged_args.root = str(staging)
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            result = _cmd_init_in_place(staged_args)
        if result != 0:
            raise FilmError(f"staged init failed with status {result}")
        (staging / "README.md").write_text(
            f"# {args.title.strip()}\n\nTheme: {args.theme.strip()}\n\n"
            f"Provider: Grok Imagine\nRoot: `{destination}`\n",
            encoding="utf-8",
        )
        if destination.exists():
            destination.rmdir()
        os.replace(staging, destination)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    payload = json.loads(captured.getvalue())
    payload["root"] = str(destination)
    emit(payload)
    return result


def cmd_resume_manifest(args: argparse.Namespace) -> int:
    """Create only the missing state manifest for a legacy film root."""
    raw_root = Path(args.root).expanduser()
    if raw_root.is_symlink():
        raise FilmError(f"Legacy root must not be a symlink: {raw_root}")
    root = raw_root.resolve()
    if not root.is_dir():
        raise FilmError(f"Legacy root must be a real directory: {root}")
    manifest_path = root / MANIFEST_NAME
    if manifest_path.exists() or manifest_path.is_symlink():
        raise FilmError(f"Manifest already exists at {manifest_path}; refusing to overwrite it")
    brief_path = root / "brief.json"
    if not brief_path.is_file():
        raise FilmError(f"Legacy root needs brief.json before manifest resume: {root}")
    brief = read_json(brief_path)
    title = str(brief.get("title") or "").strip()
    theme = str(brief.get("theme") or "").strip()
    aspect = str(brief.get("aspect_ratio") or "9:16").strip()
    if not title or not theme:
        raise FilmError("Legacy brief.json needs non-empty title and theme before manifest resume")
    manifest = empty_manifest(title=title, theme=theme, aspect=aspect)
    contract_path = root / "director-contract.json"
    graph_path = root / "drama-graph.json"
    truth = manifest["truth_contract"]
    truth["contract_sha256"] = sha256_file(contract_path) if contract_path.is_file() else ""
    truth["graph_sha256"] = sha256_file(graph_path) if graph_path.is_file() else ""
    truth["spec_sha256"] = (
        sha256_file(root / "film-spec.json") if (root / "film-spec.json").is_file() else ""
    )
    truth["timeline_sha256"] = (
        sha256_file(root / "timeline.json") if (root / "timeline.json").is_file() else ""
    )
    manifest["notes"].append(
        "Legacy resume created this manifest only; existing style, contract, still, and clip evidence remains unapproved until revalidated."
    )
    ensure_tree(root)
    save_manifest(root, manifest)
    emit(
        {
            "ok": True,
            "created": True,
            "root": str(root),
            "manifest": str(manifest_path),
            "preserved_existing_evidence": True,
            "next_step": "Revalidate and lock style plus native evidence before media generation.",
        }
    )
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
    broll_ids = [
        str(entry.get("id"))
        for shot in shots
        for entry in (shot.get("dialogue_broll") or [])
        if isinstance(entry, dict) and str(entry.get("id") or "").strip()
    ]
    inventory_ids = shot_ids + broll_ids
    dirs = film_dirs(root)
    stills = manifest.get("stills") or {}
    clips = manifest.get("clips") or {}
    style_reference = (
        style.get("style_reference") if isinstance(style.get("style_reference"), dict) else {}
    )
    style_reference_ok = True
    if style_reference:
        try:
            from scripts import style_lock as sl

            style_check = sl.validate_style_lock_bible(style)
            style_reference_ok = not any(
                str(code).startswith("STYLE_REFERENCE_") for code in style_check.get("hard") or []
            )
        except (ImportError, OSError, ValueError):
            style_reference_ok = False

    def _has_current_style_job(record: object) -> bool:
        if not style_reference:
            return True
        evidence = record.get("style_reference_job") if isinstance(record, dict) else None
        return isinstance(evidence, dict) and evidence.get(
            "style_reference_sha256"
        ) == style_reference.get("sha256")

    approved_stills = [
        sid
        for sid, record in stills.items()
        if isinstance(record, dict)
        and record.get("status") == "approved"
        and _has_current_style_job(record)
        and record_file_matches(dirs["keyframes"], record, field=f"still path for {sid}")
    ]
    review_contract = int(manifest.get("review_contract_version") or 1)
    approved_clips = [
        sid
        for sid, record in clips.items()
        if approved_clip_record(record)
        and _has_current_style_job(record)
        and (review_contract < 2 or isinstance(record.get("shot_review"), dict))
        and record_file_matches(dirs["clips"], record, field=f"clip path for {sid}")
    ]
    canonical = [
        path for path in dirs["canonical"].glob("*") if path.is_file() and not path.is_symlink()
    ]
    out_mp4 = [
        path for path in dirs["out"].glob("*.mp4") if path.is_file() and not path.is_symlink()
    ]
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
    from delivery_artifact import desktop_delivery_is_current

    desktop_exported = desktop_delivery_is_current(outputs, final_record)
    dnotes = load_director_notes(root)
    open_items = open_reshoot_items(dnotes)
    from anatomy_safety import anatomy_safety_report, requires_anatomy_safety
    from clip_uniqueness import active_clip_reuse_report
    from still_uniqueness import active_still_reuse_report

    uniqueness = active_clip_reuse_report(manifest, required_shot_ids=shot_ids)
    still_uniqueness = active_still_reuse_report(
        manifest,
        required_shot_ids=shot_ids,
        keyframes_dir=dirs["keyframes"],
    )
    anatomy_required = requires_anatomy_safety(root)
    still_anatomy = anatomy_safety_report(manifest, required_shot_ids=shot_ids, kind="stills")
    clip_anatomy = anatomy_safety_report(manifest, required_shot_ids=shot_ids, kind="clips")
    from manifest_truth import preflight_manifest

    manifest_truth = preflight_manifest(root, manifest)
    clips_complete = (
        manifest_truth["ok"]
        and bool(shot_ids)
        and all(sid in approved_clips for sid in shot_ids)
        and uniqueness["ok"]
        and style_reference_ok
    )
    gates = {
        "manifest_current": manifest_truth["ok"],
        "brief": (root / "brief.json").is_file(),
        "style_locked": bool(style.get("locked")) and style_reference_ok,
        "spec": bool(shots) and spec_error is None,
        "canonical": len(canonical) > 0,
        "stills_complete": bool(shot_ids)
        and all(sid in approved_stills for sid in shot_ids)
        and still_uniqueness["ok"],
        "clips_complete": clips_complete,
        "assembled": assembled,
        "reshoots_clear": reshoots_clear(dnotes),
        "final_complete": bool(
            manifest_truth["ok"]
            and still_uniqueness["ok"]
            and clips_complete
            and final_technical_ok
            and review_ok
            and reshoots_clear(dnotes)
        ),
        "desktop_exported": desktop_exported,
    }
    if anatomy_required:
        gates["stills_complete"] = gates["stills_complete"] and still_anatomy["ok"]
        gates["clips_complete"] = gates["clips_complete"] and clip_anatomy["ok"]
        gates["final_complete"] = (
            gates["final_complete"] and still_anatomy["ok"] and clip_anatomy["ok"]
        )
    manifest["gates"] = gates
    manifest["style_locked"] = gates["style_locked"]
    return {
        "shot_ids": inventory_ids,
        "approved_stills": approved_stills,
        "approved_clips": approved_clips,
        "canonical_count": len(canonical),
        "outputs": [str(p) for p in out_mp4],
        "spec_error": spec_error,
        "final_technical_ok": final_technical_ok,
        "final_review_ok": review_ok,
        "style_reference_ok": style_reference_ok,
        "clip_uniqueness": uniqueness,
        "still_uniqueness": still_uniqueness,
        "anatomy_safety": {
            "required": anatomy_required,
            "stills": still_anatomy,
            "clips": clip_anatomy,
        },
        "manifest_truth": manifest_truth,
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

    pipeline = detect_pipeline_stage(root, gates=gates, open_reshoot_count=open_n)
    book = read_json(root / "production-book.json") or {}
    if book.get("rigor") == "professional":
        from dispatch import build_dispatch

        packet = build_dispatch(
            root,
            gates=gates,
            open_reshoot_count=open_n,
            include_capability=False,
            write_receipt=persist,
            use_state_cache=False,
        )
        actions = list(packet.get("next_actions") or [])
        next_cmd = packet.get("next_cmd")
        next_id = packet.get("next_id")
        pipeline["workflow"] = packet.get("workflow")
        pipeline["workflow_stage"] = (packet.get("workflow") or {}).get("current_stage")
        pipeline["bound_next_action"] = packet.get("next_action")
        pipeline["state_hash"] = packet.get("state_hash")
    else:
        actions = build_next_actions(root, gates=gates, open_reshoot_count=open_n)
        next_cmd = actions[0]["cmd"] if actions else None
        next_id = actions[0].get("id") if actions else None
    if persist:
        with contextlib.suppress(OSError):
            persist_pipeline_stage(
                root,
                pipeline,
                next_cmd=next_cmd,
                next_id=next_id,
            )
    return actions, pipeline, next_cmd, next_id


def cmd_next(args: argparse.Namespace) -> int:
    """Print the single next recommended production command (lesson routing)."""
    root = Path(args.root).expanduser().resolve()
    manifest = load_manifest(root) if (root / MANIFEST_NAME).is_file() else {}
    summary = (
        recompute_gates(root, manifest) if manifest else {"gates": {}, "open_reshoot_count": 0}
    )
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
    try:
        from workflow_spine import public_flow_phase

        workflow = pipeline.get("workflow") if isinstance(pipeline, dict) else None
        phase = public_flow_phase(workflow) if isinstance(workflow, dict) else None
    except (ImportError, OSError, ValueError):
        phase = None

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
                "phase": phase,
                "pipeline_stage": pipeline,
                "stage": pipeline.get("stage"),
                "stage_label": pipeline.get("label_zh"),
                "next_actions": actions,
                "next_action": pipeline.get("bound_next_action"),
                "state_hash": pipeline.get("state_hash"),
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
                "phase": phase,
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
            "phase": phase,
            "pipeline_stage": pipeline,
            "stage": pipeline.get("stage"),
            "stage_label": pipeline.get("label_zh"),
            "next_cmd": cmd,
            "why": actions[0].get("why"),
            "id": next_id or actions[0].get("id"),
            "next_actions": actions,
            "next_action": pipeline.get("bound_next_action"),
            "state_hash": pipeline.get("state_hash"),
        }
    )
    return 0


def cmd_stage(args: argparse.Namespace) -> int:
    """Print / refresh current pipeline stage (product spine layer)."""
    root = Path(args.root).expanduser().resolve()
    manifest = load_manifest(root) if (root / MANIFEST_NAME).is_file() else {}
    summary = (
        recompute_gates(root, manifest) if manifest else {"gates": {}, "open_reshoot_count": 0}
    )
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
        try:
            from workflow_spine import public_flow_phase

            workflow = pipeline.get("workflow") if isinstance(pipeline, dict) else None
            phase = public_flow_phase(workflow) if isinstance(workflow, dict) else None
        except (ImportError, OSError, ValueError):
            phase = None
        emit(
            {
                "ok": True,
                "root": str(root),
                "phase": phase,
                "pipeline_stage": pipeline,
                "stage": pipeline.get("stage"),
                "stage_label": pipeline.get("label_zh"),
                "line": line,
                "next_cmd": next_cmd,
                "next_id": next_id,
                "next_actions": actions[:3] if actions else [],
                "next_action": pipeline.get("bound_next_action"),
                "state_hash": pipeline.get("state_hash"),
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


def cmd_quality_status(args: argparse.Namespace) -> int:
    """Read the hash-bound quality, motion, and review receipts for one film."""
    from cli_motion import motion_evidence_status
    from cli_quality import quality_contract_status
    from cli_review import review_packet_status

    root = Path(args.root).expanduser().resolve()
    payload: dict[str, Any] = {"quality": quality_contract_status(root)}
    shot_id = getattr(args, "shot_id", None)
    if shot_id:
        payload["motion"] = motion_evidence_status(root, str(shot_id))
        payload["review"] = review_packet_status(root, str(shot_id))
    emit(payload)
    return 0


def cmd_heat(args: argparse.Namespace) -> int:
    """Adult heat gates: check | vo-suggest | boost | soften-log | soften-compensate."""
    root = Path(str(args.root)).expanduser().resolve()
    action = str(getattr(args, "heat_action", None) or "check")
    try:
        from heat_check import (
            heat_boost,
            heat_check,
            heat_soften_compensate,
            heat_vo_suggest,
        )
    except Exception as exc:  # noqa: BLE001
        raise FilmError(f"Cannot import heat_check: {exc}") from exc
    if action in {"check", ""}:
        report = heat_check(root)
        emit(report)
        return 0 if report.get("ok") else 1
    if action == "vo-suggest":
        report = heat_vo_suggest(root, shot_id=getattr(args, "shot", None))
        emit(report)
        return 0
    if action == "boost":
        report = heat_boost(
            root,
            apply=bool(getattr(args, "apply", False)),
            target_score=float(getattr(args, "target_score", 90.0) or 90.0),
        )
        emit(report)
        return 0 if report.get("ok") else 1
    if action in {"soften-log", "soften-compensate"}:
        note = str(getattr(args, "note", "") or "moderation softed still/I2V")
        # soften-log is receipt-only; soften-compensate needs --apply to mutate film-spec
        apply = action == "soften-compensate" and bool(getattr(args, "apply", False))
        report = heat_soften_compensate(root, note=note, apply=apply)
        emit(report)
        return 0 if report.get("ok") else 1
    raise FilmError(f"unknown heat action: {action}")


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
    from cinematic_audit import write_audit

    cinematic = write_audit(root, require_authored_contract=True)
    report["cinematic_audit"] = cinematic
    if not cinematic.get("ok"):
        report.setdefault("hard", []).append(
            {
                "code": "CINEMATIC_AUDIT_FAILED",
                "message": ",".join(cinematic.get("blocking_codes") or []),
            }
        )
        report["hard_ok"] = False
    emit(report)
    if not report.get("hard_ok"):
        return 2
    if getattr(args, "strict", False) and not report.get("soft_ok"):
        return 3
    return 0


def cmd_cinematic_audit(args: argparse.Namespace) -> int:
    """Write a current, checksum-bound cinematic coherence audit without spending."""
    from cinematic_audit import write_audit

    report = write_audit(Path(args.root), require_authored_contract=True)
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_quality(args: argparse.Namespace) -> int:
    """Read persisted per-shot quality receipts without touching media."""
    from quality_gates import summarize_quality

    report = summarize_quality(Path(args.root), shot_id=getattr(args, "shot_id", None))
    if getattr(args, "shot_id", None):
        from take_registry import compare_takes

        manifest = load_manifest(Path(args.root).expanduser().resolve())
        report["take_comparison"] = compare_takes(manifest, str(args.shot_id))
    emit(report)
    return 0 if report["ok"] else 2


def cmd_benchmark(args: argparse.Namespace) -> int:
    from benchmark import run_benchmark

    report = run_benchmark(getattr(args, "root", None), suite=str(args.suite), mode=str(args.mode))
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_dialogue_benchmark(args: argparse.Namespace) -> int:
    from dialogue_benchmark import build_dialogue_benchmark

    report = build_dialogue_benchmark(Path(args.root))
    emit(report)
    return 0 if report.get("status") == "planned" else 2


def cmd_dialogue_benchmark_review(args: argparse.Namespace) -> int:
    from dialogue_benchmark import record_benchmark_arm

    try:
        parameters = json.loads(args.parameters_json)
    except json.JSONDecodeError as exc:
        raise FilmError("--parameters-json must be a JSON object") from exc
    if not isinstance(parameters, dict):
        raise FilmError("--parameters-json must be a JSON object")
    report = record_benchmark_arm(
        Path(args.root),
        weapon=args.weapon,
        artifact=Path(args.artifact),
        reviewer=args.reviewer,
        note=args.note,
        parameters=parameters,
    )
    emit(report)
    return 0


def cmd_dialogue_benchmark_approve(args: argparse.Namespace) -> int:
    from dialogue_benchmark import approve_benchmark_parameters

    report = approve_benchmark_parameters(
        Path(args.root), reviewer=args.reviewer, rationale=args.rationale
    )
    emit(report)
    return 0


def cmd_dialogue_production_plan(args: argparse.Namespace) -> int:
    from dialogue_production_plan import build_dialogue_production_plan

    try:
        report = build_dialogue_production_plan(Path(args.root))
    except ValueError as exc:
        emit({"ok": False, "status": "blocked", "reason": str(exc)})
        return 2
    emit(report)
    return 0


def cmd_dialogue_benchmark_queue(args: argparse.Namespace) -> int:
    from dialogue_benchmark_queue import (
        DialogueBenchmarkQueueError,
        claim,
        complete,
        enqueue,
        status,
        submit_comfy,
    )

    try:
        action = str(args.dialogue_benchmark_queue_action)
        if action == "enqueue":
            report = enqueue(Path(args.root))
        elif action == "claim":
            report = claim(Path(args.root))
        elif action == "complete":
            report = complete(Path(args.root), job_id=args.job_id, claim_token=args.claim_token)
        elif action == "submit-comfy":
            report = submit_comfy(
                Path(args.root),
                job_id=args.job_id,
                claim_token=args.claim_token,
                workflow=Path(args.workflow),
                weapon_id=args.weapon_id,
            )
        else:
            report = status(Path(args.root))
    except DialogueBenchmarkQueueError as exc:
        emit({"ok": False, "status": "blocked", "reason": str(exc)})
        return 2
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_creative_pipeline(args: argparse.Namespace) -> int:
    from creative_pipeline import (
        build_animatic_gate,
        build_radio_cut,
        preproduction_readiness,
        write_authoring_receipt,
    )

    root = Path(args.root).expanduser().resolve()
    action = str(args.pipeline_action)
    if action == "readiness":
        report = preproduction_readiness(root)
    elif action == "radio-cut":
        if args.write:
            write_authoring_receipt(
                root,
                "radio-cut",
                {
                    "timing_ok": bool(args.timing_ok),
                    "emotion_turns_ok": bool(args.emotion_turns_ok),
                    "shot_count": int(args.shot_count),
                },
            )
        report = build_radio_cut(root)
    elif action == "animatic":
        if args.write:
            write_authoring_receipt(
                root,
                "animatic",
                {
                    "coverage_ok": bool(args.coverage_ok),
                    "pace_ok": bool(args.pace_ok),
                    "performance_ok": bool(args.performance_ok),
                },
            )
        report = build_animatic_gate(root)
    else:
        raise FilmError(f"Unknown creative pipeline action: {action}")
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_dailies(args: argparse.Namespace) -> int:
    from dailies import dailies_status, update_dailies

    root = Path(args.root).expanduser().resolve()
    if args.dailies_action == "status":
        report = dailies_status(root)
    else:
        report = update_dailies(
            root,
            shot_id=args.shot_id,
            candidate=args.candidate,
            status=args.status,
            reviewer=args.reviewer,
            notes=args.notes,
            approved_budget=args.approved_budget,
            provider=args.provider,
            model=args.model,
            cost_usd=args.cost_usd,
            source_keyframe=args.source_keyframe,
            qa=json.loads(args.qa_json) if args.qa_json else None,
            director_score=args.director_score,
            issue_tags=args.issue_tag,
            reshoot_decision=args.reshoot_decision,
            selection_rationale=args.selection_rationale,
        )
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_post_quality(args: argparse.Namespace) -> int:
    from post_quality import audio_delivery_gate, premium_master_qc, register_vfx_shot, vfx_gate

    root = Path(args.root).expanduser().resolve()
    action = str(args.post_action)
    if action == "vfx-register":
        report = register_vfx_shot(
            root,
            shot_id=args.shot_id,
            plate=args.plate,
            status=args.status,
            reviewer=args.reviewer,
            notes=args.notes,
        )
    elif action == "vfx-check":
        report = vfx_gate(root)
    elif action == "audio-check":
        report = audio_delivery_gate(root)
    elif action == "master-qc":
        report = premium_master_qc(root, final=args.final)
    else:
        raise FilmError(f"Unknown post quality action: {action}")
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_provider_canary(args: argparse.Namespace) -> int:
    from provider_canary import canary_status, record_canary

    root = Path(args.root).expanduser().resolve()
    if args.canary_action == "status":
        report = canary_status(root)
    else:
        report = record_canary(
            root,
            provider=args.provider,
            output=args.output,
            reviewer=args.reviewer,
            identity_ok=args.identity_ok,
            motion_ok=args.motion_ok,
            notes=args.notes,
        )
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_delivery_package(args: argparse.Namespace) -> int:
    from delivery_package import build_delivery_package

    report = build_delivery_package(Path(args.root), allow_missing=bool(args.allow_missing))
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_quality_closure(args: argparse.Namespace) -> int:
    """Operate the evidence-only premium quality closure; never spends credits."""
    from quality_closure import build_benchmark_package, build_quality_report, record_blind_review

    root = Path(args.root).expanduser().resolve()
    action = str(args.quality_closure_action)
    if action == "package":
        report = build_benchmark_package(root)
    elif action == "report":
        report = build_quality_report(root)
    elif action == "review":
        try:
            scores = json.loads(args.scores_json)
        except json.JSONDecodeError as exc:
            raise FilmError("--scores-json must be a JSON object") from exc
        if not isinstance(scores, dict):
            raise FilmError("--scores-json must be a JSON object")
        report = record_blind_review(root, reviewer=args.reviewer, scores=scores, notes=args.notes)
    else:
        raise FilmError(f"Unknown quality closure action: {action}")
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_state_index(args: argparse.Namespace) -> int:
    """Checkpoint: state photos + keyframes + promote plan for fluid transitions."""
    skill_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from state_index_gate import run_state_index_check, write_state_index_receipt
    except ImportError as exc:
        raise FilmError(f"Cannot import state_index_gate: {exc}") from exc
    root = Path(args.root).expanduser().resolve()
    action = getattr(args, "state_index_action", None) or "check"
    if action == "approve-performance-state":
        from performance_state import approve_performance_state

        try:
            receipt = approve_performance_state(
                root,
                speaker=str(args.speaker),
                state_id=str(args.performance_state_id),
                image=Path(args.image),
                generation_receipt=Path(args.generation_receipt),
                reviewer=str(args.reviewer),
                review_note=str(args.review_note),
            )
        except ValueError as exc:
            raise FilmError(str(exc)) from exc
        emit({"ok": True, **receipt})
        return 0
    if action == "approve-state":
        from visual_bible import load_bible, save_bible
        from wardrobe_ladder import approve_state

        bible = load_bible(root)
        try:
            state = approve_state(
                bible,
                str(args.character_id),
                str(args.wardrobe_state_id),
                Path(args.image),
                root=root,
                reviewer=str(args.reviewer),
                review_note=str(args.review_note),
                generation_receipt=(
                    Path(args.generation_receipt) if args.generation_receipt else None
                ),
            )
        except ValueError as exc:
            raise FilmError(str(exc)) from exc
        save_bible(root, bible)
        emit(
            {
                "ok": True,
                "kind": "wardrobe-state-approved",
                "character_id": args.character_id,
                "state": state,
            }
        )
        return 0
    if action == "contact-sheet":
        from visual_bible import load_bible
        from wardrobe_ladder import render_contact_sheet

        try:
            sheet = render_contact_sheet(load_bible(root), str(args.character_id), root=root)
        except ValueError as exc:
            raise FilmError(str(exc)) from exc
        emit(
            {
                "ok": True,
                "kind": "wardrobe-ladder-contact-sheet",
                "character_id": args.character_id,
                **sheet,
            }
        )
        return 0
    report = run_state_index_check(root)
    path = write_state_index_receipt(root, report)
    report["receipt_path"] = str(path)
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
            "exact_state_ids": report.get("exact_state_ids") or {},
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


def cmd_promotion_report(args: argparse.Namespace) -> int:
    from promotion_report import build_promotion_report, write_promotion_report

    root = Path(args.root).expanduser().resolve()
    try:
        report = (
            write_promotion_report(root, args.out)
            if getattr(args, "out", None)
            else build_promotion_report(root)
        )
    except (OSError, ValueError) as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0


from cli_longform import cmd_longform  # noqa: E402
from cli_status import (  # noqa: E402, F401
    _status_audio_summary,
    _status_evidence,
    _status_inventory,
    _status_remotion_probe,
    cmd_status,
)


def cmd_production_evidence(args: argparse.Namespace) -> int:
    """Read-only evidence ledger for production gates."""
    from production_evidence import build_evidence

    report = build_evidence(Path(args.root).expanduser().resolve())
    emit(report)
    return 0


def _compatibility_vo_mode(spec: dict[str, Any]) -> dict[str, Any]:
    """Fill missing vo_mode with cinema dialogue primary chain (Chinese spoken)."""
    if str(spec.get("vo_mode") or "").strip():
        return spec
    shots = [
        shot
        for scene in spec.get("scenes") or []
        if isinstance(scene, dict)
        for shot in scene.get("shots") or []
        if isinstance(shot, dict)
    ]
    reason = "inferred_dialogue_drama_default"
    if shots and all(shot.get("silent") is True and not shot.get("dialogue") for shot in shots):
        reason = "inferred_dialogue_drama_zh_from_explicit_silent_shots"
    spec = dict(spec)
    spec["vo_mode"] = "dialogue_drama"
    spec["dialogue_spoken_lang"] = spec.get("dialogue_spoken_lang") or "zh"
    spec["narration_spoken_lang"] = spec.get("narration_spoken_lang") or "zh"
    spec["caption_lang"] = spec.get("caption_lang") or "zh"
    spec["compatibility"] = {
        "vo_mode": reason,
        "source_projection_mutated": False,
    }
    return spec


def _compatibility_director_intent(spec: dict[str, Any], root: Path) -> dict[str, Any]:
    """Project only signed director intent into legacy compiled specs."""
    if isinstance(spec.get("director_intent"), dict):
        return spec
    contract_path = root / "director-contract.json"
    if not contract_path.is_file():
        return spec
    contract = read_json(contract_path)
    if str(contract.get("status") or "").lower() != "locked":
        return spec
    intent = contract.get("intent")
    if not isinstance(intent, dict):
        return spec
    required = ("logline", "tone", "emotional_arc")
    if not all(intent.get(key) for key in required):
        return spec
    spec = dict(spec)
    spec["director_intent"] = {
        key: intent[key]
        for key in ("logline", "tone", "emotional_arc", "audience")
        if key in intent
    }
    spec.setdefault("compatibility", {})["director_intent"] = (
        "projected_from_locked_director_contract"
    )
    return spec


def _compatibility_screen_modes(spec: dict[str, Any]) -> dict[str, Any]:
    """Only label explicitly silent legacy shots; leave ambiguous shots blocked."""
    changed = False
    spec = dict(spec)
    scenes = []
    for scene in spec.get("scenes") or []:
        scene_copy = dict(scene) if isinstance(scene, dict) else scene
        if isinstance(scene_copy, dict):
            shots = []
            for shot in scene_copy.get("shots") or []:
                shot_copy = dict(shot) if isinstance(shot, dict) else shot
                if (
                    isinstance(shot_copy, dict)
                    and not shot_copy.get("screen_mode")
                    and shot_copy.get("silent") is True
                ):
                    shot_copy["screen_mode"] = "silence"
                    changed = True
                shots.append(shot_copy)
            scene_copy["shots"] = shots
        scenes.append(scene_copy)
    if changed:
        spec["scenes"] = scenes
        spec.setdefault("compatibility", {})["screen_mode"] = "silence_from_explicit_silent_shots"
    return spec


def _compatibility_audio_cues(spec: dict[str, Any], root: Path) -> dict[str, Any]:
    """Project declared locked-shot sound intent into non-executed cue plans."""
    contract_path = root / "director-contract.json"
    if not contract_path.is_file():
        return spec
    contract = read_json(contract_path)
    if str(contract.get("status") or "").lower() != "locked":
        return spec
    sounds = {
        str(shot.get("id")): shot.get("sound")
        for scene in contract.get("scenes") or []
        if isinstance(scene, dict)
        for shot in scene.get("shots") or []
        if isinstance(shot, dict) and isinstance(shot.get("sound"), dict)
    }
    changed = False
    spec = dict(spec)
    scenes = []
    for scene in spec.get("scenes") or []:
        scene_copy = dict(scene) if isinstance(scene, dict) else scene
        if isinstance(scene_copy, dict):
            shots = []
            for shot in scene_copy.get("shots") or []:
                shot_copy = dict(shot) if isinstance(shot, dict) else shot
                sound = sounds.get(str(shot_copy.get("id") if isinstance(shot_copy, dict) else ""))
                if (
                    isinstance(shot_copy, dict)
                    and shot_copy.get("silent") is True
                    and not shot_copy.get("audio_cues")
                    and isinstance(sound, dict)
                ):
                    duration = float(
                        shot_copy.get("duration_seconds") or shot_copy.get("duration_sec") or 0
                    )
                    ambience = str(sound.get("ambience") or "declared scene ambience")
                    cues = [
                        {
                            "kind": "ambience",
                            "start_offset_sec": 0,
                            "duration_sec": duration,
                            "asset_hint": ambience,
                        }
                    ]
                    for effect in (sound.get("effects") or [])[:2]:
                        cues.append(
                            {
                                "kind": "sfx",
                                "start_offset_sec": min(duration - 0.25, 1.0 + len(cues)),
                                "duration_sec": 0.25,
                                "asset_hint": str(effect),
                            }
                        )
                    shot_copy["audio_cues"] = cues
                    changed = True
                shots.append(shot_copy)
            scene_copy["shots"] = shots
        scenes.append(scene_copy)
    if changed:
        spec["scenes"] = scenes
        spec.setdefault("compatibility", {})["audio_cues"] = (
            "projected_from_locked_contract_sound_intent"
        )
    return spec


def _compatibility_dramatic_functions(spec: dict[str, Any]) -> dict[str, Any]:
    """Map only explicit legacy shot evidence into the current role enum."""
    spec = dict(spec)
    changed = False
    scenes = []
    for scene in spec.get("scenes") or []:
        current = dict(scene) if isinstance(scene, dict) else scene
        if isinstance(current, dict):
            shots = []
            for shot in current.get("shots") or []:
                item = dict(shot) if isinstance(shot, dict) else shot
                if isinstance(item, dict) and not item.get("dramatic_function"):
                    if str(item.get("screen_mode") or "") == "reaction":
                        item["dramatic_function"] = "reaction"
                    elif str(item.get("screen_mode") or "") == "silence" or item.get(
                        "director_beat"
                    ):
                        item["dramatic_function"] = "action"
                    else:
                        shots.append(item)
                        continue
                    changed = True
                shots.append(item)
            current["shots"] = shots
        scenes.append(current)
    if changed:
        spec["scenes"] = scenes
        spec.setdefault("compatibility", {})["dramatic_function"] = (
            "mapped_from_locked_shot_evidence"
        )
    return spec


def cmd_write_spec(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    ensure_tree(root)
    try:
        from narrative_control import NarrativeControlError, assert_projection_ready

        # write-spec creates the projection that later media gates require locked.
        assert_projection_ready(root, require_locked=False)
    except NarrativeControlError as exc:
        raise FilmError(f"{exc.code}: {exc}") from exc
    default_spec = root / "film-spec.json"
    spec_path = Path(args.spec).expanduser().resolve() if args.spec else default_spec
    spec = _compatibility_dramatic_functions(
        _compatibility_audio_cues(
            _compatibility_director_intent(
                _compatibility_screen_modes(_compatibility_vo_mode(read_json(spec_path))), root
            ),
            root,
        )
    )
    try:
        shots = validate_film_spec(
            spec,
            assign_missing_ids=True,
            film_root=root,
            enforce_narrative_timeline=True,
        )
    except FilmSpecError as exc:
        raise FilmError(str(exc)) from exc

    from cinematic_audit import audit

    # Write-spec is the graph-projection boundary and never admits an
    # incoherent shot contract into production.
    cinematic = audit(root, spec=spec)
    if not cinematic.get("ok"):
        raise FilmError(
            "cinematic audit failed: " + ",".join(cinematic.get("blocking_codes") or [])
        )

    from drama_graph import derive_graph

    # Validate the complete contract against a disposable projection before
    # touching the project. A rejected legacy spec must not become the new
    # on-disk truth merely because its graph has not yet been refreshed.
    with tempfile.TemporaryDirectory(prefix="aifilm-cinematic-") as staging:
        stage_root = Path(staging)
        write_json(stage_root / "film-spec.json", spec)
        staged_graph = derive_graph(stage_root, write=False)
        strict_cinematic = audit(
            root,
            spec=spec,
            graph=staged_graph,
            require_authored_contract=True,
        )
    if not strict_cinematic.get("ok"):
        raise FilmError(
            "cinematic audit failed: " + ",".join(strict_cinematic.get("blocking_codes") or [])
        )

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
        w_state = shot.get("wardrobe_state") or (shot.get("dsl") or {}).get("wardrobe_state")
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
    # The film spec is the projection source at this boundary. Rebuild its
    # graph before producing a strict audit so no production command can see a
    # stale or pre-contract beat map.
    derive_graph(root, write=True)
    manifest = load_manifest(root)
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
    truth = manifest.setdefault(
        "truth_contract",
        {"source_of_truth": "local-contract-and-receipts"},
    )
    truth["contract_sha256"] = sha256_file(root / "film-spec.json")
    truth["spec_sha256"] = truth["contract_sha256"]
    graph_path = root / "drama-graph.json"
    truth["graph_sha256"] = sha256_file(graph_path) if graph_path.is_file() else ""
    truth["timeline_sha256"] = sha256_file(root / "timeline.json")
    longform_plan = None
    if spec.get("production_mode") == "longform":
        try:
            from longform import LongformError, build_longform_plan

            longform_plan = build_longform_plan(root, write=True)
        except LongformError as exc:
            raise FilmError(f"longform production plan failed: {exc}") from exc
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    cont = spec.get("_continuity_lint") or lint_continuity(shots)
    write_json(root / "continuity_lint.json", cont)
    # Reconcile after writing the projection so the receipt binds the current
    # shot actions instead of the stale pre-write spec.
    try:
        from scene_sound import reconcile as reconcile_scene_sound

        scene_sound = reconcile_scene_sound(root, write=True)
    except Exception as exc:
        raise FilmError(f"scene-sound reconcile failed: {exc}") from exc
    from cinematic_audit import write_audit

    cinematic_receipt = write_audit(root, require_authored_contract=True)
    if not cinematic_receipt.get("ok"):
        raise FilmError(
            "cinematic audit failed after projection: "
            + ",".join(cinematic_receipt.get("blocking_codes") or [])
        )
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
            "longform_plan": {
                "path": str(root / "receipts" / "longform-production-plan.json"),
                "unit_count": len(longform_plan.get("units") or []),
                "content_sha256": longform_plan.get("content_sha256"),
            }
            if isinstance(longform_plan, dict)
            else None,
            "transition_intents": spec.get("transition_intents"),
            "sound_plan": spec.get("sound_plan"),
            "scene_sound": scene_sound,
            "cinematic_audit": cinematic_receipt,
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
    from media_qa import analyze_still_geometry
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
    if args.status == "approved":
        from anatomy_safety import AnatomySafetyError, require_anatomy_safe

        try:
            require_anatomy_safe(
                root=root, anatomy_safe=anatomy_safe, kind="still", shot_id=str(args.shot_id)
            )
        except AnatomySafetyError as exc:
            raise FilmError(str(exc)) from exc
        if not identity_approved:
            raise FilmError(
                "Approved stills require --identity-approved after comparing to cast master"
            )
        if not review_note:
            raise FilmError(
                "Approved stills require --review-note "
                "(e.g. 'id-ok face/hair/outfit; medium matches style-v1')"
            )
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
                if bool(getattr(args, "require_face_identity", False)) and not face_id_result.get(
                    "ok"
                ):
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
        )
        from util import sha256_file as chain_sha
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
            timeout=300,
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
            timeout=300,
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
    anatomy_safe = getattr(args, "anatomy_safe", False) is True
    queue_job_id = str(getattr(args, "queue_job_id", "") or "").strip()
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
                root=root, anatomy_safe=anatomy_safe, kind="clip", shot_id=str(args.shot_id)
            )
        except AnatomySafetyError as exc:
            raise FilmError(str(exc)) from exc
        if endpoint not in ALLOWED_VIDEO_ENDPOINTS:
            raise FilmError(
                f"Approved clips require --source-endpoint in {sorted(ALLOWED_VIDEO_ENDPOINTS)}"
            )
        if not identity_approved:
            raise FilmError(
                "Approved clips require --identity-approved after canonical identity review"
            )
        if not motion_approved:
            raise FilmError(
                "Approved clips require --motion-approved after watching the complete clip"
            )
        if not review_note:
            raise FilmError("Approved clips require --review-note with the visual review result")
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


def normalize_clip(
    src: Path, dest: Path, *, width: int, height: int, fps: int, duration: float | None
) -> None:
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


def _commit_selected_bgm_usage(
    root: Path,
    *,
    output: str | None = None,
    output_sha256: str | None = None,
) -> dict[str, Any] | None:
    """Commit approved-library use only after a successful final command."""
    selection_path = root / "receipts" / "bgm-selection.json"
    selection = _util_read_json(selection_path)
    if not isinstance(selection, dict) or not selection.get("selections"):
        return None
    mix_path = root / "audio" / "mix_report.json"
    mix = _util_read_json(mix_path)
    music_template = (
        mix.get("music_template")
        if isinstance(mix, dict) and isinstance(mix.get("music_template"), dict)
        else {}
    )
    if (
        music_template.get("source") != "approved_library"
        or music_template.get("mode") != "approved_library"
    ):
        # A stale selection receipt must not affect a procedural or legacy rerun.
        return None
    if not all(
        isinstance(item, dict) and item.get("asset_id") and item.get("sha256")
        for item in selection.get("selections") or []
    ):
        raise FilmError("approved-library selection receipt is not checksum-bound")
    selected_bindings = [
        (str(item.get("shot_id") or ""), str(item["asset_id"]), str(item["sha256"]))
        for item in selection["selections"]
    ]
    mixed_bindings = [
        (
            str(item.get("shot_id") or ""),
            str(item.get("asset_id") or ""),
            str(item.get("sha256") or ""),
        )
        for item in music_template.get("selections") or []
        if isinstance(item, dict)
    ]
    if (
        selected_bindings != mixed_bindings
        or selection.get("catalog_revision") != music_template.get("catalog_revision")
        or selection.get("catalog_sha256") != music_template.get("catalog_sha256")
    ):
        raise FilmError("approved-library selection does not match this final mix")
    checksum = str(output_sha256 or "")
    if len(checksum) != 64 and output:
        output_path = Path(output).expanduser()
        if output_path.is_file():
            checksum = sha256_file(output_path)
    if len(checksum) != 64:
        delivery = _util_read_json(root / "out" / "final-delivery.json") or {}
        checksum = str(delivery.get("output_sha256") or "")
    if len(checksum) != 64:
        raise FilmError("cannot commit BGM usage without the successful final checksum")
    from bgm_library import commit_usage, default_library_root

    committed = commit_usage(default_library_root(), selection, final_sha256=checksum)
    selection["usage_committed"] = True
    selection["usage_commit"] = committed
    write_json(selection_path, selection)
    if isinstance(mix, dict):
        music_template["usage_commit"] = committed
        mix["music_template"] = music_template
        write_json(mix_path, mix)
    return committed


def cmd_final(args: argparse.Namespace) -> int:
    """FFmpeg final, optionally followed by HyperFrames/Remotion designed-post compose-render."""
    skill_dir = Path(__file__).resolve().parents[1]
    script = skill_dir / "scripts" / "render_final.py"
    if not script.is_file():
        raise FilmError(f"Missing {script}")
    root = Path(args.root).expanduser().resolve()
    from production_truth import ProductionTruthError, require_current_canonical_truth

    try:
        require_current_canonical_truth(root)
    except ProductionTruthError as exc:
        raise FilmError(str(exc)) from exc
    post_engine = str(getattr(args, "post_engine", "hyperframes") or "hyperframes").strip().lower()
    if post_engine not in {"ffmpeg", "hyperframes", "remotion"}:
        raise FilmError("--post-engine must be ffmpeg|hyperframes|remotion")
    post_plan: dict[str, Any] | None = None
    if (root / "post-plan.json").is_file():
        sys.path.insert(0, str(skill_dir / "scripts"))
        try:
            from post_plan import PostPlanError, load_post_plan, record_render_evidence

            post_plan = load_post_plan(root, required=True)
            if post_engine != post_plan["post_owner"]:
                raise PostPlanError(
                    f"post-plan post_owner={post_plan['post_owner']}; --post-engine {post_engine} is not allowed"
                )
        except ImportError as exc:
            raise FilmError(f"Cannot import post_plan: {exc}") from exc
        except PostPlanError as exc:
            raise FilmError(str(exc)) from exc

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
        log(f"preflight ok (hard=0 soft={len(soft)}) → post_engine={post_engine}")

    from cinematic_audit import write_audit

    cinematic = write_audit(root, require_authored_contract=True, require_clip_evidence=True)
    if not cinematic.get("ok"):
        raise FilmError(
            "Cannot render final: cinematic audit failed ["
            + ", ".join(cinematic.get("blocking_codes") or [])
            + "]"
        )

    # Fail early before TTS if loop-risk VO would force boring stream_loop.
    # When receipts/tts-rehearsal.json present, measured_duration_sec preferred over estimate.
    from production_gates import (
        ProductionGateError,
        assert_heat_allows_final,
        assert_no_loop_risk,
    )

    try:
        assert_no_loop_risk(
            root,
            force=bool(getattr(args, "allow_loop_risk", False)),
            strict_tts_rehearsal=bool(getattr(args, "strict_tts_rehearsal", False)),
        )
    except ProductionGateError as exc:
        raise FilmError(str(exc)) from exc

    # Wave 6: adult-max final requires heat final_ok (S-grade), not only A
    try:
        assert_heat_allows_final(
            root,
            force=bool(getattr(args, "skip_heat_gate", False)),
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

    # ── Staged final (P0 · 2026-07-23): no assumed captions ──
    # stage_plate  → FFmpeg VO/BGM/clips; HF/Remotion path forces plate subs=off
    # stage_hf     → HyperFrames owns designed captions (export+render)
    # stage_caption→ verify pixels; HyperFrames is the sole caption owner
    # Never: hand-mux silent plate and claim "HF will have burned subs".
    stages_receipt: dict[str, Any] = {}
    subs_mode = str(getattr(args, "subs", None) or "").strip().lower()
    if not subs_mode:
        # HF/Remotion: plate must NOT burn (HF owns captions). FFmpeg: plate burns.
        subs_mode = "off" if post_engine in {"hyperframes", "remotion"} else "burn"
    plate_cards = str(getattr(args, "plate_cards", None) or "auto").strip().lower()
    if plate_cards in {"", "auto"}:
        plate_cards = "blank" if post_engine in {"hyperframes", "remotion"} else "text"
    if plate_cards not in {"text", "blank"}:
        raise FilmError("--plate-cards must be auto|text|blank")
    if post_engine in {"hyperframes", "remotion"} and subs_mode == "burn":
        log(
            "stage_plate: forcing --subs off for designed-post "
            "(HF/Remotion owns captions; plate burn would double-burn underlay)"
        )
        subs_mode = "off"
        if plate_cards == "text":
            plate_cards = "blank"

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
    if bool(getattr(args, "resume", False)):
        cmd += ["--resume"]
    if bool(getattr(args, "force", False)):
        cmd += ["--force"]
    cmd += ["--subs", subs_mode]
    cmd += ["--plate-cards", plate_cards]
    log(
        f"stage_plate: render_final.py (post_engine={post_engine}, "
        f"subs={subs_mode}, plate_cards={plate_cards}) — captions NOT assumed here"
    )
    # Short films retain the 1200s floor; longform scales by picture clock,
    # shot count and lipsync work instead of being killed by a fixed timeout.
    requested_timeout = int(getattr(args, "plate_timeout", 0) or 0)
    if requested_timeout > 0:
        plate_timeout = requested_timeout
    else:
        from longform import estimate_plate_timeout

        plate_timeout = estimate_plate_timeout(
            root,
            lipsync=str(getattr(args, "lipsync", "off") or "off"),
        )
    from pipeline_events import append_event

    append_event(
        root,
        stage="final-plate",
        phase="started",
        note=f"timeout_sec={plate_timeout}",
    )
    try:
        proc = run(cmd, check=False, timeout=plate_timeout)
    except subprocess.TimeoutExpired as exc:
        append_event(
            root,
            stage="final-plate",
            phase="failed",
            note=f"timeout_sec={plate_timeout}",
        )
        # Wave D: do not leave agents guessing — point at direct render_final + floor
        skill_scripts = Path(__file__).resolve().parent
        raise FilmError(
            f"final plate timed out after {plate_timeout}s. "
            f"Retry with --plate-timeout {max(plate_timeout * 2, 1800)} "
            f"or direct: {skill_scripts / 'runtime-python'} "
            f"{skill_scripts / 'render_final.py'} --root {root} "
            f"(set AIFILM_FFMPEG_TIMEOUT≥1800 for long mixes)"
        ) from exc
    append_event(
        root,
        stage="final-plate",
        phase="completed" if proc.returncode == 0 else "failed",
        note=f"returncode={proc.returncode}; timeout_sec={plate_timeout}",
    )
    sys.stderr.write(proc.stderr or "")
    ffmpeg_result: dict[str, Any] | None = None
    if proc.stdout:
        try:
            ffmpeg_result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            # keep raw for ffmpeg-only path
            if post_engine == "ffmpeg":
                print(proc.stdout)
    stages_receipt["plate"] = {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "subs": subs_mode,
        "plate_cards": plate_cards,
        "timeout_sec": plate_timeout,
        "ffmpeg": {
            "output": (ffmpeg_result or {}).get("output"),
            "srt": (ffmpeg_result or {}).get("srt") or str(root / "out" / "final.srt"),
            "subtitles": (ffmpeg_result or {}).get("subtitles"),
        },
    }
    if proc.returncode != 0:
        if post_engine == "ffmpeg" and not proc.stdout:
            pass
        elif post_engine != "ffmpeg":
            emit(
                {
                    "ok": False,
                    "post_engine": post_engine,
                    "stage": "plate",
                    "stages": stages_receipt,
                    "error": (proc.stderr or proc.stdout or "render_final failed")[:2000],
                    "ffmpeg": ffmpeg_result,
                }
            )
        return proc.returncode

    if post_engine == "ffmpeg":
        if ffmpeg_result is not None:
            out_obj = {
                **ffmpeg_result,
                "post_engine": "ffmpeg",
                "stages": stages_receipt,
                "caption_owner": "ffmpeg_plate",
            }
            bgm_usage = _commit_selected_bgm_usage(
                root,
                output=out_obj.get("output"),
                output_sha256=out_obj.get("output_sha256"),
            )
            if bgm_usage is not None:
                out_obj["bgm_usage"] = bgm_usage
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

    # stage_hf / stage_remotion: designed-post AFTER plate (subs off)
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from compose_render import (
            ComposeRenderError,
            compose_render,
            probe_designed_post_tooling,
            probe_remotion_readiness,
        )
        from final_stages import (
            ensure_captions_after_hf,
            patch_delivery_burned_in,
            write_stages_receipt,
        )
    except ImportError as exc:
        raise FilmError(f"Cannot import compose_render/final_stages: {exc}") from exc

    if post_engine == "hyperframes":
        tooling = probe_designed_post_tooling()
        if not tooling.get("npx") or not tooling.get("hyperframes_ok"):
            raise FilmError(
                "post-engine=hyperframes 需要 Node/npx + hyperframes；"
                f"tooling={tooling}。可改用 --post-engine ffmpeg，"
                "或安装 Node 22+ 后重试。"
            )
        log(
            "stage_hf: HyperFrames export+render owns designed captions "
            "(plate was subs=off; no double-burn assume)"
        )
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
        if post_plan is not None and result.get("rendered"):
            try:
                record_render_evidence(
                    root,
                    engine=post_engine,
                    output=result.get("output"),
                    composition_checked=bool(result.get("steps", {}).get("check", {}).get("ok")),
                    ffprobe_readback=bool(
                        result.get("register", {}).get("technical_qa", {}).get("ok")
                    ),
                    technical_qa_report=result.get("register", {}).get("report"),
                )
            except PostPlanError as exc:
                raise FilmError(str(exc)) from exc
        stages_receipt["hf"] = {
            "ok": True,
            "output": result.get("output"),
            "output_sha256": result.get("output_sha256"),
        }

        # stage_caption: verify HF put captions in delivery.  A formal HF
        # deliverable never falls back to another caption renderer: that would
        # violate the single-owner contract and hide a broken HF export.
        final_path = Path(str(result.get("output") or root / "out" / "film_final.mp4"))
        log("stage_caption: verify HF caption ownership (no assume) ...")
        caption_gate = ensure_captions_after_hf(
            root,
            final_mp4=final_path,
        )
        stages_receipt["caption"] = caption_gate
        if not caption_gate.get("ok"):
            stages_path = write_stages_receipt(root, stages_receipt)
            emit(
                {
                    "ok": False,
                    "post_engine": "hyperframes",
                    "stage": "caption",
                    "stages": stages_receipt,
                    "stages_receipt": str(stages_path),
                    "error": caption_gate.get("error")
                    or "HF caption gate failed; a HyperFrames re-render is required",
                    "next": [
                        "inspect compose/hyperframes caption layout and SRT binding",
                        "re-run: aifilm final --post-engine hyperframes",
                    ],
                }
            )
            return 2
        owner = str(caption_gate.get("caption_owner") or "hyperframes")
        burned = owner in {
            "hyperframes",
            "hyperframes_export_only",
        }
        stages_receipt["deliver"] = patch_delivery_burned_in(root, burned_in=burned, owner=owner)
        stages_path = write_stages_receipt(root, stages_receipt)
        log(f"stage_deliver: caption_owner={owner} burned_in={burned} receipt={stages_path}")
        out_obj: dict[str, Any] = {
            "ok": True,
            "post_engine": "hyperframes",
            "ffmpeg": ffmpeg_result,
            "compose": result,
            "output": str(final_path),
            "output_sha256": result.get("output_sha256"),
            "caption_owner": owner,
            "stages": stages_receipt,
            "stages_receipt": str(stages_path),
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
        if post_plan is not None and result.get("rendered"):
            try:
                record_render_evidence(
                    root,
                    engine=post_engine,
                    output=result.get("output"),
                    ffprobe_readback=bool(
                        result.get("register", {}).get("technical_qa", {}).get("ok")
                    ),
                    technical_qa_report=result.get("register", {}).get("report"),
                )
            except PostPlanError as exc:
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
        if out_obj.get("ok"):
            bgm_usage = _commit_selected_bgm_usage(
                root,
                output=out_obj.get("output"),
                output_sha256=out_obj.get("output_sha256"),
            )
            if bgm_usage is not None:
                out_obj["bgm_usage"] = bgm_usage
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
                i.get("code") for i in (preflight_report.get("soft") or []) if isinstance(i, dict)
            ],
        }
    bgm_usage = _commit_selected_bgm_usage(
        root,
        output=out_obj.get("output"),
        output_sha256=out_obj.get("output_sha256"),
    )
    if bgm_usage is not None:
        out_obj["bgm_usage"] = bgm_usage
    emit(out_obj)
    return 0


def which_npx_safe() -> str | None:
    import shutil

    return shutil.which("npx")


def cmd_review_final(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    from production_truth import ProductionTruthError, require_current_canonical_truth

    try:
        require_current_canonical_truth(root)
    except ProductionTruthError as exc:
        raise FilmError(str(exc)) from exc
    from cinematic_audit import write_audit

    cinematic = write_audit(root, require_authored_contract=True, require_media_evidence=True)
    if not cinematic.get("ok"):
        raise FilmError(
            "Cannot approve final: cinematic audit failed ["
            + ", ".join(cinematic.get("blocking_codes") or [])
            + "]"
        )
    manifest = load_manifest(root)
    review_input = None
    if getattr(args, "review_file", None):
        try:
            from final_review_input import FinalReviewInputError, apply_review_input

            review_input = apply_review_input(args, root=root, path=args.review_file)
        except FinalReviewInputError as exc:
            raise FilmError(str(exc)) from exc
    summary = recompute_gates(root, manifest)
    if not summary["gates"]["clips_complete"]:
        raise FilmError(
            "Cannot approve final: not every planned clip has endpoint, identity, motion, and decode QA"
        )
    final_record = (manifest.get("outputs") or {}).get("final_film")
    if (root / "post-plan.json").is_file():
        try:
            from post_plan import PostPlanError, load_post_plan

            plan = load_post_plan(root, required=True)
            if (
                not isinstance(final_record, dict)
                or final_record.get("post_engine") != plan["post_owner"]
            ):
                raise PostPlanError(
                    f"post-plan post_owner={plan['post_owner']} does not match final_film post_engine="
                    f"{(final_record or {}).get('post_engine')}"
                )
        except PostPlanError as exc:
            raise FilmError(f"Cannot approve final: {exc}") from exc
    out_dir = film_dirs(root)["out"]
    if not record_file_matches(out_dir, final_record, field="final film path"):
        raise FilmError(
            "Cannot approve final: final film is missing or its SHA-256 no longer matches"
        )
    final_path = safe_existing_file(out_dir, final_record["path"], field="final film path")
    try:
        technical_qa = analyze_media(final_path, require_audio=True, require_motion=True)
    except (MediaQAError, SecurityPolicyError) as exc:
        raise FilmError(str(exc)) from exc
    if not technical_qa.get("ok"):
        raise FilmError(f"Cannot approve final: technical QA failed: {technical_qa.get('errors')}")
    from final_editorial_review import audit as editorial_audit

    editorial_review = editorial_audit(root, write=True)
    if not editorial_review.get("ok"):
        codes = ", ".join(
            str(item.get("code") or "FAILED") for item in editorial_review.get("issues") or []
        )
        raise FilmError("Cannot approve final: editorial review requires recut [" + codes + "]")
    editorial_receipt = Path(str(editorial_review["path"]))
    editorial_review["receipt_sha256"] = sha256(editorial_receipt)
    # v1.23: objective delivery-quality gate before the director's subjective scorecard.
    # Fails here = not worth a human reviewer's time (decode errors, missing audio,
    # black frames, freezes, or overall score below the floor).
    from quality_check_video import QualityCheckError, load_quality_report, run_quality_check

    quality_report = load_quality_report(root)
    if not quality_report or quality_report.get("video") != str(final_path):
        try:
            quality_report = run_quality_check(
                final_path,
                out_dir=str(out_dir),
                expect_audio=True,
                expect_subtitles=True,
                srt=str(out_dir / "final.srt") if (out_dir / "final.srt").is_file() else None,
                min_score=0,
            )
        except QualityCheckError as exc:
            raise FilmError(f"Cannot approve final: delivery quality check failed: {exc}") from exc
    if quality_report.get("hard_fail"):
        failed_gates = [
            name
            for name, gate in (quality_report.get("gates") or {}).items()
            if isinstance(gate, dict) and gate.get("status") == "fail"
        ]
        raise FilmError(
            f"Cannot approve final: delivery quality hard-fail on {', '.join(failed_gates)} "
            f"(score={quality_report.get('score')}/100). "
            "Fix the technical issue then re-run review-final."
        )
    # Adult max cannot inherit a plan-only score.  The receipt binds each
    # reviewed act/climax clip and the current audio/timeline evidence.
    try:
        from adult_max_director import build_evidence

        adult_sensory = build_evidence(root, write=True)
    except (OSError, ValueError) as exc:
        raise FilmError(f"Cannot approve final: adult max sensory evidence failed: {exc}") from exc
    if adult_sensory.get("active") and not adult_sensory.get("ok"):
        raise FilmError(
            "Cannot approve final: adult max sensory evidence is incomplete ["
            + ", ".join(adult_sensory.get("codes") or [])
            + "]"
        )
    # P0 · Wave 6: heat final_ok (S-grade + arc) before final_complete
    try:
        from production_gates import ProductionGateError, assert_heat_allows_final

        heat_gate = assert_heat_allows_final(root, write_receipt=True)
    except ProductionGateError as exc:
        raise FilmError(f"Cannot approve final: {exc}") from exc
    except Exception as exc:  # pragma: no cover
        raise FilmError(f"Cannot approve final: heat final gate failed: {exc}") from exc
    if heat_gate.get("active") is False and heat_gate.get("skipped"):
        pass
    # Keep full heat receipt for audit (scorecard body)
    try:
        from heat_check import heat_check as _heat_check

        heat_rep_final = _heat_check(root)
    except Exception as exc:  # pragma: no cover
        heat_rep_final = {"ok": False, "error": str(exc)}
    with contextlib.suppress(OSError):
        write_json(
            root / "receipts" / "heat-final-gate.json",
            {
                "ok": True,
                "at": utc_now(),
                "gate": heat_gate,
                "impact_score": heat_gate.get("score"),
                "target_s": heat_gate.get("target_s"),
                "heat_line": (heat_rep_final or {}).get("line"),
            },
        )
    reviewer = str(args.reviewer or "").strip()
    notes = str(args.notes or "").strip()
    if not args.approve:
        raise FilmError(
            "Full-film review requires explicit --approve after watching the entire film"
        )
    if not reviewer or not notes:
        raise FilmError("Full-film review requires non-empty --reviewer and --notes")
    try:
        card = build_scorecard_from_cli(args)
        manifest_contract = int(manifest.get("review_contract_version") or 1)
        grades = build_grades_from_cli(args, required=manifest_contract >= 3)
        fail_reasons = parse_fail_reasons(
            list(getattr(args, "fail_reason", None) or []),
            failures=[dim for dim, passed in card.items() if not passed],
            required=manifest_contract >= 3,
        )
    except DirectorReviewError as exc:
        raise FilmError(str(exc)) from exc
    if manifest_contract >= 3 and not getattr(args, "watched_full", False):
        raise FilmError("review contract v3 requires --watched-full")
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
    from performance_timeline import build_performance_timeline

    performance_timeline = build_performance_timeline(root)
    if performance_timeline["required"] and not performance_timeline["ok"]:
        codes = ", ".join(sorted({item["code"] for item in performance_timeline["errors"]}))
        raise FilmError(f"Cannot approve final: performance timeline is incomplete: {codes}")
    from speech_performance_timing import build_speech_performance_timing

    speech_performance_timing = build_speech_performance_timing(root)
    if speech_performance_timing["required"] and not speech_performance_timing["ok"]:
        codes = ", ".join(sorted({item["code"] for item in speech_performance_timing["errors"]}))
        raise FilmError(f"Cannot approve final: speech/performance timing is incomplete: {codes}")
    from audio_provenance import build_audio_provenance

    audio_provenance = build_audio_provenance(root)
    if audio_provenance["required"] and not audio_provenance["ok"]:
        codes = ", ".join(sorted({item["code"] for item in audio_provenance["errors"]}))
        raise FilmError(f"Cannot approve final: audio provenance is incomplete: {codes}")
    from subtitle_dialogue_alignment import build_subtitle_dialogue_alignment

    subtitle_dialogue_alignment = build_subtitle_dialogue_alignment(root)
    if subtitle_dialogue_alignment["required"] and not subtitle_dialogue_alignment["ok"]:
        codes = ", ".join(sorted({item["code"] for item in subtitle_dialogue_alignment["errors"]}))
        raise FilmError(f"Cannot approve final: subtitle/dialogue alignment is incomplete: {codes}")
    from subtitle_cut_boundaries import build_subtitle_cut_boundaries

    subtitle_cut_boundaries = build_subtitle_cut_boundaries(root)
    if subtitle_cut_boundaries["required"] and not subtitle_cut_boundaries["ok"]:
        raise FilmError("Cannot approve final: subtitle crosses a hard or continue cut boundary")
    from director_ledger import build_director_ledger

    director_ledger = build_director_ledger(root)
    if director_ledger["required"] and not director_ledger["ok"]:
        raise FilmError(
            "Cannot approve final: director exception ledger has pending re-approval items"
        )

    from narrative_evidence import validate_narrative_evidence

    narrative_evidence = validate_narrative_evidence(root, require_verified=True)
    if narrative_evidence.get("required") and not narrative_evidence.get("ok"):
        codes = ", ".join(
            sorted({str(item.get("code")) for item in narrative_evidence.get("issues") or []})
        )
        raise FilmError(
            f"Cannot approve final: narrative hook/plot-point evidence is incomplete [{codes}]. "
            "Write narrative-evidence.json with executed and human_review evidence first."
        )

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
            "grades": grades,
            "fail_reasons": fail_reasons,
            "watched_full": bool(getattr(args, "watched_full", False)),
            "screening_evidence": screening_evidence,
            "performance_timeline": performance_timeline,
            "speech_performance_timing": speech_performance_timing,
            "audio_provenance": audio_provenance,
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
        "editorial_review": editorial_review,
        "scorecard": scorecard,
        "grades": grades,
        "fail_reasons": fail_reasons,
        "watched_full": bool(getattr(args, "watched_full", False)),
        "screening": {
            "path": str(final_path),
            "sha256": final_record["sha256"],
            "duration_sec": technical_qa.get("duration_sec"),
        },
        "screening_evidence": screening_evidence,
        "performance_timeline": performance_timeline,
        "speech_performance_timing": speech_performance_timing,
        "audio_provenance": audio_provenance,
        "subtitle_dialogue_alignment": subtitle_dialogue_alignment,
        "subtitle_cut_boundaries": subtitle_cut_boundaries,
        "director_ledger": director_ledger,
        "narrative_evidence": narrative_evidence,
        "adult_max_sensory": adult_sensory,
    }
    review_path = out_dir / "final-review.json"
    write_json(review_path, review)
    review["path"] = str(review_path)
    manifest.setdefault("outputs", {})["final_review"] = review
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    try:
        from pipeline_events import append_event

        append_event(root, stage="review-final", phase="completed")
        if review_input is not None:
            append_event(
                root,
                stage="review-final",
                phase="human_time",
                human_minutes=float(review_input["human_minutes"]),
                actor=str(review_input["reviewer"]),
                note="review-file",
            )
    except OSError:
        pass
    try:
        from quality_ledger import emit_quality_ledger

        quality_ledger = emit_quality_ledger(root)
    except (OSError, ValueError) as exc:
        raise FilmError(
            f"final review succeeded but quality ledger could not be written: {exc}"
        ) from exc
    try:
        from production_report import emit_production_report

        production_report = emit_production_report(root)
    except (OSError, ValueError) as exc:
        raise FilmError(
            f"final review succeeded but production report could not be written: {exc}"
        ) from exc
    try:
        from optimization_metrics import emit_metrics

        optimization_metrics = emit_metrics(root)
    except (OSError, ValueError) as exc:
        optimization_metrics = {"ok": False, "error": str(exc)}
    emit(
        {
            "ok": True,
            "final_complete": manifest["gates"]["final_complete"],
            "review": review,
            "quality_ledger": str(root / "receipts" / "quality-ledger.json"),
            "retrospective_complete": quality_ledger["retrospective_complete"],
            "production_report": production_report["paths"],
            "optimization_metrics": optimization_metrics,
        }
    )
    return 0


def cmd_final_editorial_review(args: argparse.Namespace) -> int:
    """Write the no-spend final editorial report without granting approval."""
    from final_editorial_review import audit

    report = audit(Path(args.root).expanduser().resolve(), write=True)
    emit(report)
    return 0 if report["ok"] else 2


def cmd_review_shot(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    ensure_tree(root)
    try:
        from cli.review import create_shot_review_report
        from shot_review import ShotReviewError

        report = create_shot_review_report(args)
        report["path"] = str(Path(report["path"]).resolve())
    except (ShotReviewError, MediaQAError, ValueError) as exc:
        raise FilmError(str(exc)) from exc
    emit({"ok": True, "approved": report["approved"], "review": report})
    return 0


def cmd_review_contract(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    manifest = load_manifest(root)
    if args.review_contract_action == "upgrade-v3":
        manifest["review_contract_version"] = 3
        save_manifest(root, manifest)
        emit(
            {
                "ok": True,
                "review_contract_version": 3,
                "note": "Future review-final calls require watched_full, grades, and canonical fail reasons.",
            }
        )
        return 0
    if args.review_contract_action != "migrate":
        raise FilmError(f"unknown review-contract action: {args.review_contract_action}")
    from cli.review import migrate_review_contract

    legacy, _migrated_at = migrate_review_contract(manifest)
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    emit(
        {
            "ok": True,
            "review_contract_version": 2,
            "pending_shot_reviews": legacy,
            "note": "existing approvals remain historical records; review each listed clip before it can satisfy v1.6 delivery gates",
        }
    )
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
    from cinematic_audit import write_audit

    cinematic = write_audit(root, require_authored_contract=True)
    if not cinematic.get("ok"):
        raise FilmError(
            "pilot blocked by cinematic audit ["
            + ", ".join(cinematic.get("blocking_codes") or [])
            + "]"
        )
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
        if action == "pack":
            from pilot_pack import pilot_pack

            shots_raw = str(getattr(args, "shots", "") or "")
            shots = [s.strip() for s in shots_raw.split(",") if s.strip()] or None
            emit(pilot_pack(root, shots=shots))
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
            shots = [
                s.strip() for s in str(getattr(args, "shots", "") or "").split(",") if s.strip()
            ]
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
            routing = read_json(root / "receipts" / "i2v-routing.json")
            if routing:
                approval["i2v_routing"] = {
                    "selected_provider": routing.get("selected_provider"),
                    "requested_profile": routing.get("requested_profile"),
                }
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
            "export-compose requires clips_complete (every planned shot has approved register-clip)"
        )
    requested_engine = str(getattr(args, "engine", "both") or "both")
    requested_owner = str(getattr(args, "post_owner", "") or "").strip().lower()
    if requested_owner not in {"", "ffmpeg", "hyperframes", "remotion"}:
        raise FilmError("--post-owner must be ffmpeg|hyperframes|remotion")
    owner = requested_owner or ("remotion" if requested_engine == "remotion" else "hyperframes")
    try:
        from post_plan import PostPlanError, ensure_post_plan

        post_plan, post_plan_created = ensure_post_plan(root, owner=owner)
    except ImportError as exc:
        raise FilmError(f"Cannot import post_plan: {exc}") from exc
    except PostPlanError as exc:
        raise FilmError(str(exc)) from exc
    locked_owner = str(post_plan["post_owner"])
    if not post_plan_created:
        if requested_owner and requested_owner != locked_owner:
            raise FilmError(
                f"post-plan post_owner={locked_owner}; --post-owner {requested_owner} would overwrite it"
            )
        if requested_engine not in {locked_owner, "both"}:
            raise FilmError(
                f"post-plan post_owner={locked_owner}; export-compose --engine {requested_engine} is not allowed "
                "(use the owner engine or --engine both for comparison)"
            )
    try:
        result = export_composition(
            root,
            engine=requested_engine,
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
    result["post_plan"] = {
        "path": str(root / "post-plan.json"),
        "post_owner": post_plan["post_owner"],
        "created": post_plan_created,
    }
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
    try:
        from post_plan import PostPlanError, record_render_evidence, validate_render_owner

        selected_engine = (
            str(getattr(args, "post_engine", "external") or "external")
            if getattr(args, "register_only", None)
            else str(getattr(args, "engine", "hyperframes") or "hyperframes")
        )
        plan = validate_render_owner(root, selected_engine)
    except ImportError as exc:
        raise FilmError(f"Cannot import post_plan: {exc}") from exc
    except PostPlanError as exc:
        raise FilmError(str(exc)) from exc
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
        if plan is not None:
            try:
                validate_render_owner(
                    root, str(getattr(args, "post_engine", "external") or "external")
                )
                record_render_evidence(
                    root,
                    engine=str(plan["post_owner"]),
                    output=str(args.register_only),
                    ffprobe_readback=bool(result.get("technical_qa", {}).get("ok")),
                    technical_qa_report=result.get("report"),
                )
            except PostPlanError as exc:
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
    if plan is not None and result.get("rendered"):
        try:
            record_render_evidence(
                root,
                engine=str(plan["post_owner"]),
                output=result.get("output"),
                composition_checked=bool(result.get("steps", {}).get("check", {}).get("ok")),
                ffprobe_readback=bool(result.get("register", {}).get("technical_qa", {}).get("ok")),
                technical_qa_report=result.get("register", {}).get("report"),
            )
        except PostPlanError as exc:
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
        from post_plan import PostPlanError, record_render_evidence, validate_render_owner

        plan = validate_render_owner(
            root, str(getattr(args, "post_engine", "external") or "external")
        )
    except ImportError as exc:
        raise FilmError(f"Cannot import post_plan: {exc}") from exc
    except PostPlanError as exc:
        raise FilmError(str(exc)) from exc
    manifest = load_manifest(root) if (root / MANIFEST_NAME).is_file() else {}
    if int(manifest.get("quality_evidence_contract_version") or 0) >= 1:
        from quality_closure import _shot_quality_closure

        closure = _shot_quality_closure(root)
        if not closure.get("ok") or not int(closure.get("approved_shot_count") or 0):
            raise FilmError(
                "register-final requires complete current per-shot quality evidence; "
                f"missing={closure.get('missing')}, duplicates={closure.get('duplicates')}"
            )
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
    if plan is not None:
        try:
            record_render_evidence(
                root,
                engine=str(plan["post_owner"]),
                output=str(getattr(args, "source", "")),
                ffprobe_readback=bool(result.get("technical_qa", {}).get("ok")),
                technical_qa_report=result.get("report"),
            )
        except PostPlanError as exc:
            raise FilmError(str(exc)) from exc
    emit(result)
    return 0


def cmd_post_plan(args: argparse.Namespace) -> int:
    """Create and validate the single editorial-to-post handoff contract."""
    skill_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(skill_dir / "scripts"))
    try:
        from post_plan import (
            PostPlanError,
            delivery_status,
            load_post_plan,
            new_post_plan,
            post_plan_path,
            validate_post_plan,
            write_post_plan,
        )
    except ImportError as exc:
        raise FilmError(f"Cannot import post_plan: {exc}") from exc
    root = Path(args.root).expanduser().resolve()
    try:
        if args.post_plan_action == "init":
            plan = new_post_plan(
                root,
                owner=str(getattr(args, "owner", "hyperframes") or "hyperframes"),
                edl_path=getattr(args, "edl", None),
                master_subtitles=getattr(args, "master_subtitles", "out/final.srt"),
                audio_plan=getattr(args, "audio_plan", "sound-plan.json"),
            )
            path = write_post_plan(root, plan, force=bool(getattr(args, "force", False)))
            emit({"ok": True, "path": str(path), "post_plan": plan})
            return 0
        plan = load_post_plan(root, required=True)
        result = validate_post_plan(
            root, plan, check_artifacts=bool(getattr(args, "check_artifacts", False))
        )
        result["path"] = str(post_plan_path(root))
        result["delivery"] = delivery_status(root, plan)
        if args.post_plan_action == "show":
            result["post_plan"] = plan
        emit(result)
        return 0 if result["ok"] else 2
    except PostPlanError as exc:
        raise FilmError(str(exc)) from exc


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
    proc = subprocess.run(
        [sys.executable, str(launcher), *argv],
        timeout=120,
        check=False,
    )
    return proc.returncode


def cmd_manifest(args: argparse.Namespace) -> int:
    """Preflight or explicitly migrate a manifest before production use."""
    from manifest_truth import migrate_manifest, preflight_manifest

    root = Path(args.root).expanduser().resolve()
    manifest = load_manifest(root)
    if args.manifest_action == "preflight":
        report = preflight_manifest(root, manifest)
        emit(report)
        return 0 if report["ok"] else 2
    report = migrate_manifest(root, write=bool(args.write))
    emit(report)
    return 0 if report["ok"] else 2


def cmd_truth(args: argparse.Namespace) -> int:
    """Audit production authority records without modifying the film root."""
    from production_truth import audit_production_truth

    report = audit_production_truth(Path(args.root))
    emit(report)
    return 0 if report["ok"] else 2


def cmd_closeout(args: argparse.Namespace) -> int:
    """Wave A1: heat → review gate → post-audit → optional export next_cmd."""
    from closeout import closeout_run, closeout_status

    root = Path(args.root).expanduser().resolve()
    action = str(getattr(args, "closeout_action", "run") or "run")
    if action == "status":
        report = closeout_status(root)
        emit(report)
        return 0 if report.get("ok") else 2
    report = closeout_run(
        root,
        execute=not bool(getattr(args, "status_only", False)),
        export=bool(getattr(args, "export", False)),
        export_name=getattr(args, "name", None),
    )
    emit(report)
    # 0 = delivery_ready or stopped only at optional export; 2 = hard stop mid ladder
    if report.get("delivery_ready") or report.get("ok"):
        return 0
    if report.get("stopped_at") == "export_desktop":
        return 0
    return 2


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
        raise FilmError(
            "Desktop export requires completed technical QA and explicit full-film final review"
        )
    # Wave 6: re-check adult-max heat before shipping desktop (no silent cool export)
    try:
        from production_gates import ProductionGateError, assert_heat_allows_final

        assert_heat_allows_final(root, write_receipt=False)
    except ProductionGateError as exc:
        raise FilmError(str(exc)) from exc
    post_receipt = read_json(root / "receipts" / "post-audit.json") or {}
    from post_audit import audit_freshness

    freshness = audit_freshness(root, post_receipt)
    if not post_receipt:
        raise FilmError(
            "Desktop export requires a current post-audit receipt; run aifilm post-audit --root first"
        )
    if freshness.get("stale"):
        raise FilmError(
            "Desktop export requires a fresh post-audit; evidence changed: "
            + ", ".join(freshness.get("mismatches") or [])
        )
    if not post_receipt.get("delivery_ready"):
        raise FilmError("Desktop export blocked by post-audit hard failures")
    dirs = film_dirs(root)
    try:
        reject_symlinks(dest, field="Desktop export destination")
        for key in ("out", "audio", "keyframes", "clips", "canonical"):
            reject_symlinks(dirs[key], field=f"film {key} export source")
        for meta in EXPORT_METADATA_FILES:
            if (root / meta).is_symlink():
                raise SecurityPolicyError(
                    f"Invalid export source: symbolic links are not allowed: {root / meta}"
                )
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc
    for sub in ("成片", "关键帧", "镜头片段", "定妆与场景", "简报", "项目状态"):
        try:
            safe_workspace_directory(dest, sub, field=f"Desktop {sub} directory").mkdir(
                parents=True, exist_ok=True
            )
        except SecurityPolicyError as exc:
            raise FilmError(str(exc)) from exc

    out_dir = dirs["out"]
    from delivery_artifact import DeliveryArtifactError, export_final_artifacts

    try:
        export_final_artifacts(root, manifest, dest / "成片")
    except DeliveryArtifactError as exc:
        raise FilmError(f"Desktop export final artifact is invalid: {exc}") from exc
    for side in ("final.srt", "final-delivery.json", "production-report.html"):
        src = out_dir / side
        if src.is_file():
            shutil.copy2(src, dest / "成片" / side)
    production_receipt = root / "receipts" / "production-report.json"
    if production_receipt.is_file():
        shutil.copy2(production_receipt, dest / "项目状态" / production_receipt.name)
    # clean stale intermediate copies from previous exports
    for stale in (dest / "成片").glob("*.mp4"):
        if stale.name not in ("film_final.mp4", "film_silent.mp4") and (
            "pre_" in stale.name or stale.name.endswith("_dual.mp4") or "里番" in stale.name
        ):
            with contextlib.suppress(OSError):
                stale.unlink()
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
    delivery_manifest = {
        "kind": "desktop-delivery-manifest",
        "created_at": utc_now(),
        "source_root": str(root),
        "files": {},
    }
    readback_path = dest / "成片" / "delivery-readback.json"
    readback = _util_read_json(readback_path)
    if not isinstance(readback, dict) or readback.get("ok") is not True:
        raise FilmError("Desktop export requires successful hash and decode read-back")
    delivery_manifest["readback"] = readback
    for exported in sorted((dest / "成片").iterdir()):
        if exported.is_file():
            delivery_manifest["files"][f"成片/{exported.name}"] = {
                "sha256": sha256(exported),
                "size": exported.stat().st_size,
            }
    delivery_manifest_path = dest / "项目状态" / "delivery-manifest.json"
    write_json(delivery_manifest_path, delivery_manifest)

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
    outputs = manifest.setdefault("outputs", {})
    outputs["desktop_dir"] = str(dest)
    outputs["desktop_delivery"] = {
        "directory": str(dest),
        "path": str(delivery_manifest_path),
        "sha256": sha256(delivery_manifest_path),
        "readback_path": str(readback_path),
        "readback_sha256": sha256(readback_path),
        "final_output_sha256": str(final.get("sha256") or ""),
    }
    recompute_gates(root, manifest)
    save_manifest(root, manifest)
    emit(
        {
            "ok": True,
            "desktop_dir": str(dest),
            "main_film_dir": str(dest / "成片"),
            "readback": readback,
        }
    )
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
    from cli_motion import MotionRouteError, env_plate

    try:
        rep = env_plate(args)
    except MotionRouteError as exc:
        raise FilmError(str(exc)) from exc
    emit(rep)
    return 0 if rep.get("ok") else 1


def cmd_motion_plan(args: argparse.Namespace) -> int:
    """Compile a panel-animation shot into a deterministic motion plan."""
    from cli_motion import MotionRouteError, motion_plan

    try:
        rep = motion_plan(args)
    except MotionRouteError as exc:
        raise FilmError(str(exc)) from exc
    emit(rep)
    return 0


def cmd_i2v_motion_gate(args: argparse.Namespace) -> int:
    """High-motion audit + final gate from mean rows (meat≥20 normal≥18)."""
    import json as _json

    from cli_motion import i2v_motion_gate_from_rows

    rows_path = getattr(args, "rows", None) or getattr(args, "from_json", None)
    if not rows_path:
        raise FilmError("i2v-motion-gate requires --rows JSON (list of {id,heat_phase,mean})")
    path = Path(rows_path).expanduser().resolve()
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, _json.JSONDecodeError) as exc:
        raise FilmError(f"cannot read --rows: {exc}") from exc
    if isinstance(data, dict) and isinstance(data.get("shots"), list):
        shots = data["shots"]
    elif isinstance(data, list):
        shots = data
    else:
        raise FilmError("--rows must be a JSON list or {shots:[...]}")
    root = getattr(args, "root", None)
    rep = i2v_motion_gate_from_rows(
        shots,
        root=root,
        write_receipts=bool(getattr(args, "write", False)),
        raw_complete=not bool(getattr(args, "raw_incomplete", False)),
        kb_fallback=bool(getattr(args, "kb_fallback", False)),
        style_ok=not bool(getattr(args, "style_fail", False)),
    )
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
    usage_root = getattr(args, "root", None)
    shot_id = str(getattr(args, "shot_id", "") or "")
    job_id = str(getattr(args, "job_id", "") or "")
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
                    usage_root=usage_root,
                    shot_id=shot_id,
                    job_id=job_id,
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
                    usage_root=usage_root,
                    shot_id=shot_id,
                    job_id=job_id,
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
                        usage_root=usage_root,
                        shot_id=shot_id,
                        job_id=job_id,
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
                        usage_root=usage_root,
                        shot_id=shot_id,
                        job_id=job_id,
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
                        usage_root=usage_root,
                        generation_id=getattr(args, "generation_id", None),
                    )
                )
            else:
                emit(
                    video_status(
                        str(rid),
                        usage_root=usage_root,
                        generation_id=getattr(args, "generation_id", None),
                    )
                )
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
                    usage_root=usage_root,
                    shot_id=shot_id,
                    job_id=job_id,
                )
            )
            return 0
        if action == "voices":
            emit(tts_list_voices())
            return 0
    except GrokOAuthError as exc:
        raise FilmError(str(exc)) from exc
    raise FilmError(f"unknown grok-oauth action {action!r}")


def cmd_generation_usage(args: argparse.Namespace) -> int:
    from generation_usage import (
        GenerationUsageError,
        format_usage_table,
        manual_record,
        scan_usage,
        usage_list,
        usage_status,
    )

    action = str(getattr(args, "usage_action", "") or "status")
    try:
        if action == "status":
            report = usage_status(Path(args.root))
        elif action == "list":
            report = usage_list(Path(args.root), operation=getattr(args, "operation", None))
            if getattr(args, "output_format", "json") == "table":
                print(format_usage_table(report))
                return 0 if report.get("ok") else 2
        elif action == "summary":
            report = scan_usage(Path(args.scan_root))
        elif action == "record":
            report = {
                "ok": True,
                "kind": "generation-usage-record",
                "record": manual_record(
                    Path(args.root),
                    operation=args.operation,
                    provider=args.provider,
                    model=args.model,
                    status=args.status,
                    measurement=args.measurement,
                    provider_request_id=args.provider_request_id,
                    output=Path(args.output) if args.output else None,
                    idempotency_key=args.idempotency_key,
                    shot_id=args.shot_id,
                    job_id=args.job_id,
                    input_tokens=args.input_tokens,
                    output_tokens=args.output_tokens,
                    total_tokens=args.total_tokens,
                    cost_in_usd_ticks=args.cost_in_usd_ticks,
                ),
            }
        else:
            raise FilmError(f"unknown usage action {action!r}")
    except GenerationUsageError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0 if report.get("ok") else 2


def _run_optimization_cli(args: argparse.Namespace, action: str) -> int:
    from cli_optimization import OptimizationCliError, dashboard, experiment, gold, metrics, program

    runners = {
        "metrics": metrics,
        "experiment": experiment,
        "gold": gold,
        "dashboard": dashboard,
        "optimization-program": program,
    }
    try:
        report, code = runners[action](args)
    except OptimizationCliError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return code


def cmd_metrics(args: argparse.Namespace) -> int:
    return _run_optimization_cli(args, "metrics")


def cmd_experiment(args: argparse.Namespace) -> int:
    return _run_optimization_cli(args, "experiment")


def cmd_gold(args: argparse.Namespace) -> int:
    return _run_optimization_cli(args, "gold")


def cmd_dashboard(args: argparse.Namespace) -> int:
    return _run_optimization_cli(args, "dashboard")


def cmd_optimization_program(args: argparse.Namespace) -> int:
    return _run_optimization_cli(args, "optimization-program")


def _run_quality_reporting_cli(args: argparse.Namespace, command: str) -> int:
    from cli_quality_reporting import QualityReportingCliError, production_report, quality_ledger

    runners = {"quality-ledger": quality_ledger, "production-report": production_report}
    try:
        report = runners[command](args)
    except QualityReportingCliError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0


def cmd_quality_ledger(args: argparse.Namespace) -> int:
    return _run_quality_reporting_cli(args, "quality-ledger")


def cmd_production_report(args: argparse.Namespace) -> int:
    return _run_quality_reporting_cli(args, "production-report")


def cmd_external_review(args: argparse.Namespace) -> int:
    from external_review import ExternalReviewError, capability_probe, create_report

    try:
        if args.external_review_action == "probe":
            report = capability_probe()
        else:
            report = create_report(
                args.root,
                video=args.video,
                subtitles=args.subtitles,
                director_contract=args.director_contract,
                sanitized_frame_index=args.sanitized_frame_index,
                sanitized=bool(args.sanitized),
                purpose=args.purpose,
            )
    except ExternalReviewError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0


def cmd_vibevoice_asr(args: argparse.Namespace) -> int:
    from config_loader import get_config
    from vibevoice_asr_review import VibeVoiceASRError, capability_probe, create_report

    get_config()
    try:
        if args.vibevoice_asr_action == "probe":
            report = capability_probe()
        else:
            report = create_report(args.root, audio=args.audio, subtitles=args.subtitles)
    except VibeVoiceASRError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0


def cmd_speech_preview(args: argparse.Namespace) -> int:
    """Operate the private, candidate-only Speech-to-Speech preview sidecar."""
    from speech_preview import SpeechPreviewError, export_candidate, probe, record_session, start

    try:
        if args.speech_preview_action == "probe":
            report = probe()
        elif args.speech_preview_action == "start":
            report = start(confirm=bool(args.confirm))
        elif args.speech_preview_action == "session":
            report = record_session(args.root, audio=args.audio, session_json=args.session_json)
        else:
            report = export_candidate(args.root, session_receipt=args.session_receipt)
    except SpeechPreviewError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0 if report.get("ok", True) else 2


def _cmd_graph_legacy(args: argparse.Namespace) -> int:
    """Vertical Drama Graph: legacy derive/import + canonical project/validate/status."""
    root = Path(args.root).expanduser().resolve()
    if str(getattr(args, "graph_action", "") or "") in {"validate", "status"}:
        from cli_graph import status as status_graph_cli
        from cli_graph import validate as validate_graph_cli

        runner = validate_graph_cli if args.graph_action == "validate" else status_graph_cli
        report, code = runner(args, root)
        emit(report)
        return code
    from drama_graph import derive_graph, graph_path, validate_graph
    from narrative_control import (
        GRAPH_SCHEMA_VERSION,
        draft_director_board,
        graph_content_sha256,
        graph_locked_for_projection,
    )

    action = str(getattr(args, "graph_action", "") or "")
    if action == "derive":
        existing = (
            json.loads(graph_path(root).read_text(encoding="utf-8"))
            if graph_path(root).is_file()
            else {}
        )
        if int(existing.get("schema_version") or 0) >= GRAPH_SCHEMA_VERSION:
            raise FilmError(
                "canonical drama-graph exists; use aifilm graph project or plan edit, not graph derive"
            )
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
            raise FilmError(
                "canonical drama-graph already exists; refusing legacy import overwrite"
            )
        graph = derive_graph(root, write=False)
        spec = (
            json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            if (root / "film-spec.json").is_file()
            else {}
        )
        di = spec.get("director_intent") if isinstance(spec.get("director_intent"), dict) else {}
        graph["schema_version"] = GRAPH_SCHEMA_VERSION
        graph["derived_from"] = {
            **(graph.get("derived_from") or {}),
            "mode": "legacy-import",
            "imported_at": utc_now(),
        }
        graph["story"] = {
            "genre": str(spec.get("genre") or "adult"),
            "premise": str(spec.get("description") or di.get("logline") or ""),
            "logline": str(di.get("logline") or spec.get("description") or ""),
            "theme": str(di.get("theme") or ""),
            "protagonist_ids": list(di.get("cast") or spec.get("cast_ids") or []),
            "protagonist_goal": str(di.get("protagonist_goal") or ""),
            "protagonist_want": str(di.get("protagonist_want") or ""),
            "protagonist_need": str(di.get("protagonist_need") or ""),
            "protagonist_arc": str(di.get("protagonist_arc") or ""),
            "opposition": str(di.get("opposition") or ""),
            "stakes": str(di.get("stakes") or ""),
            "climax_choice": str(di.get("climax_choice") or ""),
            "ending_hook": str(di.get("ending_hook") or ""),
            "emotional_arc": list(di.get("emotional_arc") or []),
            "act_structure": di.get("act_structure")
            if isinstance(di.get("act_structure"), dict)
            else {},
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
        emit(
            {
                "ok": True,
                "action": "import",
                "path": str(graph_path(root)),
                "receipt": str(root / "receipts" / "graph-migration.json"),
                "state": graph.get("state"),
                "content_sha256": graph_content_sha256(graph),
            }
        )
        return 0
    if action == "project":
        graph = (
            json.loads(graph_path(root).read_text(encoding="utf-8"))
            if graph_path(root).is_file()
            else {}
        )
        if int(graph.get("schema_version") or 0) < GRAPH_SCHEMA_VERSION:
            raise FilmError(
                "graph project requires canonical graph v2; run aifilm graph import first"
            )
        ready = graph_locked_for_projection(graph)
        if not ready.get("ok"):
            raise FilmError(
                "graph is not ready for projection: "
                + ", ".join(
                    ready.get("missing_scopes")
                    or [
                        i.get("code", "NARRATIVE")
                        for i in (ready.get("semantic") or {}).get("errors", [])
                    ]
                )
            )
        from story_plan import project_graph_to_film_spec

        existing = (
            json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            if (root / "film-spec.json").is_file()
            else {}
        )
        has_shots = any(
            isinstance(sc, dict) and sc.get("shots") for sc in (existing.get("scenes") or [])
        )
        if has_shots and not bool(getattr(args, "force", False)):
            raise FilmError("film-spec already has shots; pass --force to overwrite projection")
        norm_path = root / "receipts" / "story-normalize.json"
        norm = json.loads(norm_path.read_text(encoding="utf-8")) if norm_path.is_file() else None
        spec = project_graph_to_film_spec(graph, base_spec=existing, normalized=norm)
        write_json(root / "film-spec.json", spec)
        emit(
            {
                "ok": True,
                "action": "project",
                "path": str(root / "film-spec.json"),
                "source_revision": graph.get("revision"),
                "source_sha256": graph_content_sha256(graph),
            }
        )
        return 0
    raise FilmError(f"unknown graph action {action!r}")


def cmd_graph(args: argparse.Namespace) -> int:
    """Graph command adapter split between read-only and mutation domains."""
    root = Path(args.root).expanduser().resolve()
    action = str(getattr(args, "graph_action", "") or "")
    if action in {"validate", "status"}:
        from cli_graph import status as status_graph_cli
        from cli_graph import validate as validate_graph_cli

        runner = validate_graph_cli if action == "validate" else status_graph_cli
        report, code = runner(args, root)
        emit(report)
        return code

    from cli_graph_mutation import GraphMutationError, run

    try:
        report, code = run(args, root)
    except GraphMutationError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return code


def cmd_skill(args: argparse.Namespace) -> int:
    """Skill Registry route delegated to the registry CLI module."""
    from cli_skill import run

    report, code = run(args)
    emit(report)
    return code


def cmd_director(args: argparse.Namespace) -> int:
    from director_cli import (
        check,
        director_init,
        impact,
        lock_native_stage,
        migrate,
        migrate_audit,
        rebuild,
        status,
        verify,
    )

    root = Path(args.root).expanduser().resolve()
    action = args.director_action
    try:
        if action == "init":
            report = director_init(
                root,
                title=args.title,
                rigor=args.rigor,
                format_pack=args.format_pack,
                genre_pack=args.genre_pack,
                quality_target=args.quality_target,
            )
        elif action == "migrate-audit":
            report = migrate_audit(root)
        elif action == "migrate":
            report = migrate(root, title=args.title)
        elif action == "status":
            report = status(root)
        elif action == "check":
            report = check(root)
        elif action == "lock-stage":
            input_refs: dict[str, str] | None = None
            if args.input_ref:
                input_refs = {}
                for item in args.input_ref:
                    name, separator, relative = str(item).partition("=")
                    if not separator or not name.strip() or not relative.strip():
                        raise FilmError("--input-ref must use NAME=RELATIVE_PATH")
                    input_refs[name.strip()] = relative.strip()
            report = lock_native_stage(
                root,
                stage=args.stage,
                approver=args.approver,
                user_phrase=args.user_phrase,
                authorization_event=args.authorization_event,
                input_refs=input_refs,
                transaction_id=args.transaction_id,
            )
        elif action == "impact":
            report = impact(root, changed_refs=args.changed_ref, reason=args.reason)
        elif action == "rebuild":
            report = rebuild(
                root,
                changed_refs=args.changed_ref,
                reason=args.reason,
                expected_revision=args.expected_revision,
                transaction_id=args.transaction_id,
            )
        elif action == "verify":
            report = verify(root)
        else:
            raise FilmError(f"unknown director action {action!r}")
    except (OSError, ValueError) as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0 if report.get("ok") else 1


def cmd_serial(args: argparse.Namespace) -> int:
    """Run the optional serial-production contract validator."""
    from serial_quality import validate_serial

    if args.serial_action != "validate":
        raise FilmError(f"unknown serial action {args.serial_action!r}")
    report = validate_serial(Path(args.root).expanduser().resolve(), write_receipt=True)
    emit(report)
    return 0 if report.get("ok") else 1


def cmd_department(args: argparse.Namespace) -> int:
    from department_cli import (
        diff_department,
        edit_department,
        handoff_department,
        list_departments,
        lock_department,
        show_department,
        unlock_department,
        validate_department,
    )

    root = Path(args.root).expanduser().resolve()
    action = args.department_action
    try:
        if action == "list":
            report = list_departments(root)
        elif action in {"show", "status"}:
            report = show_department(root, args.department_id)
        elif action == "edit":
            report = edit_department(
                root,
                args.department_id,
                payload_file=args.payload_file,
                expected_revision=args.expected_revision,
                dry_run=args.dry_run,
            )
        elif action == "diff":
            report = diff_department(root, args.department_id, payload_file=args.payload_file)
        elif action == "handoff":
            report = handoff_department(root, args.department_id)
        elif action == "validate":
            report = validate_department(root, args.department_id)
        elif action == "lock":
            report = lock_department(
                root,
                args.department_id,
                approval_ref=args.approval_ref,
                expected_revision=args.expected_revision,
            )
        elif action == "unlock":
            report = unlock_department(
                root,
                args.department_id,
                reason=args.reason,
                expected_revision=args.expected_revision,
            )
        else:
            raise FilmError(f"unknown department action {action!r}")
    except (OSError, ValueError) as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0 if report.get("ok") else 1


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
    action = str(getattr(args, "plan_action", "") or "")
    if action == "receive":
        from narrative_control import control_status
        from story_reception import ReceptionError, load_story_reception
        from util import write_json

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan receive requires --root")
        root = Path(root_s).expanduser().resolve()
        status = control_status(root)
        if "story" in set(status.get("locked_scopes") or []):
            raise FilmError("story is locked; unlock story before receiving a revised treatment")
        try:
            reception_path = Path(str(getattr(args, "file", ""))).expanduser().resolve()
            reception = load_story_reception(reception_path)
        except ReceptionError as exc:
            raise FilmError(str(exc)) from exc
        output = root / "receipts" / "story-reception.json"
        if output.exists() and not bool(getattr(args, "force", False)):
            raise FilmError(
                "story reception already exists; pass --force before story lock to replace it"
            )
        write_json(output, reception)
        emit(
            {
                "ok": True,
                "action": "receive",
                "path": str(output),
                "source_sha256": reception["source"]["sha256"],
                "summary": {
                    "title": reception["treatment"].get("title"),
                    "logline": reception["treatment"].get("logline"),
                    "unknowns": reception["fidelity"].get("unknowns") or [],
                    "mature_intimacy": reception["treatment"].get("mature_intimacy") or {},
                },
            }
        )
        return 0
    if action in {"edit", "lock", "unlock", "replan"}:
        from cli_plan_mutation import PlanMutationError, run

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError(f"plan {action} requires --root")
        try:
            report, code = run(args, Path(root_s).expanduser().resolve())
        except PlanMutationError as exc:
            raise FilmError(f"{exc.code}: {exc}") from exc
        emit(report)
        return code
    if action == "run":
        from cli_plan_run import PlanRunError, run

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan run requires --root")
        try:
            report, code = run(args, Path(root_s).expanduser().resolve())
        except PlanRunError as exc:
            raise FilmError(str(exc)) from exc
        emit(report)
        return code
    if action == "project":
        from cli_plan_project import run

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError("plan project requires --root")
        report, code = run(args, Path(root_s).expanduser().resolve())
        emit(report)
        return code
    if action in {"validate", "status"}:
        from cli_plan import status as status_plan_cli
        from cli_plan import validate as validate_plan_cli

        root_s = getattr(args, "root", None)
        if not root_s:
            raise FilmError(f"plan {action} requires --root")
        runner = validate_plan_cli if action == "validate" else status_plan_cli
        report, code = (
            runner(args, Path(root_s).expanduser().resolve())
            if action == "validate"
            else runner(Path(root_s).expanduser().resolve())
        )
        emit(report)
        return code
    if action == "normalize":
        from cli_plan_normalize import PlanNormalizeError, run

        root_s = getattr(args, "root", None)
        try:
            report, code = run(
                args,
                Path(root_s).expanduser().resolve() if root_s else None,
            )
        except PlanNormalizeError as exc:
            raise FilmError(str(exc)) from exc
        emit(report)
        return code

    raise FilmError(f"unknown plan action {action!r}")


def cmd_workshop(args: argparse.Namespace) -> int:
    """Creative workshop contracts stay local and never invoke a provider."""
    from cli_workshop import WorkshopError, run_workshop

    try:
        report, code = run_workshop(args)
    except WorkshopError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return code


def cmd_review_ui(args: argparse.Namespace) -> int:
    """Run the loopback-only review console without duplicating approval state."""
    from review_ui import ReviewUIError, run_review_ui

    try:
        report, code = run_review_ui(args)
    except (OSError, ValueError, ReviewUIError) as exc:
        raise FilmError(str(exc)) from exc
    if args.review_ui_action != "serve":
        emit(report)
    return code


def cmd_interactive(args: argparse.Namespace) -> int:
    from cli_interactive import run_interactive

    report, code = run_interactive(args)
    emit(report)
    return code


def cmd_dispatch(args: argparse.Namespace) -> int:
    """Auto-orchestrate: craft + capability + next → single agent packet."""
    root = Path(args.root).expanduser().resolve()
    from dispatch import build_dispatch
    from dispatch_compact import compact_dispatch, record_orchestration_metrics

    gates: dict[str, Any] = {}
    open_n = 0
    if (root / MANIFEST_NAME).is_file():
        man = load_manifest(root)
        summary = recompute_gates(root, man)
        gates = summary.get("gates") or {}
        open_n = int(summary.get("open_reshoot_count") or 0)

    packet = build_dispatch(
        root,
        gates=gates,
        open_reshoot_count=open_n,
        include_capability=not bool(getattr(args, "no_capability", False)),
        write_receipt=not bool(getattr(args, "no_write", False)),
        refresh_capability=bool(getattr(args, "refresh_capability", False)),
    )
    from project_state import build_project_state, persist_project_state

    project_state = build_project_state(
        root,
        gates=gates,
        open_reshoot_count=open_n,
        next_actions=list(packet.get("next_actions") or []),
        next_cmd=packet.get("next_cmd"),
        next_id=packet.get("next_id"),
    )
    packet["project_state"] = project_state
    if not bool(getattr(args, "no_write", False)):
        packet["project_state_receipt"] = str(persist_project_state(root, project_state))

    # A no-write dispatch is a pure projection; regular dispatch updates the
    # film receipt and HUD from the same canonical snapshot.
    if not bool(getattr(args, "no_write", False)):
        try:
            from next_actions import detect_pipeline_stage, persist_pipeline_stage

            pipeline = detect_pipeline_stage(root, gates=gates, open_reshoot_count=open_n)
            persisted = persist_pipeline_stage(
                root,
                pipeline,
                next_cmd=packet.get("next_cmd"),
                next_id=packet.get("next_id"),
            )
            if persisted.get("errors"):
                packet["hud_sync_error"] = persisted["errors"]
        except Exception as exc:
            packet["hud_sync_error"] = [str(exc)[:300]]

    if bool(getattr(args, "print_cmd_only", False)):
        print(packet.get("next_cmd") or "")
        return 0 if packet.get("next_cmd") else 1
    if bool(getattr(args, "print_instruction", False)):
        print(packet.get("agent_instruction") or "")
        return 0

    configured_format = (
        str(
            getattr(args, "dispatch_format", None)
            or os.environ.get("AIFILM_DISPATCH_FORMAT")
            or "compact"
        )
        .strip()
        .lower()
    )
    if bool(getattr(args, "full", False)):
        configured_format = "full"
    if configured_format not in {"compact", "full"}:
        raise FilmError("dispatch format must be compact or full")
    output = packet if configured_format == "full" else compact_dispatch(packet)
    if configured_format == "compact" and not bool(getattr(args, "no_write", False)):
        record_orchestration_metrics(root, output)
    emit(output)
    return 0 if packet.get("ok") else 1


def cmd_advance(args: argparse.Namespace) -> int:
    """Execute a bounded sequence of allowlisted local dispatch actions."""
    root = Path(args.root).expanduser().resolve()
    from advance import AdvanceError, advance_local

    gates: dict[str, Any] = {}
    open_n = 0
    if (root / MANIFEST_NAME).is_file():
        man = load_manifest(root)
        summary = recompute_gates(root, man)
        gates = summary.get("gates") or {}
        open_n = int(summary.get("open_reshoot_count") or 0)
        save_manifest(root, man)
    try:
        report = advance_local(
            root,
            gates=gates,
            open_reshoot_count=open_n,
            max_local=int(args.max_local),
        )
    except AdvanceError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0 if report.get("ok") else 2


def cmd_autopilot(args: argparse.Namespace) -> int:
    """Run one bounded, budget-authorized automation pass for a film."""
    from autopilot import AutopilotError, autopilot_once

    try:
        report = autopilot_once(
            Path(args.root), max_actions=int(args.max_actions), dry_run=bool(args.dry_run)
        )
    except AutopilotError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0 if report.get("ok") else 2


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
    report = build_audio_plan(
        root,
        compile_timeline=bool(getattr(args, "compile", False) or getattr(args, "validate", False)),
        write_timeline=bool(getattr(args, "write_timeline", False)),
        write_voice_cast=bool(getattr(args, "write_voice_cast", False)),
        write_tts_manifest=bool(getattr(args, "write_tts_manifest", False)),
    )
    emit(report)
    return (
        1 if bool(getattr(args, "validate", False)) and report["audio_timeline"].get("error") else 0
    )


def cmd_audio_verify(args: argparse.Namespace) -> int:
    """Run the fail-closed audio delivery evidence gate for one film root."""
    from audio_delivery_gate import build_delivery_report
    from util import read_json, write_json

    root = Path(args.root).expanduser().resolve()
    audio_dir = root / "audio"
    timeline = read_json(audio_dir / "audio-timeline.json")
    manifest = read_json(audio_dir / "tts-manifest.json")
    bindings = read_json(audio_dir / "caption-bindings.json")
    production = read_json(audio_dir / "production-plan.json")
    scene_sound = read_json(root / "receipts" / "scene-sound-status.json")
    if (
        not isinstance(timeline, dict)
        or not isinstance(manifest, dict)
        or not isinstance(bindings, list)
        or not isinstance(production, dict)
        or not isinstance(scene_sound, dict)
    ):
        raise FilmError(
            "audio-verify requires unified production artifacts; run audio-produce first"
        )
    final_path = Path(args.final).expanduser().resolve() if args.final else None
    out = audio_dir / "audio-delivery-report.json"
    previous_report = read_json(out) if out.is_file() else None
    report = build_delivery_report(
        timeline=timeline,
        tts_manifest=manifest,
        subtitle_bindings=bindings,
        final_mp4=final_path,
        previous_report=previous_report if isinstance(previous_report, dict) else None,
        root=root,
        audio_production=production,
        scene_sound_receipt=scene_sound,
    )
    write_json(out, report)
    emit({**report, "path": str(out)})
    return 0 if report["ok"] else 1


def cmd_verify(args: argparse.Namespace) -> int:
    """Aggregate local automation gates without initiating generation or uploads."""
    from automation_verify import build_verification_report
    from util import write_json

    root = Path(args.root).expanduser().resolve()
    report = build_verification_report(root)
    if not bool(getattr(args, "no_write", False)):
        out = root / "receipts" / "automation-verify.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        write_json(out, report)
        report["path"] = str(out)
    emit(report)
    return 0 if report["ok"] else 1


def cmd_audio_tts_render(args: argparse.Namespace) -> int:
    from audio_tts_render import AudioTTSRenderError, render_tts_events

    try:
        emit(render_tts_events(Path(args.root)))
    except AudioTTSRenderError as exc:
        raise FilmError(str(exc)) from exc
    return 0


def cmd_audio_produce(args: argparse.Namespace) -> int:
    """Prepare the unified production-audio contract for one film."""
    from audio_production import AudioProductionError, prepare_audio_production

    try:
        emit(prepare_audio_production(Path(args.root), render_tts=bool(args.render_tts)))
    except AudioProductionError as exc:
        raise FilmError(str(exc)) from exc
    return 0


def cmd_audio_event(args: argparse.Namespace) -> int:
    from audio_event_editor import AudioEventEditError, edit_event
    from util import read_json, write_json

    root = Path(args.root).expanduser().resolve()
    audio_dir = root / "audio"
    timeline = read_json(audio_dir / "audio-timeline.json")
    if not isinstance(timeline, dict):
        raise FilmError("audio-event requires audio/audio-timeline.json")
    updates = {
        key: value
        for key, value in {
            "gain": args.gain,
            "pan": args.pan,
            "fade_in_sec": args.fade_in,
            "fade_out_sec": args.fade_out,
            "muted": args.muted,
            "locked": args.locked,
            "overlap_policy": args.overlap_policy,
            "text": args.text,
            "caption_text": args.caption_text,
        }.items()
        if value is not None
    }
    if args.performance_json is not None:
        try:
            updates["performance_cue"] = json.loads(args.performance_json)
        except json.JSONDecodeError as exc:
            raise FilmError("--performance-json must be valid JSON") from exc
    if not updates:
        raise FilmError("audio-event needs at least one control update")
    manifest_path = audio_dir / "tts-manifest.json"
    manifest = read_json(manifest_path) if manifest_path.is_file() else None
    try:
        edited, updated_manifest, bindings = edit_event(
            timeline,
            args.event,
            updates,
            force_locked=bool(args.force_locked),
            tts_manifest=manifest,
        )
    except AudioEventEditError as exc:
        raise FilmError(str(exc)) from exc
    write_json(audio_dir / "audio-timeline.json", edited)
    write_json(audio_dir / "caption-bindings.json", bindings)
    if updated_manifest is not None:
        write_json(manifest_path, updated_manifest)
    emit({"ok": True, "audio_event_id": args.event, "updates": updates})
    return 0


def cmd_bgm_candidate(args: argparse.Namespace) -> int:
    """Create/list/approve locally rendered ACE-Step BGM candidates."""
    from bgm_candidates import BGMCandidateError, approve, generate, list_candidates

    root = Path(args.root).expanduser().resolve()
    try:
        if args.bgm_candidate_action == "list":
            emit({"candidates": list_candidates(root)})
            return 0
        if args.bgm_candidate_action == "approve":
            if str(getattr(args, "target", "film") or "film") == "shared":
                from bgm_library import approve_candidate as approve_shared
                from bgm_library import default_library_root, stage_candidate

                candidates = {
                    str(item.get("asset_id") or ""): item for item in list_candidates(root)
                }
                source_record = candidates.get(str(args.asset_id))
                if not isinstance(source_record, dict):
                    raise BGMCandidateError("BGM candidate receipt not found")
                source = root / str(source_record.get("path") or "")
                staged = stage_candidate(
                    default_library_root(),
                    source,
                    {
                        "mood": source_record.get("mood") or "rnb",
                        "seed": source_record.get("seed") or 0,
                        "model": source_record.get("model") or "ACE-Step-1.5",
                        "checkpoint_fingerprint": source_record.get("checkpoint_fingerprint")
                        or "unknown",
                        "node_job_id": source_record.get("node_job_id") or "",
                        "prompt_sha256": source_record.get("prompt_sha256") or "",
                        "dramatic_tags": [],
                        "energy": 0.5,
                        "stem_profile": "pad",
                        "recipe": {
                            "mood": source_record.get("mood") or "rnb",
                            "energy": 0.5,
                            "stem_profile": "pad",
                        },
                    },
                )
                emit(
                    approve_shared(
                        default_library_root(),
                        str(staged["asset_id"]),
                        reviewer=str(getattr(args, "reviewer", "") or ""),
                        license_note=str(getattr(args, "license_note", "") or ""),
                        instrumental_confirmed=bool(getattr(args, "instrumental_confirmed", False)),
                    )
                )
                return 0
            emit(approve(root, args.asset_id))
            return 0
        base = os.environ.get("AIFILM_AUDIO_NODE_URL", "").strip()
        token = os.environ.get("AIFILM_AUDIO_NODE_TOKEN", "").strip()
        if not base or not token:
            raise BGMCandidateError("AIFILM_AUDIO_NODE_URL/TOKEN are required for ACE-Step BGM")
        prompt = (args.prompt or "").strip() or (
            f"instrumental {args.mood} background music, cinematic underscore, no vocals"
        )
        emit(
            generate(
                root,
                base_url=base,
                token=token,
                prompt=prompt,
                mood=args.mood,
                duration=args.duration,
                seed=args.seed,
            )
        )
        return 0
    except BGMCandidateError as exc:
        raise FilmError(str(exc)) from exc


def cmd_bgm_library(args: argparse.Namespace) -> int:
    from bgm_library import BGMLibraryError
    from cli_bgm_library import cmd_bgm_library as run_bgm_library

    try:
        return run_bgm_library(args, emit=emit)
    except BGMLibraryError as exc:
        raise FilmError(str(exc)) from exc


def cmd_performance_candidate(args: argparse.Namespace) -> int:
    """Create, reject, or approve private non-verbal performance candidates."""
    from config_loader import get_config
    from performance_candidates import PerformanceCandidateError, approve, generate, reject

    get_config()
    root = Path(args.root).expanduser().resolve()
    try:
        if args.performance_candidate_action == "approve":
            emit(approve(root, args.asset_id))
            return 0
        if args.performance_candidate_action == "reject":
            emit(reject(root, args.asset_id, reviewer=args.reviewer, reason=args.reason))
            return 0
        base = os.environ.get("AIFILM_AUDIO_NODE_URL", "").strip()
        token = os.environ.get("AIFILM_AUDIO_NODE_TOKEN", "").strip()
        if not base or not token:
            raise PerformanceCandidateError(
                "AIFILM_AUDIO_NODE_URL/TOKEN are required for performance generation"
            )
        emit(
            generate(
                root,
                base_url=base,
                token=token,
                cue=args.cue,
                duration=args.duration,
                seed=args.seed,
                character_id=args.character_id,
                source_authorization=args.source_authorization,
                adult_confirmed=bool(args.adult_confirmed),
                model_version=args.model_version,
            )
        )
        return 0
    except PerformanceCandidateError as exc:
        raise FilmError(str(exc)) from exc


def cmd_adult_female_voice_pack(args: argparse.Namespace) -> int:
    """Manage fixed-profile, human-reviewed adult female dialogue and breath candidates."""
    from adult_female_voice_pack import (
        AdultFemaleVoicePackError,
        approve,
        initialize,
        list_candidates,
        render_pending,
    )
    from config_loader import get_config

    get_config()
    root = Path(args.root).expanduser().resolve()
    try:
        if args.adult_female_voice_pack_action == "init":
            emit(initialize(root))
            return 0
        if args.adult_female_voice_pack_action == "list":
            emit({"candidates": list_candidates(root)})
            return 0
        if args.adult_female_voice_pack_action == "approve":
            emit(
                approve(
                    root,
                    args.asset_id,
                    reviewer=args.reviewer,
                    female_voice_confirmed=bool(args.female_voice_confirmed),
                    breath_confirmed=bool(args.breath_confirmed),
                    artifact_free_confirmed=bool(args.artifact_free_confirmed),
                )
            )
            return 0
        base = str(
            getattr(args, "node_url", "") or os.environ.get("AIFILM_AUDIO_NODE_URL", "")
        ).strip()
        token = os.environ.get("AIFILM_AUDIO_NODE_TOKEN", "").strip()
        if not base or not token:
            raise AdultFemaleVoicePackError("AIFILM_AUDIO_NODE_URL/TOKEN are required")
        emit(render_pending(root, base_url=base, token=token))
        return 0
    except AdultFemaleVoicePackError as exc:
        raise FilmError(str(exc)) from exc


def cmd_ambience_candidate(args: argparse.Namespace) -> int:
    from ambience_candidates import (
        AmbienceCandidateError,
        approve,
        attach_to_shot,
        generate,
        list_candidates,
    )

    root = Path(args.root).expanduser().resolve()
    try:
        if args.ambience_candidate_action == "list":
            emit({"candidates": list_candidates(root)})
        elif args.ambience_candidate_action == "approve":
            emit(
                approve(
                    root,
                    args.asset_id,
                    reviewer=args.reviewer,
                    heard_full=bool(args.heard_full),
                    no_speech_confirmed=bool(args.no_speech_confirmed),
                    no_music_confirmed=bool(args.no_music_confirmed),
                    artifact_free_confirmed=bool(args.artifact_free_confirmed),
                )
            )
        elif args.ambience_candidate_action == "attach":
            emit(
                attach_to_shot(
                    root,
                    args.asset_id,
                    shot_id=args.shot_id,
                    start_offset_sec=args.start_offset_sec,
                    duration_sec=args.duration,
                    acoustic_space=args.acoustic_space,
                    noncommercial_internal_ok=bool(args.noncommercial_internal_ok),
                )
            )
        else:
            base, token = (
                os.environ.get("AIFILM_AUDIO_NODE_URL", ""),
                os.environ.get("AIFILM_AUDIO_NODE_TOKEN", ""),
            )
            if not base or not token:
                raise AmbienceCandidateError("AIFILM_AUDIO_NODE_URL/TOKEN are required")
            emit(
                generate(
                    root,
                    base_url=base,
                    token=token,
                    prompt=args.prompt,
                    duration=args.duration,
                    seed=args.seed,
                )
            )
        return 0
    except AmbienceCandidateError as exc:
        raise FilmError(str(exc)) from exc


def cmd_sfx_canary(args: argparse.Namespace) -> int:
    """Generate one non-commercial, pending MMAudio SFX candidate."""
    from sfx_candidates import SFXCandidateError, generate

    try:
        emit(
            generate(
                Path(args.root),
                prompt=args.prompt,
                duration=args.duration,
                seed=args.seed,
                source_video=Path(args.video).expanduser() if args.video else None,
                noncommercial_research_ok=bool(args.noncommercial_research_ok),
            )
        )
        return 0
    except SFXCandidateError as exc:
        raise FilmError(str(exc)) from exc


def cmd_sfx_candidate(args: argparse.Namespace) -> int:
    """Generate, review, and attach non-commercial MMAudio SFX."""
    # Candidate receipts are HMAC-bound to the local audio-node credential.
    # Generation loads config itself, but the later review subcommands must
    # load the same local-only configuration before verifying that signature.
    from config_loader import get_config
    from sfx_candidates import (
        SFXCandidateError,
        approve,
        attach_to_shot,
        batch_generate_and_screen,
        generate,
        reject,
        screen_speech,
    )

    get_config()
    root = Path(args.root).expanduser().resolve()
    try:
        if args.sfx_candidate_action == "batch":
            payload = read_json(Path(args.manifest))
            candidates = payload.get("candidates") if isinstance(payload, dict) else None
            if not isinstance(candidates, list):
                raise SFXCandidateError("SFX batch manifest requires candidates array")
            emit(
                batch_generate_and_screen(
                    root,
                    candidates,
                    noncommercial_research_ok=bool(args.noncommercial_research_ok),
                )
            )
        elif args.sfx_candidate_action == "approve":
            emit(
                approve(
                    root,
                    args.asset_id,
                    reviewer=args.reviewer,
                    heard_full=bool(args.heard_full),
                    sync_confirmed=bool(args.sync_confirmed),
                    no_speech_confirmed=bool(args.no_speech_confirmed),
                    no_music_confirmed=bool(args.no_music_confirmed),
                    artifact_free_confirmed=bool(args.artifact_free_confirmed),
                    asr_speech_reviewed=bool(args.asr_speech_reviewed),
                )
            )
        elif args.sfx_candidate_action == "screen-speech":
            emit(screen_speech(root, args.asset_id))
        elif args.sfx_candidate_action == "reject":
            emit(
                reject(
                    root,
                    args.asset_id,
                    reviewer=args.reviewer,
                    reason=args.reason,
                )
            )
        elif args.sfx_candidate_action == "attach":
            emit(
                attach_to_shot(
                    root,
                    args.asset_id,
                    shot_id=args.shot_id,
                    kind=args.kind,
                    start_offset_sec=args.start_offset_sec,
                    duration_sec=args.duration,
                    material=args.material,
                    noncommercial_internal_ok=bool(args.noncommercial_internal_ok),
                )
            )
        else:
            emit(
                generate(
                    root,
                    prompt=args.prompt,
                    duration=args.duration,
                    seed=args.seed,
                    source_video=Path(args.video).expanduser() if args.video else None,
                    noncommercial_research_ok=bool(args.noncommercial_research_ok),
                )
            )
        return 0
    except SFXCandidateError as exc:
        raise FilmError(str(exc)) from exc


def cmd_sfx_library(args: argparse.Namespace) -> int:
    """Manage the shared internal non-commercial SFX armory."""
    from config_loader import get_config
    from sfx_library import (
        SFXLibraryError,
        audit,
        import_project_asset,
        write_candidate_review_pack,
    )

    get_config()
    try:
        if args.sfx_library_action == "import-project":
            emit(
                import_project_asset(
                    Path(args.root),
                    args.asset_id,
                    library_root=Path(args.library_root) if args.library_root else None,
                )
            )
        elif args.sfx_library_action == "review-pack":
            emit(
                write_candidate_review_pack(
                    args.name,
                    library_root=Path(args.library_root) if args.library_root else None,
                )
            )
        else:
            emit(audit(library_root=Path(args.library_root) if args.library_root else None))
        return 0
    except SFXLibraryError as exc:
        raise FilmError(str(exc)) from exc


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


def cmd_lipsync_pilot(args: argparse.Namespace) -> int:
    from lipsync_pilot import (
        LipsyncPilotError,
        create_pilot,
        rerun_musetalk,
        review_template,
        run_pilot,
    )

    try:
        action = str(args.lipsync_pilot_action)
        if action == "create":
            report = create_pilot(
                args.root,
                front_video=args.front_video,
                three_quarter_video=args.three_quarter_video,
                moving_video=args.moving_video,
                japanese_audio=args.japanese_audio,
                approval_receipt=args.approval_receipt,
            )
        elif action == "run":
            report = run_pilot(args.root)
        elif action == "rerun-musetalk":
            report = rerun_musetalk(args.root, sample_id=args.sample)
        else:
            report = review_template(args.root)
    except LipsyncPilotError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0 if report.get("ok", True) else 1


def cmd_lipsync_challenge(args: argparse.Namespace) -> int:
    from lipsync_challenge import (
        LipsyncChallengeError,
        build_challenge_report,
        create_blind_package,
        create_challenge,
        record_blind_review,
        register_result,
    )

    try:
        action = str(args.lipsync_challenge_action)
        if action == "create":
            report = create_challenge(
                args.root,
                fixtures={
                    "front_closeup": Path(args.front_closeup),
                    "three_quarter": Path(args.three_quarter),
                    "occlusion_motion": Path(args.occlusion_motion),
                    "anime": Path(args.anime),
                },
                japanese_audio=Path(args.japanese_audio),
                approval_receipt=Path(args.approval_receipt),
            )
        elif action == "register-result":
            report = register_result(
                args.root,
                fixture_id=args.fixture_id,
                backend_id=args.backend_id,
                output=Path(args.output),
                metrics_receipt=Path(args.metrics_receipt),
                runtime_receipt=Path(args.runtime_receipt),
            )
        elif action == "blind-package":
            report = create_blind_package(args.root)
        elif action == "review":
            report = record_blind_review(
                args.root,
                reviewer=args.reviewer,
                review=read_json(Path(args.review_json)),
            )
        else:
            report = build_challenge_report(
                args.root,
                license_receipt=Path(args.license_receipt) if args.license_receipt else None,
            )
    except LipsyncChallengeError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0 if report.get("ok", True) else 1


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

    backends = [
        b.strip() for b in str(getattr(args, "backends", "mimo,edge")).split(",") if b.strip()
    ]
    try:
        man = run_tts_ab(
            Path(args.root).expanduser().resolve(),
            shot_id=str(args.shot_id),
            backends=backends,
            voice=getattr(args, "voice", None),
            text=getattr(args, "text", None),
            spec_path=Path(args.spec).expanduser().resolve()
            if getattr(args, "spec", None)
            else None,
        )
    except TTSAbError as exc:
        raise FilmError(str(exc)) from exc
    emit(man)
    return 0 if man.get("ok") else 1


def cmd_elevenlabs_canary(args: argparse.Namespace) -> int:
    """Run a capped bilingual paid canary, or record its human review."""
    from elevenlabs_canary import ElevenLabsCanaryError, list_voices, review_candidate, run_canary

    try:
        if args.list_voices:
            result = list_voices()
        elif args.review_language or args.decision:
            if not args.review_language or not args.decision:
                raise ElevenLabsCanaryError("review requires --review-language and --decision")
            result = review_candidate(
                Path(args.root), language=args.review_language, decision=args.decision
            )
        else:
            if not args.zh_voice or not args.ja_voice:
                raise ElevenLabsCanaryError("run requires --zh-voice and --ja-voice")
            result = run_canary(
                Path(args.root),
                zh_voice=args.zh_voice,
                ja_voice=args.ja_voice,
                model=args.model,
                confirm_cost=bool(args.confirm_cost),
                max_paid_calls=int(args.max_paid_calls),
            )
    except ElevenLabsCanaryError as exc:
        result = {"ok": False, "status": "blocked", "reason": str(exc)}
    emit(result)
    return 0 if result.get("ok") else 2


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


def cmd_comfy(args: argparse.Namespace) -> int:
    from cli_comfy import run_comfy

    return run_comfy(args)


def cmd_h3(args: argparse.Namespace) -> int:
    """MiniMax H3 local motion lane (plan / run / list)."""
    from cli_h3 import run_h3

    report = run_h3(args)
    emit(report)
    return 0 if report.get("ok") is not False else 1


def cmd_workflow(args: argparse.Namespace) -> int:
    """Wave A–C throughput: closeout / pilot-pack / bulk-preflight / lease / tunnel."""
    from cli_workflow import run_workflow_cmd

    return run_workflow_cmd(args)


def cmd_node(args: argparse.Namespace) -> int:
    from cli_node import run_node

    return run_node(args, emit=emit)


def cmd_visual_text_audit(args: argparse.Namespace) -> int:
    from visual_text_audit import VisualTextAuditError, audit_clip

    try:
        report = audit_clip(
            args.root,
            args.source,
            base_url=args.base_url,
            model=args.model,
            token=os.environ.get("AIFILM_LOCAL_OMNI_TOKEN") or None,
        )
    except VisualTextAuditError as exc:
        raise FilmError(f"VISUAL_TEXT_AUDIT_ERROR: {exc}") from exc
    emit(report)
    return 0 if report["status"] == "clean" else 2


def cmd_visual_text_repair(args: argparse.Namespace) -> int:
    from visual_text_repair import VisualTextRepairError, repair_clip

    try:
        report = repair_clip(
            args.root, args.source, base_url=args.base_url, audit_path=args.audit_receipt
        )
    except VisualTextRepairError as exc:
        raise FilmError(f"VISUAL_TEXT_REPAIR_ERROR: {exc}") from exc
    emit(report)
    return 0


def cmd_weapon(args: argparse.Namespace) -> int:
    from cli_weapon import run_weapon

    return run_weapon(args, emit=emit)


def cmd_route(args: argparse.Namespace) -> int:
    from cli_route import run
    from production_router import RouteExplainError

    try:
        report, code = run(args)
    except RouteExplainError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return code


def cmd_team(args: argparse.Namespace) -> int:
    from cli_team import run
    from production_team import ProductionTeamError

    try:
        report, code = run(args)
    except ProductionTeamError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return code


def cmd_lipsync_node(args: argparse.Namespace) -> int:
    from config_loader import get_config
    from lipsync_node_client import LipsyncNodeError, health

    cfg = get_config()
    if not cfg.lipsync_node_base_url or not cfg.lipsync_node_token:
        raise FilmError(
            "set AIFILM_LIPSYNC_NODE_BASE_URL and AIFILM_LIPSYNC_NODE_TOKEN in config.env"
        )
    try:
        report = health(cfg.lipsync_node_base_url, cfg.lipsync_node_token)
    except LipsyncNodeError as exc:
        raise FilmError(str(exc)) from exc
    emit(report)
    return 0 if report.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aifilm_grok", description="ai-film-grok local control plane")
    sub = p.add_subparsers(dest="cmd", required=True)

    doctor = sub.add_parser(
        "doctor", help="Check tooling, locks, schema, backends, and security posture"
    )
    doctor.add_argument(
        "--strict", action="store_true", help="Also fail on global security warnings"
    )
    doctor.add_argument(
        "--art-check",
        action="store_true",
        help="Also run director methodology verification (pace_chart/act_structure/music_spotting)",
    )
    doctor.add_argument(
        "--art-root",
        default=".",
        help="Film root for --art-check (default: current dir)",
    )
    sub.add_parser(
        "lock-runtime", help="Fingerprint the current verified Python/FFmpeg/script runtime"
    )

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
    envp.add_argument("--prompt", required=False, default=None)
    envp.add_argument(
        "--prompt-file", default=None, help="Read environment prompt from a UTF-8 file"
    )
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

    mp = sub.add_parser(
        "motion-plan",
        help="Compile one panel-animation shot into a deterministic motion plan",
    )
    mp.add_argument("--root", required=True)
    mp.add_argument("--shot-id", required=True)

    img = sub.add_parser(
        "i2v-motion-gate",
        help=(
            "High-motion product gate: meat mean≥20 / normal≥18 → "
            "i2v-high-motion-audit + i2v-final-gate (desktop final only if ok)"
        ),
    )
    img.add_argument(
        "--rows",
        required=True,
        help="JSON list of {id,heat_phase,mean|mean_absdiff[,source]}",
    )
    img.add_argument("--root", default=None, help="Film root when --write")
    img.add_argument(
        "--write",
        action="store_true",
        help="Write receipts/i2v-high-motion-audit.json + i2v-final-gate.json",
    )
    img.add_argument("--raw-incomplete", action="store_true")
    img.add_argument("--kb-fallback", action="store_true")
    img.add_argument("--style-fail", action="store_true")

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
    goauth.add_argument(
        "--root",
        default=None,
        help="Film root; enables exact-first generation usage accounting",
    )
    goauth.add_argument("--shot-id", default="", help="Optional shot id for usage accounting")
    goauth.add_argument("--job-id", default="", help="Optional media queue job id")
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
    goauth.add_argument(
        "--generation-id",
        default=None,
        dest="generation_id",
        help="Tracking id returned by video submit; required to finish async accounting",
    )
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
    disp.add_argument(
        "--refresh-capability",
        action="store_true",
        help="Bypass the ten-minute guidance cache and run a live capability probe",
    )
    disp.add_argument(
        "--format",
        choices=("compact", "full"),
        default=None,
        dest="dispatch_format",
        help="Output compact agent packet (default) or full audit packet",
    )
    disp.add_argument("--full", action="store_true", help="Alias for --format full")
    disp.add_argument("--no-write", action="store_true", help="Do not write receipts/dispatch.json")
    advance_p = sub.add_parser(
        "advance",
        help="Execute only allowlisted local actions; stop at paid, external or human gates",
    )
    advance_p.add_argument("--root", required=True)
    advance_p.add_argument(
        "--max-local",
        type=int,
        default=3,
        help="Maximum local steps, hard-capped at 10",
    )
    autopilot_p = sub.add_parser(
        "autopilot",
        help="Execute bounded local and budget-authorized external steps; stop at every safety gate",
    )
    autopilot_p.add_argument("--root", required=True)
    autopilot_p.add_argument("--max-actions", type=int, default=3)
    autopilot_p.add_argument("--dry-run", action="store_true")

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

    ap = sub.add_parser(
        "audio-plan", help="Dry-run audio plan; optionally compile/validate audio-timeline v1"
    )
    ap.add_argument("--root", required=True)
    ap.add_argument(
        "--compile", action="store_true", help="Include compiled audio-timeline.json data in report"
    )
    ap.add_argument(
        "--validate", action="store_true", help="Fail if the v1 audio timeline is invalid"
    )
    ap.add_argument(
        "--write-timeline",
        action="store_true",
        help="Write audio/audio-timeline.json after successful compile",
    )
    ap.add_argument(
        "--write-voice-cast",
        action="store_true",
        help="Write deterministic audio/voice-cast.json from compiled speakers",
    )
    ap.add_argument(
        "--write-tts-manifest",
        action="store_true",
        help="Write audio/tts-manifest.json with one provenance-bound job per vocal event",
    )

    av = sub.add_parser(
        "audio-verify", help="Fail closed on missing audio, TTS, or subtitle evidence"
    )
    av.add_argument("--root", required=True)
    av.add_argument("--final", default=None, help="Optional final MP4 to inspect with FFprobe")

    verify = sub.add_parser(
        "verify", help="Aggregate runtime, scene-sound, audio-delivery and production gates"
    )
    verify.add_argument("--root", required=True)
    verify.add_argument(
        "--no-write", action="store_true", help="Do not write a verification receipt"
    )

    atr = sub.add_parser(
        "audio-tts-render", help="Render each event TTS asset and write actual durations"
    )
    atr.add_argument("--root", required=True)

    aprod = sub.add_parser(
        "audio-produce",
        help="Compile TTS, BGM, Foley, and ambience into one production-audio receipt",
    )
    aprod.add_argument("--root", required=True)
    aprod.add_argument(
        "--render-tts",
        action="store_true",
        help="Render the already locked TTS jobs; does not generate BGM/Foley/ambience candidates",
    )

    ae = sub.add_parser("audio-event", help="Edit one auditable audio-timeline event")
    ae.add_argument("--root", required=True)
    ae.add_argument("--event", required=True)
    ae.add_argument("--gain", type=float, default=None)
    ae.add_argument("--pan", type=float, default=None)
    ae.add_argument("--fade-in", type=float, default=None)
    ae.add_argument("--fade-out", type=float, default=None)
    ae.add_argument("--muted", action=argparse.BooleanOptionalAction, default=None)
    ae.add_argument("--locked", action=argparse.BooleanOptionalAction, default=None)
    ae.add_argument("--overlap-policy", choices=("interrupt", "cross_talk"), default=None)
    ae.add_argument("--text", default=None)
    ae.add_argument("--caption-text", default=None)
    ae.add_argument("--performance-json", default=None)
    ae.add_argument("--force-locked", action="store_true")

    bgm_candidate = sub.add_parser(
        "bgm-candidate",
        help="Generate ACE-Step BGM candidates, then explicitly approve them into the local pool",
    )
    bgm_candidate_sub = bgm_candidate.add_subparsers(dest="bgm_candidate_action", required=True)
    bgm_generate = bgm_candidate_sub.add_parser("generate", help="Create one pending BGM candidate")
    bgm_generate.add_argument("--root", required=True)
    bgm_generate.add_argument("--prompt", default="")
    bgm_generate.add_argument("--mood", default="rnb")
    bgm_generate.add_argument("--duration", type=float, default=30.0)
    bgm_generate.add_argument("--seed", type=int, required=True)
    bgm_list = bgm_candidate_sub.add_parser("list", help="List pending and approved BGM candidates")
    bgm_list.add_argument("--root", required=True)
    bgm_approve = bgm_candidate_sub.add_parser(
        "approve", help="Promote one heard candidate to audio/templates/<mood>/"
    )
    bgm_approve.add_argument("--root", required=True)
    bgm_approve.add_argument("--asset-id", required=True)
    bgm_approve.add_argument("--target", choices=("film", "shared"), default="film")
    bgm_approve.add_argument("--reviewer", default="")
    bgm_approve.add_argument("--license-note", default="")
    bgm_approve.add_argument("--instrumental-confirmed", action="store_true")

    performance_candidate = sub.add_parser(
        "performance-candidate",
        help="Generate private non-verbal performance candidates with explicit adult and source authorization",
    )
    performance_candidate_sub = performance_candidate.add_subparsers(
        dest="performance_candidate_action", required=True
    )
    performance_generate = performance_candidate_sub.add_parser(
        "generate", help="Create one pending performance candidate"
    )
    performance_generate.add_argument("--root", required=True)
    performance_generate.add_argument("--cue", required=True)
    performance_generate.add_argument("--duration", type=float, default=3.0)
    performance_generate.add_argument("--seed", type=int, required=True)
    performance_generate.add_argument("--character-id", required=True)
    performance_generate.add_argument(
        "--source-authorization", choices=("original", "authorized_reference"), required=True
    )
    performance_generate.add_argument("--adult-confirmed", action="store_true")
    performance_generate.add_argument("--model-version", default="higgs-audio-v2")
    performance_approve = performance_candidate_sub.add_parser(
        "approve", help="Promote one human-heard performance candidate"
    )
    performance_approve.add_argument("--root", required=True)
    performance_approve.add_argument("--asset-id", required=True)
    performance_reject = performance_candidate_sub.add_parser(
        "reject", help="Record a human rejection; rejected candidates cannot be approved"
    )
    performance_reject.add_argument("--root", required=True)
    performance_reject.add_argument("--asset-id", required=True)
    performance_reject.add_argument("--reviewer", required=True)
    performance_reject.add_argument("--reason", required=True)

    adult_female_voice_pack = sub.add_parser(
        "adult-female-voice-pack",
        help="Create, render, review, and approve fixed-profile adult female dialogue/breath candidates",
    )
    adult_female_voice_pack_sub = adult_female_voice_pack.add_subparsers(
        dest="adult_female_voice_pack_action", required=True
    )
    adult_female_voice_pack_init = adult_female_voice_pack_sub.add_parser("init")
    adult_female_voice_pack_init.add_argument("--root", required=True)
    adult_female_voice_pack_render = adult_female_voice_pack_sub.add_parser("render")
    adult_female_voice_pack_render.add_argument("--root", required=True)
    adult_female_voice_pack_render.add_argument(
        "--node-url",
        default="",
        help="Optional private LAN or Tailscale 100.x audio-node URL; does not persist config",
    )
    adult_female_voice_pack_list = adult_female_voice_pack_sub.add_parser("list")
    adult_female_voice_pack_list.add_argument("--root", required=True)
    adult_female_voice_pack_approve = adult_female_voice_pack_sub.add_parser("approve")
    adult_female_voice_pack_approve.add_argument("--root", required=True)
    adult_female_voice_pack_approve.add_argument("--asset-id", required=True)
    adult_female_voice_pack_approve.add_argument("--reviewer", required=True)
    adult_female_voice_pack_approve.add_argument("--female-voice-confirmed", action="store_true")
    adult_female_voice_pack_approve.add_argument("--breath-confirmed", action="store_true")
    adult_female_voice_pack_approve.add_argument("--artifact-free-confirmed", action="store_true")

    ambience_candidate = sub.add_parser(
        "ambience-candidate", help="Generate and human-approve Stable Audio ambience candidates"
    )
    ambience_sub = ambience_candidate.add_subparsers(
        dest="ambience_candidate_action", required=True
    )
    ambience_generate = ambience_sub.add_parser("generate")
    ambience_generate.add_argument("--root", required=True)
    ambience_generate.add_argument("--prompt", required=True)
    ambience_generate.add_argument("--duration", type=float, default=10.0)
    ambience_generate.add_argument("--seed", type=int, required=True)
    ambience_list = ambience_sub.add_parser("list")
    ambience_list.add_argument("--root", required=True)
    ambience_approve = ambience_sub.add_parser("approve")
    ambience_approve.add_argument("--root", required=True)
    ambience_approve.add_argument("--asset-id", required=True)
    ambience_approve.add_argument("--reviewer", required=True)
    ambience_approve.add_argument("--heard-full", action="store_true")
    ambience_approve.add_argument("--no-speech-confirmed", action="store_true")
    ambience_approve.add_argument("--no-music-confirmed", action="store_true")
    ambience_approve.add_argument("--artifact-free-confirmed", action="store_true")
    ambience_attach = ambience_sub.add_parser("attach")
    ambience_attach.add_argument("--root", required=True)
    ambience_attach.add_argument("--asset-id", required=True)
    ambience_attach.add_argument("--shot-id", required=True)
    ambience_attach.add_argument("--start-offset-sec", type=float, required=True)
    ambience_attach.add_argument("--duration", type=float, required=True)
    ambience_attach.add_argument("--acoustic-space", required=True)
    ambience_attach.add_argument("--noncommercial-internal-ok", action="store_true")

    sfx_canary = sub.add_parser(
        "sfx-canary",
        help="Generate one pending, non-commercial MMAudio SFX pilot on the private RTX node",
    )
    sfx_canary.add_argument("--root", required=True)
    sfx_canary.add_argument("--prompt", required=True)
    sfx_canary.add_argument("--duration", type=float, default=8.0)
    sfx_canary.add_argument("--seed", type=int, required=True)
    sfx_canary.add_argument("--video", default="")
    sfx_canary.add_argument("--noncommercial-research-ok", action="store_true")

    sfx_candidate = sub.add_parser(
        "sfx-candidate",
        help="Generate, human-review, and attach internal non-commercial MMAudio SFX",
    )
    sfx_candidate_sub = sfx_candidate.add_subparsers(dest="sfx_candidate_action", required=True)
    sfx_generate = sfx_candidate_sub.add_parser("generate")
    sfx_generate.add_argument("--root", required=True)
    sfx_generate.add_argument("--prompt", required=True)
    sfx_generate.add_argument("--duration", type=float, default=8.0)
    sfx_generate.add_argument("--seed", type=int, required=True)
    sfx_generate.add_argument("--video", default="")
    sfx_generate.add_argument("--noncommercial-research-ok", action="store_true")
    sfx_batch = sfx_candidate_sub.add_parser(
        "batch", help="Generate and ASR-screen 1-24 non-commercial SFX candidates"
    )
    sfx_batch.add_argument("--root", required=True)
    sfx_batch.add_argument(
        "--manifest", required=True, help="JSON: {candidates:[{prompt,duration,seed}]}"
    )
    sfx_batch.add_argument("--noncommercial-research-ok", action="store_true")
    sfx_approve = sfx_candidate_sub.add_parser("approve")
    sfx_approve.add_argument("--root", required=True)
    sfx_approve.add_argument("--asset-id", required=True)
    sfx_approve.add_argument("--reviewer", required=True)
    sfx_approve.add_argument("--heard-full", action="store_true")
    sfx_approve.add_argument("--sync-confirmed", action="store_true")
    sfx_approve.add_argument("--no-speech-confirmed", action="store_true")
    sfx_approve.add_argument("--no-music-confirmed", action="store_true")
    sfx_approve.add_argument("--artifact-free-confirmed", action="store_true")
    sfx_approve.add_argument(
        "--asr-speech-reviewed",
        action="store_true",
        help="Confirm that the candidate-only ASR leakage signal was reviewed; human listening remains required",
    )
    sfx_screen = sfx_candidate_sub.add_parser(
        "screen-speech",
        help="Run candidate-only VibeVoice-ASR leakage screening before human SFX approval",
    )
    sfx_screen.add_argument("--root", required=True)
    sfx_screen.add_argument("--asset-id", required=True)
    sfx_reject = sfx_candidate_sub.add_parser("reject")
    sfx_reject.add_argument("--root", required=True)
    sfx_reject.add_argument("--asset-id", required=True)
    sfx_reject.add_argument("--reviewer", required=True)
    sfx_reject.add_argument("--reason", required=True)
    sfx_attach = sfx_candidate_sub.add_parser("attach")
    sfx_attach.add_argument("--root", required=True)
    sfx_attach.add_argument("--asset-id", required=True)
    sfx_attach.add_argument("--shot-id", required=True)
    sfx_attach.add_argument("--kind", choices=("foley", "sfx"), required=True)
    sfx_attach.add_argument("--start-offset-sec", type=float, required=True)
    sfx_attach.add_argument("--duration", type=float, required=True)
    sfx_attach.add_argument("--material", required=True)
    sfx_attach.add_argument("--noncommercial-internal-ok", action="store_true")

    sfx_library = sub.add_parser(
        "sfx-library",
        help="Audit or import signed MMAudio takes into the shared non-commercial SFX armory",
    )
    sfx_library_sub = sfx_library.add_subparsers(dest="sfx_library_action", required=True)
    sfx_library_audit = sfx_library_sub.add_parser("audit")
    sfx_library_audit.add_argument("--library-root", default="")
    sfx_library_import = sfx_library_sub.add_parser("import-project")
    sfx_library_import.add_argument("--root", required=True, help="Legacy film project root")
    sfx_library_import.add_argument("--asset-id", required=True)
    sfx_library_import.add_argument("--library-root", default="")
    sfx_library_review = sfx_library_sub.add_parser(
        "review-pack", help="Write a listening pack from retained global SFX candidates"
    )
    sfx_library_review.add_argument("--name", required=True)
    sfx_library_review.add_argument("--library-root", default="")

    lsc = sub.add_parser(
        "lipsync-canary",
        help="Single-shot lipsync probe → receipts/lipsync-canary/ (default final still lipsync off)",
    )
    lsc.add_argument("--root", required=True)
    lsc.add_argument("--shot", "--shot-id", dest="shot_id", required=True)
    lsc.add_argument("--backend", default="auto")
    lsc.add_argument("--video", default=None)
    lsc.add_argument("--audio", default=None)

    lsp = sub.add_parser(
        "lipsync-pilot",
        help="Three-shot close-dialogue LatentSync pilot; never promotes candidate media",
    )
    lsp_sub = lsp.add_subparsers(dest="lipsync_pilot_action", required=True)
    lsp_create = lsp_sub.add_parser(
        "create", help="Register three distinct standard samples and one Japanese dialogue track"
    )
    lsp_create.add_argument("--root", required=True)
    lsp_create.add_argument("--front-video", required=True)
    lsp_create.add_argument("--three-quarter-video", required=True)
    lsp_create.add_argument("--moving-video", required=True)
    lsp_create.add_argument("--japanese-audio", required=True)
    lsp_create.add_argument("--approval-receipt", required=True)
    lsp_run = lsp_sub.add_parser(
        "run", help="Run only after the shared ComfyUI queue is proved empty"
    )
    lsp_run.add_argument("--root", required=True)
    lsp_muse = lsp_sub.add_parser(
        "rerun-musetalk",
        help="Explicit manual fallback after a classified LatentSync technical failure",
    )
    lsp_muse.add_argument("--root", required=True)
    lsp_muse.add_argument(
        "--sample",
        required=True,
        choices=("front_closeup", "three_quarter_closeup", "moving_closeup"),
    )
    lsp_review = lsp_sub.add_parser(
        "review-template", help="Write a human review template for completed pilot outputs"
    )
    lsp_review.add_argument("--root", required=True)

    lsch = sub.add_parser(
        "lipsync-challenge",
        help="Plan and evaluate the four-backend lip-sync challenge without running GPU work",
    )
    lsch_sub = lsch.add_subparsers(dest="lipsync_challenge_action", required=True)
    lsch_create = lsch_sub.add_parser("create")
    lsch_create.add_argument("--root", required=True)
    lsch_create.add_argument("--front-closeup", required=True)
    lsch_create.add_argument("--three-quarter", required=True)
    lsch_create.add_argument("--occlusion-motion", required=True)
    lsch_create.add_argument("--anime", required=True)
    lsch_create.add_argument("--japanese-audio", required=True)
    lsch_create.add_argument("--approval-receipt", required=True)
    lsch_register = lsch_sub.add_parser("register-result")
    lsch_register.add_argument("--root", required=True)
    lsch_register.add_argument(
        "--fixture-id",
        required=True,
        choices=("front_closeup", "three_quarter", "occlusion_motion", "anime"),
    )
    lsch_register.add_argument(
        "--backend-id",
        required=True,
        choices=(
            "latentsync-1.6",
            "echomimic-v3-flash",
            "longcat-video-avatar-1.5",
        ),
    )
    lsch_register.add_argument("--output", required=True)
    lsch_register.add_argument("--metrics-receipt", required=True)
    lsch_register.add_argument("--runtime-receipt", required=True)
    lsch_package = lsch_sub.add_parser("blind-package")
    lsch_package.add_argument("--root", required=True)
    lsch_review = lsch_sub.add_parser("review")
    lsch_review.add_argument("--root", required=True)
    lsch_review.add_argument("--reviewer", required=True)
    lsch_review.add_argument("--review-json", required=True)
    lsch_report = lsch_sub.add_parser("report")
    lsch_report.add_argument("--root", required=True)
    lsch_report.add_argument("--license-receipt", default="")

    lsn = sub.add_parser(
        "lipsync-node",
        help="Inspect the authenticated Windows RTX lip-sync node",
    )
    lsn.add_argument(
        "lipsync_node_action",
        nargs="?",
        default="health",
        choices=["health"],
    )

    cap = sub.add_parser(
        "capability",
        help="One-page readiness (TTS/BGM/lipsync/tools + optional FRW canary / i2v suggest)",
    )
    cap.add_argument(
        "--root", default=None, help="Film root (reads frw canary receipt + film-spec)"
    )
    cap.add_argument(
        "--run-canary",
        action="store_true",
        help="Hit FRW API canary and write receipts/frw-key-capability.json (costs credits)",
    )
    cap.add_argument("--canary-wait", action="store_true", help="With --run-canary: poll ltx-t2v")
    cap.add_argument(
        "--canary-full", action="store_true", help="With --run-canary: full template probes"
    )
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
        default="mimo,edge",
        help="Comma-separated backends (default: mimo,edge)",
    )
    tab.add_argument("--voice", default=None)
    tab.add_argument("--text", default=None, help="Override shot nar")
    tab.add_argument("--spec", default=None)

    el_canary = sub.add_parser(
        "elevenlabs-canary",
        help="Bounded Chinese+Japanese ElevenLabs TTS canary; candidates need human review",
    )
    el_canary.add_argument("--root", required=True)
    el_canary.add_argument("--zh-voice", default="", help="ElevenLabs provider voice ID")
    el_canary.add_argument("--ja-voice", default="", help="ElevenLabs provider voice ID")
    el_canary.add_argument("--model", default="eleven_multilingual_v2")
    el_canary.add_argument("--confirm-cost", action="store_true")
    el_canary.add_argument("--max-paid-calls", type=int, default=0)
    el_canary.add_argument(
        "--list-voices", action="store_true", help="List account voices; no synthesis"
    )
    el_canary.add_argument("--review-language", choices=("zh", "ja"))
    el_canary.add_argument("--decision", choices=("approve", "reject"))

    init_p = sub.add_parser("init", help="Create film root")
    init_p.add_argument("--theme", required=True)
    init_p.add_argument("--title", required=True)
    init_p.add_argument("--root", required=True)
    init_p.add_argument("--aspect", default="9:16")
    init_p.add_argument("--force", action="store_true")

    resume_manifest = sub.add_parser(
        "resume-manifest", help="Create only a missing manifest for a legacy film root"
    )
    resume_manifest.add_argument("--root", required=True)

    st = sub.add_parser("status", help="Gate status")
    st.add_argument("--root", required=True)
    st.set_defaults(no_write=True)

    truth = sub.add_parser(
        "truth", help="Read-only audit of production authority records and projection drift"
    )
    truth_sub = truth.add_subparsers(dest="truth_action", required=True)
    truth_audit = truth_sub.add_parser("audit")
    truth_audit.add_argument("--root", required=True)
    truth_audit.set_defaults(no_write=True)

    quality = sub.add_parser(
        "quality", help="Read persisted per-shot quality receipts (no media scan)"
    )
    quality.add_argument("--root", required=True)
    quality.add_argument("--shot-id", default=None)

    sub.add_parser(
        "beat-evidence", help="Validate planned shot actions against human review evidence"
    ).add_argument("--root", required=True)
    sub.add_parser(
        "editor-cut", help="Check deterministic rough-cut readiness and active take integrity"
    ).add_argument("--root", required=True)
    sub.add_parser(
        "audio-visual", help="Check audio, dialogue, subtitle and timeline alignment"
    ).add_argument("--root", required=True)

    pe = sub.add_parser("production-evidence", help="Read-only production evidence ledger")
    pe.add_argument("--root", required=True)
    ne = sub.add_parser(
        "narrative-evidence",
        help="Create or validate executed/human evidence for episode hooks and plot points",
    )
    ne_sub = ne.add_subparsers(dest="narrative_evidence_action", required=True)
    ne_init = ne_sub.add_parser("init", help="Create the plan-side evidence ledger")
    ne_init.add_argument("--root", required=True)
    ne_record = ne_sub.add_parser("record", help="Register one executed evidence item")
    ne_record.add_argument("--root", required=True)
    ne_record.add_argument("--evidence-id", required=True)
    ne_record.add_argument("--status", required=True, choices=("verified", "missing", "uncertain"))
    ne_record.add_argument("--shot-id")
    ne_record.add_argument("--start-sec", type=float)
    ne_record.add_argument("--end-sec", type=float)
    ne_record.add_argument("--media-path")
    ne_record.add_argument("--reviewer")
    ne_record.add_argument("--user-phrase")
    ne_record.add_argument("--note", default="")
    ne_validate = ne_sub.add_parser("validate", help="Validate current media-backed evidence")
    ne_validate.add_argument("--root", required=True)
    pa = sub.add_parser("post-audit", help="Unified post-production audit")
    pa.add_argument("--root", required=True)
    caption_audit = sub.add_parser(
        "caption-frame-audit",
        help="Extract final-MP4 frames during subtitle cues for human readability review",
    )
    caption_audit.add_argument("--root", required=True)
    caption_audit.add_argument("--max-frames", type=int, default=5)
    transition_audit = sub.add_parser(
        "transition-frame-audit",
        help="Extract final-MP4 frames around every planned shot transition for human review",
    )
    transition_audit.add_argument("--root", required=True)
    transition_template = sub.add_parser(
        "transition-frame-review-template",
        help="Create a per-seam human decision template for the current transition audit",
    )
    transition_template.add_argument("--root", required=True)
    transition_attest = sub.add_parser(
        "transition-frame-attest",
        help="Record human approval for current per-transition review frames",
    )
    transition_attest.add_argument("--root", required=True)
    transition_attest.add_argument("--user-phrase", required=True)
    transition_attest.add_argument(
        "--decisions",
        help="Path to completed transition-review-decisions JSON; required when the film has joins",
    )
    caption_attest = sub.add_parser(
        "caption-frame-attest",
        help="Record human readability approval for current caption review frames",
    )
    caption_attest.add_argument("--root", required=True)
    caption_attest.add_argument("--user-phrase", required=True)

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

    quality_status = sub.add_parser(
        "quality-status", help="Show hash-bound per-shot quality, motion, and review evidence"
    )
    quality_status.add_argument("--root", required=True)
    quality_status.add_argument("--shot-id")

    shot_review = sub.add_parser(
        "review-shot",
        help="Create evidence-backed first/middle/last-frame director review for one clip",
    )
    shot_review.add_argument("--root", required=True)
    shot_review.add_argument("--shot-id", required=True)
    shot_review.add_argument("--source", required=True)
    shot_review.add_argument(
        "--approve",
        action="store_true",
        help="Approve only if QA, 1–5 scores, and timestamp evidence all pass",
    )
    shot_review.add_argument("--reviewer", required=True)
    shot_review.add_argument("--notes", required=True)
    for dim in ("identity", "continuity", "composition", "motion", "narrative"):
        shot_review.add_argument(
            f"--score-{dim}", type=int, choices=range(1, 6), required=True, dest=f"score_{dim}"
        )
    shot_review.add_argument(
        "--score-coitus",
        type=int,
        choices=range(1, 6),
        required=False,
        default=None,
        dest="score_coitus",
        help="Optional mute-frame intercourse readability 1-5 (adult max)",
    )
    shot_review.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Repeat dimension@seconds:note for every review dimension",
    )
    shot_review.add_argument(
        "--performance-evidence",
        action="append",
        default=[],
        help=(
            "Repeat kind@seconds:note. Required authored story facts use "
            "start_state_visible, must_show_visible, visible_change_visible, end_state_visible; "
            "also action_visible, trigger_visible, reaction_visible, dialogue_delivery, mouth_still"
        ),
    )
    shot_review.add_argument(
        "--reference", action="append", default=[], help="Optional reference asset path; repeatable"
    )

    review_pack = sub.add_parser(
        "review-pack",
        help="Create an unapproved local decode, frame, contact-sheet and hash evidence package",
    )
    review_pack.add_argument("--root", required=True)
    review_pack.add_argument("--id", required=True, help="Stable review package id")
    review_pack.add_argument("--source", help="Existing local video path")
    review_pack.add_argument(
        "--comfy-filename",
        help="Download this named Comfy output first; mutually exclusive with --source",
    )
    review_pack.add_argument("--comfy-base-url", help="ComfyUI base URL for --comfy-filename")
    review_pack.add_argument("--comfy-subfolder", default="")
    review_pack.add_argument("--comfy-type", choices=("input", "output", "temp"), default="output")
    review_pack.add_argument("--no-expect-audio", dest="expect_audio", action="store_false")
    review_pack.set_defaults(expect_audio=True)

    review_contract = sub.add_parser(
        "review-contract",
        help="Explicitly migrate a legacy film root to v1.6 review evidence gates",
    )
    review_contract_sub = review_contract.add_subparsers(
        dest="review_contract_action", required=True
    )
    review_contract_migrate = review_contract_sub.add_parser(
        "migrate", help="Require real shot reviews for historical approved clips"
    )
    review_contract_migrate.add_argument("--root", required=True)
    review_contract_v3 = review_contract_sub.add_parser(
        "upgrade-v3", help="Opt into grades and canonical fail reasons for future final reviews"
    )
    review_contract_v3.add_argument("--root", required=True)

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

    fin = sub.add_parser(
        "final", help="Render formal final: edge-tts VO + BGM + burned Chinese subs"
    )
    fin.add_argument("--root", required=True)
    fin.add_argument("--out-name", default="film_final.mp4")
    fin.add_argument(
        "--resume",
        action="store_true",
        help="Resume valid per-shot stretch/lipsync checkpoints from receipts/checkpoints/",
    )
    fin.add_argument(
        "--force",
        action="store_true",
        help="Clear per-shot final-render checkpoints before rendering",
    )
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
    fin.add_argument(
        "--voice",
        default=None,
        help="edge voice or provider voice id; default comes from film-spec",
    )
    fin.add_argument(
        "--tts-backend",
        default=None,
        choices=["audio_node", "auto", "minimax", "fish", "edge", "external"],
        help="audio_node: private Qwen3-TTS on the 5090; auto: external > MiniMax > pinned Fish > edge",
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
        choices=["off", "auto", "on", "timeline", "approved_library"],
        help=(
            "BGM: auto/on/off retain legacy behavior; timeline uses film-local cue templates; "
            "approved_library requires shared human-approved cue matches"
        ),
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
        help="Mix gain for generated clip audio preserved as native stems (default from film-spec or 0.72; primary video sound)",
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
        choices=["auto", "off", "require", "latentsync", "external", "wav2lip"],
        help="Lip-sync OFF by default. RTX node uses LatentSync 1.6 for approved close-up repair.",
    )
    fin.add_argument("--sub-lead", type=float, default=0.08, help="Show subtitles early (seconds)")
    fin.add_argument(
        "--sub-max-unit", type=float, default=1.75, help="Max seconds per subtitle line"
    )
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
        default="blank",
        help="blank=pad only with no glyphs (default); text is an explicit FFmpeg-only compatibility override",
    )
    fin.add_argument(
        "--post-engine",
        default="hyperframes",
        choices=["ffmpeg", "hyperframes", "remotion"],
        help=(
            "Staged final: ffmpeg=plate burns captions; "
            "hyperframes=stage_plate (subs off) → stage_hf captions → "
            "stage_caption verify (HF failure blocks and must re-render) → deliver. "
            "Never assumes HF burned without gate."
        ),
    )
    fin.add_argument(
        "--subs",
        default="off",
        choices=["burn", "off"],
        help=(
            "Plate only: off is the default so HyperFrames is the sole text/caption layer; "
            "burn is an explicit FFmpeg-only compatibility override."
        ),
    )
    fin.add_argument(
        "--plate-timeout",
        type=int,
        default=0,
        help="Seconds for stage_plate; 0 auto-scales from duration, shots and lipsync (floor 1200)",
    )
    fin.add_argument(
        "--no-caption-recovery",
        action="store_true",
        help=("Deprecated compatibility flag; HyperFrames delivery never uses caption recovery"),
    )
    fin.add_argument(
        "--compose-quality",
        default=None,
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
        "--skip-heat-gate",
        action="store_true",
        help="Skip adult-max heat final_ok (S-grade) gate before final (not recommended)",
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
    review.add_argument(
        "--review-file",
        help="Hash-bound JSON emitted by review-ui; replaces reviewer/notes/score/grade/evidence flags",
    )
    review.add_argument("--approve", action="store_true")
    review.add_argument("--reviewer")
    review.add_argument("--notes")
    review.add_argument(
        "--watched-full", action="store_true", help="Required by review contract v3"
    )
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
            f"--grade-{dim.replace('_', '-')}",
            type=int,
            choices=range(1, 6),
            default=None,
            dest=f"grade_{dim}",
            help="v3 numeric grade 1-5",
        )
    review.add_argument(
        "--reshoot-shots",
        default="",
        help="Comma-separated shot ids to attach to identity/style/motion/escalation fails (writes director_notes)",
    )
    review.add_argument(
        "--screening-evidence",
        action="append",
        default=[],
        help="v1.6: repeat dimension@seconds:note for each final scorecard dimension",
    )
    review.add_argument(
        "--fail-reason",
        action="append",
        default=[],
        help="v3 repeat dimension:CANONICAL_CODE[:shot]",
    )

    editorial_review = sub.add_parser(
        "final-editorial-review",
        help="Write a hash-bound no-spend editorial review before final approval",
    )
    editorial_review.add_argument("--root", required=True)

    performance_timeline = sub.add_parser(
        "performance-timeline",
        help="Compile checksum-bound per-shot performance evidence into a director timeline",
    )
    performance_timeline.add_argument("--root", required=True)

    speech_performance_timing = sub.add_parser(
        "speech-performance-timing",
        help="Check measured dialogue duration against delivery evidence and reaction space",
    )
    speech_performance_timing.add_argument("--root", required=True)

    audio_provenance = sub.add_parser(
        "audio-provenance",
        help="Bind dialogue rehearsal audio hashes to voice carrier and registered final MP4",
    )
    audio_provenance.add_argument("--root", required=True)
    subtitle_alignment = sub.add_parser(
        "subtitle-dialogue-alignment",
        help="Check subtitle coverage and safe area for lipsync dialogue",
    )
    subtitle_alignment.add_argument("--root", required=True)
    subtitle_boundaries = sub.add_parser(
        "subtitle-cut-boundaries", help="Check subtitle cues against hard and Continue cuts"
    )
    subtitle_boundaries.add_argument("--root", required=True)

    # v1.23: delivery-level FFmpeg quality gates (objective, pre-scorecard)
    qcheck = sub.add_parser(
        "quality-check",
        help="Run 8-gate FFmpeg delivery quality check with weighted scoring",
    )
    qcheck.add_argument("video", help="Final video path")
    qcheck.add_argument("--root", default=None, help="Film root (defaults --out to <root>/out)")
    qcheck.add_argument(
        "--out", default=None, help="Output dir for quality-report.json + artefacts"
    )
    qcheck.add_argument(
        "--expect-audio", action="store_true", default=True, help="Require audio stream"
    )
    qcheck.add_argument("--no-expect-audio", dest="expect_audio", action="store_false")
    qcheck.add_argument("--expect-subtitles", action="store_true", help="Require sidecar SRT")
    qcheck.add_argument("--srt", default=None, help="Expected sidecar SRT file")
    qcheck.add_argument(
        "--min-score", type=int, default=80, help="Minimum score to pass (default 80)"
    )
    qcheck.add_argument(
        "--allow-black", action="store_true", help="Downgrade black-frame fail to warn"
    )
    qcheck.add_argument("--allow-freeze", action="store_true", help="Downgrade freeze fail to warn")

    cinematic = sub.add_parser(
        "cinematic-audit",
        help="Write a checksum-bound cinematic coherence/coverage audit (no-spend)",
    )
    cinematic.add_argument("--root", required=True)

    from cli_optimization import add_optimization_parsers

    add_optimization_parsers(sub)

    from cli_quality_reporting import add_quality_reporting_parsers

    add_quality_reporting_parsers(sub)

    benchmark_p = sub.add_parser(
        "benchmark", help="Run a no-spend premium vertical benchmark contract"
    )
    benchmark_p.add_argument("--root", default=None, help="Optional film root for receipt binding")
    benchmark_p.add_argument("--suite", choices=("premium-vertical",), default="premium-vertical")
    benchmark_p.add_argument("--mode", choices=("contract", "live"), default="contract")

    dialogue_benchmark_p = sub.add_parser(
        "dialogue-benchmark",
        help="Plan the 30–60s Qwen/keyframe/FRW-LTX benchmark without spending",
    )
    dialogue_benchmark_p.add_argument("--root", required=True)
    dialogue_benchmark_review_p = sub.add_parser(
        "dialogue-benchmark-review", help="Record a human-reviewed Qwen/keyframe/FRW-LTX arm"
    )
    dialogue_benchmark_review_p.add_argument("--root", required=True)
    dialogue_benchmark_review_p.add_argument("--weapon", required=True)
    dialogue_benchmark_review_p.add_argument("--artifact", required=True)
    dialogue_benchmark_review_p.add_argument("--reviewer", required=True)
    dialogue_benchmark_review_p.add_argument("--note", required=True)
    dialogue_benchmark_review_p.add_argument("--parameters-json", required=True)
    dialogue_benchmark_approve_p = sub.add_parser(
        "dialogue-benchmark-approve", help="Approve all reviewed dialogue benchmark parameters"
    )
    dialogue_benchmark_approve_p.add_argument("--root", required=True)
    dialogue_benchmark_approve_p.add_argument("--reviewer", required=True)
    dialogue_benchmark_approve_p.add_argument("--rationale", required=True)
    dialogue_production_plan_p = sub.add_parser(
        "dialogue-production-plan",
        help="Compile the no-spend Qwen/keyframe/FRW-LTX/LatentSync-fallback dialogue plan",
    )
    dialogue_production_plan_p.add_argument("--root", required=True)
    dialogue_benchmark_queue_p = sub.add_parser(
        "dialogue-benchmark-queue",
        help="Persist/claim the no-submit P2 Qwen/Wan/LatentSync benchmark queue",
    )
    dialogue_benchmark_queue_sub = dialogue_benchmark_queue_p.add_subparsers(
        dest="dialogue_benchmark_queue_action", required=True
    )
    for queue_action in ("enqueue", "claim", "status"):
        item = dialogue_benchmark_queue_sub.add_parser(queue_action)
        item.add_argument("--root", required=True)
    dialogue_benchmark_queue_complete_p = dialogue_benchmark_queue_sub.add_parser("complete")
    dialogue_benchmark_queue_complete_p.add_argument("--root", required=True)
    dialogue_benchmark_queue_complete_p.add_argument("--job-id", required=True)
    dialogue_benchmark_queue_complete_p.add_argument("--claim-token", required=True)
    dialogue_benchmark_queue_submit_p = dialogue_benchmark_queue_sub.add_parser("submit-comfy")
    dialogue_benchmark_queue_submit_p.add_argument("--root", required=True)
    dialogue_benchmark_queue_submit_p.add_argument("--job-id", required=True)
    dialogue_benchmark_queue_submit_p.add_argument("--claim-token", required=True)
    dialogue_benchmark_queue_submit_p.add_argument("--workflow", required=True)
    dialogue_benchmark_queue_submit_p.add_argument("--weapon-id", required=True)

    creative = sub.add_parser(
        "creative-pipeline", help="Radio cut, animatic and premium pre-production gates"
    )
    creative_sub = creative.add_subparsers(dest="pipeline_action", required=True)
    cr = creative_sub.add_parser("readiness")
    cr.add_argument("--root", required=True)
    radio = creative_sub.add_parser("radio-cut")
    radio.add_argument("--root", required=True)
    radio.add_argument("--write", action="store_true")
    radio.add_argument("--timing-ok", action="store_true")
    radio.add_argument("--emotion-turns-ok", action="store_true")
    radio.add_argument("--shot-count", type=int, default=0)
    anim = creative_sub.add_parser("animatic")
    anim.add_argument("--root", required=True)
    anim.add_argument("--write", action="store_true")
    anim.add_argument("--coverage-ok", action="store_true")
    anim.add_argument("--pace-ok", action="store_true")
    anim.add_argument("--performance-ok", action="store_true")

    dailies = sub.add_parser(
        "dailies", help="Record and audit Select/Alternate/Reject/Reshoot candidates"
    )
    dailies_sub = dailies.add_subparsers(dest="dailies_action", required=True)
    ds = dailies_sub.add_parser("status")
    ds.add_argument("--root", required=True)
    dr = dailies_sub.add_parser("record")
    dr.add_argument("--root", required=True)
    dr.add_argument("--shot-id", required=True)
    dr.add_argument("--candidate", required=True)
    dr.add_argument("--status", choices=("select", "alternate", "reject", "reshoot"), required=True)
    dr.add_argument("--reviewer", required=True)
    dr.add_argument("--notes", default="")
    dr.add_argument("--approved-budget", type=int, default=None)
    dr.add_argument("--provider", default="", help="Generation provider recorded with this take")
    dr.add_argument("--model", default="", help="Generation model recorded with this take")
    dr.add_argument(
        "--cost-usd", type=float, default=None, help="Known provider cost; never inferred"
    )
    dr.add_argument("--source-keyframe", default="", help="Approved source still/keyframe path")
    dr.add_argument("--qa-json", default="", help="Objective QA JSON object")
    dr.add_argument("--director-score", type=int, default=None, help="Director score 1-5")
    dr.add_argument("--issue-tag", action="append", default=[], help="Repeatable quality issue tag")
    dr.add_argument("--reshoot-decision", choices=("none", "reshoot", "repair"), default="")
    dr.add_argument("--selection-rationale", default="")

    postq = sub.add_parser("post-quality", help="VFX, audio and premium Master QC contracts")
    postq_sub = postq.add_subparsers(dest="post_action", required=True)
    vr = postq_sub.add_parser("vfx-register")
    vr.add_argument("--root", required=True)
    vr.add_argument("--shot-id", required=True)
    vr.add_argument("--plate", required=True)
    vr.add_argument(
        "--status", choices=("pending", "wip", "review", "approved", "rejected"), required=True
    )
    vr.add_argument("--reviewer", required=True)
    vr.add_argument("--notes", default="")
    for name in ("vfx-check", "audio-check"):
        post_check = postq_sub.add_parser(name)
        post_check.add_argument("--root", required=True)
    mq = postq_sub.add_parser("master-qc")
    mq.add_argument("--root", required=True)
    mq.add_argument("--final", default=None)

    canary = sub.add_parser("provider-canary", help="Record or inspect a real provider canary")
    canary_sub = canary.add_subparsers(dest="canary_action", required=True)
    cs = canary_sub.add_parser("status")
    cs.add_argument("--root", required=True)
    cc = canary_sub.add_parser("record")
    cc.add_argument("--root", required=True)
    cc.add_argument("--provider", choices=("grok", "seedance"), required=True)
    cc.add_argument("--output", required=True)
    cc.add_argument("--reviewer", required=True)
    cc.add_argument("--identity-ok", action="store_true")
    cc.add_argument("--motion-ok", action="store_true")
    cc.add_argument("--notes", default="")

    package = sub.add_parser(
        "delivery-package", help="Validate dual-master premium delivery assets"
    )
    package.add_argument("--root", required=True)
    package.add_argument("--allow-missing", action="store_true")

    closure = sub.add_parser(
        "quality-closure", help="No-spend premium benchmark, blind-review, and evidence report"
    )
    closure_sub = closure.add_subparsers(dest="quality_closure_action", required=True)
    closure_package = closure_sub.add_parser("package", help="Write the fixed benchmark package")
    closure_package.add_argument("--root", required=True)
    closure_report = closure_sub.add_parser(
        "report", help="Summarize evidence without inflating claims"
    )
    closure_report.add_argument("--root", required=True)
    closure_review = closure_sub.add_parser("review", help="Record one independent blind review")
    closure_review.add_argument("--root", required=True)
    closure_review.add_argument("--reviewer", required=True)
    closure_review.add_argument("--scores-json", required=True)
    closure_review.add_argument("--notes", default="")

    promotion = sub.add_parser(
        "promotion-report",
        help="Read-only candidate-to-promotion quality report",
    )
    promotion.add_argument("--root", required=True)
    promotion.add_argument(
        "--out", default=None, help="Explicit JSON report path inside the film root"
    )

    # v1.23: reference video audit — reverse-engineer shot grammar
    refaudit = sub.add_parser(
        "analyze-reference",
        help="Analyze a reference video: probe, contact sheet, keyframes, shot grammar",
    )
    refaudit.add_argument("video", help="Reference video path")
    refaudit.add_argument(
        "--root", default=None, help="Film root (writes to <root>/reference-analysis)"
    )
    refaudit.add_argument("--out", default=None, help="Output dir (overrides --root)")
    refaudit.add_argument(
        "--frames",
        default="0,3,6,9,13,18,24,30,36",
        help="Comma-separated timestamps (seconds) for keyframe extraction",
    )

    # v1.23: product brief expansion (product intro video track)
    brief_p = sub.add_parser(
        "brief",
        help="Product brief: expand a product intro into a structured video brief",
    )
    brief_sub = brief_p.add_subparsers(dest="brief_action", required=True)
    brief_expand = brief_sub.add_parser(
        "expand", help="Expand raw product text → product-brief.json"
    )
    brief_expand.add_argument("--root", required=True, help="Film root")
    brief_expand.add_argument("--text", default=None, help="Raw product description text")
    brief_expand.add_argument("--file", default=None, help="Path to product description file")
    brief_expand.add_argument("--title", default=None, help="Product name override")
    brief_expand.add_argument(
        "--target-duration", type=float, default=40.0, help="Target duration seconds"
    )
    brief_expand.add_argument(
        "--voice-style", default="warm", help="Voice style hint (warm/tech/neutral)"
    )
    brief_expand.add_argument("--language", default="zh", choices=["zh", "en"], help="VO language")

    local_llm = sub.add_parser(
        "local-llm",
        help="Opt-in private LLM drafts; cannot modify story truth or approve production",
    )
    local_llm_sub = local_llm.add_subparsers(dest="local_llm_action", required=True)
    for action, help_text in (
        ("probe", "Read the private model list without starting inference"),
        ("draft", "Generate one human-review-only creative candidate"),
        ("shot-draft", "Generate exactly two schema-validated candidate shots"),
    ):
        action_parser = local_llm_sub.add_parser(action, help=help_text)
        action_parser.add_argument(
            "--base-url",
            default=os.environ.get("AIFILM_LOCAL_LLM_BASE_URL", ""),
            help="Private OpenAI-compatible /v1 URL (or AIFILM_LOCAL_LLM_BASE_URL)",
        )
        action_parser.add_argument(
            "--model",
            default="openai/gpt-oss-20b",
            help="Approved local model id; default openai/gpt-oss-20b",
        )
        if action in {"draft", "shot-draft"}:
            action_parser.add_argument(
                "--prompt", required=True, help="Draft request; never writes film files"
            )
            action_parser.add_argument(
                "--timeout", type=int, default=45, help="1-120 seconds; default 45"
            )

    local_omni = sub.add_parser(
        "local-omni-review",
        help="Opt-in private frame review; candidate-only and cannot approve production",
    )
    local_omni_sub = local_omni.add_subparsers(dest="local_omni_review_action", required=True)
    local_omni_probe = local_omni_sub.add_parser(
        "probe", help="Read the private model list without sending frames or starting inference"
    )
    local_omni_run = local_omni_sub.add_parser(
        "run", help="Review declared sanitized workspace frames and write a candidate-only report"
    )
    for action_parser in (local_omni_probe, local_omni_run):
        action_parser.add_argument(
            "--base-url",
            default=os.environ.get("AIFILM_LOCAL_OMNI_BASE_URL", ""),
            help="Private OpenAI-compatible /v1 URL (or AIFILM_LOCAL_OMNI_BASE_URL)",
        )
        action_parser.add_argument(
            "--model",
            default="nvidia/nemotron-nano-3-30b-a3b",
            help="Private multimodal model id; default NVIDIA Nemotron Nano 30B A3B",
        )
    local_omni_run.add_argument("--root", required=True, help="Film workspace root")
    local_omni_run.add_argument(
        "--frame-index",
        required=True,
        help="In-root JSON list of 1-5 declared sanitized technical frames",
    )
    local_omni_run.add_argument(
        "--sanitized",
        action="store_true",
        help="Required declaration: frames are safe technical review samples",
    )
    local_omni_run.add_argument("--timeout", type=int, default=60, help="1-120 seconds; default 60")

    visual_text_audit = sub.add_parser(
        "visual-text-audit",
        help="Fail-closed every-frame inspection for provider-burned visual text",
    )
    visual_text_audit.add_argument("--root", required=True)
    visual_text_audit.add_argument(
        "--source", required=True, help="Video inside the film workspace"
    )
    visual_text_audit.add_argument(
        "--base-url", default=os.environ.get("AIFILM_LOCAL_OMNI_BASE_URL", "")
    )
    visual_text_audit.add_argument("--model", default="nvidia/nemotron-nano-3-30b-a3b")
    visual_text_repair = sub.add_parser(
        "visual-text-repair",
        help="Repair a rejected visual-text audit with bounded Qwen I2I frame edits",
    )
    visual_text_repair.add_argument("--root", required=True)
    visual_text_repair.add_argument(
        "--source", required=True, help="Rejected video inside the film workspace"
    )
    visual_text_repair.add_argument(
        "--base-url", default=os.environ.get("AIFILM_COMFYUI_BASE_URL", "http://127.0.0.1:18188")
    )
    visual_text_repair.add_argument("--audit-receipt", default=None)

    external_review = sub.add_parser(
        "external-review",
        help="Read-only Groq/Gemini candidate review; never changes production gates",
    )
    external_review_sub = external_review.add_subparsers(
        dest="external_review_action", required=True
    )
    external_review_sub.add_parser(
        "probe", help="Check local credential presence only; sends no media or inference request"
    )
    external_run = external_review_sub.add_parser(
        "run", help="Write a hash-bound candidate-only external review report"
    )
    external_run.add_argument("--root", required=True, help="Film workspace root")
    external_run.add_argument(
        "--video", required=True, help="Verified local MP4/audio source in root"
    )
    external_run.add_argument("--subtitles", default=None, help="Optional in-root SRT sidecar")
    external_run.add_argument(
        "--director-contract", default=None, help="Optional in-root contract JSON"
    )
    external_run.add_argument(
        "--sanitized-frame-index",
        default=None,
        help="Optional in-root JSON list of declared safe frame paths; max five frames",
    )
    external_run.add_argument(
        "--sanitized",
        action="store_true",
        help="Required for adult technical samples and every external frame upload",
    )
    external_run.add_argument(
        "--purpose",
        choices=("tts_rehearsal", "animatic", "final"),
        default="final",
        help="Audit stage recorded in the candidate-only receipt; default final",
    )

    vibevoice_asr = sub.add_parser(
        "vibevoice-asr",
        help="Local VibeVoice-ASR candidate-only subtitle and speaker review",
    )
    vibevoice_asr_sub = vibevoice_asr.add_subparsers(dest="vibevoice_asr_action", required=True)
    vibevoice_asr_sub.add_parser(
        "probe",
        help="Check local adapter configuration only; never starts inference or downloads a model",
    )
    vibevoice_run = vibevoice_asr_sub.add_parser(
        "run", help="Run the declared local adapter and write a candidate-only ASR review"
    )
    vibevoice_run.add_argument("--root", required=True, help="Film workspace root")
    vibevoice_run.add_argument("--audio", required=True, help="Verified local audio in root")
    vibevoice_run.add_argument("--subtitles", default=None, help="Optional in-root SRT sidecar")

    speech_preview = sub.add_parser(
        "speech-preview",
        help="Private RTX 5090 speech preview sidecar; candidate-only, never a production TTS backend",
    )
    speech_preview_sub = speech_preview.add_subparsers(dest="speech_preview_action", required=True)
    speech_preview_sub.add_parser(
        "probe",
        help="Validate loopback launcher and capacity-check configuration; never starts inference",
    )
    speech_start = speech_preview_sub.add_parser(
        "start", help="Request the configured private launcher after a live capacity gate"
    )
    speech_start.add_argument(
        "--confirm", action="store_true", help="Required to launch the sidecar"
    )
    speech_session = speech_preview_sub.add_parser(
        "session", help="Record one decoded, measured dialogue turn as a candidate-only receipt"
    )
    speech_session.add_argument("--root", required=True, help="Film workspace root")
    speech_session.add_argument(
        "--audio", required=True, help="Decoded reply audio inside the workspace"
    )
    speech_session.add_argument(
        "--session-json", required=True, help="In-workspace measured client result JSON"
    )
    speech_export = speech_preview_sub.add_parser(
        "export-candidate", help="Export a hash-bound preview candidate for human listening"
    )
    speech_export.add_argument("--root", required=True, help="Film workspace root")
    speech_export.add_argument(
        "--session-receipt", required=True, help="In-workspace speech-preview session receipt"
    )

    semantic_index = sub.add_parser(
        "semantic-index",
        help="Opt-in private semantic retrieval; returns source-bound review candidates only",
    )
    semantic_index_sub = semantic_index.add_subparsers(dest="semantic_index_action", required=True)
    for action, help_text in (
        ("build", "Embed allowlisted local authoring records into a derived index"),
        ("query", "Return ranked source-bound candidates from a fresh local index"),
    ):
        action_parser = semantic_index_sub.add_parser(action, help=help_text)
        action_parser.add_argument("--root", required=True, help="Film root")
        action_parser.add_argument(
            "--base-url",
            default=os.environ.get("AIFILM_LOCAL_EMBEDDING_BASE_URL", ""),
            help="Private OpenAI-compatible /v1 URL (or AIFILM_LOCAL_EMBEDDING_BASE_URL)",
        )
        action_parser.add_argument(
            "--model",
            default="text-embedding-nomic-embed-text-v1.5",
            help="Approved local embedding model; default text-embedding-nomic-embed-text-v1.5",
        )
        action_parser.add_argument(
            "--timeout", type=int, default=45, help="1-120 seconds; default 45"
        )
        if action == "query":
            action_parser.add_argument(
                "--query", required=True, help="Question to retrieve local candidates"
            )
            action_parser.add_argument(
                "--limit", type=int, default=5, help="1-20 results; default 5"
            )

    ledger = sub.add_parser(
        "director-ledger", help="Build checksum-bound ledger of human-approved exceptions"
    )
    ledger.add_argument("--root", required=True)
    autopilot = sub.add_parser(
        "planning-autopilot", help="Show safe automatic planning steps and human lock points"
    )
    autopilot.add_argument("--root", required=True)
    answer = sub.add_parser(
        "planning-answer", help="Apply structured answers to open graph authoring fields only"
    )
    answer.add_argument("--root", required=True)
    answer.add_argument(
        "--answers-json",
        required=True,
        help='JSON list: [{"node_ref":"…","field":"…","value":"…"}]',
    )
    answer.add_argument("--dry-run", action="store_true")
    answer.add_argument(
        "--expected-transaction-id",
        default=None,
        help="Require the exact transaction_id returned by a prior dry-run",
    )
    history = sub.add_parser(
        "planning-history", help="Show planning readiness progression and current blockers"
    )
    history.add_argument("--root", required=True)
    usage = sub.add_parser(
        "usage",
        help="Exact-first T2I/I2V/TTS request counts, tokens and provider costs",
    )
    usage_sub = usage.add_subparsers(dest="usage_action", required=True)
    usage_status_p = usage_sub.add_parser("status", help="Summarize one film usage ledger")
    usage_status_p.add_argument("--root", required=True)
    usage_list_p = usage_sub.add_parser("list", help="List each generation request")
    usage_list_p.add_argument("--root", required=True)
    usage_list_p.add_argument(
        "--operation",
        choices=("t2i", "image_edit", "i2v", "t2v", "tts"),
        default=None,
    )
    usage_list_p.add_argument(
        "--format",
        choices=("json", "table"),
        default="json",
        dest="output_format",
    )
    usage_summary_p = usage_sub.add_parser(
        "summary", help="Aggregate ledgers below one explicit projects directory"
    )
    usage_summary_p.add_argument("--scan-root", required=True)
    usage_record_p = usage_sub.add_parser(
        "record", help="Record one native/manual generation without inventing missing usage"
    )
    usage_record_p.add_argument("--root", required=True)
    usage_record_p.add_argument(
        "--operation",
        required=True,
        choices=("t2i", "image_edit", "i2v", "t2v", "tts"),
    )
    usage_record_p.add_argument("--provider", required=True)
    usage_record_p.add_argument("--model", default="")
    usage_record_p.add_argument(
        "--status",
        required=True,
        choices=("succeeded", "failed", "moderated"),
    )
    usage_record_p.add_argument(
        "--measurement",
        choices=("unknown", "manual_exact", "local_zero"),
        default="unknown",
    )
    usage_record_p.add_argument("--provider-request-id", default="")
    usage_record_p.add_argument("--output", default="")
    usage_record_p.add_argument("--idempotency-key", default="")
    usage_record_p.add_argument("--shot-id", default="")
    usage_record_p.add_argument("--job-id", default="")
    usage_record_p.add_argument("--input-tokens", type=int, default=None)
    usage_record_p.add_argument("--output-tokens", type=int, default=None)
    usage_record_p.add_argument("--total-tokens", type=int, default=None)
    usage_record_p.add_argument("--cost-in-usd-ticks", type=int, default=None)
    prompt_budget = sub.add_parser(
        "prompt-budget", help="Audit prompt-token estimates and repeated provider-bound lines"
    )
    prompt_budget.add_argument("--root", required=True)
    prompt_budget.add_argument(
        "--write", action="store_true", help="Write receipts/prompt-budget.json"
    )
    prompt_budget.add_argument(
        "--max-estimated-tokens",
        type=int,
        default=None,
        help="Set a review threshold; never rewrites prompts or approves compression",
    )
    compression_pilot = sub.add_parser(
        "prompt-compression-pilot",
        help="Write a hash-bound, evidence-required prompt-compression Pilot ledger",
    )
    compression_pilot.add_argument("--root", required=True)
    compression_pilot.add_argument(
        "--candidate-json",
        required=True,
        help="Root-contained JSON: source_line plus candidate prompt text for each Pilot shot",
    )
    compression_attest = sub.add_parser(
        "prompt-compression-attest",
        help="Bind candidate media/QA and existing human Pilot approval to a compression ledger",
    )
    compression_attest.add_argument("--root", required=True)
    compression_attest.add_argument("--evidence-json", required=True)
    compression_attest.add_argument("--user-phrase", required=True)

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

    heat_p = sub.add_parser(
        "heat",
        help="Adult heat: check | vo-suggest | boost | soften-log | soften-compensate",
    )
    heat_sub = heat_p.add_subparsers(dest="heat_action", required=True)
    heat_ck = heat_sub.add_parser(
        "check",
        help="One-page heat report (duration/wardrobe/VO/coitus/size/pose/montage)",
    )
    heat_ck.add_argument("--root", required=True)
    heat_vo = heat_sub.add_parser(
        "vo-suggest",
        help="Suggest denser adult nar lines by heat_phase/coitus_beat",
    )
    heat_vo.add_argument("--root", required=True)
    heat_vo.add_argument("--shot", default=None, help="Optional shot id")
    heat_boost_p = heat_sub.add_parser(
        "boost",
        help="Impact S boost plan; --apply patches duration/bare/detail/verbs/VO (never lower heat)",
    )
    heat_boost_p.add_argument("--root", required=True)
    heat_boost_p.add_argument(
        "--apply",
        action="store_true",
        help="Write field patches into film-spec + receipts/heat-boost.json",
    )
    heat_boost_p.add_argument(
        "--target-score",
        type=float,
        default=90.0,
        help="Target erotic impact score (default 90 = grade S)",
    )
    heat_sf = heat_sub.add_parser(
        "soften-log",
        help="Write receipts/moderation_soften.json dual-track compensation (never lower heat)",
    )
    heat_sf.add_argument("--root", required=True)
    heat_sf.add_argument("--note", default="", help="What was soft-moderated")
    heat_sc = heat_sub.add_parser(
        "soften-compensate",
        help="Dual-track compensate: checklist + optional --apply VO/SFX/music_energy (never lower heat)",
    )
    heat_sc.add_argument("--root", required=True)
    heat_sc.add_argument("--note", default="", help="What was soft-moderated")
    heat_sc.add_argument(
        "--apply",
        action="store_true",
        help="Write VO spice + sex SFX + music_energy into film-spec (still no still gen)",
    )

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
    sia = si_sub.add_parser(
        "approve-state",
        help="Register a human-approved local I2I wardrobe-state image; never calls a provider",
    )
    sia.add_argument("--root", required=True)
    sia.add_argument("--character-id", required=True)
    sia.add_argument("--wardrobe-state-id", required=True)
    sia.add_argument("--image", required=True)
    sia.add_argument("--reviewer", required=True)
    sia.add_argument("--review-note", required=True)
    sia.add_argument(
        "--generation-receipt",
        help="JSON receipt for this I2I generation; required for non-full states",
    )
    sipf = si_sub.add_parser(
        "approve-performance-state",
        help="Register a human-approved, hash-bound dialogue performance I2I still",
    )
    sipf.add_argument("--root", required=True)
    sipf.add_argument("--speaker", required=True)
    sipf.add_argument("--performance-state-id", required=True)
    sipf.add_argument("--image", required=True)
    sipf.add_argument("--generation-receipt", required=True)
    sipf.add_argument("--reviewer", required=True)
    sipf.add_argument("--review-note", required=True)
    sis = si_sub.add_parser(
        "contact-sheet",
        help="Render an offline visual review sheet for one wardrobe ladder; never calls a provider",
    )
    sis.add_argument("--root", required=True)
    sis.add_argument("--character-id", required=True)

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
    pk = pilot_sub.add_parser(
        "pack",
        help="Pilot GO pack: 3 shots + adult three-beat + heat/state → receipts/pilot-go.json",
    )
    pk.add_argument("--root", required=True)
    pk.add_argument("--shots", default="", help="Comma shot ids (default auto-pick)")
    ps = pilot_sub.add_parser(
        "score", help="Write receipts/pilot-scorecard.json (identity/style/motion)"
    )
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

    closeout = sub.add_parser(
        "closeout",
        help="Delivery ladder: heat → review-final gate → post-audit → optional export",
    )
    closeout_sub = closeout.add_subparsers(dest="closeout_action", required=True)
    cos = closeout_sub.add_parser("status", help="Read-only closeout ladder status")
    cos.add_argument("--root", required=True)
    cor = closeout_sub.add_parser(
        "run",
        help="Run automatable steps; stop at human review-final (never auto-approve)",
    )
    cor.add_argument("--root", required=True)
    cor.add_argument(
        "--export",
        action="store_true",
        help="After post-audit ok, emit export-desktop next_cmd (requires --name)",
    )
    cor.add_argument("--name", default=None, help="Desktop export folder name (with --export)")
    cor.add_argument(
        "--status-only",
        action="store_true",
        help="Do not run post-audit; status snapshot only",
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
    cpv.add_argument(
        "--no-export", action="store_true", help="Do not auto export-compose if missing"
    )
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
        "--post-owner",
        choices=["ffmpeg", "hyperframes", "remotion"],
        default=None,
        help="Create a missing post-plan with this owner (default follows --engine)",
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

    pp = sub.add_parser(
        "post-plan",
        help="Create or validate the editorial-to-HyperFrames/Remotion handoff",
    )
    pp.add_argument("--root", required=True)
    pp_sub = pp.add_subparsers(dest="post_plan_action", required=True)
    pp_init = pp_sub.add_parser("init", help="Write post-plan.json with one post owner")
    pp_init.add_argument(
        "--owner", choices=["ffmpeg", "hyperframes", "remotion"], default="hyperframes"
    )
    pp_init.add_argument("--edl", default=None, help="Workspace-relative video-use EDL path")
    pp_init.add_argument("--master-subtitles", default="out/final.srt")
    pp_init.add_argument("--audio-plan", default="sound-plan.json")
    pp_init.add_argument("--force", action="store_true")
    pp_validate = pp_sub.add_parser("validate", help="Validate post-plan.json")
    pp_validate.add_argument("--check-artifacts", action="store_true")
    pp_sub.add_parser("show", help="Print post-plan.json and its validation result")

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
            "frw ab catalog|plan|run|poll|rank|approve|status … | "
            "frw newvideo --model seedance-2-fast-i2v …"
        ),
    )
    frw.add_argument(
        "frw_argv",
        nargs=argparse.REMAINDER,
        help=(
            "Args passed to frw_dispatch.py. "
            "Examples: canary --root <film> ; "
            "ab catalog --root <film> ; "
            "newvideo --model seedance-2-fast-i2v --img-url … --wait"
        ),
    )

    manifest_cmd = sub.add_parser(
        "manifest", help="Preflight or explicitly migrate production manifest truth"
    )
    manifest_sub = manifest_cmd.add_subparsers(dest="manifest_action", required=True)
    manifest_preflight = manifest_sub.add_parser("preflight")
    manifest_preflight.add_argument("--root", required=True)
    manifest_migrate = manifest_sub.add_parser("migrate")
    manifest_migrate.add_argument("--root", required=True)
    manifest_migrate.add_argument(
        "--write", action="store_true", help="Persist only when migration preflight passes"
    )

    from cli_graph import add_graph_parsers

    add_graph_parsers(sub)

    director_p = sub.add_parser(
        "director",
        help=(
            "Production book: init|migrate-audit|migrate|status|check|lock-stage|"
            "impact|rebuild|verify"
        ),
    )
    director_sub = director_p.add_subparsers(dest="director_action", required=True)
    d_init = director_sub.add_parser("init")
    d_init.add_argument("--root", required=True)
    d_init.add_argument("--title", default="Untitled")
    d_init.add_argument(
        "--rigor", choices=("legacy", "guided", "professional"), default="professional"
    )
    d_init.add_argument("--format-pack", default="vertical-short")
    d_init.add_argument("--genre-pack", default="drama")
    d_init.add_argument(
        "--quality-target",
        choices=("standard", "premium_vertical"),
        default=None,
        help="Creative quality gate profile; legacy projects default to standard",
    )
    d_migrate_audit = director_sub.add_parser("migrate-audit")
    d_migrate_audit.add_argument("--root", required=True)
    d_migrate = director_sub.add_parser("migrate")
    d_migrate.add_argument("--root", required=True)
    d_migrate.add_argument("--title", default="Untitled")
    for director_action in ("status", "check", "verify"):
        action_parser = director_sub.add_parser(director_action)
        action_parser.add_argument("--root", required=True)
    serial_p = sub.add_parser("serial", help="Optional serial-drama narrative and safety gates")
    serial_sub = serial_p.add_subparsers(dest="serial_action", required=True)
    serial_validate = serial_sub.add_parser(
        "validate", help="Validate serial contract and write receipt"
    )
    serial_validate.add_argument("--root", required=True)
    d_lock_stage = director_sub.add_parser(
        "lock-stage",
        help="Human-approve and hash-lock the current stage over native evidence",
    )
    d_lock_stage.add_argument("--root", required=True)
    d_lock_stage.add_argument(
        "--stage",
        required=True,
        choices=(
            "concept_lock",
            "script_lock",
            "department_look_lock",
            "shot_animatic_lock",
            "pilot_approval",
            "bulk",
            "dailies_review",
            "selects_rough_cut",
            "picture_lock",
            "post_locks",
            "master_lock",
        ),
    )
    d_lock_stage.add_argument("--approver", default="user")
    lock_authorization = d_lock_stage.add_mutually_exclusive_group(required=True)
    lock_authorization.add_argument("--user-phrase")
    lock_authorization.add_argument("--authorization-event")
    d_lock_stage.add_argument(
        "--input-ref",
        action="append",
        default=[],
        metavar="NAME=RELATIVE_PATH",
        help="Override auto-resolved native evidence; repeat for multiple refs",
    )
    d_lock_stage.add_argument("--transaction-id", default=None)
    for director_action in ("impact", "rebuild"):
        action_parser = director_sub.add_parser(director_action)
        action_parser.add_argument("--root", required=True)
        action_parser.add_argument("--changed-ref", action="append", required=True)
        action_parser.add_argument("--reason", required=True)
        if director_action == "rebuild":
            action_parser.add_argument("--expected-revision", type=int, required=True)
            action_parser.add_argument("--transaction-id", default=None)

    department_p = sub.add_parser(
        "department",
        help="Department bibles: list|show|edit|diff|handoff|validate|lock|unlock|status",
    )
    department_sub = department_p.add_subparsers(dest="department_action", required=True)
    dept_list = department_sub.add_parser("list")
    dept_list.add_argument("--root", required=True)
    for department_action in ("show", "validate", "status"):
        action_parser = department_sub.add_parser(department_action)
        action_parser.add_argument("--root", required=True)
        action_parser.add_argument("--id", dest="department_id", required=True)
    dept_edit = department_sub.add_parser("edit")
    dept_edit.add_argument("--root", required=True)
    dept_edit.add_argument("--id", dest="department_id", required=True)
    dept_edit.add_argument("--payload-file", required=True)
    dept_edit.add_argument("--expected-revision", type=int, required=True)
    dept_edit.add_argument("--dry-run", action="store_true")
    dept_diff = department_sub.add_parser("diff")
    dept_diff.add_argument("--root", required=True)
    dept_diff.add_argument("--id", dest="department_id", required=True)
    dept_diff.add_argument("--payload-file", required=True)
    dept_handoff = department_sub.add_parser(
        "handoff", help="Verify immutable upstream bibles before a department starts work"
    )
    dept_handoff.add_argument("--root", required=True)
    dept_handoff.add_argument("--to", dest="department_id", required=True)
    dept_lock = department_sub.add_parser("lock")
    dept_lock.add_argument("--root", required=True)
    dept_lock.add_argument("--id", dest="department_id", required=True)
    dept_lock.add_argument("--approval-ref", required=True)
    dept_lock.add_argument("--expected-revision", type=int, required=True)
    dept_unlock = department_sub.add_parser("unlock")
    dept_unlock.add_argument("--root", required=True)
    dept_unlock.add_argument("--id", dest="department_id", required=True)
    dept_unlock.add_argument("--reason", required=True)
    dept_unlock.add_argument("--expected-revision", type=int, required=True)

    from cli_team import add_team_parsers

    add_team_parsers(sub)

    # Phase 2: Skill Registry shell
    skill_p = sub.add_parser("skill", help="Skill Registry: list|show|validate|run")
    skill_sub = skill_p.add_subparsers(dest="skill_action", required=True)
    sk_list = skill_sub.add_parser("list", help="List registered skills")
    sk_list.add_argument("--tag", default=None, help="Filter by tag")
    sk_list.add_argument("--phase", default=None, help="Filter by phase id (e.g. 1, 2)")
    sk_show = skill_sub.add_parser("show", help="Show one skill + contracts")
    sk_show.add_argument("--id", dest="id", required=True, help="skill_id e.g. image.animate")
    sk_validate = skill_sub.add_parser("validate", help="Validate runtime input/output envelope")
    sk_validate.add_argument("--skill-id", required=True)
    sk_validate.add_argument("--payload-file", required=True)
    sk_validate.add_argument("--direction", choices=("input", "output"), default="input")
    sk_run = skill_sub.add_parser("run", help="Run one fixed registry skill transaction")
    sk_run.add_argument("--skill-id", required=True)
    sk_run.add_argument("--payload-file", required=True)
    sk_run.add_argument("--dry-run", action="store_true")

    from cli_plan import add_plan_parsers

    add_plan_parsers(sub)
    from cli_longform import add_longform_parsers

    add_longform_parsers(sub)

    from cli_assets import add_assets_parsers

    add_assets_parsers(sub)

    from cli_workshop import add_workshop_parsers

    add_workshop_parsers(sub)

    from review_ui import add_review_ui_parsers

    add_review_ui_parsers(sub)
    from cli_interactive import add_interactive_parsers

    add_interactive_parsers(sub)

    from cli_comfy import add_comfy_parsers
    from cli_h3 import add_h3_parsers

    add_comfy_parsers(sub)
    add_h3_parsers(sub)
    from cli_node import add_node_parsers

    add_node_parsers(sub)
    from cli_weapon import add_weapon_parsers

    add_weapon_parsers(sub)
    from cli_bgm_library import add_bgm_library_parsers

    add_bgm_library_parsers(sub)
    from cli_route import add_route_parsers

    add_route_parsers(sub)

    from cli_workflow import add_workflow_parsers

    add_workflow_parsers(sub)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        # Every film-root plugin command refreshes the lightweight scene-sound
        # receipt before its own work. It never generates, downloads, or mutates
        # film-spec; write-spec repeats it after writing the new projection.
        if getattr(args, "root", None) and args.cmd != "external-review":
            root = Path(args.root).expanduser().resolve()
            if (root / "film-spec.json").is_file():
                from scene_sound import reconcile as reconcile_scene_sound

                reconcile_scene_sound(root, write=not bool(getattr(args, "no_write", False)))
        # Fast dispatch: simple one-command → one-handler (61 commands).
        # Inline branches below handle lazy imports / sub-actions.
        _SIMPLE_DISPATCH: dict[str, argparse.Namespace] = {
            "doctor": cmd_doctor,
            "lock-runtime": cmd_lock_runtime,
            "review-shot": cmd_review_shot,
            "review-contract": cmd_review_contract,
            "frw-lipsync": cmd_frw_lipsync,
            "env-plate": cmd_env_plate,
            "motion-plan": cmd_motion_plan,
            "i2v-motion-gate": cmd_i2v_motion_gate,
            "grok-oauth": cmd_grok_oauth,
            "dispatch": cmd_dispatch,
            "advance": cmd_advance,
            "autopilot": cmd_autopilot,
            "craft": cmd_craft,
            "selects": cmd_selects,
            "audio-plan": cmd_audio_plan,
            "audio-verify": cmd_audio_verify,
            "verify": cmd_verify,
            "audio-tts-render": cmd_audio_tts_render,
            "audio-produce": cmd_audio_produce,
            "audio-event": cmd_audio_event,
            "bgm-candidate": cmd_bgm_candidate,
            "bgm-library": cmd_bgm_library,
            "performance-candidate": cmd_performance_candidate,
            "adult-female-voice-pack": cmd_adult_female_voice_pack,
            "ambience-candidate": cmd_ambience_candidate,
            "sfx-canary": cmd_sfx_canary,
            "sfx-candidate": cmd_sfx_candidate,
            "sfx-library": cmd_sfx_library,
            "lipsync-node": cmd_lipsync_node,
            "lipsync-canary": cmd_lipsync_canary,
            "lipsync-pilot": cmd_lipsync_pilot,
            "lipsync-challenge": cmd_lipsync_challenge,
            "capability": cmd_capability,
            "tts-ab": cmd_tts_ab,
            "elevenlabs-canary": cmd_elevenlabs_canary,
            "init": cmd_init,
            "resume-manifest": cmd_resume_manifest,
            "status": cmd_status,
            "truth": cmd_truth,
            "quality-status": cmd_quality_status,
            "production-evidence": cmd_production_evidence,
            "stage": cmd_stage,
            "write-spec": cmd_write_spec,
            "lint-continuity": cmd_lint_continuity,
            "extract-frame": cmd_extract_frame,
            "continuity-chain": cmd_continuity_chain,
            "lock-style": cmd_lock_style,
            "style-lock": cmd_style_lock,
            "face-identity": cmd_face_identity,
            "register-still": cmd_register_still,
            "tts-rehearse": cmd_tts_rehearse,
            "register-clip": cmd_register_clip,
            "assemble": cmd_assemble,
            "ingest-footage": cmd_ingest_footage,
            "auto-cut": cmd_auto_cut,
            "shortform": cmd_shortform,
            "reencode-clips": cmd_reencode_clips,
            "final": cmd_final,
            "review-final": cmd_review_final,
            "final-editorial-review": cmd_final_editorial_review,
            "benchmark": cmd_benchmark,
            "dialogue-benchmark": cmd_dialogue_benchmark,
            "dialogue-benchmark-review": cmd_dialogue_benchmark_review,
            "dialogue-benchmark-approve": cmd_dialogue_benchmark_approve,
            "dialogue-production-plan": cmd_dialogue_production_plan,
            "visual-text-audit": cmd_visual_text_audit,
            "visual-text-repair": cmd_visual_text_repair,
            "dialogue-benchmark-queue": cmd_dialogue_benchmark_queue,
            "creative-pipeline": cmd_creative_pipeline,
            "dailies": cmd_dailies,
            "post-quality": cmd_post_quality,
            "provider-canary": cmd_provider_canary,
            "delivery-package": cmd_delivery_package,
            "quality-closure": cmd_quality_closure,
            "promotion-report": cmd_promotion_report,
            "director-notes": cmd_director_notes,
            "next": cmd_next,
            "preflight": cmd_preflight,
            "cinematic-audit": cmd_cinematic_audit,
            "quality": cmd_quality,
            "heat": cmd_heat,
            "state-index": cmd_state_index,
            "pilot": cmd_pilot,
            "closeout": cmd_closeout,
            "compose-preview": cmd_compose_preview,
            "export-compose": cmd_export_compose,
            "compose-render": cmd_compose_render,
            "post-plan": cmd_post_plan,
            "register-final": cmd_register_final,
            "export-desktop": cmd_export_desktop,
            "frw": cmd_frw,
            "manifest": cmd_manifest,
            "director": cmd_director,
            "serial": cmd_serial,
            "department": cmd_department,
            "plan": cmd_plan,
            "longform": cmd_longform,
            "assets": cmd_assets,
            "workshop": cmd_workshop,
            "review-ui": cmd_review_ui,
            "interactive": cmd_interactive,
            "usage": cmd_generation_usage,
            "metrics": cmd_metrics,
            "experiment": cmd_experiment,
            "gold": cmd_gold,
            "dashboard": cmd_dashboard,
            "optimization-program": cmd_optimization_program,
            "quality-ledger": cmd_quality_ledger,
            "production-report": cmd_production_report,
            "external-review": cmd_external_review,
            "vibevoice-asr": cmd_vibevoice_asr,
            "speech-preview": cmd_speech_preview,
            "comfy": cmd_comfy,
            "h3": cmd_h3,
            "node": cmd_node,
            "weapon": cmd_weapon,
            "route": cmd_route,
            "team": cmd_team,
            # closeout → cmd_closeout (closeout.py). pilot pack → cmd_pilot.
            "pilot-pack": cmd_workflow,
            "bulk-preflight": cmd_workflow,
            "variety-precheck": cmd_workflow,
            "select-shortlist": cmd_workflow,
            "gpu-lease": cmd_workflow,
            "tunnel-probe": cmd_workflow,
            "queue-progress": cmd_workflow,
            "agent-review-final": cmd_workflow,
        }
        handler = _SIMPLE_DISPATCH.get(args.cmd)
        if handler is not None:
            return handler(args)

        if args.cmd == "local-llm":
            from local_llm import LocalLLMError
            from local_llm import draft as local_llm_draft
            from local_llm import probe as local_llm_probe
            from local_llm import shot_draft as local_llm_shot_draft

            try:
                token = os.environ.get("AIFILM_LOCAL_LLM_TOKEN") or None
                if args.local_llm_action == "probe":
                    report = local_llm_probe(args.base_url, model=args.model, token=token)
                elif args.local_llm_action == "draft":
                    report = local_llm_draft(
                        args.base_url,
                        model=args.model,
                        prompt=args.prompt,
                        token=token,
                        timeout=args.timeout,
                    )
                else:
                    report = local_llm_shot_draft(
                        args.base_url,
                        model=args.model,
                        prompt=args.prompt,
                        token=token,
                        timeout=args.timeout,
                    )
            except LocalLLMError as exc:
                raise FilmError(f"{exc.code}: {exc}") from exc
            emit(report)
            return 0 if report.get("ok", True) else 2

        if args.cmd == "local-omni-review":
            from local_omni_review import LocalOmniReviewError
            from local_omni_review import probe as local_omni_probe
            from local_omni_review import review_frames as local_omni_review_frames

            try:
                token = os.environ.get("AIFILM_LOCAL_OMNI_TOKEN") or None
                if args.local_omni_review_action == "probe":
                    report = local_omni_probe(args.base_url, model=args.model, token=token)
                else:
                    report = local_omni_review_frames(
                        args.root,
                        args.base_url,
                        frame_index=args.frame_index,
                        model=args.model,
                        token=token,
                        sanitized=bool(args.sanitized),
                        timeout=args.timeout,
                    )
            except LocalOmniReviewError as exc:
                raise FilmError(f"LOCAL_OMNI_REVIEW_ERROR: {exc}") from exc
            emit(report)
            return 0 if report.get("ok", True) else 2

        if args.cmd == "semantic-index":
            from semantic_index import SemanticIndexError, build_index, query_index

            try:
                token = os.environ.get("AIFILM_LOCAL_EMBEDDING_TOKEN") or None
                if args.semantic_index_action == "build":
                    report = build_index(
                        args.root,
                        args.base_url,
                        model=args.model,
                        token=token,
                        timeout=args.timeout,
                    )
                else:
                    report = query_index(
                        args.root,
                        args.base_url,
                        model=args.model,
                        query=args.query,
                        limit=args.limit,
                        token=token,
                        timeout=args.timeout,
                    )
            except SemanticIndexError as exc:
                raise FilmError(f"SEMANTIC_INDEX_ERROR: {exc}") from exc
            emit(report)
            return 0

        if args.cmd == "narrative-evidence":
            from narrative_evidence import (
                NarrativeEvidenceError,
                init_narrative_evidence,
                record_narrative_evidence,
                validate_narrative_evidence,
            )

            root = Path(args.root).expanduser().resolve()
            try:
                if args.narrative_evidence_action == "init":
                    report = init_narrative_evidence(root)
                elif args.narrative_evidence_action == "record":
                    report = record_narrative_evidence(
                        root,
                        evidence_id=args.evidence_id,
                        status=args.status,
                        shot_id=args.shot_id,
                        start_sec=args.start_sec,
                        end_sec=args.end_sec,
                        media_path=args.media_path,
                        reviewer=args.reviewer,
                        user_phrase=args.user_phrase,
                        note=args.note,
                    )
                else:
                    report = validate_narrative_evidence(root, require_verified=True)
            except NarrativeEvidenceError as exc:
                report = {"ok": False, "issues": [{"code": exc.code, "message": str(exc)}]}
            emit(report)
            return 0 if report.get("ok", True) else 1
        if args.cmd == "post-audit":
            from post_audit import audit

            report = audit(Path(args.root).expanduser().resolve())
            emit(report)
            return 0 if report.get("delivery_ready") else 1
        if args.cmd == "caption-frame-audit":
            from caption_frame_audit import build_caption_frame_audit

            emit(build_caption_frame_audit(Path(args.root), max_frames=args.max_frames))
            return 0
        if args.cmd == "transition-frame-audit":
            from transition_frame_audit import build_transition_frame_audit

            emit(build_transition_frame_audit(Path(args.root)))
            return 0
        if args.cmd == "transition-frame-review-template":
            from transition_frame_audit import build_transition_review_template

            emit(build_transition_review_template(Path(args.root)))
            return 0
        if args.cmd == "transition-frame-attest":
            from transition_frame_audit import attest_transition_review

            emit(
                attest_transition_review(
                    Path(args.root),
                    user_phrase=args.user_phrase,
                    decisions_path=Path(args.decisions) if args.decisions else None,
                )
            )
            return 0
        if args.cmd == "caption-frame-attest":
            from caption_frame_audit import attest_caption_readability

            emit(attest_caption_readability(Path(args.root), user_phrase=args.user_phrase))
            return 0
        if args.cmd == "bible":
            root = Path(args.root).expanduser().resolve()
            if args.bible_cmd == "init":
                from visual_bible import load_bible, save_bible

                bible = load_bible(root)
                save_bible(root, bible)
                emit({"ok": True, "msg": "Visual Bible initialized/migrated to v2"})
            elif args.bible_cmd == "lock":
                from visual_bible import update_bible_state

                update_bible_state(root, "Approved")
                emit({"ok": True, "msg": "Visual Bible locked (Approved)"})
            elif args.bible_cmd == "state":
                from visual_bible import update_bible_state

                update_bible_state(root, args.set)
                emit({"ok": True, "msg": f"Visual Bible state updated to {args.set}"})
            return 0
        if args.cmd == "performance-timeline":
            from performance_timeline import build_performance_timeline

            report = build_performance_timeline(Path(args.root))
            emit(report)
            return 0 if report["ok"] else 2
        if args.cmd == "speech-performance-timing":
            from speech_performance_timing import build_speech_performance_timing

            report = build_speech_performance_timing(Path(args.root))
            emit(report)
            return 0 if report["ok"] else 2
        if args.cmd == "audio-provenance":
            from audio_provenance import build_audio_provenance

            report = build_audio_provenance(Path(args.root))
            emit(report)
            return 0 if report["ok"] else 2
        if args.cmd == "subtitle-dialogue-alignment":
            from subtitle_dialogue_alignment import build_subtitle_dialogue_alignment

            report = build_subtitle_dialogue_alignment(Path(args.root))
            emit(report)
            return 0 if report["ok"] else 2
        if args.cmd == "subtitle-cut-boundaries":
            from subtitle_cut_boundaries import build_subtitle_cut_boundaries

            report = build_subtitle_cut_boundaries(Path(args.root))
            emit(report)
            return 0 if report["ok"] else 2
        if args.cmd == "quality-check":
            from quality_check_video import QualityCheckError, run_quality_check

            out_dir = args.out
            if not out_dir and args.root:
                out_dir = str(Path(args.root).expanduser().resolve() / "out")
            try:
                report = run_quality_check(
                    args.video,
                    out_dir=out_dir,
                    expect_audio=args.expect_audio,
                    expect_subtitles=args.expect_subtitles,
                    srt=args.srt,
                    min_score=args.min_score,
                    allow_black=args.allow_black,
                    allow_freeze=args.allow_freeze,
                )
            except QualityCheckError as exc:
                raise FilmError(str(exc)) from exc
            emit(report)
            return 0 if report["passed"] else 1
        if args.cmd == "review-pack":
            from review_pack import (
                ReviewPackError,
                build_review_pack,
                comfy_download_target,
                ensure_review_pack_available,
            )

            supplied = [bool(args.source), bool(args.comfy_filename)]
            if sum(supplied) != 1:
                raise FilmError("review-pack requires exactly one of --source or --comfy-filename")
            root = Path(args.root).expanduser().resolve()
            source = Path(args.source).expanduser() if args.source else None
            download = None
            if args.comfy_filename:
                from comfy_armory import ComfyArmoryError, default_base_url
                from comfy_video import ComfyVideoError, download_result

                try:
                    ensure_review_pack_available(root, pack_id=args.id)
                    base_url = args.comfy_base_url or default_base_url()
                    source = comfy_download_target(
                        root, pack_id=args.id, filename=args.comfy_filename
                    )
                    download = download_result(
                        base_url,
                        {
                            "filename": args.comfy_filename,
                            "subfolder": args.comfy_subfolder,
                            "type": args.comfy_type,
                        },
                        source,
                    )
                except (
                    ComfyArmoryError,
                    ComfyVideoError,
                    ReviewPackError,
                    SecurityPolicyError,
                ) as exc:
                    raise FilmError(str(exc)) from exc
            try:
                report = build_review_pack(
                    root,
                    pack_id=args.id,
                    source=source,
                    expect_audio=args.expect_audio,
                    download=download,
                )
            except (ReviewPackError, ValueError) as exc:
                raise FilmError(str(exc)) from exc
            emit(report)
            return 0 if report["ok"] else 1
        if args.cmd == "analyze-reference":
            from reference_audit import ReferenceAuditError, run_reference_audit

            out_dir = args.out
            if not out_dir and args.root:
                out_dir = str(Path(args.root).expanduser().resolve() / "reference-analysis")
            try:
                report = run_reference_audit(args.video, out_dir=out_dir, frames=args.frames)
            except ReferenceAuditError as exc:
                raise FilmError(str(exc)) from exc
            emit(report)
            return 0
        if args.cmd == "brief":
            from product_brief import ProductBriefError, expand_product_brief, save_product_brief

            text = args.text
            if not text and args.file:
                text = Path(args.file).expanduser().resolve().read_text(encoding="utf-8")
            if not text:
                raise FilmError("brief expand requires --text or --file")
            try:
                packet = expand_product_brief(
                    text,
                    title=args.title,
                    target_duration=args.target_duration,
                    voice_style=args.voice_style,
                    language=args.language,
                )
            except ProductBriefError as exc:
                raise FilmError(str(exc)) from exc
            path = save_product_brief(args.root, packet)
            packet["receipt_path"] = str(path)
            emit(packet)
            return 0
        if args.cmd == "director-ledger":
            from director_ledger import build_director_ledger

            emit(build_director_ledger(Path(args.root)))
            return 0
        if args.cmd == "planning-autopilot":
            from planning_autopilot import build_planning_autopilot

            emit(build_planning_autopilot(Path(args.root)))
            return 0
        if args.cmd == "planning-answer":
            from planning_autopilot import apply_authoring_answers

            try:
                answers = json.loads(args.answers_json)
            except json.JSONDecodeError as exc:
                raise FilmError(f"--answers-json must be valid JSON: {exc}") from exc
            if not isinstance(answers, list):
                raise FilmError("--answers-json must be a JSON list")
            emit(
                apply_authoring_answers(
                    Path(args.root),
                    answers,
                    dry_run=bool(args.dry_run),
                    expected_transaction_id=args.expected_transaction_id,
                )
            )
            return 0
        if args.cmd == "planning-history":
            from planning_autopilot import planning_history_summary

            emit(planning_history_summary(Path(args.root)))
            return 0
        if args.cmd == "prompt-budget":
            from prompt_budget import prompt_budget_report

            emit(
                prompt_budget_report(
                    Path(args.root),
                    write=bool(args.write),
                    max_estimated_tokens=args.max_estimated_tokens,
                )
            )
            return 0
        if args.cmd == "prompt-compression-pilot":
            from prompt_compression_pilot import build_prompt_compression_pilot

            candidate_path = safe_existing_file(
                Path(args.root), args.candidate_json, field="prompt-compression candidate JSON"
            )
            candidate = read_json(candidate_path)
            if not isinstance(candidate, dict):
                raise FilmError("--candidate-json must be a JSON object")
            emit(build_prompt_compression_pilot(Path(args.root), candidate))
            return 0
        if args.cmd == "prompt-compression-attest":
            from prompt_compression_pilot import attest_prompt_compression_pilot

            evidence_path = safe_existing_file(
                Path(args.root), args.evidence_json, field="prompt-compression evidence JSON"
            )
            evidence = read_json(evidence_path)
            if not isinstance(evidence, dict):
                raise FilmError("--evidence-json must be a JSON object")
            emit(
                attest_prompt_compression_pilot(
                    Path(args.root), evidence, user_phrase=args.user_phrase
                )
            )
            return 0
        if args.cmd == "beat-evidence":
            from beat_action_evidence import build_beat_action_evidence

            report = build_beat_action_evidence(Path(args.root))
            emit(report)
            return 0 if report["ok"] else 2
        if args.cmd == "editor-cut":
            from editor_cut import build_editor_cut_report

            report = build_editor_cut_report(Path(args.root))
            emit(report)
            return 0 if report["ok"] else 2
        if args.cmd == "audio-visual":
            from audio_visual_alignment import build_audio_visual_alignment

            report = build_audio_visual_alignment(Path(args.root))
            emit(report)
            return 0 if report["ok"] else 2
        if args.cmd == "graph":
            # allow --no-derive to flip auto_derive off for status
            if getattr(args, "graph_action", None) == "status" and bool(
                getattr(args, "no_derive", False)
            ):
                args.derive_if_missing = False
            return cmd_graph(args)
        if args.cmd == "skill":
            if args.skill_action == "run":
                from skill_runner import run_skill

                report = run_skill(args.skill_id, args.payload_file, dry_run=bool(args.dry_run))
                emit(report)
                return 0 if report.get("ok") else 2
            return cmd_skill(args)
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
