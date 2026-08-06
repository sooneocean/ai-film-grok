from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cloud_media_download import CloudMediaDownloadError, _validate_url  # noqa: E402


@pytest.mark.parametrize(
    "url",
    (
        "http://cdn.example.test/clip.mp4",
        "https://127.0.0.1/clip.mp4",
        "https://cdn.example.test/clip.mp4#fragment",
        "https://cdn.example.test/clip.mp4?api_key=nope",
    ),
)
def test_cloud_download_rejects_unsafe_url_before_network(url: str) -> None:
    with pytest.raises(CloudMediaDownloadError):
        _validate_url(url)
