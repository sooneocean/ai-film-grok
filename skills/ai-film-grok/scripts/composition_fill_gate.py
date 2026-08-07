"""Shim — implementation in gates.composition_fill_gate.

Keeps `import composition_fill_gate` / CLI `python composition_fill_gate.py` working.
"""
from __future__ import annotations

from gates.composition_fill_gate import *  # noqa: F403
from gates.composition_fill_gate import main  # noqa: F401

if __name__ == "__main__":
    raise SystemExit(main())
