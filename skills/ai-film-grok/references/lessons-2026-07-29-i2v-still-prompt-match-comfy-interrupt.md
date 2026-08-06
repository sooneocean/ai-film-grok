# Lessons · I2V 静帧–prompt 对齐 + Comfy interrupt 假进度（2026-07-29）

**P0 · 后面不要再犯。**  
片例：`0728/btc-vessel-ep02-power-seed` · 镜 `ep01_sc11_bt03_sh01`  
用户原话：**「质量太差了」** → 写回记忆后收工。  
相关：`lessons-2026-07-29-comfy-multifilm-contention-oom.md` · `lessons-2026-07-29-comfy-gpu-priority-pilot-i2v.md` · 高动门 `mean≥18/20`

---

## 发生了什么（事实）

| 项 | 事实 |
|---|---|
| 门禁 | 卡 **13/14**；sc11 hero mean **~12.16 / 18** FAIL |
| 静帧实景 | **机房站姿**金发女（平板+眼镜+bare），**不是**床上 afterglow |
| 旧 prompt | 写「afterglow / sheets / hips micro-thrust」→ 与静帧语义错位 |
| 结果 | Wan 有文件但动势假/弱；用户体感 **质量差**，不是「差 1 分 mean」 |
| 重渲 | seeds 46011/12/13/21：多次 `execution_interrupted @ KSamplerAdvanced`（34–166s 被掐） |
| Grok I2V | bare 静帧 **content-moderated**，不能当救火主路径 |
| 脚本 | tmux waitfire 能扛 agent SIGKILL，**扛不住** 多片 free-memory/interrupt |
| 终态 | **无新 stand mp4**；hero 仍是 14:08 旧 after take；**PARTIAL 诚实** |

路径速查：

- film：`/Users/dex/AI FILM SPACE/0728/btc-vessel-ep02-power-seed`
- hero sc11：`clips/ep01_sc11_bt03_sh01.mp4`
- 旧 takes：`clips/comfy_wan/ep01_sc11_bt03_sh01_after_s43010.mp4`（~12.16）
- 静帧：`keyframes/ep01_sc11_bt03_sh01.png`

---

## 铁律 1 · 静帧是什么，prompt 就写什么（先看图再写动）

**类比**：给站着打电话的照片写「在床上翻滚」，模型只能瞎扭 → 质量必然差。

1. **I2V 前必读静帧**（`read_file` / 目视）：姿态、场景、道具、是否双人、是否肉戏。  
2. **禁止**只信 shot id / 剧名标签（`afterglow`、`meat`、`sc11`）自动套模板 prompt。  
3. 站姿机房 → 写 **weight shift / chest heave / glasses / tablet / LED / push-in**；床戏 afterglow 词 **不准** 硬套。  
4. 标签与静帧冲突 → **先改 still 或改标签**，禁止「错 prompt 撞 mean」。  
5. mean 过线但画面语义错 = **仍 PARTIAL**（用户会说质量差）。

---

## 铁律 2 · mean 数字绿 ≠ 质量过关

1. 高动门（平常≥18 / 肉戏≥20）是 **下限**，不是成片审美。  
2. 错 prompt 的高 mean（若强行 experimental 乱甩）也不可 register。  
3. 出货前至少：**抽 1 中帧 + 1 末帧** 看是否像本镜故事，不是只看 audit JSON。  
4. 用户说「质量差」→ **停刷分**，先对齐 still/prompt/独占 GPU，再批量。

---

## 铁律 3 · Comfy interrupt = 零进度（不要报「快好了」）

1. History：`execution_interrupted @ KSamplerAdvanced`（或 `unknown_node: error`）= **被掐**，不是模型弱。  
2. 常见元凶：他片 / 本脚本 **`free-memory`**、cancel、队列互抢、外片 `comfy_video`（含 **STAT=T 僵尸** 仍占会话）。  
3. **RUNNING 本片时禁止** 任何 client 调 free-memory / interrupt。  
4. 「RUN 了 2 分钟」≠ 快完成：34–166s 被杀 = **0 文件**。  
5. ETA 只能基于：**独占 + 完整 success receipt + 落盘 mp4 字节数**；禁止用排队轮数假装倒计时。

---

## 铁律 4 · 多片 5090：独占或 PARTIAL（强化）

与 multifilm / pilot-priority 课合并执行：

1. 一机一 owner：`ps` 看 **其他 film root** 的 `comfy_video.py generate` → 先停或等，再 submit。  
2. capacity ok **且** foreign generate=0，再 generate；submit 后 **禁止** 为「下一条 seed」抢 free-memory。  
3. 长跑用 **tmux**（macOS 无 setsid）；agent 工具 SIGKILL 会杀前台批，**不杀** Comfy 侧 interrupt。  
4. 禁宽 `pgrep -f` 自杀（shell argv 含脚本名会被 safety 拦/误杀）。  
5. 抢不到 → **PARTIAL + 路径 + 原因**，禁止空转 1 小时假「还在推进」。

---

## 铁律 5 · 救 sc11 类卡镜的正确顺序

1. 读静帧 → 重写 **匹配** prompt（站姿/场景/道具）。  
2. 确认 Comfy **独占**（无 night-lock / e-virus 等外片 generate）。  
3. 先 `adult-motion` 出 **落盘** takes（多 seed max-mean）；不够再 pilot `adult-general-experimental`+meat-motion。  
4. mean≥floor **且** 中/末帧语义过关 → promote hero → `refresh_motion_gate`。  
5. Grok I2V bare 被 moderated → **不要死磕**；走本机 Wan。  
6. 连续 ≥3 次 interrupt → **停**，报需要清场，不要无限 seed。

---

## 反模式清单（本次踩过）

| 反模式 | 后果 |
|---|---|
| afterglow 模板套站姿机房 still | mean~12、用户判质量差 |
| 多 agent 同时 Wan + free-memory | KSampler interrupt；34s 空跑 |
| 报「再 3–8 分钟」而队列 1+4 / 连 fail | 信任破产 |
| 只看 gate 13/14「就差 1 镜」 | 忽视语义/观感失败 |
| Grok I2V 救 bare afterglow | moderated |
| 后台 daemon 被 SIGKILL 当「还在跑」 | 假进度 |

---

## 验收（以后同类任务 DONE 才算）

- [ ] 静帧已目视；I2V prompt 与姿态/场景一致（有一行笔记或 receipt 摘录）  
- [ ] 本 take `receipt.ok=true` 且 `clips/**/*.mp4` 字节 >100KB  
- [ ] mean≥floor **且** 中末帧不像错戏  
- [ ] 无「仅 interrupt 失败」却写推进中  
- [ ] 多片时：foreign generate=0 或已书面 PARTIAL  

---

## 索引一句

**错 prompt 配静帧 = 质量事故；interrupt = 零进度；门绿≠好看；抢不到卡就 PARTIAL。**
