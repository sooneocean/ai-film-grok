# Memory · 2026-07-29 索引

E病毒 ch4 批跑 / 解剖修毒 / Comfy 5090 / **收尾门禁** 时先扫本页。

| 主题 | 文件 | 要点 |
|------|------|------|
| **画面抗重复·抗无聊 IRON（P0 · 后面不要再犯）** | [shot-variety-anti-boring](2026-07-29-shot-variety-anti-boring.md) · [lesson](../references/lessons-2026-07-29-shot-variety-anti-boring.md) | 门绿≠好看；motion 禁复制；camera.shot_size 真变；主戏≥4.5s；contact 可读差 |
| **成片收尾门禁 IRON（P0 · 后面不要再犯）** | [closeout-gates-iron](2026-07-29-closeout-gates-iron.md) · [lesson](../references/lessons-2026-07-29-closeout-gates-chaebol.md) | plate≠完；heat codes；sensory；truth_contract；字幕钟；quality 缓存；narrative 重绑；export 链 |
| **bulk→final 出片 IRON（P0 · 后面不要再犯）** | [evirus-ch04-bulk-final-iron](2026-07-29-evirus-ch04-bulk-final-iron.md) · [lesson](../references/lessons-2026-07-29-evirus-ch04-bulk-final-iron.md) | bare 拦→续接高动；evidence 双轮；final 超时/sidechain/字幕坑 |
| **毒镜解剖 IRON（P0 · 后面不要再犯）** | [poison-shot-anatomy-iron](2026-07-29-poison-shot-anatomy-iron.md) · [lesson](../references/lessons-2026-07-29-anatomy-milk-futa-comfy-batch.md) | 禁 futa/喷奶/霓虹器；毒 still 禁 I2V；毒 clip 禁 final |
| **Comfy 批跑 + 解剖铁律** | [evirus-ch04-comfy-anatomy-batch](2026-07-29-evirus-ch04-comfy-anatomy-batch.md) | free-memory --confirm；禁并行 5090；fix 不挡 bulk |
| 色情冲击全闸 | [adult-impact-max-gates](2026-07-28-adult-impact-max-gates.md) | coitus/size/pose/sex_arc 等 strict |
| 成人尺度 + 肉戏弧 | [07-27 adult-scale](2026-07-27-adult-scale-max-sex-arc.md) | 前戏→插入→射出 |
| 高动态 + 画风锁 | [07-27 high-motion](2026-07-27-high-motion-style-final.md) | mean≥18/20；gate 才桌面 |
| 声线分轨 | [07-24 voice](2026-07-24-ep2-voice-heat-final.md) | 口白 zh / 角色 ja / 字幕 zh |

## 片例
- `AI FILM SPACE/0728/e-virus-ch04-shelter`：5090 SSH 隧道 18188；ACE rnb BGM；anatomy_fix + batch_bare_still_i2v
- `AI FILM SPACE/0729/e-virus-ch04-shelter`：14 镜 bulk；Imagine bare I2V moderated → undress 续接；motion retake；简化混音 + PIL 字幕；`out/film_final.mp4` PARTIAL
- `AI FILM SPACE/0729/chaebol-cast-rule-max`：10 镜 adult-max；双轨 still；motion retake；简化 final + 破冻；**官方 closeout 全绿** + Desktop 包；delivery **PARTIAL**（非真 bare）

## 成片前 15 秒
1. clips 计划数齐（无 archive / orphan pilot 冒充）
2. 中/末帧抽：无 futa、无喷奶、无回穿
3. motion gate ok（mean 平常≥18 / 肉戏≥20）**且** 相邻 motion 主句不撞、contact 可读差（抗无聊）
4. TTS 齐 + BGM rnb + license
5. final：长超时或直调 render_final；sidechain 卡则 amix
6. 抽帧可见中文字幕

## 收尾前 15 秒（plate 已有）
1. heat check：无 `SEX_BOTH_UNDRESS_*` 等 hard codes（写 `partner_wardrobe_state`）
2. sensory：sex_sfx 事件 + mix artifacts + AV≥90
3. truth_contract sha = 当前 film-spec；stills 真 approved
4. timeline/film_timeline = 真 concat 钟；SRT 不跨 hard 切
5. `i2v-final-gate` ok；改片则 `rm out/quality-report.json` + 重绑 narrative
6. review-final → post-audit delivery_ready → export-desktop
