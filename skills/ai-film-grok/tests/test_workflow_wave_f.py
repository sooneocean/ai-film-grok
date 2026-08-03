"""Wave F: agent-loop glue — advance allowlist + dispatch inject bulk/variety."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from advance import ADVANCE_ACTIONS, _validate_argv  # noqa: E402
from dispatch import structured_next_action  # noqa: E402


class AdvanceAllowlistTests(unittest.TestCase):
    def test_throughput_actions_registered(self) -> None:
        for aid in (
            "closeout-run",
            "bulk-preflight",
            "variety-precheck",
            "pilot-pack",
            "export-desktop",  # P0
        ):
            self.assertIn(aid, ADVANCE_ACTIONS)

    def test_bulk_preflight_argv_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            action = {
                "skill_id": "image.animate",
                "spend_class": "local",
                "approval_class": "none",
                "argv": ["bulk-preflight", "--root", str(root), "--no-tunnel"],
            }
            policy, argv = _validate_argv(root=root, action_id="bulk-preflight", action=action)
            self.assertEqual(policy.prefix, ("bulk-preflight",))
            self.assertEqual(argv[0], "bulk-preflight")

    def test_closeout_run_policy_is_local_none(self) -> None:
        act = structured_next_action(
            {
                "id": "closeout-run",
                "cmd": 'aifilm closeout run --root "/film"',
                "stage": "post",
            }
        )
        assert act is not None
        self.assertEqual(act["spend_class"], "local")
        self.assertEqual(act["approval_class"], "none")
        self.assertEqual(act["argv"][:2], ["closeout", "run"])

    def test_bulk_preflight_policy_is_local_none(self) -> None:
        act = structured_next_action(
            {
                "id": "bulk-preflight",
                "cmd": 'aifilm bulk-preflight --root "/film" --no-tunnel',
                "stage": "visual",
            }
        )
        assert act is not None
        self.assertEqual(act["approval_class"], "none")


class DispatchInjectSmoke(unittest.TestCase):
    def test_bulk_preflight_insert_source_exists(self) -> None:
        # static contract: dispatch source mentions Wave F bulk-preflight inject
        src = (SCRIPTS / "dispatch.py").read_text(encoding="utf-8")
        self.assertIn("Wave F", src)
        self.assertIn("bulk-preflight", src)
        self.assertIn("variety-precheck", src)


if __name__ == "__main__":
    unittest.main()
