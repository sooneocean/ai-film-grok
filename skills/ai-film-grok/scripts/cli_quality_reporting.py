"""CLI domain for receipt-backed quality and production reporting."""

from __future__ import annotations

import argparse
from typing import Any


class QualityReportingCliError(ValueError):
    """A quality-reporting command could not produce its receipt."""


def add_quality_reporting_parsers(subparsers: Any) -> None:
    """Register quality-ledger and production-report without coupling to the CLI facade."""
    quality_ledger = subparsers.add_parser(
        "quality-ledger", help="Emit or complete one receipt-backed film retrospective"
    )
    quality_ledger_sub = quality_ledger.add_subparsers(dest="quality_ledger_action", required=True)
    quality_ledger_emit = quality_ledger_sub.add_parser("emit")
    quality_ledger_emit.add_argument("--root", required=True)
    quality_ledger_record = quality_ledger_sub.add_parser("record")
    quality_ledger_record.add_argument("--root", required=True)
    quality_ledger_record.add_argument("--director-score", type=int, required=True)
    quality_ledger_record.add_argument(
        "--worth-publishing",
        action="store_true",
        help="Mark this completed film as worth publishing",
    )
    quality_ledger_record.add_argument("--p0-improvement", required=True)
    quality_ledger_record.add_argument("--reshoot-reason", action="append", default=[])

    production_report = subparsers.add_parser(
        "production-report", help="Emit an auditable generation and quality retrospective"
    )
    production_report_sub = production_report.add_subparsers(
        dest="production_report_action", required=True
    )
    production_report_emit = production_report_sub.add_parser("emit")
    production_report_emit.add_argument("--root", required=True)
    production_report_emit.add_argument(
        "--history-root",
        default=None,
        help="Explicit completed-film library; overrides production-book optimization.history_root",
    )


def quality_ledger(args: argparse.Namespace) -> dict[str, Any]:
    from quality_ledger import QualityLedgerError, emit_quality_ledger, record_retrospective

    try:
        if args.quality_ledger_action == "emit":
            return emit_quality_ledger(args.root)
        return record_retrospective(
            args.root,
            director_score=args.director_score,
            worth_publishing=args.worth_publishing,
            p0_improvement=args.p0_improvement,
            reshoot_reasons=list(args.reshoot_reason or []),
        )
    except (QualityLedgerError, OSError) as exc:
        raise QualityReportingCliError(str(exc)) from exc


def production_report(args: argparse.Namespace) -> dict[str, Any]:
    from production_report import ProductionReportError, emit_production_report

    try:
        return emit_production_report(args.root, history_root=getattr(args, "history_root", None))
    except (ProductionReportError, OSError, ValueError) as exc:
        raise QualityReportingCliError(str(exc)) from exc
