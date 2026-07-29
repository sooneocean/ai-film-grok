from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from delivery_artifact import (
    DeliveryArtifactError,
    desktop_delivery_is_current,
    export_final_artifacts,
    resolve_final_artifact,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_mp4(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x96:d=0.2",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=stereo",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )


def test_resolve_uses_manifest_custom_final_instead_of_filename_fallback(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    custom = out / "custom-final.mp4"
    custom.write_bytes(b"reviewed-final")
    (out / "film_silent.mp4").write_bytes(b"not-reviewed")
    manifest = {
        "outputs": {
            "final_film": {
                "path": custom.name,
                "sha256": _sha256(custom),
            }
        }
    }

    artifact = resolve_final_artifact(tmp_path, manifest)

    assert artifact.path == custom
    assert artifact.sha256 == _sha256(custom)


def test_resolve_accepts_root_relative_out_path(tmp_path: Path) -> None:
    final = tmp_path / "out" / "custom-final.mp4"
    final.parent.mkdir()
    final.write_bytes(b"reviewed-final")
    manifest = {
        "outputs": {
            "final_film": {
                "path": "out/custom-final.mp4",
                "sha256": _sha256(final),
            }
        }
    }

    assert resolve_final_artifact(tmp_path, manifest).path == final


def test_resolve_rejects_tampered_final(tmp_path: Path) -> None:
    final = tmp_path / "out" / "film_final.mp4"
    final.parent.mkdir()
    final.write_bytes(b"changed")
    manifest = {
        "outputs": {
            "final_film": {
                "path": final.name,
                "sha256": hashlib.sha256(b"reviewed").hexdigest(),
            }
        }
    }

    with pytest.raises(DeliveryArtifactError, match="hash"):
        resolve_final_artifact(tmp_path, manifest)


def test_export_always_copies_manifest_final_when_silent_variant_exists(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    custom = out / "custom-final.mp4"
    _make_mp4(custom)
    silent = out / "film_silent.mp4"
    _make_mp4(silent)
    manifest = {
        "outputs": {
            "final_film": {
                "path": custom.name,
                "sha256": _sha256(custom),
            }
        }
    }
    destination = tmp_path / "export"
    destination.mkdir()

    copied = export_final_artifacts(tmp_path, manifest, destination)

    assert [path.name for path in copied] == ["custom-final.mp4", "film_silent.mp4"]
    assert _sha256(destination / "custom-final.mp4") == _sha256(custom)


def test_export_writes_hash_bound_decode_readback(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    final = out / "film_final.mp4"
    _make_mp4(final)
    manifest = {
        "outputs": {
            "final_film": {
                "path": final.name,
                "sha256": _sha256(final),
            }
        }
    }
    destination = tmp_path / "export"
    destination.mkdir()

    copied = export_final_artifacts(tmp_path, manifest, destination)

    assert copied == [destination / "film_final.mp4"]
    receipt = json.loads((destination / "delivery-readback.json").read_text(encoding="utf-8"))
    item = receipt["artifacts"][0]
    assert receipt["ok"] is True
    assert item["source_sha256"] == _sha256(final)
    assert item["copied_sha256"] == _sha256(destination / "film_final.mp4")
    assert item["hash_match"] is True
    assert item["decode"]["ok"] is True
    assert any(stream["codec_type"] == "video" for stream in item["probe"]["streams"])
    assert any(stream["codec_type"] == "audio" for stream in item["probe"]["streams"])


def test_desktop_delivery_gate_requires_current_manifest_and_readback(tmp_path: Path) -> None:
    final_sha256 = "a" * 64
    delivery = tmp_path / "delivery"
    (delivery / "成片").mkdir(parents=True)
    (delivery / "项目状态").mkdir()
    readback = delivery / "成片" / "delivery-readback.json"
    readback.write_text(
        json.dumps(
            {
                "kind": "desktop-delivery-readback",
                "ok": True,
                "artifacts": [
                    {
                        "path": "film_final.mp4",
                        "source_sha256": final_sha256,
                        "copied_sha256": final_sha256,
                        "hash_match": True,
                        "decode": {"ok": True},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = delivery / "项目状态" / "delivery-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "kind": "desktop-delivery-manifest",
                "readback": json.loads(readback.read_text(encoding="utf-8")),
            }
        ),
        encoding="utf-8",
    )
    outputs = {
        "desktop_delivery": {
            "directory": str(delivery),
            "path": str(manifest),
            "sha256": _sha256(manifest),
            "readback_path": str(readback),
            "readback_sha256": _sha256(readback),
            "final_output_sha256": final_sha256,
        }
    }

    assert desktop_delivery_is_current(outputs, {"sha256": final_sha256}) is True
    readback.write_text("{}\n", encoding="utf-8")
    assert desktop_delivery_is_current(outputs, {"sha256": final_sha256}) is False
