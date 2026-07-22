# 题材迁移测试（Genre Migration Test）

> 2026-07-22 · 用三个非色情 logline 验证 P0–P5 可迁移性，暴露 lessons 隐式耦合。
> `principles.md` 要求「换 logline 试一次」——本文件是执行记录。

## 测试方法

对每个 logline 走 Director's Lens Phase A–D（故事重构→场景→分镜→film-spec seed），
检查：P0–P5 字段能否填满？dramatic_function 枚举够用？成人规则是否误触发？

---

## Case 1 · 恐怖

**Logline**: 深夜值班的护士发现，走廊尽头的病房每次灯亮，病人数会多一个。

### P0–P5 映射

| 能力 | 字段 | 填写 |
|------|------|------|
| P0 | visible_change | 走廊灯灭→亮；空床→有人影 |
| P0 | story_beat | 观众第一次怀疑「数不对」 |
| P1 | cast | 值班护士（固定身份） |
| P2 | continuity | 灯光闪烁一致；走廊空间连续 |
| P3 | camera_axis | locked → dolly_in（逼近病房）→ pull_back（逃离） |
| P4 | nar=action=motion | 「她又数了一遍——多了一个」= 数数动作= push-in |
| P5 | 分层 | 走廊环境 LTX T2V；护士 hero I2V |

### dramatic_function 脊柱

```text
hook（走廊空）→ approach（灯亮）→ sensory（呼吸声逼近）
→ reaction（护士回头）→ action（推门）→ afterglow（床上多一人）
```

✅ 枚举完全够用。六拍结构与色气一致——证明 dramatic_function 是题材无关的。

### 成人规则误触发？

- `heat_scale` 未设 → sex_floor_strict / sex_wardrobe_strict 不触发 ✅
- `wardrobe_state` 留空 → 继承默认 full，无卸装约束 ✅
- BGM 默认 `rnb` → 恐怖应改 `dark`（需手动设，或加 audience→mood 推断）

### 发现的隐式耦合

1. **BGM 默认 rnb** 写在 SKILL.md「色气 BGM 默认 rnb」——对恐怖是错的。应改为跟 director_intent.tone 推断，不硬绑题材。
2. **dramatic_function 色气六镜脊柱** 在 directors-lens.md 写死为 `hook→approach→sensory→reaction→action→afterglow`——恐怖完全适用，但文档措辞暗示这是色气专用。应标注「脊柱题材无关」。

---

## Case 2 · 喜剧

**Logline**: 一个社恐程序员把「已读不回」练成了超能力，直到他妈妈发来一条消息。

### P0–P5 映射

| 能力 | 字段 | 填写 |
|------|------|------|
| P0 | visible_change | 手机屏幕已读→未读→消失 |
| P0 | story_beat | 从得意→恐慌 |
| P1 | cast | 程序员（固定身份） |
| P2 | continuity | 手机界面一致；场景从卧室→公司→家 |
| P3 | camera_axis | pan_with（跟手机）→ locked（对脸反应）→ handheld（慌） |
| P4 | nar=action=motion | 「他已读不回全世界」= 手指划过= pan-with |
| P5 | 分层 | 手机界面 insert；人物 hero I2V |

### dramatic_function 脊柱

```text
hook（展示超能力）→ approach（妈妈消息出现）→ sensory（手指悬在屏幕上）
→ reaction（面部僵住）→ action（疯狂找撤销键）→ afterglow（妈妈已到家门口）
```

✅ 枚举够用。喜剧的「抖包袱」= afterglow 的反转——spine 不变。

### 成人规则误触发？

- `heat_scale` 无 → 全部 sex 规则跳过 ✅
- `cast_mode=auto` → 未推断第二女主 ✅

### 发现的隐式耦合

1. **pace_chart 默认慢燃** ——喜剧节奏完全不同（快切 + deadpan hold）。pace_chart 应可跟 genre/audience 推断快节奏，不应默认慢燃。
2. **transition_fluency 默认 cinematic** ——喜剧常用 smash_cut + 节奏断点，cinematic 的 smooth glue 会拖。

---

## Case 3 · 公路

**Logline**: 两个陌生人拼车横穿沙漠，因为都以为对方是要杀自己的人。

### P0–P5 映射

| 能力 | 字段 | 填写 |
|------|------|------|
| P0 | visible_change | 车窗外的地貌变化；后视镜里对方的眼神 |
| P0 | story_beat | 从互相试探→发现误会→真正危机 |
| P1 | cast | 两个角色（hero + partner，双人戏） |
| P2 | continuity | 车内空间一致；沙漠光线随时间变 |
| P3 | camera_axis | OTS 正反打（双人戏核心）→ insert（地图/枪）→ wide（沙漠） |
| P4 | nar=action=motion | 「他握着方向盘，比平时紧了三寸」= 握紧= locked static |
| P5 | 分层 | 沙漠环境 LTX T2V wide；车内 hero I2V OTS |

### dramatic_function 脊柱

```text
hook（上路）→ approach（试探对话）→ sensory（手伸向储物箱）
→ reaction（对方也伸手）→ action（枪亮相）→ afterglow（发现是误会，真危险在后）
```

✅ 双人对话戏完全适用 character-stance 的 OTS/reverse/reaction_to 语法。

### 成人规则误触发？

- 无 heat_scale → 无 ✅

### 发现的隐式耦合

无额外——公路片的 P0–P5 映射最干净。

---

## 结论

| 维度 | 可迁移？ | 说明 |
|------|----------|------|
| P0–P5 六大能力 | ✅ 完全可迁移 | 换题材只换 bible/cast/nar/motion 词表 |
| dramatic_function 枚举 | ✅ 够用 | 六拍脊柱题材无关 |
| character-stance 语法 | ✅ 双人/单人通用 | |
| **BGM 默认 rnb** | ⚠️ 隐式耦合 | 应跟 tone 推断 |
| **pace_chart 默认慢燃** | ⚠️ 隐式耦合 | 应跟 genre/audience |
| **transition_fluency 默认 cinematic** | ⚠️ 隐式耦合 | 喜剧需 smash |
| 成人 sex/wardrobe 规则 | ✅ 不误触发 | heat_scale 未设则全跳过 |

## 行动项

1. BGM mood：`write-spec` 按 `director_intent.tone` 推断（恐怖→dark，喜剧→upbeat），不硬绑 rnb
2. pace_chart：加 `audience` / `genre` hint → 推断快慢
3. directors-lens.md 六拍脊柱标注「题材无关」
4. 成人专项规则入口收拢到 `ecchi-story.md`，主脊只留指针（已有，需确认主脊未重复展开）
