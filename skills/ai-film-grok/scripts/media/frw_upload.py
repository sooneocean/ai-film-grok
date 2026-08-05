"""Typed, URL-safe FRW upload handoff used only by fallback providers."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import subprocess
import sys
import urllib.parse
from pathlib import Path


class FrwUploadError(RuntimeError):
    pass


def sha256_file(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).expanduser().resolve().open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _public_http_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise FrwUploadError("FRW upload response did not contain a public HTTP(S) URL")
    if parsed.username or parsed.password:
        raise FrwUploadError("FRW upload URL contains credentials")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "127.0.0.1", "::1"}:
        raise FrwUploadError("FRW upload URL points to localhost")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (address.is_private or address.is_loopback or address.is_link_local):
        raise FrwUploadError("FRW upload URL points to a private or link-local address")
    return url


def extract_upload_url(payload: object) -> str:
    """Accept the provider's url/image_url/file_url response variants."""
    candidates: list[object] = []
    if isinstance(payload, dict):
        data = payload.get("data")
        candidates.extend((payload.get("url"), payload.get("image_url"), payload.get("file_url")))
        if isinstance(data, dict):
            candidates.extend((data.get("url"), data.get("image_url"), data.get("file_url")))
            nested = data.get("data")
            if isinstance(nested, dict):
                candidates.extend(
                    (nested.get("url"), nested.get("image_url"), nested.get("file_url"))
                )
    for candidate in candidates:
        if candidate:
            return _public_http_url(candidate)
    raise FrwUploadError("FRW upload response missing data.url, data.image_url, or data.file_url")


def upload_file(path: Path | str, *, category: str = "image") -> str:
    """Run the FRW upload primitive without leaking its URL into receipts."""
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.is_symlink():
        raise FrwUploadError(f"upload input is not a regular file: {source}")
    launcher = Path(__file__).resolve().parent.parent / "frw_dispatch.py"
    probe = subprocess.run(
        [
            sys.executable,
            str(launcher),
            "upload-probe",
            "--file-path",
            str(source),
            "--category",
            category,
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if probe.returncode != 0:
        raise FrwUploadError(
            (probe.stderr or probe.stdout or "FRW upload authorization probe failed").strip()[:300]
        )
    proc = subprocess.run(
        [
            sys.executable,
            str(launcher),
            "upload",
            "--file-path",
            str(source),
            "--category",
            category,
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    payload = None
    for line in reversed(lines):
        try:
            payload = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "FRW upload failed").strip()[:300]
        raise FrwUploadError(detail)
    return extract_upload_url(payload)


def upload_typed_inputs(
    start: Path | str,
    *,
    end: Path | str | None = None,
    category: str = "image",
) -> dict[str, object]:
    """Upload typed I2I or first-last inputs and return checksum-bound handoff data.

    URLs remain transient caller data; the returned lineage is safe to persist after
    removing ``start_url``/``end_url``.  A pair checksum binds ordering and prevents
    a swapped first/last frame from masquerading as the same shot.
    """
    start_path = Path(start).expanduser().resolve()
    start_sha = sha256_file(start_path)
    start_url = upload_file(start_path, category=category)
    result: dict[str, object] = {
        "input_mode": "first_last" if end is not None else "i2i",
        "start_sha256": start_sha,
        "start_url": start_url,
    }
    if end is not None:
        end_path = Path(end).expanduser().resolve()
        end_sha = sha256_file(end_path)
        result.update(
            {
                "end_sha256": end_sha,
                "end_url": upload_file(end_path, category=category),
                "pair_checksum": hashlib.sha256(f"{start_sha}:{end_sha}".encode()).hexdigest(),
            }
        )
    return result
