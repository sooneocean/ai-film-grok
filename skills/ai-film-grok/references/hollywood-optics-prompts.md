# 好莱坞光学焦段与灯光注入规范（2026-08-04）

> **P0 · Hollywood DP Optics + Lighting Injection**
> 本文件定义 Keyframe 状态照与 I2V Prompt 的自动注入词库，使每一帧画面具备电影级摄影美学。

## 一、焦段矩阵（景别 → Lens Focal Length）

| 景别 (`shot_size`) | 推荐焦段 | 景深效果 | Prompt 注入词（自动拼接首行） |
|---|---|---|---|
| `wide` / `establishing` | 35mm | 深焦；环境主导 | `cinematic 35mm, deep focus, full environment visible, natural horizon` |
| `medium full` / `medium` | 50mm | 中等景深；人物+背景均衡 | `cinematic 50mm, moderate depth of field, character and environment balanced` |
| `close-up` | 85mm | 浅景深；背景虚化 | `cinematic 85mm portrait, f/1.4, creamy bokeh, shallow depth of field, subject sharp` |
| `insert` / `sensory` (物件) | 105mm macro | 极浅景深；细节主导 | `cinematic 105mm macro, extreme shallow depth, detail fills frame, surrounding blurred` |
| `reaction` (人脸反应) | 85mm | 浅景深；表情主导 | `cinematic 85mm, soft bokeh, full head with headroom, facial micro-expression readable` |

**使用规则**：
1. 写入 film-spec 时不必手动填焦段，**由 Prompt 构造器在 write-spec 阶段按 `shot_size` 自动注入**。
2. 若用户在 `dsl.motion` 首行已写明焦段，则**保留用户写法**，不覆盖。
3. 禁止在对白/特写镜中使用 `wide shot` + `85mm`（焦段与景别矛盾）。

---

## 二、三点式灯光矩阵（基调 → Lighting Setup）

| 场景基调 | 主光 (Key Light) | 辅光 (Fill Light) | 轮廓光 (Rim Light) | Prompt 注入句 |
|---|---|---|---|---|
| **温暖亲密 (Warm Intimate)** | 软光 45° 侧面 | 暖色低强度 (3:1) | 发丝逆光 | `warm cinematic key light 45° side, soft fill 3:1 ratio, golden hair backlight, teal shadows amber skin` |
| **冷峻紧张 (Cool Tense)** | 硬光侧面 | 极弱冷调 (6:1) | 蓝白逆光 | `cold hard side key light, minimal fill 6:1, crisp blue backlight, deep contrast, teal grade throughout` |
| **戏剧高潮 (Dramatic Peak)** | 低角度硬光 | 近乎无 | 强烈逆光剪影 | `low-angle hard key, near-zero fill, powerful rim backlight, silhouette-ready, high contrast cinematic` |
| **余韵温柔 (Afterglow Soft)** | 漫射软光 | 暖填充 (2:1) | 微弱发丝光 | `diffused warm key, gentle fill 2:1, subtle hair light, soft shadows, golden hour mood` |
| **中性日常 (Neutral)** | 软光正 45° | 均衡填充 (3:1) | 自然背景分离 | `natural 3-point lighting, 45° soft key, balanced fill, natural separation from background` |

**使用规则**：
1. `director_intent.tone` 映射到以上基调（`intimate → Warm`；`thriller → Cool`；`climax → Dramatic`；`afterglow → Soft`）。
2. 同一 scene 内基调**不频繁切换**；跨 scene 转换时，过渡镜头先切基调再切对白。

---

## 三、Teal & Orange 色彩对比（好莱坞标配调色）

```text
Shadow Zone: teal / dark cyan (#1A3A3A ~ #0D2B2B)
Midtone: neutral grey-beige (#C0B080)
Highlight / Skin: warm amber / golden (#F5C070 ~ #E8903A)
```

**注入词**（`color_grade` 字段或 Prompt 末行）：
```text
teal shadows, warm amber highlights, cinematic color grade, skin tones warm and saturated
```

---

## 四、对白三相表演 Prompt 词库

对白镜头中，Keyframe / I2V Prompt 必须按三相覆盖：

| 阶段 | 时段 | 必须包含的 Prompt 片段 |
|---|---|---|
| **Pre-Speech** (前置反应) | 0.15–0.25s 开口前 | `subtle intake of breath before speaking, eyes shift slightly, lips part gently` |
| **Spoken Delivery** (口型动态) | TTS 音频全长 | `mouth clearly articulates dialogue, natural lip sync, facial muscles engaged, eye contact maintained` |
| **Afterglow Breath** (话后余韵) | 0.35–0.70s 收尾后 | `soft exhale after speaking, expression slowly releases, eyes settle or glance away` |

**长台词拆镜规则** (>4.5s)：
```text
Line duration > 4.5s
  → 说话者主镜 (Speaker Shot): 前 2/3 台词 + Pre-Speech + mid delivery
  → 听者反应切镜 (Listener Cutaway): 后 1/3 台词 (off-camera) + Reaction CU
  → 音轨(DX)连续不断; 画面完成一次电影级别切镜
```

---

## 五、自检清单（write-spec 后 · I2V 提交前）

```text
[ ] 每镜 shot_size 已映射到对应焦段注入词
[ ] 场景基调已映射到三点式灯光预设
[ ] 对白镜 Prompt 包含 Pre-Speech + Delivery + Afterglow 三段
[ ] 长台词 (>4.5s) 已拆分为说话者+反应切镜
[ ] 色彩调色词 (teal shadows, warm amber) 已注入
[ ] 未出现平光/均光无层次描述（documentary 除外）
```

## 六、关联文件

- [hard-defaults.md](hard-defaults.md) → 5-Track 混音、零旁白 IRON
- [directors-lens.md](directors-lens.md) → DP 焦段矩阵（写入运镜词表后）
- [5track-audio-master.md](5track-audio-master.md) → 声音架构
- [dialogue-first-workflow.md](dialogue-first-workflow.md) → 三相表演 DAG
