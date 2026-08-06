from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from aifilm_grok import _classify_doctor_readiness  # noqa: E402


def test_optional_lipsync_absence_does_not_fail_core_or_strict() -> None:
    report = _classify_doctor_readiness(
        core_checks={"ffmpeg": True, "requested_lipsync_backend": True},
        optional_capabilities={
            "lipsync": {
                "enabled": False,
                "requested_backend": "auto",
                "ready": False,
            }
        },
        environment_warnings=[],
    )

    assert report["ok"] is True
    assert report["strict_ok"] is True
    assert report["strict_status"] == "pass"
    assert report["strict_blocking"] is False
    assert report["core_readiness"]["failed_checks"] == []
    assert report["optional_capabilities"]["lipsync"]["ready"] is False


def test_optional_capability_warning_does_not_fail_strict() -> None:
    report = _classify_doctor_readiness(
        core_checks={"ffmpeg": True},
        optional_capabilities={
            "warnings": ["Grok OAuth not ready"],
            "grok_oauth": {"ready": False},
        },
        environment_warnings=[],
    )

    assert report["ok"] is True
    assert report["strict_ok"] is True


def test_environment_advisory_preserves_default_ok_but_fails_strict() -> None:
    report = _classify_doctor_readiness(
        core_checks={"ffmpeg": True},
        optional_capabilities={},
        environment_warnings=["global permission mode is unsafe"],
    )

    assert report["ok"] is True
    assert report["strict_ok"] is False
    assert report["strict_status"] == "advisory_only"
    assert report["strict_blocking"] is False
    assert report["environment_advisories"] == {
        "ok": False,
        "warnings": ["global permission mode is unsafe"],
        "severity": "advisory",
        "blocks_core": False,
    }


def test_core_failure_fails_default_and_strict_compatibility_fields() -> None:
    report = _classify_doctor_readiness(
        core_checks={"ffmpeg": True, "runtime_lock": False},
        optional_capabilities={},
        environment_warnings=[],
    )

    assert report["ok"] is False
    assert report["strict_ok"] is False
    assert report["strict_status"] == "blocked"
    assert report["strict_blocking"] is True
    assert report["core_readiness"]["failed_checks"] == ["runtime_lock"]
