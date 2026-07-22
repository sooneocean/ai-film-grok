# 色气叙事规范（里番 / ecchi / 成人漫剧短片）

目标：**完播 + 脸红心跳 + 看点与刺激点双满**。色气主要靠 **画面调度与说书人措辞**，不靠毁脸对口型。

> **2026-07-20**：成人漫剧默认 **`heat_scale: max`**；生成规划与剪辑师过片拆开，见 [editor-cut-pass.md](editor-cut-pass.md)、[lessons-2026-07-20-editor-cut-ecchi-scale.md](lessons-2026-07-20-editor-cut-ecchi-scale.md)。  
> **2026-07-21**：**尺度比例拉高**——前戏→进行→高潮完成 必须占片比多数。  
> **女主弹性**：默认**单女主**；多女主仅当用户 Prompt / 多张女主参考图 / 显式字段要求时启用。代码：`resolve_heroine_cast_mode` · `lint_heat_arc` · `lint_multi_heroine`。

## 默认：`vo_mode: storyteller`

说书人可以比角色「更荤」——描述身体距离、气味、呼吸、衣服摩擦、**结合与完成**，而角色只需「演」出来。

## 双 KPI（成人漫剧必检）

| KPI | 白话 | 镜位抓手 |
|---|---|---|
| **看点** | 为什么愿意看完 | 权力差、性格翻转、落锁仪式、金句、场景质感 |
| **刺激点** | 为什么脸红心跳 | 距离阶梯顶格、服装失序、主动作（沉腰/锁腿）、办事完成、余韵钩子 |

只满一个 = 尺度失败。Editor’s Cut 的 Story 轴必须两项都 pass。

## 热度档 `heat_scale`（film-spec / Lens 必填）

| 档 | 画面 | VO | 何时 |
|---|---|---|---|
| `soft` | 氛围距离 | 暗示 | 用户明确降火 |
| `medium` | 半步失序 | 明确暧昧 | 非成人 brief |
| `hot` | 失序+权力 | 直接身体动词 | 色气短片 |
| **`max`** | **顶格 suggestive + 高潮主动作** | **办事完成可说满** | **成人性爱/里番/漫剧默认** |

- 用户说「成人 / 办事完成 / 性爱短剧 / 尺度拉满」→ **必须 max**，禁止默默 medium。  
- max 仍：**角色 18+ 成人**、同意虚构；still **避免**硬核生殖器特写连撞审核。  
- **双轨**：画面顶格姿态（跨坐/沉腰/攥床单/锁腿/滑肩）+ VO 全荤；审核拦画面时 **加重 VO/SFX/insert**，禁止整片退回「只脸红眨眼」。

## 色气升级清单（每条片至少占 4 项；max 档至少 6 项全占）

1. **身体距离阶梯**：远 → 中 → 贴近（耳语距离）→ 贴身/骑跨 → 余韵  
2. **服装失序**：扣子、肩带、腰带、湿透、滑肩（可 suggestive；max 允许半脱仪式）  
3. **感官词**：热、潮、喘、香、心跳、指尖、腿软、攥白  
4. **权力差**：她/他主导「教你规矩 / 加演 / 落锁」  
5. **双关金句**：表面规矩，潜台词色情  
6. **办事完成拍**（max 必选）：至少 1 镜主动作结合 + 1 镜完成/高潮反应  
7. **禁止扫兴**：不要用说教收尾；用「未完 / 续借 / 下回 / 下一场换你」悬着

## 弱 vs 强（改写示例）

| 弱（像段子合集） | 强（像里番预告） |
|---|---|
| 今天主题是双关 | 她把「双关」写在黑板上，粉笔灰落在锁骨上 |
| 别想歪 | 她说别想歪——却把椅子拉近半掌 |
| 下课了 | 铃响了，她没起身，只问你还想不想「加练」 |

## 分镜骨架

### 6 镜 · ~40–55s（hot 以下）

| 镜 | 功能 | 色气点 |
|---|---|---|
| 1 | 登场 | 服装/场所压迫感 |
| 2 | 靠近 | 空间变窄（书架/柜台/后座） |
| 3 | 感官特写 | 嘴、锁骨、汗、眼神（仍可不说话） |
| 4 | 对方反应 | 脸红/躲/喘（观众代入） |
| 5 | 身体行动 | 走道、弯腰、伸手、压近 |
| 6 | 余韵钩子 | 未完成的邀请 |

### 10 镜 · ~55–70s（**max / 办事完成** 推荐）

| 镜 | 功能 | `heat_phase` | 看点 / 刺激点 |
|---|---|---|---|
| 01 | hook | setup | 登场压迫 / 门与边界（**短**） |
| 02 | approach | setup→foreplay | 拽入·空间变窄 |
| 03 | sensory | **foreplay** | **落锁** / 贴身第一刀 |
| 04 | reaction | **foreplay** | 耳语距离·权力翻转 |
| 05 | action | **foreplay** | 解扣/失序 |
| 06 | sensory | **act** | 骑跨/压近·主动作起 |
| 07 | action | **act** | 膝锁腰·节奏进行中 |
| 08 | action | **act→climax** | **沉腰办事**（刺激峰值） |
| 09 | sensory | **climax** | **腿软/办完/高潮反应**（完成拍·必选） |
| 10 | afterglow | afterglow | 钩子未完 |

满 60s：优先 **加 act/climax 镜** 或 insert（指节床单），禁止 loop 撑时长。

---

## 尺度比例（2026-07-21 · 拉高亲密核）

### `heat_phase` 枚举（每镜建议写；write-spec 可从 dramatic_function 推断）

| phase | 白话 | 画面抓手 |
|---|---|---|
| `setup` | 登场/边界 | 门、距离远、权力差建立 |
| `foreplay` | 前戏 | 贴身、解扣、耳语、落锁、感官 |
| `act` | **进行中** | 骑跨、沉腰、锁腿、节奏连续（可多镜） |
| `climax` | **高潮完成** | 办完反应、攥床单、失声、腿软（≥1 镜） |
| `afterglow` | 余韵钩子 | 未完邀请，禁说教 |
| `bridge` | 转场垫 | 空镜/物件，不抢亲密核时长 |

### 亲密核（intimacy core）vs 性爱片段（sex core）

```text
亲密核 intimacy = foreplay + act + climax   （镜数占比 · 建议）
性爱片段 sex    = act + climax only         （duration_sec 加权 · 产品底）
```

| `heat_scale` | 亲密核**参考**（镜比） | **性爱片段时长**（act+climax / 总 duration_sec） | setup 参考 | 说明 |
|---|---|---|---|---|
| max（成人/办事完成） | **建议** ≥ 60% | **硬底 ≥ 20%**（write-spec 默认 `sex_floor_strict`） | **建议** ≤ 25% | 尺度太小根因常是 setup/foreplay 占满、性爱时长不足 |
| **max + 重口男向**（「重口/男向/尺度太小」） | **目标 ≥ 70%** | **目标 ≥ 40%**（`audience_profile: hardcore_male`） | **setup ≤ 2 镜 / ≤20%** | act **≥4** + climax **≥2**（10 镜 60s） |
| hot | 建议 ≥ 40% | soft floor ≥ 15% | — | 弹性 |
| medium 及以下 / 未写 | 不要求 | 不要求 | — | 跟 brief |

**60s / 10×6s 速算**：性爱硬底 20% = **≥12s** act+climax（最少 2 镜满 6s，或 1×10s+余量）；大尺度建议 **≥3–4 镜 act + 1–2 climax**（≥35–40%）。

**弹性原则**：用户 brief 要热 → 拉高性爱时长；用户只要暧昧 → `heat_scale` 别钉 max / 设 `sex_floor_strict:false`。  
**参考脊柱**（max 60s）：1–2 setup + 2 foreplay + **3–4 act** + **1–2 climax** + 1 afterglow。

| 字段 | 含义 |
|---|---|
| `sex_min_duration_ratio` | 覆盖性爱时长底（默认 max=0.20；hardcore=0.40） |
| `sex_floor_strict` | `HEAT_SEX_DURATION_LOW` 是否 hard-fail write-spec（**max 默认 true**） |
| `sex_wardrobe_strict` | 全装/铠甲办事是否 hard-fail（**max 默认 true**） |
| `wardrobe_state` | 每镜：`full`→`armored`→`partial`→`undressed`→`bare` |
| `_heat_arc.sex_duration_ratio` | 指标：性爱秒数 / 总秒数 |
| `_heat_arc.wardrobe` | 卸甲拍 + act 衣着状态 |

详见 [lessons-2026-07-21-sex-duration-floor.md](lessons-2026-07-21-sex-duration-floor.md) · [lessons-2026-07-21-sex-undress-ladder.md](lessons-2026-07-21-sex-undress-ladder.md) · [lessons-2026-07-21-wardrobe-no-redress-still.md](lessons-2026-07-21-wardrobe-no-redress-still.md)（**脱下禁止穿回 · undress-anchor**）。

### 办事卸甲阶梯（wardrobe ladder · 硬底）

```text
定妆 full/armored → 前戏 partial（失序/半脱/卸甲动作）→ act undressed/bare → climax bare
```

| 禁止（act/climax） | 必须 |
|---|---|
| 全装正装跨坐 | `wardrobe_state`: partial / undressed / bare |
| 铠甲完整「办事」 | 至少 1 镜 **卸甲/脱衣动作**（foreplay 或 act 入口） |
| 只写 heat_phase=act 仍穿完整 tech dress | still/I2V：**铠甲/裙落，裸露皮肤可读** |

静帧 prompt 抓手：`armor discarded` · `dress off` · `bare skin` · `半裸` · `卸甲` · `skin-to-skin`。  
审核软化：可用 **suggestive undressed**（非硬核生殖器特写），但**不得退回全装**。

### 重口男向（2026-07-21 · 用户嫌尺度小时强制）

触发：`重口` / `成人重口` / `男向` / `重口男性观众` / `尺度太小` / `不够色`。

| 项 | 规则 |
|---|---|
| `director_intent.audience` | 写明「重口男向短片观众」 |
| `heat_scale` | **必须 max** |
| Selects | 优先 latch/失序/跨坐/沉腰/高潮；**丢掉**空台口走秀 |
| VO | 身体动词说满（沉腰/顶/腿软/办完）；禁纯文艺灯暗句当主句 |
| 画面 | 姿态一眼读得出在办事；审核软化用 VO+insert **补刺激**，禁整片退回牵手 |
| 剪辑 | 必须蒙太奇（insert/smash/montage），见 [lessons-2026-07-21-montage-hardcore-male.md](lessons-2026-07-21-montage-hardcore-male.md) |
| **景别堆叠** | 全景→中→近→特写加压；act 禁止回退全景；见 [lessons-2026-07-21-size-ladder-hardcore-stack.md](lessons-2026-07-21-size-ladder-hardcore-stack.md) |
| **性交冲击力** | 静帧可读「正在结合」；六拍 ENTRY→UNION→RHYTHM→LOCK→FINISH→HOOK；Mute Frame 测试；见 [lessons-2026-07-21-intercourse-impact-benchmark.md](lessons-2026-07-21-intercourse-impact-benchmark.md) |
| **剧情动词** | 边界关闭 / 失序 / 主导 / 办事进行 / 完成 / 钩子 **六拍可见**；VO 动词=画面动作 |

```json
{
  "heat_scale": "max",
  "heat_phase_auto": true,
  "heat_arc_advise": true,
  "heat_arc_strict": false,
  "sex_floor_strict": true,
  "sex_wardrobe_strict": true,
  "sex_vo_strict": true,
  "sex_min_duration_ratio": 0.20,
  "director_intent": { "audience_profile": "hardcore_male" }
}
```

| 字段 | 含义 |
|---|---|
| （不写 heat_scale） | **不自动钉 max** |
| `heat_phase_auto` | 从 dramatic_function 填 phase（不猜 climax） |
| `heat_arc_advise` | `_heat_arc` 多打 info 建议 |
| `heat_arc_strict` | 全部 heat warning 升 hard（默认关） |
| `sex_floor_strict` | **性爱时长** hard（max 默认 **开**） |
| `sex_wardrobe_strict` | **卸甲/脱衣** hard（max 默认 **开**） |
| `sex_vo_strict` | **旁白荤梗** hard（max 默认 **开**） |
| `sex_min_duration_ratio` | 性爱时长底；hardcore_male 未写时 lint 用 0.40 |

`_heat_arc`：`sex_duration_ratio` + `wardrobe` + `vo_spice`；max 默认挡 write-spec。

### 12 镜 max 脊柱（多女主或满 70s）

| 区 | 镜数 | phase |
|---|---|---|
| setup | 1–2 | setup |
| 前戏 | 2–3 | foreplay |
| 进行 | **4–5** | **act（比例最高）** |
| 高潮完成 | **2** | **climax**（主女 + 可选第二女主反应） |
| 余韵 | 1 | afterglow |

---

## 女主弹性（single 默认 · multi 按证据）

### 决策顺序（agent 必跟）

```text
1. 用户显式 cast_mode / multi_heroine
2. heroine_ids 数量（≥2 → multi）
3. 用户上传女主参考图张数（≥2 女主脸 + Prompt 含双/多女）
4. cast_masters 女角键数量（≥2 → multi）
5. Prompt 关键词（双女主 / 两个女 / two girls / dual heroine…）
6. 否则 → single（一张女主图 / 一个女主名就够）
```

| `cast_mode` | 含义 |
|---|---|
| **`auto`（默认）** | 按上表推断 |
| `single` | 强制单女主；忽略「双女」误报时用 |
| `multi` | 强制多女主 |

write-spec 写出：`cast_mode` 解析结果 + `_multi_heroine.resolved` + `_cast_mode_notes`。

### 单女主（默认路径）

```json
{
  "heat_scale": "max",
  "cast_mode": "auto",
  "multi_heroine": false,
  "director_intent": { "cast": ["hero", "partner"] }
}
```

- 一张 `cast/<id>-v1` 即可  
- **不**要求 dual、不要求第二个 focal  
- 亲密核比例规则仍适用（与女主人数无关）

### 多女主（仅证据成立时）

```json
{
  "heat_scale": "max",
  "cast_mode": "auto",
  "multi_heroine": true,
  "heroine_ids": ["kei", "viv"],
  "cast_masters": { "kei": "…", "viv": "…" },
  "female_ref_image_count": 2,
  "user_prompt": "双女主…",
  "director_intent": {
    "cast": ["kei", "viv", "partner"],
    "heroines": ["kei", "viv"],
    "logline": "…双女主…"
  }
}
```

也可不写 `multi_heroine`：用户 Prompt 写「双女主」+ 两张女主 ref / 两个 cast master → auto 升 multi。

### 定妆（按模式）

| 模式 | 资产 |
|---|---|
| single | 1× cast master + lookbook |
| multi | **每个 heroine_id 一张** cast master；可选 dual lookbook |

- still：`image_edit` 第一参考 = **本镜 focal** 的 cast  
- continue：同女主才字节 promote；**换女主 = cut 缝**

### 多女主分镜纪律（仅 multi 激活）

1. 每女主 ≥1 镜 `focal_character=<id>`  
2. ≥1 镜 `viewpoint: dual`  
3. 高潮：A 完成 + B 反应，或 dual 完成  
4. VO 可点名切换；一镜一句一事  

### lint

| 模式 | 行为 |
|---|---|
| single | **跳过** multi lint（无 dual/focal 警告） |
| multi | `MULTI_HEROINE_FOCAL_GAP` / `MULTI_HEROINE_NO_DUAL` soft |
| `multi_heroine_strict` | multi 下升 hard |

### Agent 读用户输入时

| 输入 | 动作 |
|---|---|
| 一段文 + **1 张**女主图 | `cast_mode=single`，一 master |
| 「双女主」+ **2 张**脸 | multi，两 master，两 focal |
| 只写「她」无第二女 | 勿臆造第二女主 |
| 用户后补第二张图 | 升 multi，补 cast + re-plan 部分镜 |

## 旁白长度（避免 6s 镜头被撑成 13s 慢动作）

I2V 默认 **6 秒**。口白过长 → 旧版会慢放/冻帧，观感差。

| 档 | 每镜 `nar` 字数 | 约 VO 时长 | 画面策略 |
|---|---|---|---|
| **推荐** | **28–42 字** | 6–9s | 轻慢 + 循环仍自然 |
| **硬上限（write-spec）** | **≤ 55 字** | ≤11s | 超限直接 `vo_budget` 失败 |
| 避免 | 70+ 字长段 | 13s+ | 拆成两镜，或砍感官复句 |

实现：`scripts/film_spec.py` → `MAX_NAR_CHARS` / `validate_nar_budget`。量产纪律见 [production-discipline.md](production-discipline.md)。

说书人可以色，但**一句一事**：一镜只推进一个距离/感官点。

## 说书人口吻模板（max 办事剧 = 全程荤梗）

> **硬底**：`heat_scale=max` 时 **每镜 `nar` 都要荤梗**；act/climax 必须办事动词。  
> 码：`HEAT_VO_SPICE_MISSING` / `HEAT_VO_SEX_VERB_WEAK` · `sex_vo_strict` 默认 true。  
> 见 [lessons-2026-07-21-sex-vo-spice.md](lessons-2026-07-21-sex-vo-spice.md)。

| 段 | 弱（禁） | 强（要） |
|---|---|---|
| setup | 话说那天夜里… | 展厅**落锁**。今晚只**加演**你一场。 |
| foreplay | 她回眸一笑。 | 肩带一滑，**规矩**失效；**贴身**半掌。 |
| act | 夜色温柔。 | **沉腰吃进**。再沉，**节奏**是她给的。 |
| climax | 心跳加速。 | 她**失声**。背一弓——这一场**办穿**了。 |
| afterglow | 灯灭了。故事却刚好开始。 | 贴耳：**下一场——换你顶。** |

- 开场：「落锁。今晚只办你 / 加演你。」  
- 中段：「沉腰 / 顶 / 磨 / 吃进 / 锁腰」= 画面同动词  
- 金句：双关可留，但**不能只有双关没有身体**  
- 收束：**换你顶 / 未完 / 下一场**，禁说教晚安

## 与 `vo_mode` 的配合

- **storyteller**：几乎所有荤都在 `nar`；I2V 禁止 “mouth speaking”
- **hybrid**：仅 shot03 或 shot06 一句角色金句 + lipsync 可选
- **character**：整片对白；必须接受嘴型不完美或有 MuseTalk

## 用户反馈 → 改写优先级

| 反馈 | 动作 |
|---|---|
| 口型没跟上 | **不要硬上 Wav2Lip**；切/保持 storyteller；I2V 改 idle |
| 不够色气 / **尺度太小** | 升 `heat_scale:max`；重写 5/7/8/9；跑 [Editor’s Cut](editor-cut-pass.md)；双 KPI 看点+刺激点 |
| 像段子合集 | 删讲解句，改感官句；收束改悬念邀请 |
| 审核软化后整片变温 | **禁止**；换角度 suggestive + 加重 VO/SFX + insert 补偿 |
| **动态跟口白对不上 / 两三镜就腻** | 见 [lessons-2026-07-17-vo-motion-link.md](lessons-2026-07-17-vo-motion-link.md)：**口白·动作锁** + **三镜防腻**；重写 action/motion 首要动词，不是再加 blink |
| **语音卡 / 拖腔** | 见 [lessons-2026-07-20-vo-drag-motion-snap.md](lessons-2026-07-20-vo-drag-motion-snap.md)：短 VO 禁 atempo 拉慢；说书用 `visual_fit:vo` + `vo_rate +5%~+8%` |
| **动态没速度感** | I2V 换狠主动词（snap/yank/decisive）；motion_score&lt;5 必 re-I2V |
| **大尺度 still/I2V 审核** | 画面 clothed/suggestive + 距离阶梯；**荤点留给 VO**；禁同 prompt 连撞 |

## 口白·动作锁（2026-07-17）

> 闭眼听旁白应能猜画面在动什么。

| 镜位 | `nar` 写法 | `dsl.action` / `motion` |
|---|---|---|
| 中段推进 | **动作新闻**：「门一落锁」「金扣一松」 | 先写 latch turn / unhook buckle，再 blink |
| 感官 | 感官词绑定可见物：呼吸、指尖、锁骨光 | 呼吸起伏 / 指尖颤 可为主 |
| 余韵 | 才写诗与悬念 | micro hold 可为主 |

**禁止**：整片 10 镜 motion 都是 `soft blink, breath, hair, slow push-in`。

## 三镜防腻

任意连续 3 镜至少满足 2 项：

1. 景别带变化（全身 / 半身 / 特写）
2. 主动词不同（落锁 ≠ 转头 ≠ 解扣 ≠ 俯压）
3. 机位轴不同（平视 / 微仰 / 侧脸 / POV）

`write-spec` 输出 `_vo_motion_link`；`preflight` soft 提示；可选 `vo_motion_strict: true` 硬拦。

