"""Gold-set calibration for early-reject metrics; never a delivery approval."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, write_json


def calibrate(manifest_path: Path | str) -> dict[str, Any]:
    path = Path(manifest_path).expanduser().resolve()
    manifest = read_json(path)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("items"), list):
        raise ValueError("gold manifest requires an items array")
    items = [item for item in manifest["items"] if isinstance(item, dict)]
    if len(items) < 20:
        return {"ok": False, "code": "GOLD_SAMPLE_TOO_SMALL", "count": len(items), "minimum": 20}
    tp = fp = fn = tn = 0
    agreements = 0
    total = 0
    for item in items:
        if (
            not item.get("media_sha256")
            or not isinstance(item.get("reviews"), list)
            or len(item["reviews"]) < 2
        ):
            return {"ok": False, "code": "GOLD_EVIDENCE_INCOMPLETE", "item": item.get("id")}
        reviews = item["reviews"][:2]
        left, right = bool(reviews[0].get("human_fail")), bool(reviews[1].get("human_fail"))
        agreements += int(left == right)
        total += 1
        actual, predicted = left or right, bool(item.get("early_reject"))
        if predicted and actual:
            tp += 1
        elif predicted:
            fp += 1
        elif actual:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    po = agreements / total
    expected = ((tp + fp) / total) * ((tp + fn) / total) + ((fn + tn) / total) * ((fp + tn) / total)
    kappa = (po - expected) / (1 - expected) if expected != 1 else 1.0
    report = {
        "ok": precision >= 0.9 and kappa >= 0.6,
        "kind": "gold-calibration",
        "count": len(items),
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "cohens_kappa": round(kappa, 4),
        "threshold_comparison": {
            "before": manifest.get("threshold_before"),
            "after": manifest.get("threshold_after"),
        },
        "threshold_promotion_allowed": precision >= 0.9 and kappa >= 0.6,
        "human_review_replacement": False,
    }
    write_json(path.with_name("gold-calibration.json"), report)
    return report
