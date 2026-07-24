from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aifilm_grok import grok_permission_mode  # noqa: E402
from backend_lock import create_lock_entry, verify_backend_lock  # noqa: E402
from runtime_policy import verify_requirements_lock, verify_runtime_lock  # noqa: E402


class RequirementsLockTests(unittest.TestCase):
    def test_current_environment_matches_declared_requirements(self) -> None:
        lock = Path(__file__).resolve().parents[1] / "requirements.lock"
        report = verify_requirements_lock(lock)
        self.assertTrue(report["ok"], report)
        self.assertIn("numpy", report["packages"])


class DoctorConfigTests(unittest.TestCase):
    def test_permission_mode_is_read_from_ui_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.toml"
            config.write_text('[ui]\npermission_mode = "always-approve"\n', encoding="utf-8")
            self.assertEqual(grok_permission_mode(config), "always-approve")


class BackendLockTests(unittest.TestCase):
    def test_weight_and_entrypoint_hashes_must_match_and_be_explicitly_trusted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Wav2Lip"
            (root / "checkpoints").mkdir(parents=True)
            (root / "inference.py").write_text("print('safe wrapper')\n", encoding="utf-8")
            weight = root / "checkpoints" / "wav2lip_gan.pth"
            weight.write_bytes(b"test-weight")
            lock_path = Path(tmp) / "backend-lock.json"

            untrusted = create_lock_entry("wav2lip", root, trusted_weights=False)
            lock_path.write_text(json.dumps({"backends": {"wav2lip": untrusted}}), encoding="utf-8")
            self.assertFalse(verify_backend_lock("wav2lip", root, lock_path)["ok"])

            trusted = create_lock_entry("wav2lip", root, trusted_weights=True)
            lock_path.write_text(json.dumps({"backends": {"wav2lip": trusted}}), encoding="utf-8")
            self.assertTrue(verify_backend_lock("wav2lip", root, lock_path)["ok"])

            weight.write_bytes(b"changed-weight")
            changed = verify_backend_lock("wav2lip", root, lock_path)
            self.assertFalse(changed["ok"])
            self.assertTrue(any("fingerprint" in error for error in changed["errors"]))


class RuntimeLockTests(unittest.TestCase):
    def test_default_lock_discovers_new_python_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            scripts.mkdir()
            (scripts / "new_quality_gate.py").write_text("VALUE = 1\n", encoding="utf-8")
            from runtime_policy import build_runtime_lock

            report = build_runtime_lock(root)

            self.assertIn("scripts/new_quality_gate.py", report["scripts"])

    def test_script_change_invalidates_runtime_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            scripts.mkdir()
            script = scripts / "tool.py"
            script.write_text("print('v1')\n", encoding="utf-8")
            lock_path = root / "runtime-lock.json"
            from runtime_policy import build_runtime_lock

            lock_path.write_text(
                json.dumps(build_runtime_lock(root, script_paths=[script])), encoding="utf-8"
            )
            self.assertTrue(verify_runtime_lock(root, lock_path)["ok"])
            script.write_text("print('v2')\n", encoding="utf-8")
            self.assertFalse(verify_runtime_lock(root, lock_path)["ok"])


if __name__ == "__main__":
    unittest.main()
