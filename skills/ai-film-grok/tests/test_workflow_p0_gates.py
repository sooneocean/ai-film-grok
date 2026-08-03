"""P0: local no-spend gates demoted from human_required; export advance glue."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from advance import ADVANCE_ACTIONS, AdvanceError, _validate_argv  # noqa: E402
from dispatch import structured_next_action  # noqa: E402
from next_actions import _export_desktop_name  # noqa: E402


class LocalNonePolicyTests(unittest.TestCase):
    def test_export_desktop_is_local_none(self) -> None:
        act = structured_next_action(
            {
                "id": "export-desktop",
                "cmd": 'aifilm export-desktop --root "/film" --name "DemoFilm"',
                "stage": "deliver",
            }
        )
        assert act is not None
        self.assertEqual(act["spend_class"], "local")
        self.assertEqual(act["approval_class"], "none")
        self.assertEqual(act["skill_id"], "export.package")
        self.assertEqual(act["argv"][:1], ["export-desktop"])

    def test_dailies_status_is_local_none(self) -> None:
        act = structured_next_action(
            {
                "id": "dailies_review-evidence",
                "cmd": 'aifilm dailies status --root "/film"',
                "stage": "post",
            }
        )
        assert act is not None
        self.assertEqual(act["approval_class"], "none")
        self.assertEqual(act["spend_class"], "local")

    def test_pilot_pack_space_and_hyphen_are_local_none(self) -> None:
        for cmd in (
            'aifilm pilot pack --root "/film"',
            'aifilm pilot-pack --root "/film"',
        ):
            act = structured_next_action({"id": "pilot-pack", "cmd": cmd, "stage": "agent"})
            assert act is not None, cmd
            self.assertEqual(act["approval_class"], "none", cmd)
            self.assertEqual(act["spend_class"], "local", cmd)

    def test_pilot_approve_stays_human(self) -> None:
        act = structured_next_action(
            {
                "id": "pilot-approve",
                "cmd": 'aifilm pilot approve --root "/film" --user-phrase "pilot 过"',
                "stage": "agent",
            }
        )
        assert act is not None
        self.assertEqual(act["approval_class"], "human_required")

    def test_review_final_stays_human(self) -> None:
        act = structured_next_action(
            {
                "id": "review-final",
                "cmd": (
                    'aifilm review-final --root "/film" --approve --reviewer you '
                    "--score-identity pass"
                ),
                "stage": "post",
            }
        )
        assert act is not None
        self.assertEqual(act["approval_class"], "human_required")

    def test_export_placeholder_name_not_structured(self) -> None:
        act = structured_next_action(
            {
                "id": "export-desktop",
                "cmd": 'aifilm export-desktop --root "/film" --name "<中文名>"',
            }
        )
        self.assertIsNone(act)


class AdvanceExportAllowlistTests(unittest.TestCase):
    def test_export_desktop_registered(self) -> None:
        self.assertIn("export-desktop", ADVANCE_ACTIONS)
        self.assertEqual(ADVANCE_ACTIONS["export-desktop"].prefix, ("export-desktop",))

    def test_export_desktop_argv_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            action = {
                "skill_id": "export.package",
                "spend_class": "local",
                "approval_class": "none",
                "argv": ["export-desktop", "--root", str(root), "--name", "DemoFilm"],
            }
            policy, argv = _validate_argv(root=root, action_id="export-desktop", action=action)
            self.assertEqual(policy.prefix, ("export-desktop",))
            self.assertEqual(argv[0], "export-desktop")

    def test_export_desktop_rejects_force_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            action = {
                "skill_id": "export.package",
                "spend_class": "local",
                "approval_class": "none",
                "argv": [
                    "export-desktop",
                    "--root",
                    str(root),
                    "--name",
                    "DemoFilm",
                    "--force",
                ],
            }
            with self.assertRaises(AdvanceError):
                _validate_argv(root=root, action_id="export-desktop", action=action)

    def test_pilot_pack_hyphen_argv_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            action = {
                "skill_id": "quality.inspect",
                "spend_class": "local",
                "approval_class": "none",
                "argv": ["pilot-pack", "--root", str(root)],
            }
            policy, argv = _validate_argv(root=root, action_id="pilot-pack", action=action)
            self.assertEqual(policy.prefix, ("pilot-pack",))
            self.assertEqual(argv[0], "pilot-pack")


class ExportNameHelperTests(unittest.TestCase):
    def test_export_name_from_film_spec_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text(
                '{"title": "财阀家的规则 MAX"}\n',
                encoding="utf-8",
            )
            self.assertEqual(_export_desktop_name(root), "财阀家的规则-MAX")

    def test_export_name_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_export_desktop_name(Path(tmp)), "GrokFilm")


if __name__ == "__main__":
    unittest.main()
