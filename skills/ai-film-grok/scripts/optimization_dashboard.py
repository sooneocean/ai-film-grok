"""Safe static optimisation report builder."""

from __future__ import annotations

import html
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from optimization_program import WEEKLY_METRICS, weekly_summary
from util import read_json


def _row(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "root": metrics.get("metadata", {}).get("film_root", "unknown"),
        "state": metrics.get("data_quality", {}).get("state"),
        "final": metrics.get("funnel", {}).get("final_complete"),
        "cost": metrics.get("l3", {}).get("usd_per_pass_min"),
        "wall": metrics.get("l3", {}).get("wall_sec_init_to_verified"),
        "retry": metrics.get("l3", {}).get("retry_count"),
        "human": metrics.get("l3", {}).get("human_minutes"),
        "errors": metrics.get("error_pareto", {}),
    }


def build(roots_dir: Path | str, *, days: int, out: Path | str) -> dict[str, Any]:
    if days <= 0:
        raise ValueError("days must be positive")
    source = Path(roots_dir).expanduser().resolve()
    destination = Path(out).expanduser().resolve()
    if not source.is_dir():
        raise ValueError("roots-dir must be an existing directory")
    rows: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    cutoff = datetime.now(UTC) - timedelta(days=days)
    for candidate in source.rglob("metrics.json"):
        if "receipts" not in candidate.parts:
            continue
        if datetime.fromtimestamp(candidate.stat().st_mtime, tz=UTC) < cutoff:
            continue
        payload = read_json(candidate)
        if isinstance(payload, dict) and payload.get("kind") == "optimization-metrics":
            rows.append(_row(payload))
            reports.append(payload)
    counts = {
        "runs": len(rows),
        "known": sum(item["state"] == "known" for item in rows),
        "final_complete": sum(bool(item["final"]) for item in rows),
    }
    weekly = weekly_summary(reports)
    weekly_lines = "".join(
        "<tr><td>"
        + html.escape(name)
        + "</td><td>"
        + html.escape(
            str(
                weekly["metrics"][name]["value"]
                if weekly["metrics"][name]["value"] is not None
                else "unknown"
            )
        )
        + "</td><td>"
        + html.escape(str(weekly["metrics"][name]["sample_count"]))
        + "</td></tr>"
        for name in WEEKLY_METRICS
    )
    lines = "".join(
        "<tr>"
        + "".join(
            f"<td>{html.escape(str(value if value is not None else 'unknown'))}</td>"
            for value in (
                row["root"],
                row["state"],
                row["final"],
                row["cost"],
                row["wall"],
                row["retry"],
                row["human"],
                row["errors"],
            )
        )
        + "</tr>"
        for row in rows
    )
    page = f"""<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><title>ai-film-grok optimisation dashboard</title><style>body{{font:14px system-ui;margin:2rem;color:#1d2433}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}td,th{{border:1px solid #ccd3dd;padding:.45rem;text-align:left}}th{{background:#eef2f7}}.warn{{color:#9b3a00}}</style><h1>Optimisation dashboard</h1><p>Last {days} days request. Static, receipt-only report.</p><p>Runs: {counts["runs"]} · Complete: {counts["final_complete"]} · Known data: {counts["known"]}</p><p class=\"warn\">Unknown values are intentionally not converted to zero.</p><h2>Weekly decision metrics</h2><p>Data quality: {html.escape(str(weekly["data_quality"]))}</p><table><thead><tr><th>Metric</th><th>Value</th><th>Known samples</th></tr></thead><tbody>{weekly_lines}</tbody></table><table><thead><tr><th>Film root</th><th>Data</th><th>Final</th><th>$/pass-min</th><th>Wall sec</th><th>Retries</th><th>Human min</th><th>Error Pareto</th></tr></thead><tbody>{lines}</tbody></table></html>"""
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "index.html"
    target.write_text(page, encoding="utf-8")
    return {
        "ok": True,
        "kind": "optimization-dashboard",
        "roots_dir": str(source),
        "days": days,
        "out": str(target),
        "counts": counts,
        "weekly_summary": weekly,
    }
