from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from source_chain import (  # noqa: E402
    SourceChainError,
    append_source,
    new_source_chain,
    validate_source_chain,
)


def _sha(char: str) -> str:
    return char * 64


def test_source_chain_requires_every_level_and_exact_parent_hash() -> None:
    chain = new_source_chain("shot01")
    append_source(chain, "Style", "style-main", _sha("a"))
    append_source(chain, "Cast", "cast-hero", _sha("b"), parent_ref="style-main")
    append_source(
        chain,
        "StatePhoto",
        "state-red",
        _sha("c"),
        parent_ref="cast-hero",
        wardrobe_state="red-dress",
    )
    append_source(
        chain,
        "Keyframe",
        "kf-shot01",
        _sha("d"),
        parent_ref="state-red",
        wardrobe_state="red-dress",
    )
    append_source(
        chain,
        "Clip",
        "clip-shot01",
        _sha("e"),
        parent_ref="kf-shot01",
        wardrobe_state="red-dress",
    )
    append_source(
        chain,
        "PromotedTail",
        "tail-shot01",
        _sha("f"),
        parent_ref="clip-shot01",
        wardrobe_state="red-dress",
    )

    report = validate_source_chain(chain, require_complete=True)
    assert report["ok"], report
    assert [node["level"] for node in chain["nodes"]] == [
        "Style",
        "Cast",
        "StatePhoto",
        "Keyframe",
        "Clip",
        "PromotedTail",
    ]
    assert chain["nodes"][1]["parentHash"] == chain["nodes"][0]["hash"]


def test_source_chain_rejects_skip_stale_parent_and_wardrobe_regression() -> None:
    chain = new_source_chain("shot01")
    append_source(chain, "Style", "style-main", _sha("a"))
    with pytest.raises(SourceChainError, match="expected Cast"):
        append_source(chain, "Keyframe", "kf", _sha("d"), parent_ref="style-main")

    append_source(chain, "Cast", "cast-hero", _sha("b"), parent_ref="style-main")
    append_source(
        chain,
        "StatePhoto",
        "state-red",
        _sha("c"),
        parent_ref="cast-hero",
        wardrobe_state="red-dress",
    )
    with pytest.raises(SourceChainError, match="wardrobe regression"):
        append_source(
            chain,
            "Keyframe",
            "kf",
            _sha("d"),
            parent_ref="state-red",
            wardrobe_state="blue-dress",
        )

    stale = copy.deepcopy(chain)
    stale["nodes"][0]["assetHash"] = _sha("9")
    assert not validate_source_chain(stale)["ok"]


def test_source_chain_rejects_shot_relabel_and_chain_hash_tampering() -> None:
    chain = new_source_chain("shot01")
    append_source(chain, "Style", "style-main", _sha("a"))

    relabeled = copy.deepcopy(chain)
    relabeled["shotId"] = "shot02"
    assert not validate_source_chain(relabeled)["ok"]

    stale_digest = copy.deepcopy(chain)
    stale_digest["chainHash"] = _sha("f")
    assert not validate_source_chain(stale_digest)["ok"]
