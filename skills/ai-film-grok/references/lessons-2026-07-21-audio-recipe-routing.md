# Lessons · 2026-07-21 · 场景自适应 audio_recipe

**层**：voice · **P**：默认可复现；能力不足降级；不静默开唱

## 规则

1. 片级 `audio_policy`（默认 `mode=auto`，**allow_sung=false**）  
2. 镜级 `audio_recipe` 由 beat 路由：`hook/action→narrate_bed`，`sensory/afterglow 短→bed_focus`，`reaction/bridge→narrate_thin`  
3. `sung_beat` 仅 `musical_hybrid` + allow_sung + 能力就绪；否则 `degraded_from`  
4. write-spec 写 `_audio_routing` + `bed_gain_hint`；final 调床响度  

## 入口

`scripts/audio_recipe.py` · [audio-recipe.md](audio-recipe.md)
