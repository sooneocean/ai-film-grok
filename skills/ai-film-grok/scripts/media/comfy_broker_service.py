#!/usr/bin/env python3
"""Loopback-only authenticated gateway for a single private ComfyUI worker.

The broker deliberately exposes no global mutation endpoints.  It is intended
to be reached only through an SSH local forward, never directly from the LAN.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

_WEAPON_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,95}$")
_PROMPT_ID = re.compile(r"^[0-9a-f-]{16,64}$")
_READ_EXACT = frozenset({"/system_stats", "/features", "/queue", "/object_info"})
_READ_PREFIXES = ("/models/", "/object_info/", "/history/", "/view", "/pysssss/metadata/")


def _token() -> str:
    value = str(os.environ.get("AIFILM_COMFY_BROKER_TOKEN") or "")
    if len(value) < 32:
        raise RuntimeError("AIFILM_COMFY_BROKER_TOKEN must be at least 32 characters")
    return value


def _upstream() -> str:
    value = str(os.environ.get("AIFILM_COMFY_BROKER_UPSTREAM", "http://127.0.0.1:8188")).rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("AIFILM_COMFY_BROKER_UPSTREAM must be loopback HTTP")
    return value


def _allowed_weapon_ids() -> frozenset[str]:
    raw = str(os.environ.get("AIFILM_COMFY_BROKER_WEAPON_IDS") or "")
    values = frozenset(part.strip() for part in raw.split(",") if part.strip())
    if not values or any(not _WEAPON_ID.fullmatch(value) for value in values):
        raise RuntimeError("AIFILM_COMFY_BROKER_WEAPON_IDS must list registered weapon ids")
    return values


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _authorized(request: Request) -> None:
    supplied = request.headers.get("authorization") or ""
    if not secrets.compare_digest(supplied, f"Bearer {_token()}"):
        raise HTTPException(status_code=401, detail="unauthorized")


def _safe_read_path(path: str) -> bool:
    return path in _READ_EXACT or path.startswith(_READ_PREFIXES)


def _proxy(
    method: str,
    path: str,
    *,
    query: str = "",
    body: bytes | None = None,
    content_type: str | None = None,
) -> Response:
    target = f"{_upstream()}{path}" + (f"?{query}" if query else "")
    headers = {"Accept": "*/*"}
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(target, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return Response(
                content=response.read(),
                status_code=response.status,
                media_type=response.headers.get_content_type(),
            )
    except urllib.error.HTTPError as exc:
        return Response(content=exc.read(), status_code=exc.code, media_type="application/json")
    except (OSError, urllib.error.URLError) as exc:
        raise HTTPException(status_code=502, detail="ComfyUI upstream unavailable") from exc


@app.get("/health")
async def health(request: Request) -> dict[str, Any]:
    _authorized(request)
    return {"ok": True, "kind": "aifilm-comfy-broker", "upstream": "loopback"}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def gateway(path: str, request: Request) -> Response:
    _authorized(request)
    normalized = "/" + path
    if request.method == "GET":
        if not _safe_read_path(normalized):
            raise HTTPException(status_code=403, detail="endpoint is not broker-allowed")
        return _proxy("GET", normalized, query=request.url.query)
    if request.method == "POST" and normalized == "/upload/image":
        body = await request.body()
        if not body or len(body) > 512 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="upload size is invalid")
        return _proxy(
            "POST", normalized, body=body, content_type=request.headers.get("content-type")
        )
    if request.method == "POST" and normalized == "/prompt":
        weapon_id = request.headers.get("x-aifilm-weapon-id") or ""
        claimed_sha = request.headers.get("x-aifilm-workflow-sha256") or ""
        if weapon_id not in _allowed_weapon_ids() or not _WEAPON_ID.fullmatch(weapon_id):
            raise HTTPException(status_code=403, detail="registered weapon id is required")
        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="prompt body must be JSON") from exc
        graph = payload.get("prompt") if isinstance(payload, dict) else None
        client_id = str(payload.get("client_id") or "") if isinstance(payload, dict) else ""
        if not isinstance(graph, Mapping) or not graph or not client_id.startswith("aifilm-"):
            raise HTTPException(status_code=400, detail="invalid armory prompt envelope")
        if not secrets.compare_digest(claimed_sha.lower(), _canonical_sha256(graph)):
            raise HTTPException(status_code=400, detail="workflow checksum mismatch")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return _proxy("POST", normalized, body=body, content_type="application/json")
    # In particular: /interrupt, /free and POST /queue remain unreachable.
    raise HTTPException(status_code=403, detail="endpoint is not broker-allowed")
