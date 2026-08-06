"""Motion/FRW CLI — extracted from aifilm_grok (public cmd strings unchanged).

Uses scripts/core for film IO/emit/gates (no hub cycle for basic IO).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from util.errors import FilmError


def add_motion_ops_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
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
            "High-motion product gate (soft≥10 medium≥16 normal≥18 meat≥20); "
            "--root auto-fills DF from film-spec; writes audit+final-gate"
        ),
    )
    img.add_argument(
        "--rows",
        required=False,
        default=None,
        help=(
            "Optional JSON list of {id,heat_phase,mean|mean_absdiff"
            "[,dramatic_function,wardrobe_state,tier,source]}; "
            "omit when using --root auto-collect"
        ),
    )
    img.add_argument(
        "--root",
        default=None,
        help="Film root: auto-collect rows from film-spec + means; required for --write",
    )
    img.add_argument(
        "--write",
        action="store_true",
        help="Write receipts (default on when only --root is passed)",
    )
    img.add_argument("--raw-incomplete", action="store_true")
    img.add_argument("--kb-fallback", action="store_true")
    img.add_argument("--style-fail", action="store_true")

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

def cmd_frw(args: argparse.Namespace) -> int:
    """Proxy to local frwclaw-pro dispatch (bulk 2V preferred path).

    Special: ``frw canary`` → scripts/frw_canary.py (key capability receipt).
    """
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    # New structure: scripts/frw_dispatch.py; fallback to media/ for compat.
    launcher = Path(__file__).resolve().parents[1] / "frw_dispatch.py"
    if not launcher.is_file():
        launcher = Path(__file__).resolve().parents[1] / "media" / "frw_dispatch.py"
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


def cmd_frw_lipsync(args: argparse.Namespace) -> int:
    """FRW cloud lipsync (ltx/wan/seedance) — probe or run face+audio."""
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401
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
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    try:
        rep = env_plate(args)
    except MotionRouteError as exc:
        raise FilmError(str(exc)) from exc
    emit(rep)
    return 0 if rep.get("ok") else 1


def cmd_motion_plan(args: argparse.Namespace) -> int:
    """Compile a panel-animation shot into a deterministic motion plan."""
    from cli_motion import MotionRouteError, motion_plan
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    try:
        rep = motion_plan(args)
    except MotionRouteError as exc:
        raise FilmError(str(exc)) from exc
    emit(rep)
    return 0


def cmd_i2v_motion_gate(args: argparse.Namespace) -> int:
    """High-motion audit + final gate (rows JSON and/or --root auto DF enrich)."""
    import json as _json

    from cli_motion import i2v_motion_gate_from_rows
    from core.constants import MANIFEST_NAME  # noqa: F401
    from core.emit import emit
    from core.film_io import (  # noqa: F401
        empty_manifest,
        ensure_tree,
        load_director_notes,
        load_manifest,
        save_director_notes,
        save_manifest,
    )
    from core.gates import recompute_gates  # noqa: F401

    rows_path = getattr(args, "rows", None) or getattr(args, "from_json", None)
    root = getattr(args, "root", None)
    shots: list = []
    auto = False
    if rows_path:
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
    elif root:
        auto = True
    else:
        raise FilmError(
            "i2v-motion-gate requires --rows JSON or --root "
            "(auto: film-spec DF/wardrobe + takes/audit means)"
        )
    # --root alone defaults to writing receipts (agent loop)
    write = bool(getattr(args, "write", False)) or (auto and not rows_path)
    rep = i2v_motion_gate_from_rows(
        shots,
        root=root,
        write_receipts=write,
        raw_complete=not bool(getattr(args, "raw_incomplete", False)),
        kb_fallback=bool(getattr(args, "kb_fallback", False)),
        style_ok=not bool(getattr(args, "style_fail", False)),
        auto_from_root=auto,
    )
    emit(rep)
    return 0 if rep.get("ok") else 1

