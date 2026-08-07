"""Honesty-rail R3 · dual-checkout drift probe."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TestCheckoutDrift(unittest.TestCase):
    def test_missing_paths_non_git_safe(self) -> None:
        from core.checkout_drift import check_checkout_drift

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "nope-plugin"
            d = Path(tmp) / "nope-dev"
            rep = check_checkout_drift(plugin_path=p, dev_path=d)
            self.assertTrue(rep.get("ok"))
            self.assertIn(rep.get("status"), {"missing", "non_git"})

    def test_clean_matching_heads(self) -> None:
        from core import checkout_drift as cd

        with tempfile.TemporaryDirectory() as tmp:
            plugin = Path(tmp) / "plugin"
            dev = Path(tmp) / "dev"
            plugin.mkdir()
            dev.mkdir()

            def fake_run(cwd, *args, timeout=8.0):  # noqa: ANN001
                # git rev-parse --is-inside-work-tree
                if args[:2] == ("rev-parse", "--is-inside-work-tree"):
                    return 0, "true", ""
                if args[:2] == ("rev-parse", "HEAD"):
                    return 0, "abc123deadbeef", ""
                if args[:2] == ("rev-parse", "--show-toplevel"):
                    return 0, str(cwd), ""
                if args[:2] == ("status", "--porcelain"):
                    return 0, "", ""
                return 1, "", "unknown"

            with mock.patch.object(cd, "_run_git", side_effect=fake_run):
                rep = cd.check_checkout_drift(plugin_path=plugin, dev_path=dev)
            self.assertEqual(rep.get("status"), "clean")
            self.assertFalse(rep.get("warn"))
            self.assertTrue(rep.get("ok"))

    def test_head_mismatch_warns(self) -> None:
        from core import checkout_drift as cd

        with tempfile.TemporaryDirectory() as tmp:
            plugin = Path(tmp) / "plugin"
            dev = Path(tmp) / "dev"
            plugin.mkdir()
            dev.mkdir()
            heads = {str(plugin.resolve()): "aaa111", str(dev.resolve()): "bbb222"}

            def fake_run(cwd, *args, timeout=8.0):  # noqa: ANN001
                key = str(Path(cwd).resolve())
                if args[:2] == ("rev-parse", "--is-inside-work-tree"):
                    return 0, "true", ""
                if args[:2] == ("rev-parse", "HEAD"):
                    return 0, heads.get(key, "xxx"), ""
                if args[:2] == ("rev-parse", "--show-toplevel"):
                    return 0, key, ""
                if args[:2] == ("status", "--porcelain"):
                    return 0, " M dirty.py", ""
                if args[0] == "rev-list":
                    return 0, "1\t2", ""
                return 1, "", "unknown"

            with mock.patch.object(cd, "_run_git", side_effect=fake_run):
                rep = cd.check_checkout_drift(plugin_path=plugin, dev_path=dev)
            self.assertEqual(rep.get("status"), "drift")
            self.assertTrue(rep.get("warn"))
            self.assertTrue(rep.get("ok"))  # soft for doctor
            self.assertIn("NEVER hand-copy", " ".join(rep.get("next") or []))

    def test_dirty_same_head_no_warn(self) -> None:
        from core import checkout_drift as cd

        with tempfile.TemporaryDirectory() as tmp:
            plugin = Path(tmp) / "plugin"
            dev = Path(tmp) / "dev"
            plugin.mkdir()
            dev.mkdir()

            def fake_run(cwd, *args, timeout=8.0):  # noqa: ANN001
                if args[:2] == ("rev-parse", "--is-inside-work-tree"):
                    return 0, "true", ""
                if args[:2] == ("rev-parse", "HEAD"):
                    return 0, "samehead00", ""
                if args[:2] == ("rev-parse", "--show-toplevel"):
                    return 0, str(cwd), ""
                if args[:2] == ("status", "--porcelain"):
                    return 0, "?? artifacts/noise.json", ""
                return 1, "", "unknown"

            with mock.patch.object(cd, "_run_git", side_effect=fake_run):
                rep = cd.check_checkout_drift(plugin_path=plugin, dev_path=dev)
            self.assertEqual(rep.get("status"), "dirty")
            self.assertFalse(rep.get("warn"))


if __name__ == "__main__":
    unittest.main()
