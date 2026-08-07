"""C6.3 Lane A honesty: no *deletable* dead whole-file modules.

Lane A criteria (CTO): 0 import ∧ 0 CLI ∧ 0 test → delete.
After human review, residual 0-import hits are intentional (examples, probes,
route inventory) — this test freezes that set so new dead code fails closed.
"""

from __future__ import annotations

import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TESTS = Path(__file__).resolve().parents[1] / "tests"
SKILL = Path(__file__).resolve().parents[1]

# Documented intentional residuals (not delete targets).
ALLOW_ZERO_IMPORT = frozenset(
    {
        "adapters/cosyvoice_infer.example.py",  # deprecated stub → cosyvoice_tts
        "adapters/xai_openai_compat.example.py",  # offline OpenAI-compat skeleton
        "node/backend_probe.py",  # lipsync node probe (node.env.example)
        "tools/route_inventory.py",  # routing-map inventory CLI (manual)
    }
)


def _mod_keys(rel: Path) -> set[str]:
    parts = list(rel.with_suffix("").parts)
    keys = {parts[-1]}
    if len(parts) > 1:
        keys.add(".".join(parts))
    return keys


def _is_shim(text: str) -> bool:
    if "hard-compat" in text.lower() or "_sys.modules[__name__]" in text:
        return True
    if text.count("\n") < 25 and "from " in text and text.count("def ") <= 1:
        return True
    return False


def test_lane_a_only_intentional_residuals() -> None:
    all_py = [
        p
        for p in SCRIPTS.rglob("*.py")
        if "__pycache__" not in p.parts and p.name != "__init__.py"
    ]
    texts = {p: p.read_text(encoding="utf-8", errors="ignore") for p in all_py}
    # Exclude this file so allowlist path strings do not self-mask candidates.
    test_blob = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in TESTS.rglob("test_*.py")
        if p.name != "test_c6_lane_a_delete_scan.py"
    )
    cli_blob = ""
    for p in list(SCRIPTS.glob("cli*.py")) + list((SCRIPTS / "cli").rglob("*.py") if (SCRIPTS / "cli").is_dir() else []):
        cli_blob += texts.get(p, "")
    skill_md = SKILL / "SKILL.md"
    if skill_md.is_file():
        cli_blob += skill_md.read_text(encoding="utf-8", errors="ignore")
    hub = SCRIPTS / "aifilm_grok.py"
    if hub.is_file():
        cli_blob += hub.read_text(encoding="utf-8", errors="ignore")

    zero: list[str] = []
    for p, text in texts.items():
        rel = p.relative_to(SCRIPTS).as_posix()
        if _is_shim(text):
            continue
        keys = _mod_keys(Path(rel))
        imported = False
        for q, t in texts.items():
            if q == p:
                continue
            for k in keys:
                if re.search(rf"(?:from|import)\s+{re.escape(k)}\b", t):
                    imported = True
                    break
            if imported:
                break
        if imported:
            continue
        if any(k in cli_blob for k in keys if len(k) > 3):
            continue
        if any(k in test_blob for k in keys if len(k) > 3):
            continue
        zero.append(rel)

    unexpected = sorted(set(zero) - ALLOW_ZERO_IMPORT)
    missing_allow = sorted(ALLOW_ZERO_IMPORT - set(zero))
    assert not unexpected, (
        f"new Lane A delete candidates (0 import/CLI/test) — review & delete or allowlist: {unexpected}"
    )
    # If an allowlisted file gains importers/tests, drop it from ALLOW (don't keep zombie allow).
    assert not missing_allow, (
        f"allowlist entries no longer match scan (gained importers/tests?) — update ALLOW: {missing_allow}"
    )
