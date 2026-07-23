# Beat Spines · 多类型节拍骨架总纲

> 40 年导演方法论注入 · P0-1 去类型偏移
>
> 原则：`dramatic_function` 枚举是**通用叙事原语**，不绑定任何单一类型默认。
> 节拍骨架（beat spine）按 `genre` 切换；成人仍是默认之一但不再是唯一骨架。

## 一、问题背景

历史上 `dramatic_function` 七值（hook/approach/sensory/reaction/action/afterglow/bridge）
脱胎于色气六镜脊柱（`hook → approach → sensory → reaction → action → afterglow`）。
`directors-lens.md:160` 原文：「色气默认六镜脊柱」。
`film-spec.md:153` 原文：「对照 ecchi-story 六镜骨架」。

后果：所有类型片——悬疑、文艺、纪录、剧情——的镜头戏剧功能被强制映射到
approach/sensory/afterglow，这是**类型偏移**，不是通用方法论。
一部悬疑片的「线索发现」被塞进 `sensory`（感官特写），
一部纪录片的「事实陈述」被塞进 `approach`（靠近、空间变窄）——语义错位。

## 二、`genre` 字段

新增片级字段 `story.genre`（drama-graph schema）与 `genre`（film-spec schema）。

```json
"genre": {
  "type": "string",
  "enum": ["adult", "drama", "mystery", "arthouse", "documentary"],
  "description": "Beat spine selector. Determines which beat template drives dramatic_function assignment."
}
```

- **default（缺省）**：`"adult"` —— 向后兼容，老项目行为不变。
- **显式声明**：用户在 creative-brief 或 `genre` 字段指定类型。
- **detect**：`detect_genre()` 从 brief 文本信号推断，与 `detect_heat_signals()` 并行运行。
  证据优先：若 brief 含成人信号（`detect_heat_signals` 的 markers）且无显式 genre，
  则 `genre=adult`。若显式 genre 非 adult，则尊重显式声明（成人信号降为 warning）。

## 三、`dramatic_function` 枚举（不变，但去绑定）

七值枚举保持不变（向后兼容），但**每个值的语义描述**从色气专属升级为通用：

| 值 | 通用语义（去色气绑定） | 成人映射（genre=adult 时） |
|---|---|---|
| `hook` | 开场钩子：异常/欲望/冲突入口 | 登场/压迫感 |
| `approach` | 靠近：空间收窄、关系升温、信息逼近 | 靠近、空间变窄 |
| `sensory` | 感官细节：触感/气味/温度/质感特写 | 感官特写 |
| `reaction` | 反应：对方/观众代入的情绪回馈 | 对方/代入反应 |
| `action` | 行动：局势改变的身体/事件推进 | 身体行动推进 |
| `afterglow` | 余韵：结果沉淀、钩子、未完成 | 余韵/钩子 |
| `bridge` | 过渡：时空跳转、纯连接 | 过渡/连接 |

关键变化：`approach` 不再默认等于「脱衣靠近」，`sensory` 不再默认等于「肉体感官」。
它们的语义随 `genre` 上下文变化——在悬疑片里 `sensory` = 线索物证特写，
在纪录片里 `approach` = 信息逼近/调查深入。

## 四、多类型 Beat Spine 定义

每种 genre 对应一套 beat spine（`GENRE_SPINES`）。所有 spine 的 beat
`dramatic_function` 必须是七值枚举之一（兼容 write-spec 门禁），
但 beat 的 `key`/`objective`/`weight`/`shots_n` 按类型定制。

### 4.1 `adult`（成人 · 默认，向后兼容）

沿用现有 `DEFAULT_BEAT_SPINE` / `ADULT_MAX_BEAT_SPINE` / `HARDCORE_MALE_BEAT_SPINE`
/ `DUAL_CLIMAX_BEAT_SPINE`。**行为不变**——`select_beat_spine()` 在 `genre=adult`
时走原有 heat 信号逻辑。

脊柱：`hook → approach → sensory → reaction → action → afterglow`

### 4.2 `drama`（剧情）

经典三幕叙事弧，适用于情感/关系/社会题材短片。

| beat key | dramatic_function | objective | weight |
|---|---|---|---|
| `hook` | `hook` | 建立人物处境与核心张力 | 0.12 |
| `setup` | `approach` | 人物关系与空间建立 | 0.18 |
| `rising` | `action` | 冲突升级，主角行动推进 | 0.22 |
| `turn` | `reaction` | 转折点：反应/抉择/觉醒 | 0.20 |
| `climax` | `action` | 高潮：决定性对抗或选择 | 0.18 |
| `resolution` | `afterglow` | 结果沉淀与新常态 | 0.10 |

### 4.3 `mystery`（悬疑/惊悚）

信息驱动结构：谜面→线索→误导→真相。

| beat key | dramatic_function | objective | weight |
|---|---|---|---|
| `hook` | `hook` | 谜面/异常事件抛出 | 0.14 |
| `investigate` | `approach` | 调查深入，信息逼近 | 0.20 |
| `clue` | `sensory` | 关键线索/物证特写 | 0.16 |
| `red_herring` | `reaction` | 误导/假线索反应 | 0.14 |
| `reveal` | `action` | 真相揭露/行动推进 | 0.24 |
| `aftermath` | `afterglow` | 余波与新疑问 | 0.12 |

### 4.4 `arthouse`（文艺）

氛围/情绪驱动，弱情节强意境，留白为主。

| beat key | dramatic_function | objective | weight |
|---|---|---|---|
| `mood_open` | `hook` | 建立氛围与情绪基调 | 0.16 |
| `observe` | `sensory` | 静观：人物/环境的感官凝视 | 0.22 |
| `gesture` | `approach` | 微妙接近/关系微变 | 0.18 |
| `silence` | `reaction` | 留白/沉默中的情绪涌动 | 0.18 |
| `shift` | `action` | 情绪转折（非情节转折） | 0.14 |
| `echo` | `afterglow` | 回响/未决的余韵 | 0.12 |

### 4.5 `documentary`（纪录/纪实）

事实陈述驱动，去戏剧化，强调信息与证据。

| beat key | dramatic_function | objective | weight |
|---|---|---|---|
| `premise` | `hook` | 主题/问题引入 | 0.14 |
| `context` | `approach` | 背景/语境建立 | 0.18 |
| `evidence` | `sensory` | 事实/数据/物证呈现 | 0.22 |
| `perspective` | `reaction` | 观点/访谈/立场 | 0.20 |
| `conclusion` | `action` | 结论/推论推进 | 0.16 |
| `coda` | `afterglow` | 余思/开放问题 | 0.10 |

## 五、选择逻辑

`select_beat_spine()` 升级签名：

```python
def select_beat_spine(
    heat: dict[str, Any] | None = None,
    *,
    genre: str | None = None,           # NEW
    target_duration: float | None = None,
    multi_scene: bool = False,
) -> list[dict[str, Any]]:
```

选择优先级：
1. `genre` 显式非 `adult` → 返回 `GENRE_SPINES[genre]`（忽略 heat 信号，
   成人信号降为 warning）。
2. `genre == "adult"` 或 genre 缺省 + heat 信号 → 走原有 adult spine 逻辑。
3. genre 缺省 + 无 heat 信号 → `genre` 默认 `"adult"`（向后兼容），
   返回 `DEFAULT_BEAT_SPINE`。

## 六、detect_genre() 信号推断

与 `detect_heat_signals()` 并行。从 brief 文本检测 genre 信号词：

- **drama**：「剧情」「家庭」「社会」「关系」「成长」「现实」「伦理」
- **mystery**：「悬疑」「惊悚」「推理」「谜」「案件」「调查」「真相」「凶杀」
- **arthouse**：「文艺」「实验」「意象」「诗意」「留白」「氛围」「艺术」
- **documentary**：「纪录」「纪实」「真实」「访谈」「历史」「科普」
- **adult**：沿用 `_HEAT_MAX_MARKERS`（detect_heat_signals 已有）

证据优先级：显式 `genre` 字段 > 成人信号 > 其他类型信号 > 默认 adult。
若同时命中多个类型信号，取首个匹配（不叠加），并 warning 提示用户确认。

## 七、向后兼容保证

- `dramatic_function` 枚举**不变**——所有 genre 的 beat 都用七值枚举，
  write-spec 门禁零改动。
- `genre` 字段**缺省 = adult**——老项目行为不变。
- `select_beat_spine()` 不传 genre 参数时行为不变（默认 adult）。
- `normalize_story()` 返回新增 `genre` 字段，但不改变已有字段结构。
- 成人产品硬底（`sex≥30%`、卸装阶梯等）仅在 `genre=adult` 时生效——
  非 adult genre 时这些门禁不触发（它们本就是成人专项）。

## 八、考验机制

| 层 | 考验内容 |
|---|---|
| schema | `genre` 枚举校验（drama-graph + film-spec） |
| detect | `detect_genre()` 信号推断 + warning |
| select | `select_beat_spine(genre=...)` 返回正确 spine |
| write-spec | `dramatic_function` 必须属于七值枚举（已有门禁，不变） |
| 测试 | 各 genre spine 结构正确 + 向后兼容 + detect 信号 |

## 九、未来扩展

新增 genre 只需在 `GENRE_SPINES` 添加一套 beat spine（key/objective/weight/dramatic_function），
无需改 enum、无需改 write-spec、无需改门禁。这是去 type-bias 的核心收益——
类型可扩展，骨架可切换，但考验机制（七值枚举 + write-spec 门禁）不变。
