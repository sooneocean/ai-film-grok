"""JSON stdout emit for CLI / agent consumers."""

from __future__ import annotations

import json
import os
import sys
from typing import Any


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
