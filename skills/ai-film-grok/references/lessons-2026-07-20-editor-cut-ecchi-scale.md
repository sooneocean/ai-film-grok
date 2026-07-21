# Lessons · 2026-07-20 · Editor’s Cut + 成人漫剧最大尺度

> **P 码**：P3 动能 · P4 语义 · P5 分层  
> **案例片**：《薇薇安·夜锁》`vivian-private-encore-60s`  
> **用户原话**：过了；生成规划与事后剪辑可拆开；剪辑师视角全方位优化；尺度拉到最高，成人漫剧要有看点也有刺激点。

## 失败 / 缺口（证据）

| 现象 | 证据 | 根因 |
|---|---|---|
| 成片 ~46s vs brief 60s | `film_final.mp4` 45.9s | 规划阶段只顾 10×6s 库存，**未做剪辑师时长验收**；VO 贴合后未加镜补满 |
| 尺度偏软 | 用户反馈「尺度还是太小」 | still/I2V 过早全面 clothed 软化；**热度档位未在 Lens 钉死为 max**；高潮镜审核后未用 insert/权力差/VO 把刺激补满 |
| 06/09 画面审核软化 | moderation on slip-shoulder / sheets-climax still·I2V | 同 prompt 连撞；未走「画面 suggestive 极限 + VO 全荤」双轨；软化后未 Editor Cut 加 insert 补偿 |
| FRW Seedance 403 | frw newvideo 403 | 已有 degrade 路径；本片全 Grok——需记账，不混 endpoint |
| 规划=剪辑混成一步 | 一次 final 即交付心态 | 缺 **Editor’s Cut Pass** 强制关卡 |

## 用户贡献的正确抽象（采纳）

1. **生成规划 ≠ 事后剪辑**  
   - 规划：故事弧、分镜、still、I2V、库存齐  
   - 剪辑：在**已有素材**上，用剪辑师视角优化 **画面·动作·声音·剧情** 四轴  
2. **成人漫剧双 KPI**  
   - **看点**：权力差、性格翻转、金句、场景仪式感（落锁/解扣）  
   - **刺激点**：距离阶梯顶格、服装失序、办事完成、余韵钩子  
3. **尺度默认拉满**（成人题材）——除非用户降档

## 固化规则

### R1 · Editor’s Cut 强制关（见 [editor-cut-pass.md](editor-cut-pass.md)）

clips 齐 → 写 `receipts/editor-cut.md`（四轴）→ 再交付级 final。  
禁止把「第一次拼板成功」等同艺术完成。

### R2 · 成人漫剧默认 `heat_scale: max`

film-spec / Director’s Lens 必填热度：

| 档 | 画面 | VO | 适用 |
|---|---|---|---|
| soft | 氛围距离 | 暗示 | 全年龄边缘 |
| medium | 半步失序 | 明确暧昧 | 旧默认偏这里 |
| hot | 失序+权力 | 直接身体动词 | 色气短片 |
| **max** | **顶格 suggestive + 高潮主动作** | **办事完成可说满** | **成人漫剧默认** |

max 仍遵守：成年角色、同意虚构、**禁**未成年；still 避免硬核生殖器特写连撞审核——**刺激用姿态/节奏/VO/插镜叠满**。

### R3 · 双轨生成（防审核坍缩尺度）

| 轨 | 内容 | 失败时 |
|---|---|---|
| A 画面 | 顶格 suggestive：跨坐、沉腰、攥床单、锁腿、滑肩、耳语——姿态狠、衣仍「有布」 | moderation → 换角度/半身/插物件，**不**整段改成只 blink |
| B 声画外 | VO 说满结合/完成/感官；SFX 落锁/解扣/床响 | 画面软化时 **加重 B 轨**，并加 insert 镜 |

禁止：审核一次失败 → 整片降到「只脸红眨眼」。

### R4 · 高潮结构（办事完成必占镜）

成人 60s 至少：

1. 落锁/边界（hook–approach）  
2. 失序升级 ≥2 镜（扣/肩/膝锁）  
3. **办事主动作 ≥1 镜**（沉腰/吃进/顶撞——画面姿态 + VO 动词）  
4. **完成/腿软 ≥1 镜**  
5. 余韵钩子  

缺 3–4 → Editor Cut 判 escalation fail，必须补镜或 re-I2V。

### R5 · 时长：brief 60s → 库存与剪辑双保

- 规划：`n_shots * duration_sec − transitions ≥ target * 0.95`  
- 剪辑：实测 plate &lt; target×0.85 → **加镜**（优先高潮前后 insert / 第二动作拍），禁止 loop  

### R6 · 改什么走哪条路

| 用户反馈 | 先做 |
|---|---|
| 尺度不够 | heat_scale=max；重写 2/5/7/8/9；Editor Cut |
| 节奏平 | craft 重串 + re-final |
| 某镜死 | re-I2V |
| 不够色但能动 | 加重 VO+SFX+insert，再考虑 re-still |

## 不可宣称

- 未跑 Editor’s Cut 四轴 → 不得称「剪辑已优化 / 成片已调校」  
- 仅 VO 荤、画面全程礼貌站桩 → 不得称 heat_scale=max  
- 审核软化未补偿 → 不得 score-escalation pass（用户未特批时）

## 命令提示（agent）

```bash
# 库存齐后
# 写 receipts/editor-cut.md → 按清单 re-I2V / 改 nar / 改 craft
"$AIFILM" write-spec --root "<root>"
"$AIFILM" tts-rehearse --root "<root>" --backend edge
"$AIFILM" final --root "<root>" --post-engine hyperframes --music-mood rnb --tts-backend edge
```

## 本片结果

- review-final 用户「过了」；桌面导出 `薇薇安夜锁`  
- 教训已进 skill；**下一部成人漫剧从 Lens 起默认 max + Editor Cut**  
