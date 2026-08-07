"""FastAPI gateway for the localhost review / selection console.

This is the *framework* layer promised by the web-console plan.  It does NOT
re-implement any rule: every security primitive (token compare, loopback
origin check, path-escape media resolution, hash-bound selection) and every
business action (gate aggregation, asset listing, selection) is delegated to
the *same* modules the stdlib ``review_ui.py`` server uses — ``web_core``,
``gate_panel``, ``asset_picker``.  Swapping the transport
(``ThreadingHTTPServer`` -> ``FastAPI``/``uvicorn``) therefore cannot change a
single security or domain behaviour.

The only new runtime dependency is FastAPI + uvicorn, already pinned in
``requirements.lock``.
"""

from __future__ import annotations

import json
import mimetypes
import socket
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from web_core import (
    WebConsoleConflict,
    WebConsoleError,
    WebConsoleForbidden,
    generate_token,
    loopback_origin_ok,
    safe_media_path,
    token_matches,
)

MAX_BODY = 128 * 1024
VALID_KINDS = ("bgm", "character", "voice", "shot")


def _console_html() -> bytes:
    return (Path(__file__).resolve().parent / "web" / "console.html").read_bytes()


def _media_response(path: Path, request: Request) -> Response:
    """Range-aware media streaming; behaviour mirrors ``review_ui._media``."""
    size = path.stat().st_size
    start, end = 0, size - 1
    status = 200
    raw = request.headers.get("Range")
    if raw:
        try:
            unit, value = raw.split("=", 1)
            left, right = value.split("-", 1)
            if unit != "bytes":
                raise ValueError
            start = int(left) if left else max(0, size - int(right))
            end = int(right) if right else size - 1
            if start < 0 or end < start or start >= size:
                raise ValueError
            end = min(end, size - 1)
            status = 206
        except ValueError:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    body = path.read_bytes()[start : end + 1]
    headers = {
        "Content-Type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        "Accept-Ranges": "bytes",
        "Content-Length": str(len(body)),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return Response(content=body, status_code=status, headers=headers)


def create_app(root: str | Path, token: str, port: int) -> FastAPI:
    """Build a configured FastAPI app.  Testable without binding a socket."""
    base = Path(root).expanduser().resolve()

    app = FastAPI(title="AI Film Review Console (FastAPI gateway)")
    app.state.root = base
    app.state.token = token
    app.state.port = port

    def require_auth(request: Request) -> None:
        provided = (
            request.query_params.get("token")
            or request.headers.get("X-Review-Token")
            or request.cookies.get("AIFILM_REVIEW")
            or ""
        )
        if not token_matches(provided, token):
            raise HTTPException(status_code=401, detail="invalid session token")

    def require_loopback(request: Request) -> None:
        # State-changing requests must originate from this loopback server.
        origin = request.headers.get("Origin", "")
        if origin and not loopback_origin_ok(origin, port):
            raise HTTPException(status_code=403, detail="cross-origin request rejected")

    # ---- pages ----
    @app.get("/", dependencies=[Depends(require_auth)])
    def console_root() -> Response:
        return HTMLResponse(
            _console_html(),
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/console", dependencies=[Depends(require_auth)])
    def console_page() -> Response:
        return HTMLResponse(
            _console_html(),
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/review", dependencies=[Depends(require_auth)])
    def review_page() -> Response:
        from review_ui import _PAGE

        return HTMLResponse(
            _PAGE.encode("utf-8"),
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )

    # ---- media (BGM library) ----
    @app.get("/media-lib/{rest_of_path:path}", dependencies=[Depends(require_auth)])
    def media_lib(rest_of_path: str, request: Request) -> Response:
        from bgm_library import default_library_root

        lib_root = default_library_root()
        try:
            candidate = safe_media_path(lib_root, rest_of_path)
        except WebConsoleError:
            raise HTTPException(status_code=404, detail="media not found")
        return _media_response(candidate, request)

    # ---- gates panel ----
    @app.get("/api/gates", dependencies=[Depends(require_auth)])
    def api_gates() -> dict[str, Any]:
        import gate_panel

        return gate_panel.collect_gates(base)

    # ---- asset picker ----
    @app.get("/api/assets", dependencies=[Depends(require_auth)])
    def api_assets(kind: str = "bgm") -> dict[str, Any]:
        import asset_picker

        if kind not in VALID_KINDS:
            raise HTTPException(status_code=400, detail=f"unknown asset kind: {kind}")
        return asset_picker.list_assets(base, kind)

    @app.get("/api/console-state", dependencies=[Depends(require_auth)])
    def api_console_state() -> dict[str, Any]:
        import asset_picker

        return asset_picker.console_state(base)

    # ---- selection (state-changing: auth + loopback) ----
    @app.post("/api/select", dependencies=[Depends(require_auth), Depends(require_loopback)])
    async def api_select(request: Request) -> dict[str, Any]:
        import asset_picker

        try:
            length = int(request.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        if length < 0 or length > MAX_BODY:
            raise HTTPException(status_code=400, detail="invalid request body size")
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="request body must be JSON")
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="request body must be a JSON object")
        try:
            return asset_picker.select_asset(base, **payload)
        except WebConsoleConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except WebConsoleForbidden as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except WebConsoleError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except TypeError as exc:
            raise HTTPException(status_code=400, detail=f"invalid selection fields: {exc}")

    # ---- onboarding wizard (references / story / characters -> go) ----
    @app.get("/api/onboarding", dependencies=[Depends(require_auth)])
    def api_onboarding_state() -> dict[str, Any]:
        import onboarding

        return onboarding.get_state(base)

    @app.post("/api/onboarding/step", dependencies=[Depends(require_auth), Depends(require_loopback)])
    async def api_onboarding_step(request: Request) -> dict[str, Any]:
        import onboarding

        try:
            length = int(request.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        if length < 0 or length > MAX_BODY:
            raise HTTPException(status_code=400, detail="invalid request body size")
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="request body must be JSON")
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="request body must be a JSON object")
        try:
            return onboarding.submit_step(
                base,
                payload["step"],
                payload.get("payload", {}),
                expected_revision=payload.get("expected_revision"),
            )
        except WebConsoleConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except WebConsoleError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except (KeyError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid onboarding fields: {exc}")

    @app.post("/api/onboarding/go", dependencies=[Depends(require_auth), Depends(require_loopback)])
    async def api_onboarding_go(request: Request) -> dict[str, Any]:
        import onboarding

        try:
            length = int(request.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        if length < 0 or length > MAX_BODY:
            raise HTTPException(status_code=400, detail="invalid request body size")
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="request body must be JSON")
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="request body must be a JSON object")
        try:
            return onboarding.go(base, expected_revision=payload.get("expected_revision"))
        except WebConsoleConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        except WebConsoleError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return app


def serve(root: str | Path, *, port: int = 0) -> dict[str, Any]:
    """Run the FastAPI gateway on loopback with a one-time token.

    Mirrors ``review_ui.serve`` so operators can swap transports without
    changing how they launch the console (same token-in-URL bootstrap).
    """
    import uvicorn

    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise WebConsoleError("film root must be an existing directory")

    token = generate_token()
    if port == 0:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]

    app = create_app(base, token, port)
    url = f"http://127.0.0.1:{port}/?token={token}"
    print(
        json.dumps(
            {"ok": True, "url": url, "root": str(base), "token": token},
            ensure_ascii=False,
        ),
        flush=True,
    )
    uvicorn.run(app, host="127.0.0.1", port=port)
    return {"ok": True, "url": url, "root": str(base)}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="FastAPI review/selection console gateway")
    parser.add_argument("--root", required=True, help="film workspace root")
    parser.add_argument("--port", type=int, default=0, help="loopback port (0 = random)")
    args = parser.parse_args()
    serve(args.root, port=args.port)


if __name__ == "__main__":
    main()
