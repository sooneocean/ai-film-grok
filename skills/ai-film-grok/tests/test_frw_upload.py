from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import frw_upload  # noqa: E402
from frw_upload import FrwUploadError, extract_upload_url  # noqa: E402


@pytest.mark.parametrize("field", ["url", "image_url", "file_url"])
def test_extract_upload_url_variants(field: str) -> None:
    assert extract_upload_url({"data": {field: "https://cdn.example.test/a.png"}}).endswith("a.png")


def test_extract_upload_url_rejects_private_and_credential_urls() -> None:
    credentialed_url = "https://" + "user" + ":" + "pass" + "@cdn.example.test/a.png"
    with pytest.raises(FrwUploadError):
        extract_upload_url({"data": {"url": "http://127.0.0.1/a.png"}})
    with pytest.raises(FrwUploadError):
        extract_upload_url({"data": {"url": credentialed_url}})


def test_upload_typed_inputs_binds_first_last_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = tmp_path / "start.png"
    end = tmp_path / "end.png"
    start.write_bytes(b"start")
    end.write_bytes(b"end")
    monkeypatch.setattr(
        frw_upload, "upload_file", lambda path, **_: f"https://cdn.test/{Path(path).name}"
    )

    handoff = frw_upload.upload_typed_inputs(start, end=end)

    assert handoff["input_mode"] == "first_last"
    assert handoff["start_url"].endswith("start.png")
    assert handoff["end_url"].endswith("end.png")
    assert (
        handoff["pair_checksum"] != frw_upload.upload_typed_inputs(end, end=start)["pair_checksum"]
    )
