"""Shared, pure aggregation for per-shot dialogue contracts.

Both specification validation and preflight must report the same dialogue
violations.  Keep the scan independent of files and CLI state so those entry
points cannot drift apart.
"""

from __future__ import annotations

from typing import Any

from dialogue_contract import validate_dialogue_contract


def summarize_dialogue_contracts(shots: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate every declared shot contract and preserve its shot provenance."""
    reports: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for shot in shots:
        contracts = shot.get("dialogue_contracts")
        if not isinstance(contracts, list):
            continue
        for contract in contracts:
            if not isinstance(contract, dict):
                errors.append(
                    {
                        "code": "DIALOGUE_CONTRACT_INVALID",
                        "message": "dialogue_contracts entries must be objects",
                        "shot_id": shot.get("id"),
                    }
                )
                continue
            report = validate_dialogue_contract(contract)
            reports.append(report)
            errors.extend(
                {**error, "shot_id": shot.get("id")} for error in report.get("errors") or []
            )
    return {
        "ok": not errors,
        "contracts_validated": len(reports),
        "error_count": len(errors),
        "errors": errors,
        "codes": sorted({str(error.get("code") or "DIALOGUE") for error in errors}),
    }
