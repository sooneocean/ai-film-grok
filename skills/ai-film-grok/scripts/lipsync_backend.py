#!/usr/bin/env python3
"""Pluggable lip-sync backends for ai-film-grok (post-VO face retime).

Solves: silent Grok I2V + edge-tts overlay without mouth match.
Industry path: video/image + audio → MuseTalk / Wav2Lip / external CLI.
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

from backend_lock import verify_backend_lock
from security_policy import (
    SecurityPolicyError,
    expand_argv,
    load_allowed_env,
    minimal_subprocess_env,
    parse_argv_json,
)


class LipSyncError(RuntimeError):
    pass


BACKEND_PRIORITY = ("musetalk", "wav2lip", "external")


def _load_skill_config_env() -> None:
    """Load skill-local config.env if present (does not override existing env)."""
    cfg = Path(__file__).resolve().parents[1] / "config.env"
    load_allowed_env(
        cfg,
        allowed_keys={
            "AIFILM_LIPSYNC_BACKEND",
            "AIFILM_LIPSYNC_ARGV",
            "AIFILM_MUSETALK_ROOT",
            "AIFILM_WAV2LIP_ROOT",
        },
    )


_load_skill_config_env()


def emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def env_backend() -> str:
    return (os.environ.get("AIFILM_LIPSYNC_BACKEND") or "auto").strip().lower()


def backend_lock_path() -> Path:
    return Path(__file__).resolve().parents[1] / "backend-lock.json"


def backend_trust(kind: str, root: Path | None) -> dict[str, Any]:
    if root is None:
        return {"ok": False, "errors": [f"{kind} root or weights are missing"]}
    return verify_backend_lock(kind, root, backend_lock_path())


def musetalk_root() -> Path | None:
    raw = os.environ.get("AIFILM_MUSETALK_ROOT")
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw).expanduser())
    candidates.extend(
        [
            Path.home() / "YDEX/INPORTANT WORK/lipsync-backends/MuseTalk",
            Path.home() / "YDEX/INPORTANT WORK/MuseTalk",
            Path.home() / "src/MuseTalk",
            Path.home() / "MuseTalk",
        ]
    )
    for candidate in candidates:
        path = candidate.resolve()
        # require weights to call it "ready" (free install may be incomplete on Mac)
        weights = path / "models" / "musetalkV15" / "unet.pth"
        weights_alt = path / "models" / "musetalk" / "pytorch_model.bin"
        if path.is_dir() and (weights.is_file() or weights_alt.is_file()):
            return path
    return None


def wav2lip_root() -> Path | None:
    raw = os.environ.get("AIFILM_WAV2LIP_ROOT")
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw).expanduser())
    candidates.extend(
        [
            Path.home() / "YDEX/INPORTANT WORK/lipsync-backends/Wav2Lip",
            Path.home() / "YDEX/INPORTANT WORK/Wav2Lip",
            Path.home() / "src/Wav2Lip",
            Path.home() / "Wav2Lip",
        ]
    )
    for candidate in candidates:
        path = candidate.resolve()
        ckpt = path / "checkpoints" / "wav2lip_gan.pth"
        if path.is_dir() and (path / "inference.py").is_file() and ckpt.is_file():
            return path
    return None


def external_argv_template() -> list[str] | None:
    raw = os.environ.get("AIFILM_LIPSYNC_ARGV")
    if raw and raw.strip():
        try:
            return parse_argv_json(raw, variable="AIFILM_LIPSYNC_ARGV")
        except SecurityPolicyError as exc:
            raise LipSyncError(str(exc)) from exc
    if os.environ.get("AIFILM_LIPSYNC_CMD"):
        raise LipSyncError(
            "AIFILM_LIPSYNC_CMD is disabled because shell templates are unsafe; use AIFILM_LIPSYNC_ARGV JSON"
        )
    return None


def probe() -> dict[str, Any]:
    mt = musetalk_root()
    w2 = wav2lip_root()
    mt_trust = backend_trust("musetalk", mt)
    w2_trust = backend_trust("wav2lip", w2)
    external_error = None
    try:
        ext = external_argv_template()
    except LipSyncError as exc:
        ext = None
        external_error = str(exc)
    backends = {
        "external": bool(ext),
        "musetalk": bool(
            mt
            and mt_trust.get("ok")
            and (
                (mt / "aifilm_infer.py").is_file() or (mt / "scripts" / "aifilm_infer.py").is_file()
            )
        ),
        "wav2lip": bool(
            w2
            and w2_trust.get("ok")
            and (
                (w2 / "inference.py").is_file()
                or (w2 / "inference_onnx.py").is_file()
                or list(w2.glob("**/inference.py"))
            )
        ),
    }
    # Only explicitly locked local backends are eligible for automatic selection.
    ready = [name for name in BACKEND_PRIORITY if backends.get(name)]
    return {
        "ok": True,
        "ffmpeg": shutil.which("ffmpeg"),
        "env_backend": env_backend(),
        "backends": backends,
        "ready": ready,
        "default_choice": ready[0] if ready else None,
        "policy": "explicitly locked MuseTalk/Wav2Lip, then structured external argv",
        "musetalk_root": str(mt) if mt else None,
        "wav2lip_root": str(w2) if w2 else None,
        "backend_lock": str(backend_lock_path()),
        "backend_trust": {"musetalk": mt_trust, "wav2lip": w2_trust},
        "external_argv_set": bool(ext),
        "external_config_error": external_error,
        "note": (
            "No local lipsync backend found. Install MuseTalk/Wav2Lip or set AIFILM_LIPSYNC_ARGV. "
            "See references/lipsync.md"
            if not ready
            else "At least one lipsync backend is configured."
        ),
    }


def resolve_backend(requested: str) -> str:
    req = (requested or "auto").lower()
    if req == "auto" and env_backend() != "auto":
        req = env_backend()
    if req == "off":
        return "off"
    info = probe()
    ready = info["ready"]
    if req == "auto":
        return ready[0] if ready else "off"
    if req == "require":
        if not ready:
            raise LipSyncError(
                "lipsync required but no backend ready (see lipsync_backend.py doctor)"
            )
        return ready[0]
    if req not in ("external", "musetalk", "wav2lip"):
        raise LipSyncError(f"Unknown backend {req}")
    if req == "external" and info.get("external_config_error"):
        raise LipSyncError(str(info["external_config_error"]))
    if req not in ready:
        raise LipSyncError(f"Backend {req} not configured")
    return req


def run_external(video: Path, audio: Path, out: Path, template: list[str]) -> None:
    try:
        argv = expand_argv(
            template,
            {"video": str(video), "audio": str(audio), "out": str(out)},
            variable="AIFILM_LIPSYNC_ARGV",
        )
    except SecurityPolicyError as exc:
        raise LipSyncError(str(exc)) from exc
    log(f"lipsync external: {argv[0]} ({len(argv) - 1} args)")
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=300,
            env=minimal_subprocess_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LipSyncError(f"external lipsync could not run: {exc}") from exc
    if proc.returncode != 0:
        raise LipSyncError(f"external lipsync failed: {(proc.stderr or proc.stdout)[:1500]}")
    if not out.is_file() or out.stat().st_size == 0:
        raise LipSyncError(f"external lipsync produced no output: {out}")


def run_wav2lip(video: Path, audio: Path, out: Path, root: Path) -> None:
    trust = backend_trust("wav2lip", root)
    if not trust.get("ok"):
        raise LipSyncError(f"Wav2Lip backend is not trusted: {trust.get('errors')}")
    inference = root / "inference.py"
    if not inference.is_file():
        found = list(root.glob("**/inference.py"))
        if not found:
            raise LipSyncError(f"Wav2Lip inference.py not found under {root}")
        inference = found[0]
    # checkpoint search
    ckpts = list((root / "checkpoints").glob("wav2lip_gan.pth")) + list(
        (root / "checkpoints").glob("wav2lip.pth")
    )
    if not ckpts:
        ckpts = list(root.glob("**/wav2lip_gan.pth")) + list(root.glob("**/wav2lip.pth"))
    if not ckpts:
        raise LipSyncError(
            f"Wav2Lip checkpoint missing under {root} (need wav2lip_gan.pth or wav2lip.pth)"
        )
    ckpt = ckpts[0]
    out.parent.mkdir(parents=True, exist_ok=True)
    # Prefer small batches for CPU / Apple Silicon free path
    cmd = [
        sys.executable,
        str(inference),
        "--checkpoint_path",
        str(ckpt),
        "--face",
        str(video),
        "--audio",
        str(audio),
        "--outfile",
        str(out),
        "--face_det_batch_size",
        "1",
        "--wav2lip_batch_size",
        "8",
        "--pads",
        "0",
        "20",
        "0",
        "0",
    ]
    # Static image path: slightly better talking-head when input is a still
    if video.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
        cmd += ["--fps", "25"]
    log(f"lipsync wav2lip: {' '.join(cmd)}")
    proc = subprocess.run(
        cmd,
        timeout=60,
        cwd=str(root),
        capture_output=True,
        text=True,
        env=minimal_subprocess_env(),
    )
    if proc.returncode != 0:
        raise LipSyncError(f"wav2lip failed: {(proc.stderr or proc.stdout)[:2000]}")
    if not out.is_file():
        raise LipSyncError("wav2lip finished but outfile missing")


def run_musetalk(video: Path, audio: Path, out: Path, root: Path) -> None:
    """Invoke MuseTalk via a generated one-shot config if inference entry exists."""
    trust = backend_trust("musetalk", root)
    if not trust.get("ok"):
        raise LipSyncError(f"MuseTalk backend is not trusted: {trust.get('errors')}")
    # Prefer a user-provided wrapper script inside the repo
    wrappers = [
        root / "aifilm_infer.py",
        root / "scripts" / "aifilm_infer.py",
    ]
    for wrapper in wrappers:
        if wrapper.is_file():
            cmd = [
                sys.executable,
                str(wrapper),
                "--video",
                str(video),
                "--audio",
                str(audio),
                "--out",
                str(out),
            ]
            log(f"lipsync musetalk wrapper: {' '.join(cmd)}")
            proc = subprocess.run(
                cmd,
                timeout=60,
                cwd=str(root),
                capture_output=True,
                text=True,
                env=minimal_subprocess_env(),
            )
            if proc.returncode != 0:
                raise LipSyncError(
                    f"musetalk wrapper failed: {(proc.stderr or proc.stdout)[:2000]}"
                )
            if not out.is_file():
                raise LipSyncError("musetalk wrapper produced no output")
            return

    raise LipSyncError(
        "Generic MuseTalk scripts.inference is disabled because the upstream version invokes shell commands "
        "with unquoted media paths. Install an audited aifilm_infer.py wrapper or use AIFILM_LIPSYNC_ARGV."
    )


def lipsync_one(
    *,
    video: Path,
    audio: Path,
    out: Path,
    backend: str = "auto",
) -> dict[str, Any]:
    video = video.expanduser().resolve()
    audio = audio.expanduser().resolve()
    out = out.expanduser().resolve()
    if not video.is_file():
        raise LipSyncError(f"video missing: {video}")
    if not audio.is_file():
        raise LipSyncError(f"audio missing: {audio}")
    chosen = resolve_backend(backend)
    if chosen == "off":
        return {"ok": False, "skipped": True, "reason": "no backend / off", "backend": "off"}

    out.parent.mkdir(parents=True, exist_ok=True)
    if chosen == "external":
        run_external(video, audio, out, external_argv_template() or [])
    elif chosen == "wav2lip":
        root = wav2lip_root()
        if not root:
            raise LipSyncError("wav2lip root missing")
        run_wav2lip(video, audio, out, root)
    elif chosen == "musetalk":
        root = musetalk_root()
        if not root:
            raise LipSyncError("musetalk root missing")
        run_musetalk(video, audio, out, root)
    else:
        raise LipSyncError(f"unhandled backend {chosen}")

    return {
        "ok": True,
        "backend": chosen,
        "video": str(video),
        "audio": str(audio),
        "out": str(out),
        "bytes": out.stat().st_size,
    }


def should_lipsync_shot(shot: dict[str, Any]) -> bool:
    if "lipsync" in shot:
        return bool(shot["lipsync"])
    dsl = shot.get("dsl") or {}
    cast = dsl.get("cast") or shot.get("cast") or []
    if not cast:
        return False
    cam = dsl.get("camera") or {}
    size = str(cam.get("shot_size") or cam.get("size") or "").lower()
    talking_sizes = (
        "close-up",
        "closeup",
        "close up",
        "medium close-up",
        "medium closeup",
        "mcu",
        "cu",
        "medium",
        "medium shot",
        "ms",
    )
    if any(s in size for s in talking_sizes):
        return True
    # title keywords
    title = str(shot.get("title") or "").lower()
    return bool(any(k in title for k in ("joke", "punch", "talk", "讲", "口", "对镜")))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ai-film-grok lipsync backend")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    run_p = sub.add_parser("run")
    run_p.add_argument("--video", required=True)
    run_p.add_argument("--audio", required=True)
    run_p.add_argument("--out", required=True)
    run_p.add_argument("--backend", default="auto")
    args = p.parse_args(argv)
    try:
        if args.cmd == "doctor":
            emit(probe())
            return 0
        result = lipsync_one(
            video=Path(args.video),
            audio=Path(args.audio),
            out=Path(args.out),
            backend=args.backend,
        )
        emit(result)
        return 0 if result.get("ok") or result.get("skipped") else 2
    except LipSyncError as exc:
        emit({"ok": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
