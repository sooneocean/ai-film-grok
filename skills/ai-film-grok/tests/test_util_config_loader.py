"""C6.4 base contracts for util.config_loader (env resolve + cache fingerprint)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import util.config_loader as cl  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_config_cache():
    cl._CONFIG = None
    cl._CONFIG_ENV_FINGERPRINT = None
    yield
    cl._CONFIG = None
    cl._CONFIG_ENV_FINGERPRINT = None


def test_env_prefers_primary_over_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRIMARY_KEY", "  primary  ")
    monkeypatch.setenv("ALIAS_KEY", "alias")
    assert cl._env("PRIMARY_KEY", "ALIAS_KEY") == "primary"


def test_env_falls_back_to_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PRIMARY_KEY", raising=False)
    monkeypatch.setenv("ALIAS_KEY", "alias")
    assert cl._env("PRIMARY_KEY", "ALIAS_KEY") == "alias"


def test_env_missing_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_SUCH_ENV_AIFILM_XYZ", raising=False)
    assert cl._env("NO_SUCH_ENV_AIFILM_XYZ") == ""


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1", True),
        ("true", True),
        ("YES", True),
        ("on", True),
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
        ("", None),
    ],
)
def test_env_bool(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool | None
) -> None:
    key = "AIFILM_TEST_BOOL_CFG"
    if raw == "":
        monkeypatch.delenv(key, raising=False)
    else:
        monkeypatch.setenv(key, raw)
    assert cl._env_bool(key) is expected


def test_env_int_valid_and_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFILM_TEST_INT_CFG", "42")
    assert cl._env_int("AIFILM_TEST_INT_CFG") == 42
    monkeypatch.setenv("AIFILM_TEST_INT_CFG", "nope")
    assert cl._env_int("AIFILM_TEST_INT_CFG") is None
    monkeypatch.delenv("AIFILM_TEST_INT_CFG", raising=False)
    assert cl._env_int("AIFILM_TEST_INT_CFG") is None


def test_resolve_bool_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIFILM_TEST_RESOLVE_BOOL", raising=False)
    assert cl._resolve_bool("AIFILM_TEST_RESOLVE_BOOL", default=True) is True
    monkeypatch.setenv("AIFILM_TEST_RESOLVE_BOOL", "0")
    assert cl._resolve_bool("AIFILM_TEST_RESOLVE_BOOL", default=True) is False


def test_resolve_int_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIFILM_TEST_RESOLVE_INT", raising=False)
    assert cl._resolve_int("AIFILM_TEST_RESOLVE_INT", default=7) == 7
    monkeypatch.setenv("AIFILM_TEST_RESOLVE_INT", "9")
    assert cl._resolve_int("AIFILM_TEST_RESOLVE_INT", default=7) == 9


def test_get_config_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFILM_TTS_BACKEND", "edge")
    monkeypatch.setenv("AIFILM_I2V_PROFILE", "grok_primary")
    cfg = cl.get_config()
    assert cfg.tts_backend == "edge"
    assert cfg.i2v_profile == "grok_primary"


def test_get_config_cache_invalidates_on_env_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AIFILM_TTS_BACKEND", "mimo")
    first = cl.get_config()
    assert first.tts_backend == "mimo"
    # same fingerprint → same object
    second = cl.get_config()
    assert second is first
    monkeypatch.setenv("AIFILM_TTS_BACKEND", "edge")
    third = cl.get_config()
    assert third is not first
    assert third.tts_backend == "edge"


def test_load_config_dict_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFILM_TTS_BACKEND", "edge")
    data = cl.load_config()
    assert isinstance(data, dict)
    assert data.get("tts_backend") == "edge"
    # root arg is accepted but ignored (secrets not switched by film path)
    data2 = cl.load_config(root=Path("/tmp/not-a-film-root-for-config"))
    assert data2.get("tts_backend") == "edge"


def test_generate_example_contains_safety_header() -> None:
    text = cl.generate_example()
    assert "Never commit config.env" in text
    assert "AIFILM_TTS_BACKEND" in text


def test_config_env_fingerprint_stable_sort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFILM_Z_TEST", "1")
    monkeypatch.setenv("AIFILM_A_TEST", "2")
    fp = cl._config_env_fingerprint()
    keys = [k for k, _ in fp if k.startswith("AIFILM_")]
    assert keys == sorted(keys)
