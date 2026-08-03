# 荒岛九十九 EP1 · 节奏 / 静帧内容 / 口白 / 丝滑成片

> 2026-08-03 · 片源：`AI FILM SPACE/0803/huangdao-99-ep01`《荒岛九十九·第一回》  
> 用户反馈链：**第二镜是啥 → 口白有问题 → 剪辑怪 → 不要图片要影片 → 要节奏像电影 → 末帧接首帧 + HyperFrames 丝滑 → 推进到最后**  
> 映射：P0 先验后生 · P3 动能 · P4 声画 · 对白主链 · continue 帧链 · 设计后期

## 失败现场（成片「看不下去」的真因）

| 现象 | 根因 | 错误「救法」 |
|---|---|---|
| **第二镜像设定图** | keyframe 误用 **角色 turnaround / 多格表情板**；H3/I2V 只是把拼图动起来 | 继续 bulk / 只重 final |
| **口白语种乱** | `dialogue_spoken_lang=zh` 但 `cast_voices` 仍 **ja-JP-***；ledger 只有 `spoken_text_ja`；旧 TTS 英文残留 | 用户说「先这样」就 ship 英文，后再骂节奏 |
| **剪辑像 PPT** | 每镜硬切 ~6s；对白 VO≈2s → **vo/plate≈0.3–0.5 死气**；动作镜也 6s 平铺 | 只加 BGM / loudnorm |
| **静图当片** | moderated 后 Ken Burns / still-motion 装片；用户明确 **不接受图片** | 说「代理可过门」当 DONE |
| **镜间跳戏** | 未 `extract-frame --promote-keyframe`；下镜从 cast 重开 | 只靠 xfade 糊接缝 |
| **final 门禁红** | wardrobe ladder / tts-rehearsal / impact 等硬拦，agent 卡死或假完成 | 空转 preflight 不出片 |

## 正确做法（决策树）

### A. 静帧内容 · 禁设定图入戏（P0）

1. **一镜一连续叙事静帧**：单场景、单构图、可读 `playable_action`。  
2. **禁止** 入 `keyframes/<shot>.png` 再 I2V：  
   - character sheet / turnaround / 多格表情板  
   - 带「ORTHO / POSE / model sheet」标注的拼图  
   - 纯定妆半身无剧情空间关系（当该镜叙事是两人互动/办事时）  
3. register-still **approved** 前：几何门 + `lint_still_not_character_sheet`（**路径含 sheet/turnaround/ortho 等硬拦**；多格+白板仅 soft 警示，agent 仍须肉眼拒设定图）。  
4. 发现 sheet：archive → 按 shot `must_show`/`visible_change` 重生 → 再 I2V。  
5. **禁** 用 `cp cast-master` / multi-view 拼图冒充剧情 still。

### B. 口白语言锁（P0 · 对白主链）

1. `dialogue_spoken_lang=zh` ⇒ **强制**  
   - `cast_voices` 角色 = `zh-CN-YunxiNeural`（男）/ `zh-CN-XiaoyiNeural`（女）  
   - ledger / 镜头字段：`spoken_text` / `spoken_text_zh` = 中文对白；`caption_text` 中文  
2. **禁止** 同时 `spoken_lang=zh` + `cast_voices=ja-JP-*`（荒岛案现场）。  
3. 日文仅显式 `dialogue_spoken_lang=ja` 或用户点名。  
4. final 前自检表：`speaker | voice | spoken_lang=zh | caption=zh | screen_mode`。  
5. 用户赶时间说「口白先这样」→ 可 ship，但 **receipt 标 PARTIAL**，不得改写 hard-defaults 默认为英文。

### C. 节奏 · VO-fit 电影剪（P0）

1. **对白镜**：`duration ≈ pre(0.15–0.25) + VO + post(0.35–0.70)`，**禁止** 短 VO 硬贴 6s plate 填静音（体感死气）。  
2. **动作/silence 镜**：按 beat 给时长（接近 3.5–5s、办事 4.5–6s、余韵略拖），**禁止** 全片等长 6s。  
3. 总片长优先 **看得下去**；硬凑 60s → **加镜/加字**，禁止拖腔（见 [vo-drag-motion-snap](lessons-2026-07-20-vo-drag-motion-snap.md)）。  
4. 默认 `visual_fit: vo` 对 dialogue_drama；preflight `VO_DRAG_OR_DEAD_AIR` 在 vo/plate&lt;0.55 应对 **对白镜 hard 建议 VO-fit 重剪**（ship 路径可 soft）。  
5. 节奏验收：用户能否在 10s 内感到「有对话互动」，而不是「每格等三秒」。

### D. 要影片不要图（P0）

1. 交付 clip **禁止** 纯 still / Ken Burns 冒充 I2V（用户原话：画面不接受图片）。  
2. moderated → **末帧 continue + H3/本地** 或 降敏但仍是 **真 I2V**；记 PARTIAL 原因，**禁止** 静默 still 过 final。  
3. motion_score 失败的 hero 须 re-I2V；threshold 贴边不算「好看」。

### E. 末帧 → 下镜首帧（P0 · 帧链）

1. 每镜 register 后：`aifilm extract-frame --shot-id S --which last --promote-keyframe NEXT`。  
2. 下镜 I2V **必须** 从 promoted keyframe/seed 开，**禁止** 回 cast master 重起（除非 hard cut 且 continuity_chain 标明 smash）。  
3. continue 镜 prompt 按 **真实末帧** 衣着/姿势写，不写开场设定。  
4. 用户要「丝滑」时：帧链 **先于** 转场特效；xfade 不能补身份跳变。

### F. 丝滑成片路径（门禁红也能交付）

当 `aifilm final` 被 wardrobe/rehearsal 等 **与已齐 clips 无关** 的门卡住，且用户要看片：

1. **Plate 层**：VO-fit 分镜 → 变长 xfade(0.22–0.50) + acrossfade → rnb 侧链 + loudnorm → `out/*-plate-silk.mp4`  
2. **Post 层**：**HyperFrames** underlay + 中文 `caption_text` 淡入淡出 + 轻 grade；`plate subs=off`  
3. 交付命名：`*-silk-final.mp4`；`receipts/delivery-final.json`；**诚实 PARTIAL**（非 `final_complete`）  
4. **禁止** 把 ship-cut 标成 gate 全绿 master；完整 closeout 仍走 review-final → post-audit → export-desktop  

## 代码与门禁挂点

| 位置 | 行为 |
|---|---|
| `media_qa.lint_still_not_character_sheet` | approved still 启发式拦 multi-panel sheet |
| `register-still` | approved 失败码 `STILL_LOOKS_LIKE_CHARACTER_SHEET` |
| hard-defaults / stages/visual·voice·post | 本课 P0 行 |
| 既有 | `extract-frame --promote-keyframe` · VO drag soft · HF caption owner |

## Agent 自检（final 前 60 秒）

```text
[ ] 每镜 keyframe 是单场景剧情（不是 sheet）
[ ] cast_voices 语言 = dialogue_spoken_lang
[ ] 对白镜 vo/plate ≥ 0.55 或已 VO-fit 重剪
[ ] 无 Ken Burns 静图当 hero clip
[ ] 邻镜 last→promote 已跑（或 smash 已记）
[ ] 交付片路径 + 抽帧可见中文字幕
[ ] 若跳过 aifilm final 门：PARTIAL + delivery receipt
```

## 片例路径

- 成片：`huangdao-99-ep01/out/huangdao-99-ep01-silk-final.mp4`  
- 回执：`receipts/cinematic-silk-plate.json` · `receipts/delivery-final.json` · `receipts/silk-continuity-hf.json`
