# 效果 ROI 优化 Todo Plan（E0–E5）

**Status:** **SHIP 2.41.19** · E1–E5 默认肌肉接线 + 测  
**日期：** 2026-08-07  
**Repo：** `/Users/dex/.grok/plugins/ai-film-grok`

## 结论

产线能力已齐；本板把 **静帧喂料否决 → 身份 promote → 效果记分卡/弱 take 补烧 → mode 覆盖硬收据 → music-director ship draft → prompt densify** 打成默认路径，而非再贴 IRON 散文。

## 波次

| ID | 状态 | 机读 |
|----|------|------|
| E1 still-feed veto | ✅ | `gates/effect_roi.still_feed_blocks_h3` · `next_actions` |
| E1.4 soft still lint | ✅ | `lint_soft_still_recipe` · preflight soft |
| E2 face promote | ✅ | `assert_face_lock_allows_promote` · `select_shortlist` |
| E3 scorecard + reburn | ✅ | `build_effect_scorecard` · ship-prep steps |
| E3 below-floor ban promote | ✅ | select_shortlist skip below_floor |
| E4 densify dialogue/soft | ✅ | `h3_official_prompt._action` |
| E4 music-director draft | ✅ | ship-prep step |
| E5 mode override hard | ✅ | `h3_workflow.run_h3_shot` reason required |

## 测

`tests/test_effect_roi_e1_e5.py` · 相关 ship-prep / face_lock 回归

## 逃生

`AIFILM_SKIP_STILL_FEED_GATE` · `AIFILM_SKIP_FACE_LOCK_PROMOTE` · `AIFILM_ALLOW_BELOW_FLOOR_PROMOTE` · `AIFILM_H3_MODE_OVERRIDE_REASON` / `AIFILM_ALLOW_H3_MODE_OVERRIDE`

## 非目标

巨石 peel · lipsync 复活 · 真 CV 毒镜 · 无 GPU 假 drain
