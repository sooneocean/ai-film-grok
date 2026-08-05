"""Parser registration for the asset registry command domain."""

from __future__ import annotations

from typing import Any


def add_assets_parsers(subparsers: Any) -> None:
    """Register asset commands without coupling parser setup to the CLI facade."""
    assets_parser = subparsers.add_parser(
        "assets",
        help="Asset registry: sync|status|check (Phase 4 Character/Location/Prop/State)",
    )
    assets_sub = assets_parser.add_subparsers(dest="assets_action", required=True)
    sync = assets_sub.add_parser(
        "sync",
        help="Structure bible locations/props + wardrobe variants + cast-state slots + timeline",
    )
    sync.add_argument("--root", required=True)
    sync.add_argument("--force", action="store_true", help="Re-structure locations/props objects")
    sync.add_argument("--no-write", action="store_true")
    sync.add_argument("--no-graph", action="store_true", help="Do not patch drama-graph")
    status = assets_sub.add_parser("status", help="Show assets-registry summary")
    status.add_argument("--root", required=True)
    status.add_argument("--sync", action="store_true", help="Sync if missing")
    check = assets_sub.add_parser(
        "check", help="Align assets-registry with state-index + wardrobe re-dress risks"
    )
    check.add_argument("--root", required=True)
    check.add_argument("--no-sync", action="store_true", help="Do not re-sync before check")
