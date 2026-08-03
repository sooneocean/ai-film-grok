#!/usr/bin/env python3
"""Render HyperFrames / Remotion designed-post packages and register final_film.

Pipeline (HyperFrames):
  export-compose (optional) → check → render → audio mux → QA → register (post_engine=hyperframes)

Remotion:
  media-copy always; auto remotion render+register when node_modules ready;
  otherwise ok=false, rendered=false + exact next_steps (not silent success).

Optional --require-preview: need receipts/compose-preview.json from compose-preview.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from logger import log
from media_probe import run_media_to_output
from media_qa import MediaQAError, analyze_media
from runtime_policy import sha256
from security_policy import (
    SecurityPolicyError,
    minimal_subprocess_env,
    reject_symlinks,
    safe_existing_file,
    safe_output_path,
    safe_workspace_directory,
)
from util import read_json as _util_read_json
from util import utc_now, write_json

SCHEMA_VERSION = 1


class ComposeRenderError(RuntimeError):
    """User-facing compose render error."""


def read_json(path: Path) -> dict[str, Any]:
    """Strict read_json — raises ComposeRenderError on missing (unlike util.read_json's None)."""
    data = _util_read_json(path)
    if data is None:
        raise ComposeRenderError(f"Missing JSON: {path}")
    return data


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    env = minimal_subprocess_env()
    # hyperframes/npx need PATH + HOME; keep minimal but usable
    for key in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "NODE_PATH", "npm_config_cache"):
        if key in os.environ:
            env[key] = os.environ[key]
    # Allow npx network cache under user home
    if "HOME" in env:
        env.setdefault("npm_config_cache", str(Path(env["HOME"]) / ".npm"))
    argv = list(cmd)
    if argv and Path(argv[0]).name == "ffmpeg" and "-nostdin" not in argv:
        argv.insert(1, "-nostdin")
    return subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        check=check,
        capture_output=True,
        text=True,
        env=env,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
    )


def which_npx() -> str | None:
    return shutil.which("npx")


def probe_designed_post_tooling() -> dict[str, Any]:
    """Non-blocking readiness for HyperFrames designed-post path."""
    npx = which_npx()
    node = shutil.which("node")
    info: dict[str, Any] = {
        "npx": npx,
        "node": node,
        "hyperframes_ok": False,
        "hyperframes_version": None,
        "error": None,
    }
    if not npx:
        info["error"] = "npx missing — install Node.js 22+ for --post-engine hyperframes"
        return info
    try:
        proc = run([npx, "--yes", "hyperframes", "--version"], check=False, timeout=120)
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        # e.g. "hyperframes v0.7.60" or just "0.7.60"
        ver = None
        for token in out.replace("\n", " ").split():
            if token[0].isdigit() or (
                token.startswith("v") and len(token) > 1 and token[1].isdigit()
            ):
                ver = token.lstrip("v")
                break
        info["hyperframes_version"] = ver or (out[:80] if out else None)
        info["hyperframes_ok"] = proc.returncode == 0
        if proc.returncode != 0:
            info["error"] = (proc.stderr or proc.stdout or "hyperframes --version failed")[:300]
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired) as exc:
        info["error"] = str(exc)[:300]
    return info


def probe_remotion_readiness(root: Path) -> dict[str, Any]:
    """Whether compose/remotion can auto-render (deps installed + Root + Film).

    Scaffold package.json alone is not enough — node_modules must exist.
    """
    rem = root / "compose" / "remotion"
    info: dict[str, Any] = {
        "dir": str(rem),
        "package_json": False,
        "has_npm_deps_declared": False,
        "node_modules": False,
        "remotion_cli": False,
        "root_tsx": False,
        "film_tsx": False,
        "media_copy_plan": False,
        "npx": which_npx(),
        "ready": False,
        "missing": [],
    }
    if not rem.is_dir():
        info["missing"].append("compose/remotion/ — run export-compose --engine remotion|both")
        return info

    pkg = rem / "package.json"
    info["package_json"] = pkg.is_file()
    if pkg.is_file():
        try:
            data = read_json(pkg)
            deps = {}
            if isinstance(data.get("dependencies"), dict):
                deps.update(data["dependencies"])
            if isinstance(data.get("devDependencies"), dict):
                deps.update(data["devDependencies"])
            info["has_npm_deps_declared"] = bool("remotion" in deps or "@remotion/cli" in deps)
        except ComposeRenderError:
            info["has_npm_deps_declared"] = False

    nm = rem / "node_modules"
    info["node_modules"] = nm.is_dir()
    remotion_bin = nm / ".bin" / "remotion"
    remotion_pkg = nm / "remotion"
    remotion_cli = nm / "@remotion" / "cli"
    info["remotion_cli"] = remotion_bin.is_file() or remotion_pkg.is_dir() or remotion_cli.is_dir()

    info["root_tsx"] = (rem / "src" / "Root.tsx").is_file()
    info["film_tsx"] = (rem / "src" / "Film.tsx").is_file()
    info["media_copy_plan"] = (rem / "media-copy-plan.json").is_file()

    missing: list[str] = []
    if not info["package_json"]:
        missing.append("package.json")
    if not info["has_npm_deps_declared"]:
        missing.append("package.json remotion dependencies")
    if not info["node_modules"] or not info["remotion_cli"]:
        missing.append("node_modules (run: cd compose/remotion && npm install)")
    if not info["root_tsx"]:
        missing.append("src/Root.tsx")
    if not info["film_tsx"]:
        missing.append("src/Film.tsx")
    if not info["media_copy_plan"]:
        missing.append("media-copy-plan.json")
    if not info["npx"]:
        missing.append("npx on PATH")
    info["missing"] = missing
    info["ready"] = len(missing) == 0
    return info


def remotion_actionable_next_steps(root: Path, *, rem_dir: Path | None = None) -> list[str]:
    """Short bootstrap → render → register steps (keywords kept for tests/agents)."""
    root_s = str(root)
    rem = rem_dir or (root / "compose" / "remotion")
    rem_s = str(rem)
    return [
        f'1. One-shot (network once): "$AIFILM" final --root "{root_s}" '
        f"--post-engine remotion --npm-install --tts-backend edge --music-mood rnb",
        f'2. Or compose-render: "$AIFILM" compose-render --root "{root_s}" '
        f"--engine remotion --npm-install  # media-copy + npm install + remotion render + register",
        f'3. Deps already installed: "$AIFILM" compose-render --root "{root_s}" --engine remotion',
        f'4. Manual: cd "{rem_s}" && npm install && npx remotion render src/index.ts Film '
        f"out/film_remotion.mp4",
        f'5. Register: "$AIFILM" register-final --root "{root_s}" '
        f'--source "{rem_s}/out/film_remotion.mp4" --post-engine remotion',
        f'6. Prefer HyperFrames one-shot: "$AIFILM" final --root "{root_s}" --post-engine hyperframes',
    ]


def plate_subtitles_burned_in(root: Path) -> bool | None:
    """Read out/final-delivery.json subtitles.burned_in. None if unknown."""
    path = root / "out" / "final-delivery.json"
    if not path.is_file():
        return None
    try:
        data = read_json(path)
    except ComposeRenderError:
        return None
    subs = data.get("subtitles") if isinstance(data.get("subtitles"), dict) else {}
    if "burned_in" not in subs:
        return None
    return bool(subs.get("burned_in"))


def assert_underlay_not_double_burn(
    root: Path,
    *,
    layout: str,
    allow_burned_underlay: bool = False,
) -> dict[str, Any]:
    """Hard gate: underlay + FFmpeg burned captions = double-burn disaster.

    Staged contract (final_stages.py · 2026-07-23):
      stage_plate  → always --subs off for designed-post (no assume captions)
      stage_hf     → HyperFrames owns designed captions
      stage_caption→ verify pixels; pil_recovery is explicit, never assumed
    Hand path final (burn) → export underlay → compose still double-burns.
    """
    layout_l = (layout or "auto").strip().lower()
    if allow_burned_underlay:
        return {"ok": True, "skipped": True, "reason": "allow_burned_underlay"}
    # Resolve auto like export: final present → underlay risk surface
    has_final = (root / "out" / "film_final.mp4").is_file()
    effective = layout_l
    if layout_l == "auto":
        effective = "underlay" if has_final else "multiclip"
    if effective != "underlay":
        return {"ok": True, "layout": effective, "burned_in": plate_subtitles_burned_in(root)}

    burned = plate_subtitles_burned_in(root)
    if burned is True:
        raise ComposeRenderError(
            "underlay double-burn blocked: out/final-delivery.json has "
            "subtitles.burned_in=true (FFmpeg already burned captions). "
            "Re-run final with --subs off (or --post-engine hyperframes|remotion), "
            "or pass --allow-burned-underlay to override, or use layout=multiclip."
        )
    return {"ok": True, "layout": effective, "burned_in": burned}


def which_npm() -> str | None:
    return shutil.which("npm")


def remotion_npm_install(
    rem_dir: Path,
    *,
    timeout: int = 900,
    npm_bin: str | None = None,
) -> dict[str, Any]:
    """Explicit npm install in compose/remotion (network; never silent).

    Called only when compose-render --npm-install is set. Failures raise with
    actionable next_steps — do not invent a rendered MP4.
    """
    rem_dir = rem_dir.expanduser().resolve()
    pkg = rem_dir / "package.json"
    if not pkg.is_file():
        raise ComposeRenderError(
            f"remotion npm install: missing {pkg} — run export-compose --engine remotion first"
        )
    npm = npm_bin or which_npm()
    if not npm:
        raise ComposeRenderError(
            "npm not found on PATH — install Node.js 22+, or run without --npm-install "
            f'and manually: cd "{rem_dir}" && npm install'
        )

    env = minimal_subprocess_env()
    for key in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "NODE_PATH", "npm_config_cache"):
        if key in os.environ:
            env[key] = os.environ[key]
    if "HOME" in env:
        env.setdefault("npm_config_cache", str(Path(env["HOME"]) / ".npm"))

    cmd = [npm, "install", "--no-fund", "--no-audit"]
    log(f"npm install (remotion) → {rem_dir}")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(rem_dir),
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ComposeRenderError(
            f"npm install timed out after {timeout}s in {rem_dir}. "
            "Retry with network, or install manually then compose-render without --npm-install."
        ) from exc
    except OSError as exc:
        raise ComposeRenderError(f"npm install failed to start: {exc}") from exc

    log_text = ((proc.stdout or "") + (proc.stderr or ""))[-4000:]
    if proc.returncode != 0:
        raise ComposeRenderError(
            "npm install failed (network/version/permissions). "
            f"exit={proc.returncode} cwd={rem_dir}\n"
            f"{log_text[-1500:]}\n"
            f'Manual: cd "{rem_dir}" && npm install\n'
            "Then: aifilm compose-render --root … --engine remotion\n"
            "Or prefer: aifilm final --post-engine hyperframes"
        )
    return {
        "ok": True,
        "cwd": str(rem_dir),
        "cmd": cmd,
        "returncode": proc.returncode,
        "log_tail": log_text[-800:],
    }


def remotion_render(
    rem_dir: Path,
    output: Path,
    *,
    composition_id: str = "Film",
    entry: str = "src/index.ts",
    timeout: int = 3600,
) -> dict[str, Any]:
    """Run remotion render when package is bootstrapped (prefer local .bin).

    CLI form: remotion render <entry> <composition-id> <output>
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    entry_path = rem_dir / entry
    if not entry_path.is_file():
        # older scaffolds without explicit entry still try composition-only form
        entry_arg: list[str] = []
    else:
        entry_arg = [entry]
    local_bin = rem_dir / "node_modules" / ".bin" / "remotion"
    if local_bin.is_file():
        cmd = [str(local_bin), "render", *entry_arg, composition_id, str(output)]
    else:
        npx = which_npx()
        if not npx:
            raise ComposeRenderError("npx not found — install Node.js for Remotion render")
        cmd = [npx, "remotion", "render", *entry_arg, composition_id, str(output)]
    log(f"remotion render {' '.join(entry_arg + [composition_id])} → {output}")
    env = minimal_subprocess_env()
    for key in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "NODE_PATH", "npm_config_cache"):
        if key in os.environ:
            env[key] = os.environ[key]
    if "HOME" in env:
        env.setdefault("npm_config_cache", str(Path(env["HOME"]) / ".npm"))
    # Ensure local node_modules/.bin is first on PATH
    nm_bin = rem_dir / "node_modules" / ".bin"
    if nm_bin.is_dir():
        env["PATH"] = str(nm_bin) + os.pathsep + env.get("PATH", "")

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(rem_dir),
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ComposeRenderError(f"remotion render timed out after {timeout}s") from exc
    log_text = ((proc.stdout or "") + (proc.stderr or ""))[-4000:]
    if proc.returncode != 0 or not output.is_file() or output.stat().st_size < 100:
        raise ComposeRenderError(
            "remotion render failed: " + (log_text or f"exit {proc.returncode}")
        )
    return {
        "ok": True,
        "output": str(output),
        "bytes": output.stat().st_size,
        "composition_id": composition_id,
        "log_tail": log_text[-500:],
    }


def probe_has_audio(path: Path) -> bool:
    try:
        proc = run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                str(path),
            ],
            check=False,
        )
        return "audio" in (proc.stdout or "").lower()
    except (OSError, subprocess.SubprocessError):
        return False


def pdur(path: Path) -> float:
    """Fail-loud duration probe — never invent silent defaults on missing media."""
    try:
        from media_duration import MediaDurationError, probe_duration_sec
    except ImportError:
        p = Path(path)
        if not p.is_file():
            raise RuntimeError(f"media missing for duration probe: {p}") from None
        proc = run(
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
        raw = (proc.stdout or "").strip()
        if not raw:
            raise RuntimeError(f"unreadable duration (empty ffprobe): {path}") from None
        return float(raw)
    try:
        return probe_duration_sec(path, label="compose_render")
    except MediaDurationError as exc:
        raise RuntimeError(str(exc)) from exc


def copy_remotion_media(root: Path) -> dict[str, Any]:
    """Execute media-copy-plan.json into compose/remotion/public/.

    Fail-closed: every plan item must copy; partial success is not ok.
    """
    rem = root / "compose" / "remotion"
    plan_path = rem / "media-copy-plan.json"
    if not plan_path.is_file():
        raise ComposeRenderError(
            "compose/remotion/media-copy-plan.json missing — run export-compose first"
        )
    plan = read_json(plan_path)
    items = plan.get("items") if isinstance(plan.get("items"), list) else []
    if not items:
        raise ComposeRenderError("media-copy-plan.json has no items — re-run export-compose")
    public = rem / "public"
    public.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, str]] = []
    errors: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            errors.append(f"invalid plan item: {item!r}")
            continue
        from_rel = item.get("from_film_rel")
        to_public = item.get("to_public")
        if not isinstance(from_rel, str) or not isinstance(to_public, str):
            errors.append(f"plan item missing from/to: {item!r}")
            continue
        try:
            src = safe_existing_file(root, from_rel, field=f"remotion source {from_rel}")
            dest = (public / to_public).resolve()
            dest.relative_to(public.resolve())
        except (SecurityPolicyError, ValueError) as exc:
            errors.append(f"{from_rel} → {to_public}: {exc}")
            continue
        except ComposeRenderError as exc:
            errors.append(str(exc))
            continue
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied.append({"from": from_rel, "to": str(dest.relative_to(rem.resolve()))})
        except OSError as exc:
            errors.append(f"copy failed {from_rel}: {exc}")
    write_json(
        rem / "media-copy-receipt.json",
        {
            "copied_at": utc_now(),
            "count": len(copied),
            "planned": len(items),
            "items": copied,
            "errors": errors,
        },
    )
    if errors or len(copied) != len(items):
        raise ComposeRenderError(
            f"remotion media-copy incomplete: {len(copied)}/{len(items)} ok; errors={errors[:5]}"
        )
    return {"ok": True, "count": len(copied), "items": copied, "planned": len(items)}


def probe_mean_volume_db(path: Path, *, sample_sec: float = 12.0) -> float | None:
    """Rough loudness probe via ffmpeg volumedetect. None if unavailable."""
    try:
        proc = run(
            [
                "ffmpeg",
                "-hide_banner",
                "-ss",
                "1",
                "-t",
                str(max(2.0, float(sample_sec))),
                "-i",
                str(path),
                "-af",
                "volumedetect",
                "-f",
                "null",
                "-",
            ],
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stderr or "") + (proc.stdout or "")
    mean = None
    for line in text.splitlines():
        if "mean_volume:" in line:
            # e.g. [Parsed_volumedetect_0 @ …] mean_volume: -22.9 dB
            try:
                part = line.split("mean_volume:", 1)[1].strip().split()[0]
                mean = float(part)
            except (IndexError, ValueError):
                continue
    return mean


def _preferred_mix_audio_sources(root: Path) -> list[Path]:
    """Production VO+BGM mix first (designed-post picture should not ship native clip hum)."""
    ordered: list[Path] = []
    for rel in (
        "audio/mixed.wav",  # final pipeline: VO + ducked BGM
        "out/_final_work/mixed.wav",
        "out/film_final.mp4",  # full plate audio
        "out/film_final_audio_src.mp4",
    ):
        p = root / rel
        if p.is_file():
            ordered.append(p)
    return ordered


def _designed_post_effects(root: Path) -> list[tuple[Path, float, float]]:
    """Return generated designed-post stings with their verified clock placement."""
    receipt = root / "compose" / "hyperframes" / "media-stage-receipt.json"
    if not receipt.is_file():
        return []
    try:
        data = read_json(receipt)
    except ComposeRenderError:
        return []
    cues = data.get("cinematic_audio_cues")
    if not isinstance(cues, list):
        return []
    effects: list[tuple[Path, float, float]] = []
    volume_by_id = {"suspense-intro": 0.16, "suspense-outro": 0.12}
    media_dir = receipt.parent / "media"
    for cue in cues:
        if not isinstance(cue, dict):
            continue
        cue_id = str(cue.get("id") or "")
        if cue_id not in volume_by_id:
            continue
        path = media_dir / f"{cue_id}.wav"
        try:
            start = float(cue.get("start_sec"))
        except (TypeError, ValueError):
            continue
        if path.is_file() and not path.is_symlink() and start >= 0:
            effects.append((path, start, volume_by_id[cue_id]))
    return effects


def _ffmpeg_mux_video_with_audio(
    video: Path,
    audio_src: Path,
    out: Path,
    *,
    effects: list[tuple[Path, float, float]] | None = None,
) -> None:
    effects = effects or []
    command = ["ffmpeg", "-y", "-i", str(video), "-i", str(audio_src)]
    filter_inputs = ["[1:a]volume=1[base]"]
    mix_inputs = ["[base]"]
    for index, (effect, start, volume) in enumerate(effects, start=2):
        command.extend(["-i", str(effect)])
        label = f"fx{index}"
        delay_ms = max(0, int(round(start * 1000)))
        filter_inputs.append(f"[{index}:a]adelay={delay_ms}:all=1,volume={volume}[{label}]")
        mix_inputs.append(f"[{label}]")
    if effects:
        filter_inputs.append(
            f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=0[mixed]"
        )
    command.extend(
        [
            "-filter_complex",
            ";".join(filter_inputs),
            "-map",
            "0:v:0",
            "-map",
            "[mixed]" if effects else "[base]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-shortest",
            str(out),
        ]
    )
    run_media_to_output(
        command,
        out,
        timeout=600,
        min_bytes=1000,
    )


def _audio_video_clock_ok(
    video: Path,
    audio_src: Path,
    *,
    max_skew_sec: float = 0.75,
) -> tuple[bool, float, float, float]:
    """Return (ok, video_dur, audio_dur, skew). Reject hard clock skew that desyncs VO/subs."""
    try:
        v = float(pdur(video))
        a = float(pdur(audio_src))
    except Exception:
        return False, 0.0, 0.0, 999.0
    skew = abs(v - a)
    return skew <= max_skew_sec, v, a, skew


def ensure_audio_mux(
    video: Path,
    root: Path,
    out: Path,
) -> dict[str, Any]:
    """Attach production VO/BGM mix to designed-post video.

    Prefer audio/mixed.wav (final pipeline) over quiet native I2V hum **only when
    durations match the picture clock**. Muxing a 69s plate mix onto a 62s underlay
    (or the reverse) silently desyncs VO vs burned/designed captions.

    Passthrough only when no mix stems exist and video already has usable loudness.
    """
    preferred = _preferred_mix_audio_sources(root)
    effects = _designed_post_effects(root)
    # Use production mix when present — even if video has a silent-ish audio track
    # (Remotion/HF often inherit near-silent clip audio → mean ~-50dB).
    for audio_src in preferred:
        if audio_src.suffix.lower() in {".wav", ".mp3", ".m4a", ".aac"} or probe_has_audio(
            audio_src
        ):
            ok_clock, v_dur, a_dur, skew = _audio_video_clock_ok(video, audio_src)
            if not ok_clock:
                log(
                    f"skip mux {audio_src.name}: duration skew {skew:.2f}s "
                    f"(video={v_dur:.2f}s audio={a_dur:.2f}s) — would desync VO/subs; "
                    f"re-run final so plate+mix share one clock"
                )
                continue
            try:
                _ffmpeg_mux_video_with_audio(video, audio_src, out, effects=effects)
            except (ComposeRenderError, subprocess.CalledProcessError, OSError) as exc:
                log(f"mux from {audio_src.name} failed: {exc}")
                continue
            if out.is_file() and out.stat().st_size > 1000 and probe_has_audio(out):
                return {
                    "ok": True,
                    "action": "mux_from_mix"
                    if "mixed" in audio_src.name or "narration" in audio_src.name
                    else "mux_from_final",
                    "audio_source": str(audio_src),
                    "has_audio": True,
                    "mean_volume_db": probe_mean_volume_db(out),
                    "video_duration_sec": v_dur,
                    "audio_duration_sec": a_dur,
                    "duration_skew_sec": skew,
                }

    # No production mix — keep video audio if it is actually audible
    if probe_has_audio(video):
        mean = probe_mean_volume_db(video)
        if mean is None or mean > -42.0:
            if video.resolve() != out.resolve():
                shutil.copy2(video, out)
            return {
                "ok": True,
                "action": "passthrough",
                "has_audio": True,
                "mean_volume_db": mean,
            }
        log(f"video audio too quiet (mean_volume={mean} dB) and no mixed.wav — trying stem rebuild")

    candidates: list[Path] = []
    for rel in (
        "out/film_final.mp4",
        "out/film_final_audio_src.mp4",
    ):
        p = root / rel
        if p.is_file() and probe_has_audio(p):
            candidates.append(p)
    # Stem pair
    vo = next(
        (
            p
            for p in (
                root / "audio" / "narration.wav",
                root / "out" / "voice.wav",
                root / "audio" / "voice.wav",
                root / "out" / "_final_work" / "voice_cat.wav",
            )
            if p.is_file()
        ),
        None,
    )
    bgm = next(
        (
            p
            for p in (
                root / "audio" / "bgm_procedural.wav",
                root / "out" / "music.wav",
                root / "audio" / "music.wav",
                root / "out" / "_final_work" / "music.wav",
                root / "out" / "_final_work" / "bgm_stereo.wav",
            )
            if p.is_file()
        ),
        None,
    )

    if candidates:
        audio_src = candidates[0]
        _ffmpeg_mux_video_with_audio(video, audio_src, out, effects=effects)
        return {
            "ok": True,
            "action": "mux_from_final",
            "audio_source": str(audio_src),
            "has_audio": True,
            "mean_volume_db": probe_mean_volume_db(out),
        }

    if vo is not None:
        # mix vo (+ optional bgm) then mux
        work = out.parent / "_compose_audio_work"
        work.mkdir(parents=True, exist_ok=True)
        mixed = work / "mixed.m4a"
        if bgm is not None:
            run_media_to_output(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(vo),
                    "-i",
                    str(bgm),
                    "-filter_complex",
                    "[0:a]volume=1.2[a0];[1:a]volume=0.45[a1];[a0][a1]amix=inputs=2:duration=longest:dropout_transition=0[a]",
                    "-map",
                    "[a]",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    str(mixed),
                ],
                mixed,
                timeout=600,
                min_bytes=100,
            )
        else:
            run_media_to_output(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(vo),
                    "-c:a",
                    "aac",
                    "-b:a",
                    "192k",
                    str(mixed),
                ],
                mixed,
                timeout=600,
                min_bytes=100,
            )
        run_media_to_output(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video),
                "-i",
                str(mixed),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
                str(out),
            ],
            out,
            timeout=600,
            min_bytes=1000,
        )
        return {
            "ok": True,
            "action": "mux_from_stems",
            "vo": str(vo),
            "bgm": str(bgm) if bgm else None,
            "has_audio": True,
        }

    raise ComposeRenderError(
        "Composed video has no audio and no audio source found. "
        "Run `aifilm final` first (for VO/BGM) or ensure film_final.mp4 exists, then compose-render again."
    )


def register_final_film(
    root: Path,
    source: Path,
    *,
    out_name: str = "film_final.mp4",
    post_engine: str,
    require_motion: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Copy source into out/, run technical QA, write manifest.outputs.final_film."""
    root = root.expanduser().resolve()
    try:
        reject_symlinks(root, field="film root")
        out_dir = safe_workspace_directory(root, "out", field="out directory")
        out_dir.mkdir(parents=True, exist_ok=True)
        final_path = safe_output_path(
            out_dir, out_name, suffixes={".mp4"}, field="final output name"
        )
    except SecurityPolicyError as exc:
        raise ComposeRenderError(str(exc)) from exc

    source = source.expanduser().resolve()
    if not source.is_file():
        raise ComposeRenderError(f"Source MP4 missing: {source}")

    if post_engine == "hyperframes":
        # All formal HyperFrames registrations, including --register-only and
        # register-final, share this fail-closed ownership gate.
        try:
            from final_stages import ensure_captions_after_hf

            caption_gate = ensure_captions_after_hf(root, final_mp4=source)
        except Exception as exc:
            raise ComposeRenderError(f"could not verify HyperFrames captions: {exc}") from exc
        if not caption_gate.get("ok"):
            raise ComposeRenderError(
                str(
                    caption_gate.get("error")
                    or "HyperFrames caption gate failed; re-render required"
                )
            )

    if source.resolve() != final_path.resolve():
        shutil.copy2(source, final_path)

    try:
        technical_qa = analyze_media(final_path, require_audio=True, require_motion=require_motion)
    except MediaQAError as exc:
        raise ComposeRenderError(str(exc)) from exc
    if not technical_qa.get("ok"):
        raise ComposeRenderError(f"Final MP4 failed technical QA: {technical_qa.get('errors')}")

    digest = sha256(final_path)
    duration = float(technical_qa.get("duration_sec") or pdur(final_path))
    report = {
        "schema_version": SCHEMA_VERSION,
        "created_at": utc_now(),
        "output": str(final_path),
        "output_sha256": digest,
        "duration_sec": duration,
        "post_engine": post_engine,
        "technical_qa": technical_qa,
        "registered_from": str(source),
    }
    report_path = safe_output_path(
        out_dir, "final-delivery.json", suffixes={".json"}, field="delivery report"
    )
    write_json(report_path, report)

    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise ComposeRenderError("manifest.json missing")
    manifest = read_json(manifest_path)
    # Invalidate prior human approval — hash changed
    outputs = manifest.setdefault("outputs", {})
    prev_review = outputs.get("final_review")
    if isinstance(prev_review, dict):
        outputs["final_review_stale"] = {
            "reason": "final_film replaced",
            "previous_sha256": prev_review.get("output_sha256"),
            "at": utc_now(),
        }
        outputs.pop("final_review", None)
    outputs["final_film"] = {
        "path": final_path.name,
        "sha256": digest,
        "duration_sec": duration,
        "report": report_path.name,
        "assembled_at": utc_now(),
        "technical_qa": technical_qa,
        "post_engine": post_engine,
    }
    manifest.setdefault("gates", {})["final_complete"] = False
    manifest["updated_at"] = utc_now()
    write_json(manifest_path, manifest)

    return {
        "ok": True,
        "output": str(final_path),
        "output_sha256": digest,
        "duration_sec": duration,
        "post_engine": post_engine,
        "technical_qa": technical_qa,
        "report": str(report_path),
        "final_complete": False,
        "note": "Run review-final after full watch; final_complete stays false until scorecard pass",
    }


def hyperframes_check(hf_dir: Path, *, strict: bool = False) -> dict[str, Any]:
    npx = which_npx()
    if not npx:
        raise ComposeRenderError("npx not found on PATH — install Node.js")
    cmd = [npx, "--yes", "hyperframes", "check", "--json"]
    if strict:
        cmd.append("--strict")
    proc = run(cmd, cwd=hf_dir, check=False, timeout=600)
    payload: dict[str, Any] = {"returncode": proc.returncode}
    stdout = (proc.stdout or "").strip()
    if stdout:
        try:
            # may be multi-line JSON or with logs; take last JSON object
            payload["result"] = json.loads(stdout)
        except json.JSONDecodeError:
            # try last line
            for line in reversed(stdout.splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        payload["result"] = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
            else:
                payload["stdout_tail"] = stdout[-2000:]
    if proc.returncode != 0:
        err = (proc.stderr or "")[-2000:]
        raise ComposeRenderError(
            f"hyperframes check failed (exit {proc.returncode}): {err or payload}"
        )
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    # doctor-style: check may print ok nested
    ok = result.get("ok")
    if ok is False:
        raise ComposeRenderError(f"hyperframes check reported not ok: {result}")
    return payload


def hyperframes_render(
    hf_dir: Path,
    output: Path,
    *,
    quality: str = "standard",
    fps: int | None = None,
    stream: bool = True,
) -> dict[str, Any]:
    npx = which_npx()
    if not npx:
        raise ComposeRenderError(
            "npx not found on PATH — install Node.js 22+ for HyperFrames "
            "(or use --post-engine ffmpeg)"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        npx,
        "--yes",
        "hyperframes",
        "render",
        "--quality",
        quality,
        "--output",
        str(output),
    ]
    if fps is not None:
        cmd += ["--fps", str(int(fps))]
    log(f"hyperframes render ({quality}) → {output}")

    env = minimal_subprocess_env()
    for key in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "NODE_PATH", "npm_config_cache"):
        if key in os.environ:
            env[key] = os.environ[key]
    if "HOME" in env:
        env.setdefault("npm_config_cache", str(Path(env["HOME"]) / ".npm"))

    collected: list[str] = []
    if stream:
        # Live progress on stderr; keep tail for error reports
        proc = subprocess.Popen(
            cmd,
            cwd=str(hf_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            bufsize=1,
        )
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                collected.append(line)
                sys.stderr.write(line)
                sys.stderr.flush()
            returncode = proc.wait(timeout=3600)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise ComposeRenderError("hyperframes render timed out after 3600s") from None
        log_text = "".join(collected)
    else:
        proc_done = run(cmd, cwd=hf_dir, check=False, timeout=3600)
        returncode = proc_done.returncode
        log_text = (proc_done.stdout or "") + (proc_done.stderr or "")

    if returncode != 0 or not output.is_file() or output.stat().st_size < 100:
        raise ComposeRenderError(
            "hyperframes render failed: " + (log_text[-3000:] or f"exit {returncode}")
        )
    return {
        "ok": True,
        "output": str(output),
        "bytes": output.stat().st_size,
        "quality": quality,
        "log_tail": log_text[-500:],
    }


def assert_preview_receipt(root: Path) -> dict[str, Any]:
    """Hard gate for --require-preview (designed-post path)."""
    try:
        from compose_preview import has_valid_preview_receipt, load_preview_receipt

        if not has_valid_preview_receipt(root):
            raise ComposeRenderError(
                "require-preview: missing or invalid receipts/compose-preview.json — "
                f'run: aifilm compose-preview --root "{root}" '
                "then re-run final/compose-render"
            )
        rec = load_preview_receipt(root) or {}
        return {"ok": True, "url": rec.get("url"), "started_at": rec.get("started_at")}
    except ComposeRenderError:
        raise
    except Exception as exc:
        raise ComposeRenderError(
            f"require-preview: cannot read preview receipt ({exc}) — "
            f'run: aifilm compose-preview --root "{root}"'
        ) from exc


# HyperFrames is strongest at 30–90s, hard ceiling ~3min (per hyperframes/SKILL.md).
# Beyond 90s we emit a non-fatal segmentation advisory so agents route long pieces
# through per-segment HF render + FFmpeg concat instead of one monolithic render.
HF_STRONG_MAX_SEC = 90.0
HF_HARD_CEILING_SEC = 180.0


def duration_advisory(total_duration_sec: float | None) -> dict[str, Any]:
    """Return a non-fatal advisory for HyperFrames duration limits.

    Returns ``{"advisory": bool, "action": str|None, "segment_count": int}``.
    """
    if not total_duration_sec or total_duration_sec <= 0:
        return {"advisory": False, "action": None, "segment_count": 1}
    if total_duration_sec <= HF_STRONG_MAX_SEC:
        return {"advisory": False, "action": None, "segment_count": 1}
    action = None
    seg_count = 1
    if total_duration_sec <= HF_HARD_CEILING_SEC:
        # Segment into ≤90s chunks for HF render, then FFmpeg concat
        seg_count = max(2, int(-(-total_duration_sec // HF_STRONG_MAX_SEC)))
        action = (
            f"duration {total_duration_sec:.1f}s > 90s (HF sweet spot) — "
            f"segment into {seg_count} ≤90s HF renders, then FFmpeg concat "
            f"(per hyperframes/SKILL.md: 30–90s strongest, ~3min ceiling)"
        )
    else:
        seg_count = max(3, int(-(-total_duration_sec // HF_STRONG_MAX_SEC)))
        action = (
            f"duration {total_duration_sec:.1f}s > {HF_HARD_CEILING_SEC}s HF ceiling — "
            f"route to /general-video style per-segment render + concat "
            f"(split into {seg_count} segments); HF is not the right tool for >3min"
        )
    return {"advisory": True, "action": action, "segment_count": seg_count}


def compose_render(
    root: Path,
    *,
    engine: str = "hyperframes",
    export_first: bool = True,
    force_export: bool = True,
    layout: str = "auto",
    compose_preset: str = "auto",
    quality: str = "standard",
    out_name: str = "film_final.mp4",
    register: bool = True,
    skip_check: bool = False,
    keep_raw: bool = False,
    require_preview: bool = False,
    npm_install: bool = False,
    npm_install_timeout: int = 900,
    title_dur: float = 1.5,
    end_dur: float = 1.5,
    allow_burned_underlay: bool = False,
    title_sequence: str | None = None,
    end_roll: str | None = None,
) -> dict[str, Any]:
    """End-to-end designed-post render.

    HyperFrames: check → render → audio mux → register (post_engine=hyperframes).
    Remotion: media-copy always; optional --npm-install then auto-render when ready;
    otherwise return rendered:false + exact bootstrap/render/register next_steps.
    engine=both: export both + remotion media-copy + **render HyperFrames only**
    (Remotion is not auto-rendered; use --engine remotion for that).
    """
    root = root.expanduser().resolve()
    engine = (engine or "hyperframes").strip().lower()
    if engine not in {"hyperframes", "remotion", "both"}:
        raise ComposeRenderError(f"unsupported engine {engine!r}")

    try:
        from platform_package import PlatformPackageError, assert_no_double_burn_override

        assert_no_double_burn_override(root, allow_burned_underlay=allow_burned_underlay)
    except PlatformPackageError as exc:
        raise ComposeRenderError(str(exc)) from exc

    steps: dict[str, Any] = {}

    # Resolve layout for gates: when reusing export, honor package layout if CLI says auto
    layout_l = (layout or "auto").strip().lower()
    if layout_l == "auto" and not export_first:
        for probe in (
            root / "compose" / "hyperframes" / "composition-data.json",
            root / "compose" / "remotion" / "public" / "composition-data.json",
            root / "compose" / "package.json",
        ):
            if not probe.is_file():
                continue
            try:
                pdata = read_json(probe)
            except ComposeRenderError:
                continue
            # remotion public composition-data nests layout at remotion.layout too
            pkg_layout = pdata.get("layout")
            if not pkg_layout and isinstance(pdata.get("remotion"), dict):
                pkg_layout = pdata["remotion"].get("layout")
            if isinstance(pkg_layout, str) and pkg_layout.strip():
                layout_l = pkg_layout.strip().lower()
                steps["layout_from_package"] = layout_l
                break
    if layout_l == "auto":
        # Prefer underlay when final exists — unless plate already burned captions
        # (auto-fallback multiclip avoids hard fail + silent double-burn).
        has_final = (root / "out" / "film_final.mp4").is_file()
        burned = plate_subtitles_burned_in(root)
        if has_final and burned is True and not allow_burned_underlay:
            layout_l = "multiclip"
            steps["layout_auto_fallback"] = {
                "from": "underlay",
                "to": "multiclip",
                "reason": "subtitles.burned_in=true — avoid double-burn",
            }
            log(
                "layout=auto → multiclip (plate has burned-in captions; "
                "re-final --subs off for underlay, or --allow-burned-underlay)"
            )
        else:
            layout_l = "underlay" if has_final else "multiclip"

    # Double-burn gate before expensive export/render
    steps["double_burn_gate"] = assert_underlay_not_double_burn(
        root,
        layout=layout_l,
        allow_burned_underlay=allow_burned_underlay,
    )

    if require_preview and engine in {"hyperframes", "both", "remotion"}:
        steps["preview_receipt"] = assert_preview_receipt(root)

    # Fail fast before expensive export when HF tooling is missing
    if engine in {"hyperframes", "both"}:
        tooling = probe_designed_post_tooling()
        steps["tooling"] = tooling
        if not tooling.get("npx"):
            raise ComposeRenderError(
                "npx missing — install Node.js 22+，或改用 aifilm final --post-engine ffmpeg"
            )

    if export_first:
        from export_composition import ComposeExportError, export_composition

        try:
            exp_engine = "both" if engine == "both" else engine
            # Pass resolved layout (not raw "auto") so burned plates export multiclip
            steps["export"] = export_composition(
                root,
                engine=exp_engine,
                title_dur=title_dur,
                end_dur=end_dur,
                force=force_export,
                layout=layout_l if layout_l in {"multiclip", "underlay"} else layout,
                compose_preset=compose_preset,
                title_sequence=title_sequence,
                end_roll=end_roll,
            )
            exp = steps["export"]
            if isinstance(exp, dict) and isinstance(exp.get("layout"), str):
                layout_l = str(exp["layout"]).strip().lower() or layout_l
        except ComposeExportError as exc:
            raise ComposeRenderError(str(exc)) from exc

    if engine in {"remotion", "both"}:
        try:
            steps["remotion_media_copy"] = copy_remotion_media(root)
        except (ComposeRenderError, SecurityPolicyError) as exc:
            if engine == "remotion":
                raise ComposeRenderError(str(exc)) from exc
            steps["remotion_media_copy"] = {"ok": False, "error": str(exc)}
        if engine == "both":
            # Contract: both does not auto-render Remotion (HF only below).
            rem_ready = probe_remotion_readiness(root)
            steps["remotion_render"] = {
                "skipped": True,
                "reason": (
                    "engine=both exports both + copies remotion media, then renders "
                    "HyperFrames only. To render Remotion: compose-render --engine remotion "
                    "or final --post-engine remotion"
                ),
                "readiness": {
                    "ready": rem_ready.get("ready"),
                    "missing": rem_ready.get("missing"),
                },
            }

    if engine == "remotion":
        rem = root / "compose" / "remotion"
        readiness = probe_remotion_readiness(root)
        steps["remotion_readiness"] = readiness
        next_steps = remotion_actionable_next_steps(root, rem_dir=rem)

        if not readiness.get("ready") and npm_install:
            # Explicit network bootstrap — only when user asked --npm-install
            if not (rem / "package.json").is_file():
                return {
                    "ok": False,
                    "engine": "remotion",
                    "rendered": False,
                    "post_engine": None,
                    "steps": steps,
                    "error": "npm-install requested but compose/remotion/package.json missing",
                    "next_steps": next_steps,
                    "next": next_steps,
                }
            try:
                steps["npm_install"] = remotion_npm_install(rem, timeout=int(npm_install_timeout))
            except ComposeRenderError as exc:
                # Honest failure with next steps (no fake MP4)
                return {
                    "ok": False,
                    "engine": "remotion",
                    "rendered": False,
                    "post_engine": None,
                    "steps": steps,
                    "error": str(exc),
                    "next_steps": next_steps,
                    "next": next_steps,
                    "message": "npm install failed; fix network/deps or use HyperFrames",
                }
            readiness = probe_remotion_readiness(root)
            steps["remotion_readiness_after_install"] = readiness

        if not readiness.get("ready"):
            hint = "pass --npm-install once (network), or: cd compose/remotion && npm install"
            # Not silent success: ok=False + rendered=false + exact next steps
            return {
                "ok": False,
                "engine": "remotion",
                "rendered": False,
                "post_engine": None,
                "steps": steps,
                "missing": readiness.get("missing") or [],
                "error": (
                    "Remotion package not ready for automated render "
                    f"(missing: {', '.join(readiness.get('missing') or ['unknown'])}). "
                    f"Media copy may have completed; {hint}."
                ),
                "message": (
                    "Remotion scaffold + media-copy only. Automated render needs "
                    "node_modules. Use --npm-install or install manually. "
                    "Prefer: aifilm final --post-engine hyperframes"
                ),
                "next_steps": next_steps,
                "next": next_steps,
            }

        out_dir = safe_workspace_directory(root, "out", field="out")
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_out = out_dir / "film_remotion_raw.mp4"
        if raw_out.exists():
            raw_out.unlink()
        steps["render"] = remotion_render(rem, raw_out, composition_id="Film")

        mixed_out = out_dir / "film_remotion.mp4"
        steps["audio"] = ensure_audio_mux(raw_out, root, mixed_out)
        if not keep_raw and raw_out.is_file() and raw_out.resolve() != mixed_out.resolve():
            try:
                raw_out.unlink()
                steps["cleanup_raw"] = True
            except OSError:
                steps["cleanup_raw"] = False

        result: dict[str, Any] = {
            "ok": True,
            "engine": "remotion",
            "rendered": True,
            "output": str(mixed_out),
            "steps": steps,
            "next": [
                f'aifilm review-final --root "{root}" --approve --reviewer <you> --notes "…" '
                "--score-identity pass --score-style pass --score-motion pass "
                "--score-escalation pass --score-audio pass --score-subs pass --score-dead-air pass"
            ],
        }
        if register:
            try:
                reg = register_final_film(
                    root,
                    mixed_out,
                    out_name=out_name,
                    post_engine="remotion",
                    require_motion=True,
                    force=True,
                )
                result["register"] = reg
                result["output"] = reg["output"]
                result["output_sha256"] = reg["output_sha256"]
                result["duration_sec"] = reg.get("duration_sec")
                result["post_engine"] = "remotion"
            except ComposeRenderError as exc:
                result["register_error"] = str(exc)
                result["hint"] = (
                    "画面已写出 out/film_remotion.mp4，但技术 QA 未过，未写入 final_film。"
                    "可 aifilm register-final --source … --post-engine remotion 手动接入。"
                )
                raise ComposeRenderError(f"{exc} | hint={result['hint']}") from exc
        # Remotion duration advisory — non-fatal
        _rem_out = Path(result["output"]) if result.get("output") else None
        result["duration_advisory"] = duration_advisory(
            result.get("duration_sec")
            or (pdur(_rem_out) if _rem_out and _rem_out.is_file() else None)
        )
        return result

    # HyperFrames path (also engine=both after remotion media copy)
    hf_dir = root / "compose" / "hyperframes"
    if not (hf_dir / "index.html").is_file():
        raise ComposeRenderError(
            f"Missing {hf_dir / 'index.html'} — run export-compose --engine hyperframes first"
        )

    if not skip_check:
        steps["check"] = hyperframes_check(hf_dir)

    out_dir = safe_workspace_directory(root, "out", field="out")
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_out = out_dir / "film_hyperframes_raw.mp4"
    if raw_out.exists():
        raw_out.unlink()
    steps["render"] = hyperframes_render(hf_dir, raw_out, quality=quality, stream=True)

    mixed_out = out_dir / "film_hyperframes.mp4"
    steps["audio"] = ensure_audio_mux(raw_out, root, mixed_out)

    # Drop intermediate raw unless debugging (saves disk on multi-shot films)
    if not keep_raw and raw_out.is_file() and raw_out.resolve() != mixed_out.resolve():
        try:
            raw_out.unlink()
            steps["cleanup_raw"] = True
        except OSError:
            steps["cleanup_raw"] = False

    result = {
        "ok": True,
        "engine": "hyperframes",
        "rendered": True,
        "raw": str(raw_out) if keep_raw and raw_out.is_file() else None,
        "output": str(mixed_out),
        "quality": quality,
        "steps": steps,
        "next": [
            f'aifilm review-final --root "{root}" --approve --reviewer <you> --notes "…" '
            "--score-identity pass --score-style pass --score-motion pass "
            "--score-escalation pass --score-audio pass --score-subs pass --score-dead-air pass"
        ],
    }

    # This command is also a formal HyperFrames-final entry point, so it must
    # enforce the same single caption owner as `aifilm final`.  Do this before
    # registration: an HF render without verified HF captions is not a final.
    try:
        from final_stages import ensure_captions_after_hf

        caption_gate = ensure_captions_after_hf(root, final_mp4=mixed_out)
    except Exception as exc:
        raise ComposeRenderError(f"could not verify HyperFrames captions: {exc}") from exc
    result["caption"] = caption_gate
    if not caption_gate.get("ok"):
        raise ComposeRenderError(
            str(caption_gate.get("error") or "HyperFrames caption gate failed; re-render required")
        )

    if register:
        try:
            reg = register_final_film(
                root,
                mixed_out,
                out_name=out_name,
                post_engine="hyperframes",
                require_motion=True,
                force=True,
            )
            result["register"] = reg
            result["output"] = reg["output"]
            result["output_sha256"] = reg["output_sha256"]
            result["duration_sec"] = reg.get("duration_sec")
            from final_stages import patch_delivery_burned_in

            result["caption_delivery"] = patch_delivery_burned_in(
                root,
                burned_in=True,
                owner=str(caption_gate["caption_owner"]),
            )
        except ComposeRenderError as exc:
            result["register_error"] = str(exc)
            result["hint"] = (
                "画面已写出 out/film_hyperframes.mp4，但技术 QA 未过，未写入 final_film。"
                "可修 compose HTML 后重跑，或 aifilm register-final --source … 手动接入。"
            )
            raise ComposeRenderError(f"{exc} | hint={result['hint']}") from exc

    # HF duration advisory (>90s sweet spot, ~3min ceiling) — non-fatal
    _dur = result.get("duration_sec") or (pdur(mixed_out) if mixed_out.is_file() else None)
    result["duration_advisory"] = duration_advisory(_dur)
    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Render compose package (HyperFrames) to formal final")
    p.add_argument("--root", required=True)
    p.add_argument("--engine", default="hyperframes", choices=["hyperframes", "remotion", "both"])
    p.add_argument("--no-export", action="store_true", help="Skip export-compose")
    p.add_argument("--no-force-export", action="store_true")
    p.add_argument(
        "--layout",
        default="auto",
        choices=["auto", "multiclip", "underlay"],
        help="Composition layout (auto: underlay if film_final exists)",
    )
    p.add_argument(
        "--compose-preset",
        default="auto",
        choices=["auto", "ecchi-rnb", "minimal"],
        help="Title/caption visual preset (auto from sound_plan.mood / tone)",
    )
    p.add_argument(
        "--require-preview",
        action="store_true",
        help="Require receipts/compose-preview.json from compose-preview before HF render",
    )
    p.add_argument(
        "--npm-install",
        action="store_true",
        help="Remotion only: run npm install in compose/remotion before render (network)",
    )
    p.add_argument(
        "--npm-install-timeout",
        type=int,
        default=900,
        help="Seconds for --npm-install (default 900)",
    )
    p.add_argument("--quality", default="standard", choices=["draft", "standard", "high"])
    p.add_argument("--out-name", default="film_final.mp4")
    p.add_argument("--no-register", action="store_true")
    p.add_argument("--skip-check", action="store_true")
    p.add_argument(
        "--keep-raw",
        action="store_true",
        help="Keep out/film_hyperframes_raw.mp4 after audio mux",
    )
    p.add_argument("--title-dur", type=float, default=1.5)
    p.add_argument("--end-dur", type=float, default=1.5)
    p.add_argument(
        "--title-sequence",
        default=None,
        choices=["auto", "none"],
        help="Override film-spec title_sequence mode (auto=spec/default, none=suppress)",
    )
    p.add_argument(
        "--end-roll",
        default=None,
        choices=["auto", "none", "cast_only", "full"],
        help="Override film-spec end_roll mode (auto=spec/default, none=suppress)",
    )
    p.add_argument(
        "--allow-burned-underlay",
        action="store_true",
        help="Allow underlay when plate already has burned-in captions (double-burn risk)",
    )
    p.add_argument(
        "--register-only",
        default=None,
        help="Only register an existing MP4 as final_film (path)",
    )
    p.add_argument("--post-engine", default="external", help="Label when using --register-only")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.register_only:
            result = register_final_film(
                Path(args.root),
                Path(args.register_only),
                out_name=args.out_name,
                post_engine=str(args.post_engine or "external"),
                force=True,
            )
        else:
            result = compose_render(
                Path(args.root),
                engine=args.engine,
                export_first=not args.no_export,
                force_export=not args.no_force_export,
                layout=args.layout,
                compose_preset=str(getattr(args, "compose_preset", "auto") or "auto"),
                quality=args.quality,
                out_name=args.out_name,
                register=not args.no_register,
                skip_check=args.skip_check,
                keep_raw=bool(args.keep_raw),
                require_preview=bool(getattr(args, "require_preview", False)),
                npm_install=bool(getattr(args, "npm_install", False)),
                npm_install_timeout=int(getattr(args, "npm_install_timeout", 900) or 900),
                title_dur=args.title_dur,
                end_dur=args.end_dur,
                allow_burned_underlay=bool(getattr(args, "allow_burned_underlay", False)),
                title_sequence=getattr(args, "title_sequence", None),
                end_roll=getattr(args, "end_roll", None),
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        # remotion not-ready returns structured ok=False without raising
        if isinstance(result, dict) and result.get("ok") is False:
            return 2
        return 0
    except ComposeRenderError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
