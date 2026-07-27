# 高动态常态 + 画风锁 + 交付门（P0 · 2026-07-27 ep3 案）

**用户原话（合并）**  
- 后半没有动态 / I2V 像没成功 → 实际是 **交付了半成品**  
- 高动态非常重要 · **肉戏拉最高** · **平常也要中高**  
- 肉戏要能 **连戏**  
- 有一些 **画风不一致**  
- 教训写回记忆 · 高动态必须 **常态发生**

**片例 root**：`AI FILM SPACE/0727/ep3`（E病毒 ep3）

---

## 1. 系统层根因（比「某一镜坏了」更深）

把失败看成 **四层漏斗**，任一层假绿都会把烂片交到用户手上：

```text
[生成层] I2V API 返回 mp4
    ↓  漏：429/moderated/弱 10s 微抖
[选型层] raw / boost / takes 里选谁装片
    ↓  漏：装了弱 raw，库里已有 mean20+ 不用
[拼装层] concat + 混音 + 烧字
    ↓  漏：I2V 未齐就 final；并行写同一 exports
[交付层] 拷桌面 / 口头 DONE
    ↓  漏：无 package motion 门、无 style 抽帧
用户看见：后半静 / 半写实跳戏 / 嫌弃
```

**核心洞见**  
1. **生成成功 ≠ 可交付**（raw 24/24 仍可能全是微抖或半写实）。  
2. **动能与画风是正交两闸**：mean 高可以是「油光半写实在抖」；cel 静帧 mean 低也不能交。  
3. **库内多 take 是资产**：选型比再烧一次便宜；永远 `argmax(mean|时长够)`。  
4. **Agent 自我欺骗路径**：`ok` 字段 / 文件存在 / 体积变大 → 当完成；用户只看 **成片像素**。

---

## 2. 反模式清单（禁止再犯）

| 反模式 | 为何坏 | 正确做法 |
|--------|--------|----------|
| Ken Burns 垫底当 I2V | 后半「有文件」无戏 | 无真实 I2V 禁止进 final |
| mean 阈值设 2 | 呼吸也过门 | 平常≥18 肉戏≥20 |
| 只报 raw 完成 | 用户打开是旧桌面文件 | gate ok 才改桌面 mtime |
| 高动 prompt 无 MEDIUM LOCK | 漂半写实 | 每条 I2V 首段 cel 锁 |
| 用 chain last-frame 直接交付 | 连戏+漂移叠加 | chain 与 still-source 双候选竞标 |
| 10s 单条硬撑 | 长时长短动 | 6s×2 hybrid |
| explicit 肉戏词硬刚审核 | 全 MOD 零产出 | 身体力学词 + 仍要求大幅动 |
| chain 无条件覆盖高动 | 连戏了但肉戏「泄力」 | mean≥旧×0.85 且 ≥肉戏门 |
| 并行写同一 film_final | 半截文件/互相覆盖 | 单 writer；work 目录隔离 |
| vocal_color 默认开 | 用户明确禁娇喘 | never / gain=0 永久除非显式恢复 |
| 口头「高动态很重要」不入库 | 下集又松 | **本文件 P0 + hard-defaults + SKILL** |

---

## 3. 双闸模型：Motion Gate × Medium Gate

### 3.1 Motion（像素动能）

度量：`mean_absdiff`，ffmpeg `fps=5,scale=140:248` 灰阶相邻帧。

| tier | 镜类 | 硬底 | 目标 |
|------|------|------|------|
| normal | 蒙太奇/走位/对话 | **≥ 18** | ≥ 20 |
| meat | act/climax/贴身欲望/发热失控 | **≥ 20** | **≥ 24** |
| package | 成片 1:00→尾 抽检 | **≥ 18** | — |
| package_meat | 肉戏时间窗（本集约 73s+） | **≥ 18** | — |

**肉戏 10s 策略**  
1. 先试 6s 高动（往往 mean 更高、审核略松）  
2. 末帧或同 still 再 6s  
3. concat 裁 10s → hybrid  
4. 与「单条 10s」竞标取 max mean  

### 3.2 Medium（画风介质）

| 检查 | 过 | 不过 |
|------|----|------|
| 源图 | style-locked still / keyframe | 漂移 last-frame 单独当源交付 |
| Prompt 首段 | MEDIUM LOCK cel + NEVER photoreal/3D/oil | 只有 motion 形容词 |
| 抽帧 vs style-v1 | 线稿/平涂语言一致 | 整段油光半写实、脸模换族 |

```text
MEDIUM LOCK: high-quality anime illustration, cel shaded, clean lineart,
same character design sheet language as style-v1 / film-style-v2;
NEVER photoreal, NEVER 3D CGI, NEVER oily semi-realistic skin render.
```

**装片竞标公式（概念）**

```text
candidates = raw ∪ boost ∪ takes ∪ style_relock ∪ chain_hybrid
eligible  = { c | duration(c) ≥ shot.dur - 0.25
              and mean(c) ≥ thr(tier)
              and medium_ok(c) }   # 抽帧/人工/启发式
pick      = argmax mean(eligible)
# 若 chain 候选：另要求 mean(chain) ≥ 0.85 * mean(best_still_source)
```

---

## 4. 连戏（continuity）正确姿势

目标：sc07→sc08 姿态/光位/服装 **可读连续**，且不牺牲肉戏动能。

| 步骤 | 动作 |
|------|------|
| A | 主候选：style-locked still + 高动 + MEDIUM LOCK |
| B | 辅候选：prev last-frame seed + 同 MEDIUM LOCK + 高动 |
| C | 仅当 B 的 mean≥max(肉戏门, 0.85×A) **且** medium 不漂 → 用 B |
| D | 服装：卸装后只前进（既有 no-redress）；连戏 seed 仍验肩胸 |

**失败时**：保留 A（高动 still-source）；在 receipt 记 `continuity=partial`，勿为连戏泄动态。

---

## 5. 交付状态机（唯一 DONE 定义）

```text
I2V 批次完成
  → audit.json（逐镜 mean + tier）
  → weak 重跑（串行防 429）
  → 选型装 _i2v_raw
  → style audit 抽帧（开场/中/肉戏）
  → concat + TTS（无 color）+ burn 字幕
  → package motion（after_60 / meat 窗）
  → 写 i2v-final-gate.json {ok:true, ...}
  → 拷贝桌面 film_final（改 mtime）
  → 用户侧：关播放器重开
```

**禁止**：在 audit 红灯时改桌面；用 `film_final_nocolor` 冒充 I2V 完成。

---

## 6. Agent 决策树（落地）

```text
IF 用户抱怨「没动态」:
  先 ffprobe 桌面 mtime vs exports；先测 package after_60
  IF 桌面旧/KB: 选型装高动 + rebuild（未必重烧全片 I2V）
  IF raw 真弱: 强化 prompt 重跑 weak

IF 用户要「高动态常态」:
  门槛用 §3.1；写进 gate；勿降回 2

IF 用户要「肉戏最高」:
  meat thr≥20 目标24；6s×2；审核软词硬动

IF 用户要「连戏」:
  走 §4 双候选；禁止无条件 chain 覆盖

IF 用户要「画风一致」:
  从 stills 重跑 + MEDIUM LOCK（style-relock）
  勿只调 color grade 假装 medium 统一

IF 准备 DONE:
  必须 gate.ok 且桌面 size/mtime 对齐 exports
```

---

## 7. 收据契约（建议文件名）

| 文件 | 内容 |
|------|------|
| `receipts/i2v-high-motion-audit.json` | 每镜 mean、tier、thr、ok |
| `receipts/i2v-final-gate.json` | ok、after_60、meat 窗、path、vocal_color=0 |
| `receipts/style-relock-i2v.json` | 画风重跑结果 |
| `receipts/continuity-chain-result.json` | 链装片与否 |
| `MOTION-POLICY.md`（片根） | 本片硬锁摘要 |
| `out/_style_audit/*.jpg` | 交付前抽帧证据 |

---

## 8. 与既有 P0 的咬合

| 既有 | 本课补的洞 |
|------|------------|
| meaningful-motion | 有语义；本课加 **可测 mean** |
| wardrobe / endframe no-redress | 衣着；本课加 **medium 不漂** |
| verify-before-generate | 先验 still；本课加 **后验 package+style** |
| adult-max-iron | 时长/露；本课加 **肉戏动能最高** |
| voice-tracks | 本课固定 **vocal_color never**（用户 07-27） |
| final 字幕门 | 仍要硬烧中文；与 motion gate **并列** |

---

## 9. 优化 backlog（未写进代码的下步）

1. `aifilm` 子命令：`motion-audit` / `motion-pick-best` / `final-gate` 自动化  
2. register-clip 增加 `score_motion` 数值与 thr 比较硬拦  
3. style-relock：可选 image_edit 把 still 再锁 cel 再 I2V  
4. 并行：仅 **读** 可并行；**写 raw/final** 必须队列化  
5. 审核失败自动改写 prompt 模板库（身体力学词表）

---

## 10. 一页清单（复制即用）

```text
[ ] still medium 先验（style-v1）
[ ] I2V prompt = MEDIUM LOCK + 高动身体动词
[ ] 串行防 429；肉戏 6s×2 可选
[ ] pick max mean among takes（时长够）
[ ] audit 平常≥18 肉戏≥20
[ ] style audit 开场/中/肉戏
[ ] chain 仅双过才换
[ ] package after_60≥18
[ ] vocal_color=0
[ ] gate.json ok → 桌面
[ ] 用户关播放器重开
```

## 版本

- 2026-07-27 v1：立制门槛 + 画风锁 + 交付门  
- 2026-07-27 v2：四层漏斗、反模式、双闸竞标、连戏决策树、收据契约、backlog（深入优化写回）
