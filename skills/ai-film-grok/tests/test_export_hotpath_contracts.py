"""M3 · export hotpath contracts (fast — no ffmpeg / no slow marker).

Fail-closed surfaces for designed-post export:

- missing plate / package → ComposeExportError (not silent empty)
- resolve_compose_preset rejects unknown garbage
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

pytestmark = pytest.mark.hotpath

from export_composition import (  # noqa: E402
    ComposeExportError,
    export_composition,
    resolve_compose_preset,
)


class ExportHotpathContracts(unittest.TestCase):
    def test_resolve_compose_preset_rejects_garbage(self) -> None:
        with self.assertRaises(ComposeExportError):
            resolve_compose_preset({}, preset="not-a-real-preset-xyz")

    def test_resolve_compose_preset_auto_minimal(self) -> None:
        got = resolve_compose_preset({}, preset="auto")
        self.assertIn(got, {"minimal", "ecchi-rnb"})

    def test_export_missing_root_content_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ComposeExportError):
                export_composition(root, engine="hyperframes")


if __name__ == "__main__":
    unittest.main()
