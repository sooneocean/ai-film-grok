from scripts.visual_bible import load_bible, migrate_to_v2, save_bible, update_bible_state


def test_migrate_to_v2_from_v1():
    v1_bible = {
        "title": "Legacy Project",
        "identity_lock": "silver hair, red eyes",
        "cast_masters": {"hero": "path/to/hero.png"},
        "locked": True,
    }

    v2_bible = migrate_to_v2(v1_bible)
    assert v2_bible["schema_version"] == 2
    assert v2_bible["state"] == "Approved"
    assert v2_bible["locked"] is True
    assert "characters" in v2_bible
    assert "hero" in v2_bible["characters"]
    assert v2_bible["characters"]["hero"]["identity"] == "silver hair, red eyes"
    assert v2_bible["characters"]["hero"]["cast_master"] == "path/to/hero.png"


def test_update_bible_state(tmp_path):
    root = tmp_path

    bible = {"schema_version": 2, "state": "Draft", "locked": False, "title": "Test"}
    save_bible(root, bible)

    update_bible_state(root, "Candidate")
    loaded = load_bible(root)
    assert loaded["state"] == "Candidate"
    assert loaded["locked"] is False

    update_bible_state(root, "Approved")
    loaded = load_bible(root)
    assert loaded["state"] == "Approved"
    assert loaded["locked"] is True
