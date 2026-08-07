"""FastAPI gateway for the localhost review / selection console.

This is the *framework* layer promised by the web-console plan.  It does NOT
re-implement any rule: every security primitive (token compare, loopback
origin check, path-escape media resolution, hash-bound selection) and every
business action (gate aggregation, asset listing, selection, review) is
delegated to the *same* modules the stdlib ``review_ui.py`` server uses —
``web_core``, ``gate_panel``, ``asset_picker``, ``review_control``,
``onboarding``.  Swapping the transport (``ThreadingHTTPServer`` ->
``FastAPI``/``uvicorn``) therefore cannot change a single security or domain
behaviour.

Route surface: ``web_routes.ROUTES`` (``fastapi=True``).  Error JSON always
includes both ``error`` and ``detail`` (same message) so console.js and
FastAPI clients stay compatible.

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
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from web_core import (
    WebConsoleConflict,
    WebConsoleError,
    WebConsoleForbidden,
    generate_token,
    loopback_origin_ok,
    safe_media_path,
    token_matches,
)
from web_routes import error_body

MAX_BODY = 128 * 1024
MAX_UPLOAD = 20 * 1024 * 1024


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


def _http_error(status: int, message: str) -> HTTPException:
    """Raise HTTPException; app exception handler rewrites body to error+detail."""
    return HTTPException(status_code=status, detail=str(message))


async def _read_json_body(request: Request, *, max_size: int = MAX_BODY) -> dict[str, Any]:
    try:
        length = int(request.headers.get("Content-Length", "0") or "0")
    except ValueError:
        length = 0
    if length < 0 or length > max_size:
        raise _http_error(400, "invalid request body size")
    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise _http_error(400, "request body must be JSON") from exc
    if not isinstance(payload, dict):
        raise _http_error(400, "request body must be a JSON object")
    return payload


def create_app(root: str | Path, token: str, port: int) -> FastAPI:
    """Build a configured FastAPI app.  Testable without binding a socket."""
    base = Path(root).expanduser().resolve()

    app = FastAPI(title="AI Film Review Console (FastAPI gateway)")
    app.state.root = base
    app.state.token = token
    app.state.port = port

    @app.exception_handler(StarletteHTTPException)
    async def unified_http_exception(request: Request, exc: StarletteHTTPException) -> Response:
        """Emit ``{error, detail}`` so console.js always finds ``error``."""
        detail = exc.detail
        if isinstance(detail, dict):
            msg = str(detail.get("error") or detail.get("detail") or detail)
            body = {**error_body(msg), **{k: v for k, v in detail.items() if k not in ("error", "detail")}}
            return JSONResponse(status_code=exc.status_code, content=body)
        if isinstance(detail, list):
            # FastAPI validation errors — keep structure under detail, still set error.
            msg = "request validation failed"
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": msg, "detail": detail},
            )
        return JSONResponse(status_code=exc.status_code, content=error_body(str(detail)))

    def require_auth(request: Request) -> None:
        provided = (
            request.query_params.get("token")
            or request.headers.get("X-Review-Token")
            or request.cookies.get("AIFILM_REVIEW")
            or ""
        )
        if not token_matches(provided, token):
            raise _http_error(401, "invalid session token")

    def require_loopback(request: Request) -> None:
        # State-changing requests must originate from this loopback server.
        origin = request.headers.get("Origin", "")
        if origin and not loopback_origin_ok(origin, port):
            raise _http_error(403, "cross-origin request rejected")

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

    # ---- media ----
    @app.get("/media/{rest_of_path:path}", dependencies=[Depends(require_auth)])
    def media_film(rest_of_path: str, request: Request) -> Response:
        try:
            candidate = safe_media_path(base, rest_of_path)
        except WebConsoleError:
            raise _http_error(404, "media not found") from None
        return _media_response(candidate, request)

    @app.get("/media-lib/{rest_of_path:path}", dependencies=[Depends(require_auth)])
    def media_lib(rest_of_path: str, request: Request) -> Response:
        from bgm_library import default_library_root

        lib_root = default_library_root()
        try:
            candidate = safe_media_path(lib_root, rest_of_path)
        except WebConsoleError:
            raise _http_error(404, "media not found") from None
        return _media_response(candidate, request)

    # ---- review (parity with stdlib review_ui) ----
    @app.get("/api/status", dependencies=[Depends(require_auth)])
    def api_status() -> dict[str, Any]:
        from review_control import autopilot_status, load_settings, review_queue

        return {
            "queue": review_queue(base),
            "settings": load_settings(base),
            "autopilot": autopilot_status(base),
        }

    @app.get("/api/final-review-template", dependencies=[Depends(require_auth)])
    def api_final_review_template() -> dict[str, Any]:
        from final_review_input import review_input_template

        try:
            return review_input_template(base)
        except ValueError as exc:
            raise _http_error(404, str(exc)) from exc

    @app.post("/api/action", dependencies=[Depends(require_auth), Depends(require_loopback)])
    async def api_action(request: Request) -> dict[str, Any]:
        from review_control import ReviewControlConflict, ReviewControlError, record_action

        payload = await _read_json_body(request)
        try:
            return record_action(base, **payload)
        except ReviewControlConflict as exc:
            raise _http_error(409, str(exc)) from exc
        except (ReviewControlError, TypeError, ValueError) as exc:
            raise _http_error(400, str(exc)) from exc

    @app.post("/api/settings", dependencies=[Depends(require_auth), Depends(require_loopback)])
    async def api_settings(request: Request) -> dict[str, Any]:
        from review_control import ReviewControlConflict, ReviewControlError, update_settings

        payload = await _read_json_body(request)
        try:
            return update_settings(base, **payload)
        except ReviewControlConflict as exc:
            raise _http_error(409, str(exc)) from exc
        except (ReviewControlError, TypeError, ValueError) as exc:
            raise _http_error(400, str(exc)) from exc

    @app.post("/api/advance", dependencies=[Depends(require_auth), Depends(require_loopback)])
    async def api_advance(request: Request) -> dict[str, Any]:
        from review_control import ReviewControlConflict, ReviewControlError, advance_to_next_review

        payload = await _read_json_body(request)
        try:
            return advance_to_next_review(base, **payload)
        except ReviewControlConflict as exc:
            raise _http_error(409, str(exc)) from exc
        except (ReviewControlError, TypeError, ValueError) as exc:
            raise _http_error(400, str(exc)) from exc

    @app.post(
        "/api/final-review-input",
        dependencies=[Depends(require_auth), Depends(require_loopback)],
    )
    async def api_final_review_input(request: Request) -> dict[str, Any]:
        from final_review_input import write_review_input

        payload = await _read_json_body(request)
        try:
            return write_review_input(base, payload)
        except (TypeError, ValueError) as exc:
            raise _http_error(400, str(exc)) from exc

    # ---- gates panel ----
    @app.get("/api/gates", dependencies=[Depends(require_auth)])
    def api_gates() -> dict[str, Any]:
        import gate_panel

        return gate_panel.collect_gates(base)

    # ---- asset picker (VALID_KINDS single source: asset_picker) ----
    @app.get("/api/assets", dependencies=[Depends(require_auth)])
    def api_assets(kind: str = "bgm") -> dict[str, Any]:
        import asset_picker

        try:
            return asset_picker.list_assets(base, kind)
        except WebConsoleError as exc:
            raise _http_error(400, str(exc)) from exc

    @app.get("/api/console-state", dependencies=[Depends(require_auth)])
    def api_console_state() -> dict[str, Any]:
        import asset_picker

        return asset_picker.console_state(base)

    # ---- workspace file (read-only: auth only; path-escape safe) ----
    @app.get("/api/file", dependencies=[Depends(require_auth)])
    def api_file(path: str = "", request: Request = None) -> Response:  # noqa: ARG001
        if not path or path.startswith("/"):
            raise _http_error(400, "invalid file path")
        try:
            candidate = safe_media_path(base, path)
        except WebConsoleError:
            raise _http_error(404, "file not found") from None
        return _media_response(candidate, request)

    # ---- selection (state-changing: auth + loopback) ----
    @app.post("/api/select", dependencies=[Depends(require_auth), Depends(require_loopback)])
    async def api_select(request: Request) -> dict[str, Any]:
        import asset_picker

        payload = await _read_json_body(request)
        try:
            return asset_picker.select_asset(base, **payload)
        except WebConsoleConflict as exc:
            raise _http_error(409, str(exc)) from exc
        except WebConsoleForbidden as exc:
            raise _http_error(403, str(exc)) from exc
        except WebConsoleError as exc:
            raise _http_error(400, str(exc)) from exc
        except TypeError as exc:
            raise _http_error(400, f"invalid selection fields: {exc}") from exc

    # ---- onboarding wizard ----
    @app.get("/api/onboarding", dependencies=[Depends(require_auth)])
    def api_onboarding_state() -> dict[str, Any]:
        import onboarding

        return onboarding.get_state(base)

    @app.post("/api/onboarding/step", dependencies=[Depends(require_auth), Depends(require_loopback)])
    async def api_onboarding_step(request: Request) -> dict[str, Any]:
        import onboarding

        payload = await _read_json_body(request)
        try:
            return onboarding.submit_step(
                base,
                payload["step"],
                payload.get("payload", {}),
                expected_revision=payload.get("expected_revision"),
            )
        except WebConsoleConflict as exc:
            raise _http_error(409, str(exc)) from exc
        except WebConsoleError as exc:
            raise _http_error(400, str(exc)) from exc
        except (KeyError, TypeError) as exc:
            raise _http_error(400, f"invalid onboarding fields: {exc}") from exc

    @app.post("/api/onboarding/go", dependencies=[Depends(require_auth), Depends(require_loopback)])
    async def api_onboarding_go(request: Request) -> dict[str, Any]:
        import onboarding

        payload = await _read_json_body(request)
        try:
            return onboarding.go(base, expected_revision=payload.get("expected_revision"))
        except WebConsoleConflict as exc:
            raise _http_error(409, str(exc)) from exc
        except WebConsoleError as exc:
            raise _http_error(400, str(exc)) from exc

    @app.post("/api/upload", dependencies=[Depends(require_auth), Depends(require_loopback)])
    async def api_upload(request: Request) -> dict[str, Any]:
        import onboarding

        payload = await _read_json_body(request, max_size=MAX_UPLOAD)
        try:
            return onboarding.handle_upload(
                base,
                filename=str(payload.get("filename") or ""),
                data_url=str(payload.get("data_url") or ""),
            )
        except WebConsoleError as exc:
            raise _http_error(400, str(exc)) from exc

    @app.post("/api/onboarding/brief", dependencies=[Depends(require_auth), Depends(require_loopback)])
    async def api_onboarding_brief(request: Request) -> dict[str, Any]:
        import onboarding

        payload = await _read_json_body(request)
        try:
            return onboarding.submit_brief(
                base,
                story_text=str(payload.get("story_text") or ""),
                image_paths=payload.get("image_paths"),
                hints=payload.get("hints"),
                expected_revision=payload.get("expected_revision"),
            )
        except WebConsoleConflict as exc:
            raise _http_error(409, str(exc)) from exc
        except WebConsoleError as exc:
            raise _http_error(400, str(exc)) from exc
        except (KeyError, TypeError) as exc:
            raise _http_error(400, f"invalid brief fields: {exc}") from exc

    @app.post(
        "/api/onboarding/decompose",
        dependencies=[Depends(require_auth), Depends(require_loopback)],
    )
    async def api_onboarding_decompose(request: Request) -> dict[str, Any]:
        import onboarding

        payload = await _read_json_body(request)
        try:
            return onboarding.decompose(
                base,
                expected_revision=payload.get("expected_revision"),
                brief=payload.get("brief"),
            )
        except WebConsoleConflict as exc:
            raise _http_error(409, str(exc)) from exc
        except WebConsoleError as exc:
            raise _http_error(400, str(exc)) from exc
        except (KeyError, TypeError) as exc:
            raise _http_error(400, f"invalid decompose fields: {exc}") from exc

    @app.post("/api/onboarding/plan", dependencies=[Depends(require_auth), Depends(require_loopback)])
    async def api_onboarding_plan(request: Request) -> dict[str, Any]:
        import onboarding

        payload = await _read_json_body(request)
        try:
            return onboarding.save_plan(
                base,
                payload.get("plan", {}),
                expected_revision=payload.get("expected_revision"),
            )
        except WebConsoleConflict as exc:
            raise _http_error(409, str(exc)) from exc
        except WebConsoleError as exc:
            raise _http_error(400, str(exc)) from exc
        except (KeyError, TypeError) as exc:
            raise _http_error(400, f"invalid plan fields: {exc}") from exc

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
    url = f"http://127.0.0.1:{port}/console?token={token}"
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
