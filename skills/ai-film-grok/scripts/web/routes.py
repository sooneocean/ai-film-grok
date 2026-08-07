"""Single source of truth for localhost workbench HTTP routes.

Both gateways (stdlib ``review_ui`` and FastAPI ``web_api``) must stay aligned
with this table.  Tests assert FastAPI openapi paths cover every route marked
``fastapi=True``; docs and inventory can render the same list.

Error body contract (both gateways):
  ``{"error": "<message>", "detail": "<message>"}``
so console.js can always read ``error`` (and FastAPI clients can still use
``detail``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Gateway = Literal["stdlib", "fastapi"]


@dataclass(frozen=True)
class RouteSpec:
    method: str
    path: str
    handler_id: str
    domain: str
    stdlib: bool = True
    fastapi: bool = True
    auth: bool = True
    """POST state-changing routes require loopback Origin when True."""
    loopback: bool = False
    note: str = ""


# Pages + media + full API surface of the review/selection workbench.
ROUTES: tuple[RouteSpec, ...] = (
    # ---- pages (B1 single shell) ----
    RouteSpec(
        "GET",
        "/",
        "page.shell_or_invite",
        "web.console_html",
        note="workbench shell; invite cookie on stdlib",
    ),
    RouteSpec("GET", "/console", "page.console", "web.console_html"),
    RouteSpec("GET", "/studio", "page.console_alias", "web.console_html", fastapi=False),
    RouteSpec("GET", "/review", "page.review", "review_ui", note="验片专页（可 iframe）"),
    # ---- review (stdlib complete; FastAPI parity target) ----
    RouteSpec("GET", "/api/status", "review.status", "review_control"),
    RouteSpec(
        "GET",
        "/api/final-review-template",
        "review.final_template",
        "final_review_input",
    ),
    RouteSpec(
        "POST",
        "/api/action",
        "review.action",
        "review_control",
        loopback=True,
    ),
    RouteSpec(
        "POST",
        "/api/settings",
        "review.settings",
        "review_control",
        loopback=True,
    ),
    RouteSpec(
        "POST",
        "/api/advance",
        "review.advance",
        "review_control",
        loopback=True,
    ),
    RouteSpec(
        "POST",
        "/api/final-review-input",
        "review.final_input",
        "final_review_input",
        loopback=True,
    ),
    RouteSpec(
        "POST",
        "/api/stop",
        "review.stop",
        "review_ui",
        fastapi=False,
        loopback=True,
        note="stdlib session stop only",
    ),
    # ---- selection / gates / state ----
    RouteSpec("GET", "/api/gates", "gates.collect", "gate_panel"),
    RouteSpec("GET", "/api/assets", "assets.list", "asset_picker"),
    RouteSpec("GET", "/api/console-state", "console.state", "asset_picker"),
    RouteSpec("GET", "/api/live", "director.live", "web.projection"),
    RouteSpec("GET", "/api/events", "director.events", "web.projection"),
    RouteSpec("GET", "/api/stream", "director.stream", "web.sse_stream", note="SSE live feed"),
    RouteSpec("GET", "/api/takes", "takes.list_or_compare", "web.takes_api"),
    RouteSpec("POST", "/api/takes/review", "takes.review", "web.takes_api", loopback=True),
    RouteSpec("GET", "/api/file", "media.workspace_file", "web_core"),
    RouteSpec(
        "POST",
        "/api/select",
        "assets.select",
        "asset_picker",
        loopback=True,
    ),
    # ---- onboarding ----
    RouteSpec("GET", "/api/onboarding", "onboarding.state", "onboarding"),
    RouteSpec(
        "POST",
        "/api/onboarding/step",
        "onboarding.step",
        "onboarding",
        loopback=True,
    ),
    RouteSpec(
        "POST",
        "/api/onboarding/go",
        "onboarding.go",
        "onboarding",
        loopback=True,
    ),
    RouteSpec(
        "POST",
        "/api/onboarding/brief",
        "onboarding.brief",
        "onboarding",
        loopback=True,
    ),
    RouteSpec(
        "POST",
        "/api/onboarding/decompose",
        "onboarding.decompose",
        "onboarding",
        loopback=True,
    ),
    RouteSpec(
        "POST",
        "/api/onboarding/plan",
        "onboarding.plan",
        "onboarding",
        loopback=True,
    ),
    RouteSpec(
        "POST",
        "/api/upload",
        "onboarding.upload",
        "onboarding",
        loopback=True,
    ),
    # ---- media (prefix routes; method+prefix key) ----
    RouteSpec("GET", "/media/{path}", "media.film", "web_core", note="prefix /media/"),
    RouteSpec(
        "GET",
        "/media-lib/{path}",
        "media.bgm_lib",
        "bgm_library",
        note="prefix /media-lib/",
    ),
)


def routes_for(gateway: Gateway) -> list[RouteSpec]:
    if gateway == "stdlib":
        return [r for r in ROUTES if r.stdlib]
    return [r for r in ROUTES if r.fastapi]


def route_keys(gateway: Gateway) -> set[tuple[str, str]]:
    """(METHOD, path) pairs for a gateway."""
    return {(r.method.upper(), r.path) for r in routes_for(gateway)}


def api_route_keys(gateway: Gateway) -> set[tuple[str, str]]:
    """API-only keys (path starts with /api/)."""
    return {(m, p) for m, p in route_keys(gateway) if p.startswith("/api/")}


def error_body(message: str) -> dict[str, str]:
    """Unified error JSON for both gateways."""
    text = str(message)
    return {"error": text, "detail": text}


def routes_table() -> list[dict[str, Any]]:
    """JSON-serializable inventory for docs / doctor."""
    rows: list[dict[str, Any]] = []
    for r in ROUTES:
        rows.append(
            {
                "method": r.method,
                "path": r.path,
                "handler_id": r.handler_id,
                "domain": r.domain,
                "stdlib": r.stdlib,
                "fastapi": r.fastapi,
                "auth": r.auth,
                "loopback": r.loopback,
                "note": r.note,
            }
        )
    return rows
