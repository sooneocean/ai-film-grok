"""Final film manifest entry (closeout)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from util import utc_now


def build_final_film_manifest_entry(*, final_path: Path, output_sha256: str, duration_sec: float, report_path: Path, technical_qa: dict[str, Any], official_final: dict[str, Any] | None) -> dict[str, Any]:
    from final.delivery_class import delivery_fields_from_official_final
    entry = {
        "path": str(final_path.name),
        "sha256": output_sha256,
        "duration_sec": duration_sec,
        "report": str(report_path.name),
        "assembled_at": utc_now(),
        "technical_qa": technical_qa,
    }
    entry.update(delivery_fields_from_official_final(official_final))
    return entry
