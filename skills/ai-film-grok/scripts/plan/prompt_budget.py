"""Read-only prompt economy audit based on prompt-assembly receipts."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from util import read_json, write_json


def _estimate_tokens(text: str) -> int:
    return (len(text) + 3) // 4


def _line_kind(line: str) -> str:
    """Repeated visual constraints can be intentional continuity controls."""
    if line.startswith(("Style:", "Lighting:", "Character ", "Wardrobe ")):
        return "identity_or_style_lock"
    if line.startswith(("Costume continuity HARD:", "Coitus readability HARD:")):
        return "continuity_hard_lock"
    if line.startswith(("Continuity:", "Start already:")):
        return "state_lock"
    if line.startswith(("Cinematography:", "Action:", "Motion/Action:")):
        return "shot_specific_direction"
    return "review_before_removal"


def prompt_budget_report(
    root: Path, *, write: bool = False, max_estimated_tokens: int | None = None
) -> dict[str, Any]:
    """Show provider-bound prompt cost without changing any generated prompt."""
    if max_estimated_tokens is not None and max_estimated_tokens < 1:
        raise ValueError("max_estimated_tokens must be positive")
    root = Path(root).expanduser().resolve()
    receipts_dir = root / "receipts"
    rows: list[dict[str, Any]] = []
    line_counts: Counter[str] = Counter()
    line_shots: dict[str, list[str]] = {}
    local_reference_chars = 0
    local_reference_count = 0
    for path in sorted(receipts_dir.glob("prompt_assembly_*.json")):
        receipt = read_json(path) or {}
        prompt = str(receipt.get("prompt_text") or "")
        if not prompt:
            continue
        metrics = (
            receipt.get("prompt_metrics") if isinstance(receipt.get("prompt_metrics"), dict) else {}
        )
        tokens = int(metrics.get("estimated_input_tokens") or _estimate_tokens(prompt))
        rows.append(
            {
                "shot_id": receipt.get("shot_id") or path.stem.removeprefix("prompt_assembly_"),
                "receipt": str(path),
                "characters": len(prompt),
                "estimated_input_tokens": tokens,
            }
        )
        shot_id = str(receipt.get("shot_id") or path.stem.removeprefix("prompt_assembly_"))
        for line in (line.strip() for line in prompt.splitlines() if line.strip()):
            line_counts[line] += 1
            line_shots.setdefault(line, []).append(shot_id)
        reference_instruction = str(receipt.get("reference_instruction") or "")
        if reference_instruction:
            local_reference_count += 1
            local_reference_chars += len(reference_instruction)

    total_tokens = sum(row["estimated_input_tokens"] for row in rows)
    repeated = []
    compression_candidates = []
    protected_repeated_lines = []
    for line, occurrences in line_counts.most_common():
        if occurrences < 2:
            continue
        item = {
            "line": line,
            "occurrences": occurrences,
            "shot_ids": line_shots[line],
            "estimated_repeated_tokens": _estimate_tokens(line) * occurrences,
            "classification": _line_kind(line),
        }
        repeated.append(item)
        if item["classification"] == "review_before_removal":
            compression_candidates.append(
                {
                    **item,
                    "estimated_tokens_saved_if_pilot_approved": _estimate_tokens(line)
                    * (occurrences - 1),
                    "requires_pilot_equivalence": True,
                    "apply_automatically": False,
                }
            )
        else:
            protected_repeated_lines.append(item)
    report = {
        "ok": True,
        "kind": "prompt-budget",
        "read_only": not write,
        "provider_billing_note": "Token counts are local character-based estimates; provider billing is authoritative.",
        "shot_count": len(rows),
        "total_estimated_input_tokens": total_tokens,
        "average_estimated_input_tokens": round(total_tokens / len(rows), 1) if rows else 0,
        "largest_shots": sorted(rows, key=lambda row: row["estimated_input_tokens"], reverse=True)[
            :5
        ],
        "repeated_provider_lines": repeated,
        "protected_repeated_lines": protected_repeated_lines,
        "compression_candidates": compression_candidates,
        "max_estimated_tokens": max_estimated_tokens,
        "budget_status": (
            "not_set"
            if max_estimated_tokens is None
            else "within_budget"
            if total_tokens <= max_estimated_tokens
            else "over_budget_review_required"
        ),
        "local_only_reference_instructions": {
            "count": local_reference_count,
            "characters_kept_out_of_provider_prompts": local_reference_chars,
        },
        "recommendation": (
            "Only compression_candidates may be tested; preserve protected locks. No prompt is rewritten until a director-approved Pilot proves equivalence."
        ),
    }
    if write:
        path = receipts_dir / "prompt-budget.json"
        write_json(path, report)
        report["path"] = str(path)
    return report
