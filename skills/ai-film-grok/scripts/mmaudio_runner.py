#!/usr/bin/env python3
"""Run MMAudio demo with a Windows-safe soundfile output shim."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def _save(path, audio, sample_rate, *args, **kwargs):
    import soundfile

    array = audio.detach().float().cpu().numpy()
    if array.ndim == 2:
        array = array.T
    soundfile.write(str(path), array, sample_rate, subtype="PCM_16")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: mmaudio_runner.py DEMO.PY [args ...]")
    import torchaudio

    torchaudio.save = _save
    demo = str(Path(sys.argv[1]).resolve())
    sys.argv = [demo, *sys.argv[2:]]
    runpy.run_path(demo, run_name="__main__")


if __name__ == "__main__":
    main()
