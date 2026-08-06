"""Narrow HTTPS-only download boundary for completed cloud video artifacts."""

from __future__ import annotations

import http.client
import ipaddress
import os
import socket
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from security_policy import SecurityPolicyError, safe_output_path, safe_workspace_directory
from util import sha256_file

MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024
MAX_REDIRECTS = 3
_SENSITIVE_QUERY_KEYS = frozenset(
    {"api_key", "apikey", "authorization", "credential", "key", "secret", "signature", "token"}
)


class CloudMediaDownloadError(ValueError):
    """A provider artifact is not safe to download into the workspace."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, *, pinned_ip: str, **kwargs: object) -> None:
        super().__init__(host, **kwargs)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        if self._tunnel_host:
            self._tunnel()
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


class _PinnedHTTPSHandler(HTTPSHandler):
    def __init__(self, pinned_ip: str) -> None:
        super().__init__()
        self._pinned_ip = pinned_ip

    def https_open(self, req: Request):  # type: ignore[override]
        return self.do_open(
            lambda host, **kwargs: _PinnedHTTPSConnection(
                host, pinned_ip=self._pinned_ip, **kwargs
            ),
            req,
        )


def _validate_url(value: str) -> tuple[str, str]:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise CloudMediaDownloadError("cloud artifact must use a credential-free HTTPS URL")
    for key, _value in parse_qsl(parsed.query, keep_blank_values=True):
        normalized = key.lower().replace("-", "_")
        if normalized in _SENSITIVE_QUERY_KEYS:
            raise CloudMediaDownloadError(
                "cloud artifact URL must not contain credential parameters"
            )
    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError:
        pass
    else:
        raise CloudMediaDownloadError("cloud artifact URL may not use an IP-literal host")
    try:
        resolved = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise CloudMediaDownloadError("cloud artifact hostname could not be resolved") from exc
    if not resolved:
        raise CloudMediaDownloadError("cloud artifact hostname did not resolve publicly")
    public_ips: list[str] = []
    for _family, _socktype, _proto, _canon, address in resolved:
        ip = ipaddress.ip_address(address[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise CloudMediaDownloadError(
                "cloud artifact hostname resolves to a non-public address"
            )
        public_ips.append(str(ip))
    return value, public_ips[0]


def download_cloud_video(root: Path | str, *, candidate_id: str, url: str) -> dict[str, object]:
    """Fetch one public video URL without retaining the URL in project receipts."""
    base = Path(root).expanduser().resolve()
    try:
        output_root = safe_workspace_directory(base, "outputs", field="cloud output directory")
    except SecurityPolicyError as exc:
        raise CloudMediaDownloadError(str(exc)) from exc
    output_root.mkdir(parents=True, exist_ok=True)
    destination_dir = output_root / "cloud-candidates"
    if destination_dir.is_symlink():
        raise CloudMediaDownloadError("cloud output directory may not be a symbolic link")
    destination_dir.mkdir(exist_ok=True)
    try:
        destination = safe_output_path(
            destination_dir,
            f"{candidate_id}.mp4",
            suffixes={".mp4"},
            field="cloud candidate output",
        )
    except SecurityPolicyError as exc:
        raise CloudMediaDownloadError(str(exc)) from exc

    current, pinned_ip = _validate_url(url)
    if destination.exists() or destination.is_symlink():
        raise CloudMediaDownloadError("cloud candidate output already exists")
    partial = destination.with_name(f".{destination.name}.partial")
    if partial.exists() or partial.is_symlink():
        raise CloudMediaDownloadError("cloud candidate partial output already exists")
    try:
        for _redirect in range(MAX_REDIRECTS + 1):
            opener = build_opener(_NoRedirect(), _PinnedHTTPSHandler(pinned_ip))
            try:
                response = opener.open(Request(current, headers={"Accept": "video/*"}), timeout=30)
            except HTTPError as exc:
                if exc.code not in {301, 302, 303, 307, 308}:
                    raise CloudMediaDownloadError(
                        "cloud artifact download returned an HTTP error"
                    ) from exc
                location = exc.headers.get("Location")
                if not location:
                    raise CloudMediaDownloadError(
                        "cloud artifact redirect has no location"
                    ) from exc
                current, pinned_ip = _validate_url(urljoin(current, location))
                continue
            with response:
                content_type = str(response.headers.get("Content-Type") or "").lower()
                if not content_type.startswith("video/mp4"):
                    raise CloudMediaDownloadError("cloud artifact response is not video media")
                if (
                    str(response.headers.get("Content-Encoding") or "identity").lower()
                    != "identity"
                ):
                    raise CloudMediaDownloadError(
                        "cloud artifact response must not be content encoded"
                    )
                declared = response.headers.get("Content-Length")
                if declared is not None and (
                    not declared.isdigit() or int(declared) > MAX_DOWNLOAD_BYTES
                ):
                    raise CloudMediaDownloadError("cloud artifact exceeds download size limit")
                total = 0
                descriptor = os.open(
                    partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
                )
                with os.fdopen(descriptor, "wb") as handle:
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > MAX_DOWNLOAD_BYTES:
                            raise CloudMediaDownloadError(
                                "cloud artifact exceeds download size limit"
                            )
                        handle.write(chunk)
                if total < 10_000:
                    raise CloudMediaDownloadError("cloud artifact is unexpectedly small")
                with partial.open("rb") as handle:
                    prefix = handle.read(12)
                if len(prefix) < 12 or prefix[4:8] != b"ftyp":
                    raise CloudMediaDownloadError("cloud artifact does not have an MP4 signature")
                try:
                    os.link(partial, destination, follow_symlinks=False)
                except FileExistsError as exc:
                    raise CloudMediaDownloadError("cloud candidate output already exists") from exc
                partial.unlink()
                return {
                    "path": str(destination.relative_to(base)),
                    "sha256": sha256_file(destination),
                    "bytes": total,
                    "content_type": content_type.split(";", 1)[0],
                    "hostname": urlparse(current).hostname,
                    "redirects": _redirect,
                }
        raise CloudMediaDownloadError("cloud artifact exceeded redirect limit")
    except (OSError, URLError) as exc:
        raise CloudMediaDownloadError("cloud artifact download failed") from exc
    finally:
        partial.unlink(missing_ok=True)
