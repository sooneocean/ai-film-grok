#!/usr/bin/env python3
"""DEPRECATED stub — use cosyvoice_tts.py (HTTP production adapter).

Wire into ai-film-grok:
  AIFILM_TTS_BACKEND=external
  COSYVOICE_BASE_URL=http://127.0.0.1:9880
  COSYVOICE_REF_WAV=/path/to/heroine_ref.wav
  AIFILM_TTS_ARGV='["python3","$HOME/.grok/skills/ai-film-grok/scripts/adapters/cosyvoice_tts.py","--text-file","{text_file}","--out","{out}","--voice","{voice}"]'

One character = one --ref / COSYVOICE_REF_WAV (10–30s clean speech). Never change ref mid-film.
See references/opensource-tts.md and references/voices.md.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

# Prefer the production HTTP adapter in the same directory.
_prod = Path(__file__).resolve().parent / "cosyvoice_tts.py"
if _prod.is_file():
    sys.argv[0] = str(_prod)
    runpy.run_path(str(_prod), run_name="__main__")
else:
    raise SystemExit(
        "Install CosyVoice2 HTTP server and use adapters/cosyvoice_tts.py.\n"
        "This example file only forwards to cosyvoice_tts.py."
    )
