"""Auditable production retrospective built from existing film receipts."""

from __future__ import annotations

import html
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from generation_usage import summarize_records, usage_list
from optimization_metrics import emit_metrics
from production_book import read_production_book
from quality_ledger import emit_quality_ledger
from util import canonical_json_sha256, read_json, sha256_file, utc_now, write_json

REPORT_VERSION = 1
REPORT_PATH = Path("receipts/production-report.json")
HTML_PATH = Path("out/production-report.html")
OPERATION_LABELS = {
    "t2i": "T2I",
    "image_edit": "I2I",
    "i2v": "I2V",
    "t2v": "T2V",
    "tts": "TTS",
}


class ProductionReportError(ValueError):
    """A production report cannot be emitted from trustworthy receipts."""


def _root(root: Path | str) -> Path:
    return Path(root).expanduser().resolve()


def _source(base: Path, relative: Path) -> dict[str, Any]:
    path = base / relative
    return {
        "path": str(relative),
        "state": "known" if path.is_file() else "unknown",
        "sha256": sha256_file(path) if path.is_file() else None,
    }


def _tokens(records: list[dict[str, Any]]) -> dict[str, Any]:
    values = {"input": 0, "output": 0, "total": 0}
    reported = 0
    for record in records:
        usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
        if any(name in usage for name in ("input_tokens", "output_tokens", "total_tokens")):
            reported += 1
            values["input"] += int(usage.get("input_tokens") or 0)
            values["output"] += int(usage.get("output_tokens") or 0)
            values["total"] += int(usage.get("total_tokens") or 0)
    return {
        "state": "known" if reported else "unknown",
        "reported_requests": reported,
        "unknown_requests": len(records) - reported,
        "values": values if reported else None,
    }


def _operation_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record.get("operation") or "unknown")].append(record)
    rows = []
    for operation in sorted(grouped, key=lambda item: (OPERATION_LABELS.get(item, item), item)):
        batch = grouped[operation]
        summary = summarize_records(batch)
        rows.append(
            {
                "operation": operation,
                "label": OPERATION_LABELS.get(operation, operation.upper()),
                "requests_total": len(batch),
                "status_counts": summary["status_counts"],
                "retry_count": _retry_count(batch),
                "tokens": _tokens(batch),
                "cost_in_usd_ticks": summary["cost_in_usd_ticks"],
                "cost_usd": summary["cost_usd"],
                "unknown_cost_requests": summary["unknown_cost_requests"],
            }
        )
    return rows


def _retry_count(records: list[dict[str, Any]]) -> int:
    attempts: Counter[str] = Counter()
    for record in records:
        key = str(record.get("shot_id") or record.get("job_id") or record.get("generation_id"))
        attempts[key] += 1
    return sum(max(0, count - 1) for count in attempts.values())


def _breakdown(records: list[dict[str, Any]], *keys: str) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, ...]] = Counter(
        tuple(str(record.get(key) or "unknown") for key in keys) for record in records
    )
    return [
        {**dict(zip(keys, identity, strict=True)), "requests": count}
        for identity, count in sorted(counts.items())
    ]


def _quality(report: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    delivery = report.get("delivery") if isinstance(report.get("delivery"), dict) else {}
    manual = report.get("manual") if isinstance(report.get("manual"), dict) else {}
    quality = report.get("quality") if isinstance(report.get("quality"), dict) else {}
    return {
        "final_complete": delivery.get("final_complete") is True,
        "review_approved": delivery.get("review_approved") is True,
        "director_score": manual.get("director_score"),
        "worth_publishing": manual.get("worth_publishing"),
        "manual_p0_improvement": manual.get("p0_improvement"),
        "error_pareto": quality.get("error_pareto", {}),
        "usd_per_pass_min": metrics.get("l3", {}).get("usd_per_pass_min"),
    }


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _comparison(
    base: Path,
    *,
    template_id: str | None,
    history_root: Path | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    if not template_id:
        return {"state": "not_configured", "reason": "template_id_missing", "sample_count": 0}
    if history_root is None:
        return {"state": "not_configured", "reason": "history_root_missing", "sample_count": 0}
    if not history_root.is_dir():
        return {
            "state": "not_configured",
            "reason": "history_root_not_directory",
            "sample_count": 0,
        }
    candidates: list[dict[str, Any]] = []
    for path in sorted(history_root.rglob(str(REPORT_PATH))):
        candidate_root = path.parent.parent.resolve()
        if candidate_root == base:
            continue
        payload = read_json(path)
        if not isinstance(payload, dict) or payload.get("kind") != "production-report":
            continue
        if payload.get("template_id") != template_id:
            continue
        quality = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
        data_quality = (
            payload.get("data_quality") if isinstance(payload.get("data_quality"), dict) else {}
        )
        if not (quality.get("final_complete") and quality.get("review_approved")):
            continue
        if data_quality.get("state") == "invalid":
            continue
        candidates.append(payload)
    metric_names = ("director_score", "usd_per_pass_min")
    metrics: dict[str, Any] = {}
    for name in metric_names:
        current_value = current.get(name)
        prior = [
            float((item.get("quality") or {}).get(name))
            for item in candidates
            if isinstance((item.get("quality") or {}).get(name), (int, float))
        ]
        median = _median(prior)
        metrics[name] = {
            "current": current_value if isinstance(current_value, (int, float)) else None,
            "historical_median": median,
            "difference": float(current_value) - median
            if isinstance(current_value, (int, float)) and median is not None
            else None,
            "state": "known"
            if isinstance(current_value, (int, float)) and median is not None
            else "unknown",
        }
    return {
        "state": "known" if candidates else "no_comparable_completed_films",
        "history_root": str(history_root),
        "template_id": template_id,
        "sample_count": len(candidates),
        "metrics": metrics,
    }


def _p0(
    quality: dict[str, Any], usage: dict[str, Any], comparison: dict[str, Any]
) -> dict[str, str]:
    manual = quality.get("manual_p0_improvement")
    if isinstance(manual, str) and manual.strip():
        return {"source": "director_retrospective", "recommendation": manual.strip()}
    errors = quality.get("error_pareto") if isinstance(quality.get("error_pareto"), dict) else {}
    if errors:
        code = next(iter(errors))
        return {"source": "error_pareto", "recommendation": f"优先修复最高频问题：{code}。"}
    if int(usage.get("unknown_cost_requests") or 0) > 0:
        return {
            "source": "data_quality",
            "recommendation": "先补齐原生生成工具的 usage record，避免下一部作品在成本比较上失真。",
        }
    cost = (comparison.get("metrics") or {}).get("usd_per_pass_min", {})
    if (
        isinstance(cost, dict)
        and isinstance(cost.get("difference"), (int, float))
        and cost["difference"] > 0
    ):
        return {
            "source": "cohort_cost",
            "recommendation": "在不降低审核门槛下，优先减少同镜头的失败重试与未通过生成。",
        }
    return {
        "source": "next_retrospective",
        "recommendation": "完成导演复盘，记录下一部作品唯一的 P0 改进项。",
    }


def _html_report(report: dict[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row['label']))}</td>"
        f"<td>{row['requests_total']}</td>"
        f"<td>{html.escape(str(row['status_counts']))}</td>"
        f"<td>{row['retry_count']}</td>"
        f"<td>{html.escape(str(row['tokens']['values'] if row['tokens']['state'] == 'known' else 'N/A'))}</td>"
        f"<td>{html.escape(str(row['cost_usd']))}</td>"
        f"<td>{row['unknown_cost_requests']}</td>"
        "</tr>"
        for row in report["generation"]["operations"]
    )
    comparison = report["comparison"]
    p0 = report["next_p0"]
    return f"""<!doctype html><html lang=\"zh-Hant\"><meta charset=\"utf-8\"><title>AI 影片生成复盘</title><style>body{{font:15px system-ui;margin:2rem;color:#1d2433}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccd3dd;padding:.45rem;text-align:left}}th{{background:#eef2f7}}.warn{{color:#9b3a00}}</style><h1>AI 影片生成复盘</h1><p>作品：{html.escape(str(report["film_root"]))}</p><p>请求：{report["generation"]["requests_total"]}；重试：{report["generation"]["retry_count"]}；已知成本：{html.escape(str(report["generation"]["cost_usd"]))}；未知成本请求：{report["generation"]["unknown_cost_requests"]}</p><p class=\"warn\">Token 与成本只显示真实回执；未知值不会归零。</p><h2>生成组成</h2><table><thead><tr><th>类型</th><th>请求</th><th>状态</th><th>重试</th><th>Token</th><th>成本 USD</th><th>未知成本</th></tr></thead><tbody>{rows}</tbody></table><h2>同模板趋势</h2><p>{html.escape(str(comparison))}</p><h2>下一部 P0</h2><p>{html.escape(p0["recommendation"])}</p></html>"""


def emit_production_report(
    root: Path | str, *, history_root: Path | str | None = None
) -> dict[str, Any]:
    base = _root(root)
    try:
        ledger = emit_quality_ledger(base)
    except (OSError, ValueError) as exc:
        raise ProductionReportError(f"quality ledger could not be refreshed: {exc}") from exc
    metrics = emit_metrics(base)
    records = usage_list(base).get("records") or []
    if not isinstance(records, list):
        raise ProductionReportError("generation usage records must be a list")
    try:
        book = read_production_book(base)
    except FileNotFoundError:
        book = {}
    optimization = book.get("optimization") if isinstance(book.get("optimization"), dict) else {}
    configured_history = history_root or optimization.get("history_root")
    library = _root(configured_history) if configured_history else None
    summary = summarize_records(records)
    current_quality = _quality(ledger, metrics)
    comparison = _comparison(
        base,
        template_id=str(optimization.get("template_id") or "") or None,
        history_root=library,
        current=current_quality,
    )
    sources = [
        _source(base, Path("production-book.json")),
        _source(base, Path("receipts/generation-usage.json")),
        _source(base, Path("receipts/quality-ledger.json")),
        _source(base, Path("receipts/metrics.json")),
        _source(base, Path("out/final-review.json")),
    ]
    report = {
        "schema_version": REPORT_VERSION,
        "kind": "production-report",
        "generated_at": utc_now(),
        "film_root": str(base),
        "template_id": str(optimization.get("template_id") or "") or None,
        "data_quality": {
            "state": "invalid"
            if metrics.get("data_quality", {}).get("state") == "invalid"
            else "known",
            "sources": sources,
            "untracked_native_generation_warning": int(summary["unknown_cost_requests"]) > 0,
        },
        "generation": {
            "requests_total": summary["requests_total"],
            "status_counts": summary["status_counts"],
            "retry_count": _retry_count(records),
            "tokens": _tokens(records),
            "cost_in_usd_ticks": summary["cost_in_usd_ticks"],
            "cost_usd": summary["cost_usd"],
            "unknown_cost_requests": summary["unknown_cost_requests"],
            "operations": _operation_rows(records),
            "providers": _breakdown(records, "provider", "model"),
            "shots": _breakdown(records, "shot_id", "operation"),
        },
        "quality": current_quality,
        "comparison": comparison,
    }
    report["next_p0"] = _p0(current_quality, report["generation"], comparison)
    report["content_sha256"] = canonical_json_sha256(report)
    write_json(base / REPORT_PATH, report)
    html_path = base / HTML_PATH
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(_html_report(report), encoding="utf-8")
    report["paths"] = {"json": str(base / REPORT_PATH), "html": str(html_path)}
    return report
