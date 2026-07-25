#!/usr/bin/env python3
"""Higgs Audio adapter boundary.

Higgs releases change their inference entrypoint more often than the plugin's
control plane should.  A trusted JSON argv command is therefore required for
actual inference; this wrapper still provides a stable text/performance wire.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", nargs="?", default="synth")
    ap.add_argument("--text-file", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--voice", default="")
    ap.add_argument("--performance-file", default="")
    args = ap.parse_args()
    if args.command == "doctor":
        raw = os.environ.get("HIGGS_AUDIO_ARGV", "").strip()
        print(json.dumps({"ok": bool(raw), "argv_configured": bool(raw)}))
        return 0 if raw else 1
    raw = os.environ.get("HIGGS_AUDIO_ARGV", "").strip()
    if not raw:
        raise SystemExit("Higgs Audio requires HIGGS_AUDIO_ARGV trusted JSON inference command")
    try:
        argv = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"HIGGS_AUDIO_ARGV invalid JSON: {exc}") from exc
    if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
        raise SystemExit("HIGGS_AUDIO_ARGV must be a JSON string array")
    perf = (
        Path(args.performance_file).read_text(encoding="utf-8") if args.performance_file else "{}"
    )
    replacements = {
        "{text_file}": args.text_file,
        "{out}": args.out,
        "{voice}": args.voice,
        "{performance_file}": args.performance_file,
        "{performance_json}": perf,
    }
    command = [next((replacements.get(x, x) for x in [item]), item) for item in argv]
    p = subprocess.run(command, check=False)
    if p.returncode:
        raise SystemExit(p.returncode)
    if not Path(args.out).is_file():
        raise SystemExit("Higgs Audio command completed without producing output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
