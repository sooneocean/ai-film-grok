#!/usr/bin/env python3
"""P0 user-source fidelity — 金瓶梅案 / plan template pollution."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from edit_policy import (  # noqa: E402
    is_template_nar_pollution,
    lint_user_source_fidelity,
)
from story_plan import (  # noqa: E402
    _character_candidates,
    _scene_chunks,
    is_template_nar,
    preserve_user_nar,
    run_plan,
    select_beat_spine,
)


class UserSourceFidelityTests(unittest.TestCase):
    def test_preserve_user_nar_keeps_poem(self) -> None:
        user = "二八佳人体似酥。腰间仗剑斩愚夫，暗里教君骨髓枯。"
        out = preserve_user_nar(user, heat_phase="setup", coitus_beat="entry")
        self.assertIn("二八佳人", out)
        self.assertNotIn("展厅落锁", out)

    def test_preserve_user_nar_keeps_caise(self) -> None:
        user = "财可通神，色能枯骨。唯有这财色二字，世人看不破。"
        out = preserve_user_nar(user, heat_phase="foreplay", coitus_beat="undress")
        self.assertIn("财可通神", out)
        self.assertNotIn("肩带一滑", out)

    def test_empty_falls_back_to_template(self) -> None:
        out = preserve_user_nar("", heat_phase="setup", coitus_beat="entry")
        self.assertTrue(is_template_nar(out) or "加演" in out or "落锁" in out)

    def test_no_auto_dual_climax_on_long_hardcore(self) -> None:
        heat = {
            "spine": "hardcore_male",
            "hardcore": True,
            "heat_scale": "max",
            "dual_climax": False,
        }
        spine = select_beat_spine(heat, target_duration=120)
        keys = [s.get("key") for s in spine]
        # dual climax spine has more keys / second round markers
        self.assertNotIn("act2", keys)
        self.assertLessEqual(len(spine), 12)

    def test_explicit_dual_still_works(self) -> None:
        heat = {"spine": "dual_climax", "dual_climax": True, "heat_scale": "max"}
        spine = select_beat_spine(heat, target_duration=40)
        self.assertGreaterEqual(len(spine), 10)

    def test_character_blocklist_and_bullet(self) -> None:
        raw = """
角色：
- 西门庆：俊朗霸道、肌肉结实
- 吴月娘：端庄美艳
标题：不该当角色
基调：古风
"""
        chars = _character_candidates(raw)
        names = {c["name"] for c in chars}
        self.assertIn("西门庆", names)
        self.assertIn("吴月娘", names)
        self.assertNotIn("标题", names)
        self.assertNotIn("基调", names)

    def test_time_bracket_scene_chunks(self) -> None:
        raw = """
【00:00-00:10 开场】
诗白灰烬。

【00:10-00:35 青楼】
西门庆挥金。

【00:35-00:60 回家】
月娘侍候。
"""
        chunks = _scene_chunks(raw)
        self.assertGreaterEqual(len(chunks), 3)

    def test_lint_pollution_ratio(self) -> None:
        shots = [
            {"id": f"s{i}", "nar": "展厅落锁。今晚只加演你。", "heat_phase": "act"}
            for i in range(6)
        ]
        rep = lint_user_source_fidelity(
            shots, heat_scale="max", source_excerpt="西门庆在青楼挥金，月娘在家等他。"
        )
        self.assertFalse(rep.get("ok"))
        self.assertIn("USER_SOURCE_NAR_POLLUTED", rep.get("codes") or [])

    def test_lint_clean_user_nars(self) -> None:
        shots = [
            {"id": "s1", "nar": "二八佳人体似酥。色字如剑。", "heat_phase": "setup"},
            {"id": "s2", "nar": "财可通神，色能枯骨。", "heat_phase": "foreplay"},
            {"id": "s3", "nar": "压桌撕襟。沉腰办事。", "heat_phase": "act"},
            {"id": "s4", "nar": "九月廿五欲结十兄弟。", "heat_phase": "afterglow"},
        ]
        rep = lint_user_source_fidelity(
            shots, heat_scale="max", source_excerpt="二八佳人，财可通神，色能枯骨。"
        )
        self.assertTrue(rep.get("ok"), rep)
        self.assertTrue(all(is_template_nar_pollution(s["nar"]) is False for s in shots))

    def test_no_source_means_fidelity_is_not_applicable(self) -> None:
        shots = [{"id": f"s{i}", "nar": "展厅落锁。今晚只加演你。"} for i in range(4)]
        rep = lint_user_source_fidelity(shots, heat_scale="max")
        self.assertTrue(rep["ok"])
        self.assertFalse(rep["applicable"])

    def test_plan_run_jinpingmei_excerpt_no_zhan_ting_majority(self) -> None:
        story = """
竖屏重口成人漫剧 第1集 酒色财气
角色：
- 西门庆：俊朗霸道
- 吴月娘：端庄美艳

【00:00-00:10 开场】
旁白：二八佳人体似酥，腰间仗剑斩愚夫，暗里教君骨髓枯。

【00:10-00:35 青楼】
西门庆青楼挥金如土，怀抱半裸女子。
旁白：财可通神，色能枯骨，唯有财色二字世人看不破。

【00:35-00:60 回家】
西门庆压吴月娘于桌案，撕襟揉胸，沉腰办事。
吴月娘：官人别闹，兄弟们要来。
西门庆：今晚先要了你再说。

【00:60-01:30 酒宴】
与应伯爵饮酒。集尾：九月廿五，西门庆欲结十兄弟。
"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = run_plan(
                root,
                story,
                title="金瓶梅测试保真",
                target_duration=90,
                apply_film_spec=True,
                force=True,
            )
            self.assertTrue(report.get("ok"), report)
            spec = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            nars = []
            for sc in spec.get("scenes") or []:
                for sh in sc.get("shots") or []:
                    nars.append(str(sh.get("nar") or ""))
            self.assertGreaterEqual(len(nars), 3)
            polluted = sum(1 for n in nars if is_template_nar(n) or "展厅落锁" in n)
            # majority must be user-faithful, not template
            self.assertLess(
                polluted / max(1, len(nars)),
                0.40,
                f"too many template nars: {nars}",
            )
            joined = " ".join(nars)
            # at least one user token survives
            self.assertTrue(
                any(
                    tok in joined
                    for tok in ("二八", "佳人", "财可通神", "色能枯骨", "西门", "月娘", "九月")
                ),
                joined,
            )


if __name__ == "__main__":
    unittest.main()
