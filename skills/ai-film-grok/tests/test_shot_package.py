from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from department_contracts import (  # noqa: E402
    migrate_audio_bible,
    migrate_post_bible,
    migrate_style_bible,
)
from shot_package import (  # noqa: E402
    ShotPackageError,  # noqa: E402
    check_shot_package_current,
    compile_shot_package,
)


def _lock_nodes(bible: dict) -> dict:
    for node in bible["nodes"].values():
        node["state"] = "locked"
        node["approval_ref"] = f"approval-{node['id']}"
    return bible


def _graph() -> dict:
    return {
        "episodes": [
            {
                "id": "ep01",
                "scenes": [
                    {
                        "id": "sc01",
                        "beats": [
                            {
                                "id": "bt01",
                                "shots": [
                                    {
                                        "id": "shot01",
                                        "narrativePurpose": "the reveal",
                                        "wardrobeState": "red-dress",
                                        "locationId": "hotel",
                                        "characterIds": ["hero"],
                                        "duration_sec": 6,
                                        "dsl": {"subject": "hero", "action": "turns"},
                                        "nar": "Do not look back.",
                                        "performance": {"intent": "restrained"},
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def test_package_contains_exact_department_node_ids_and_hashes() -> None:
    visual = _lock_nodes(
        migrate_style_bible({"characters": {"hero": {}}, "locations": {"hotel": {}}})
    )
    audio = _lock_nodes(migrate_audio_bible({"voice": "eve"}))
    post = _lock_nodes(migrate_post_bible({"captions": "zh-en"}))

    package = compile_shot_package(
        "shot01",
        graph=_graph(),
        visual_bible=visual,
        audio_bible=audio,
        post_bible=post,
    )

    assert package["readOnly"] is True
    assert len(package["packageHash"]) == 64
    refs = {
        ref["nodeId"]: ref["hash"]
        for department in package["departments"].values()
        for ref in department
    }
    for node_id in (
        "visual.face.primary",
        "visual.hair.primary",
        "visual.makeup.primary",
        "visual.wardrobe.primary",
        "visual.location.primary",
        "visual.art.primary",
        "visual.prop.primary",
        "visual.cinematography.primary",
        "audio.voice.primary",
        "post.captions.primary",
    ):
        assert len(refs[node_id]) == 64
    assert check_shot_package_current(
        package,
        graph=_graph(),
        visual_bible=visual,
        audio_bible=audio,
        post_bible=post,
    )["current"]


def test_package_hash_is_stable_and_detects_changed_source_node() -> None:
    graph = _graph()
    visual = _lock_nodes(migrate_style_bible({"characters": {"hero": {}}}))
    audio = _lock_nodes(migrate_audio_bible({}))
    post = _lock_nodes(migrate_post_bible({}))
    first = compile_shot_package(
        "shot01",
        graph=graph,
        visual_bible=visual,
        audio_bible=audio,
        post_bible=post,
    )
    second = compile_shot_package(
        "shot01",
        graph=copy.deepcopy(graph),
        visual_bible=copy.deepcopy(visual),
        audio_bible=copy.deepcopy(audio),
        post_bible=copy.deepcopy(post),
    )
    assert first["packageHash"] == second["packageHash"]

    changed = copy.deepcopy(visual)
    changed["nodes"]["wardrobe"]["data"] = {"wardrobe": "blue"}
    report = check_shot_package_current(
        first,
        graph=graph,
        visual_bible=changed,
        audio_bible=audio,
        post_bible=post,
    )
    assert not report["current"]
    assert "visual.wardrobe.primary" in report["changedNodeIds"]


def test_package_tracks_workshop_creative_projection() -> None:
    graph = _graph()
    graph["episodes"][0]["scenes"][0]["beats"][0]["shots"][0]["creative"] = {
        "shot_function": "evidence reveal",
        "end_state": "ticket remains visible",
    }
    visual = _lock_nodes(migrate_style_bible({"characters": {"hero": {}}}))
    audio = _lock_nodes(migrate_audio_bible({}))
    post = _lock_nodes(migrate_post_bible({}))
    package = compile_shot_package(
        "shot01", graph=graph, visual_bible=visual, audio_bible=audio, post_bible=post
    )
    refs = {ref["nodeId"] for ref in package["departments"]["performance"]}
    assert "creative.shot.shot01" in refs


def test_package_detects_execution_shot_fields_and_rejects_stale_nodes() -> None:
    graph = _graph()
    visual = _lock_nodes(migrate_style_bible({"characters": {"hero": {}}}))
    audio = _lock_nodes(migrate_audio_bible({}))
    post = _lock_nodes(migrate_post_bible({}))
    package = compile_shot_package(
        "shot01",
        graph=graph,
        visual_bible=visual,
        audio_bible=audio,
        post_bible=post,
    )
    changed_graph = copy.deepcopy(graph)
    changed_graph["episodes"][0]["scenes"][0]["beats"][0]["shots"][0]["wardrobeState"] = (
        "blue-dress"
    )
    assert not check_shot_package_current(
        package,
        graph=changed_graph,
        visual_bible=visual,
        audio_bible=audio,
        post_bible=post,
    )["current"]

    stale_visual = copy.deepcopy(visual)
    stale_visual["nodes"]["hair"]["state"] = "stale"
    stale_visual["nodes"]["hair"]["approval_ref"] = None
    with pytest.raises(ShotPackageError, match="not currently locked"):
        compile_shot_package(
            "shot01",
            graph=graph,
            visual_bible=stale_visual,
            audio_bible=audio,
            post_bible=post,
        )


def test_package_rejects_shot_with_only_an_id() -> None:
    graph = {
        "episodes": [
            {
                "id": "ep01",
                "scenes": [
                    {
                        "id": "sc01",
                        "beats": [{"id": "bt01", "shots": [{"id": "shot-empty"}]}],
                    }
                ],
            }
        ]
    }
    with pytest.raises(ShotPackageError, match="missing execution fields"):
        compile_shot_package(
            "shot-empty",
            graph=graph,
            visual_bible=_lock_nodes(migrate_style_bible({})),
            audio_bible=_lock_nodes(migrate_audio_bible({})),
            post_bible=_lock_nodes(migrate_post_bible({})),
        )
