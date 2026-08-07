"""Premium vertical preflight probes (W3 peel)."""

from __future__ import annotations

from pathlib import Path

from gates.preflight_issues import _issue


def append_premium_vertical_issues(
    root: Path,
    hard: list[dict[str, str]],
    soft: list[dict[str, str]] | None = None,
) -> None:
    """Append premium_vertical creative/preproduction hard issues (mutates hard).

    Missing production-book is soft-empty (standard roots stay compatible).
    Only quality_target=premium_vertical hard-blocks.
    """
    # re-use soft for API symmetry
    _ = soft
    from util import read_json

    # Premium vertical is an authored creative contract, not a styling hint.
    # Keep standard/legacy roots compatible while failing closed before paid work.
    book = read_json(root / "production-book.json") or {}
    if isinstance(book, dict) and book.get("quality_target", "standard") == "premium_vertical":
        try:
            from creative_quality import validate_premium_vertical

            creative = validate_premium_vertical(root)
            for issue in creative.get("errors") or []:
                hard.append(
                    _issue(
                        "hard",
                        str(issue.get("code") or "CREATIVE_QUALITY_MISSING"),
                        str(issue.get("message") or "premium creative contract failed"),
                        fix="aifilm plan edit/graph project/write-spec 后重新运行 preflight",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            hard.append(_issue("hard", "CREATIVE_QUALITY_VALIDATION_FAILED", str(exc)[:200]))
        try:
            from creative_pipeline import preproduction_readiness

            readiness = preproduction_readiness(root, write=True)
            for blocker in readiness.get("blockers") or []:
                hard.append(
                    _issue(
                        "hard",
                        str(blocker.get("code") or "PREPRODUCTION_NOT_READY"),
                        str(blocker.get("message") or "premium pre-production gate failed"),
                        fix="完成 Radio Cut 与 Animatic 人审回执后重新运行 preflight",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            hard.append(_issue("hard", "PREPRODUCTION_READINESS_FAILED", str(exc)[:200]))
