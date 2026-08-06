"""Wave G: pilot-approved bulk requires bulk-preflight (fail closed)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

pytestmark = pytest.mark.hotpath

from media_queue import MediaQueue, QueueError  # noqa: E402
from workflow_pack import WorkflowPackError  # noqa: E402


def _seed(root: Path) -> tuple[Path, Path]:
    (root / "receipts").mkdir(parents=True, exist_ok=True)
    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "g",
                "heat_scale": "soft",
                "scenes": [
                    {
                        "shots": [
                            {
                                "id": "shot01",
                                "nar": "一",
                                "duration_sec": 6,
                                "dsl": {"subject": "a", "action": "b", "motion": "c"},
                            }
                        ]
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "manifest.json").write_text("{}", encoding="utf-8")
    prompt = root / "p.txt"
    prompt.write_text("x", encoding="utf-8")
    img = root / "i.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    return prompt, img


class BulkPreflightHardGateTests(unittest.TestCase):
    def test_pilot_approved_blocks_when_preflight_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt, img = _seed(root)
            (root / "receipts" / "pilot-approval.json").write_text(
                json.dumps(
                    {
                        "approved": True,
                        "approved_by": "user",
                        "shots": ["shot01"],
                        "notes": "pilot 过",
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch("media_queue.assert_pilot_allows_add", return_value={"ok": True}):
                with mock.patch("media_queue.assert_heat_allows_media", return_value={"ok": True}):
                    with mock.patch(
                        "media_queue.build_shot_contract",
                        return_value={"ok": True, "errors": []},
                    ):
                        with mock.patch(
                            "media_queue.canonical_contract_required",
                            return_value=False,
                        ):
                            with mock.patch(
                                "workflow_pack.assert_bulk_preflight",
                                side_effect=WorkflowPackError("bulk preflight failed: pilot"),
                            ):
                                q = MediaQueue(root, budget_units=5)
                                with self.assertRaises(QueueError) as ctx:
                                    q.add_job(
                                        shot_id="shot01",
                                        operation="image_to_video",
                                        prompt_file=prompt,
                                        inputs=[img],
                                        allow_without_pilot=False,
                                    )
                                self.assertIn("bulk preflight", str(ctx.exception).lower())

    def test_allow_without_pilot_skips_hard_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt, img = _seed(root)
            called = {"n": 0}

            def _boom(*_a, **_k):
                called["n"] += 1
                raise AssertionError("preflight must not run")

            with mock.patch("media_queue.assert_pilot_allows_add", return_value={"ok": True}):
                with mock.patch("media_queue.assert_heat_allows_media", return_value={"ok": True}):
                    with mock.patch(
                        "media_queue.build_shot_contract",
                        return_value={"ok": True, "errors": []},
                    ):
                        with mock.patch(
                            "media_queue.canonical_contract_required",
                            return_value=False,
                        ):
                            with mock.patch(
                                "workflow_pack.assert_bulk_preflight",
                                side_effect=_boom,
                            ):
                                q = MediaQueue(root, budget_units=5)
                                try:
                                    q.add_job(
                                        shot_id="shot01",
                                        operation="image_to_video",
                                        prompt_file=prompt,
                                        inputs=[img],
                                        allow_without_pilot=True,
                                    )
                                except Exception:
                                    pass
                                self.assertEqual(called["n"], 0)


if __name__ == "__main__":
    unittest.main()
