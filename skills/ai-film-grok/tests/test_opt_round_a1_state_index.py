"""A1 · state_index wardrobe_ladder ImportError must not silent-skip."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TestWardrobeLadderImportFailClosed(unittest.TestCase):
    def test_import_error_hard_on_non_full(self) -> None:
        from state_index_gate import run_state_index_check

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text(
                json.dumps(
                    {
                        "heat_scale": "max",
                        "scenes": [
                            {
                                "shots": [
                                    {
                                        "id": "s1",
                                        "wardrobe_state": "bare",
                                        "heroine_ids": ["hero"],
                                    }
                                ]
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (root / "style-bible.json").write_text("{}", encoding="utf-8")
            (root / "manifest.json").write_text(
                json.dumps({"clips": {}}), encoding="utf-8"
            )

            real_import = __import__

            def boom(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
                if name == "wardrobe_ladder" or (
                    name.startswith("wardrobe_ladder")
                ):
                    raise ImportError("no wardrobe_ladder")
                return real_import(name, globals, locals, fromlist, level)

            with mock.patch("builtins.__import__", side_effect=boom):
                rep = run_state_index_check(root)
            hard = rep.get("hard") or []
            codes = {str(h.get("code")) for h in hard if isinstance(h, dict)}
            self.assertIn(
                "WARDROBE_LADDER_MODULE_MISSING",
                codes,
                msg=f"codes={codes} hard={hard[:6]} soft={rep.get('soft')}",
            )
            self.assertFalse(rep.get("ok"), msg="non-full + missing module must not ok")


if __name__ == "__main__":
    unittest.main()
