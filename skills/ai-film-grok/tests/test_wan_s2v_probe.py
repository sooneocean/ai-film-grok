"""1:1 test for media.wan_s2v_probe (P3-1 migration + contract lock).

Migrated from scripts/wan_s2v_probe.py into the media package. The probe only
proves named ComfyUI dependencies; tests fake the HTTP layer so no network or
model load occurs.
"""
from __future__ import annotations

import pytest

from media import wan_s2v_probe

REQUIRED = wan_s2v_probe.REQUIRED_CLASS_TYPES


def test_model_names_pure():
    assert wan_s2v_probe._model_names(["a", "b "]) == {"a", "b"}
    assert wan_s2v_probe._model_names("notaseq") == set()
    assert wan_s2v_probe._model_names([1, 2]) == set()
    assert wan_s2v_probe._model_names([]) == set()


def test_probe_ready_when_deps_present(monkeypatch):
    object_info = {name: {} for name in REQUIRED}

    def fake_request(url: str, path: str):
        if path == "/object_info":
            return object_info
        if path == "/models/diffusion_models":
            return ["wan2.2_s2v_14B_fp8_scaled.safetensors"]
        if path == "/models/audio_encoders":
            return ["wav2vec2_large_english_fp16.safetensors"]
        return []

    monkeypatch.setattr(wan_s2v_probe, "_json_request", fake_request)
    monkeypatch.setattr(wan_s2v_probe, "normalize_base_url", lambda u: u)

    report = wan_s2v_probe.probe_wan_s2v("http://comfy.local")
    assert report["ok"] is True
    assert report["class_types_ready"] is True
    assert report["named_weights_present"] is True
    assert report["execution_ready"] is False
    assert report["auto_submission_blocked"] is True
    assert report["auto_download_blocked"] is True


def test_probe_reports_missing_class_type(monkeypatch):
    object_info = {"AudioEncoderLoader": {}}  # 2 of 3 required missing

    def fake_request(url: str, path: str):
        if path == "/object_info":
            return object_info
        return []

    monkeypatch.setattr(wan_s2v_probe, "_json_request", fake_request)
    monkeypatch.setattr(wan_s2v_probe, "normalize_base_url", lambda u: u)

    report = wan_s2v_probe.probe_wan_s2v("http://comfy.local")
    assert report["class_types_ready"] is False
    assert "WanSoundImageToVideo" in report["missing_class_types"]
    assert report["readiness"] == "dependency_contract_incomplete"
