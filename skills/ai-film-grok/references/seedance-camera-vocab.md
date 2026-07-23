# Seedance 运镜/视觉词库（cinema_prompt 适配）

> 2026-07-23 · ai-film-grok × songguoxs/seedance-prompt-skill
> **用途**：`scripts/cinema_prompt.py` 的词库源，供 I2V provider 生成电影级运镜 prompt。
> **母法**：词库是 Seedance 的 camera language + visual styles 适配版；不替代 I2V 接戏动作。

## 一句话

| 层 | 职责 | 落地 |
|----|------|------|
| `camera_axis` | 旧 enum（`dolly_in` 等），向后兼容 `story_plan` | `dsl.camera_axis` |
| `camera_prompt` | 富文本中文运镜描述 | `dsl.camera_prompt` → `prompts/*.txt` |
| 结构化字段 | move/shot_type/angle/pacing/focus/palette/lighting | `dsl.*` |

---

## Camera Language（运镜语言）

来源：Seedance camera language 词库。

### 镜头景别（Shot types）

| key | 中文 | 用法 |
|-----|------|------|
| `ecu` | 大特写（ECU） | 情绪密度最高，仅局部 |
| `cu` | 特写（CU） | 面部占满，呼吸微表情 |
| `mcu` | 中近景（MCU） | 对话与情绪并重 |
| `ms` | 中景（MS） | 动作与关系可见 |
| `mls` | 中远景（MLS） | 人物在环境中 |
| `fs` | 全景（FS） | 全身入画 |
| `ws` | 远景（WS） | 环境主导 |
| `ews` | 大远景（EWS） | 史诗/孤独 |

### 运镜（Camera moves）

| key | 中文 |
|-----|------|
| `dolly_in` | 缓慢推镜 |
| `dolly_out` | 缓慢拉镜 |
| `pan_with` | 跟摇 |
| `tilt_up` / `tilt_down` | 仰摇 / 俯摇 |
| `tracking` | 侧跟 |
| `crane_up` / `crane_down` | 摇臂升 / 降 |
| `handheld` | 手持微抖 |
| `locked` | 固定机位 |
| `ecu_hold` | 大特写凝住 |
| `low_lean` | 低位前倾 |
| `pull_back` | 后撤 |
| `orbit` | 环绕 |
| `push_pull_breath` | 呼吸式推拉 |

### 角度 / 节奏 / 焦点 / 转场

- **角度**：`eye` 平视 / `low` 仰拍 / `high` 俯拍 / `dutch` 荷兰角 / `overhead` 顶俯 / `ots` 过肩
- **节奏**：`slow` / `medium` / `fast` / `hold`
- **焦点**：`rack` 焦点转换 / `deep` 深焦 / `shallow` 浅焦 / `pull` 失焦→合焦
- **转场**：`hard` / `match` / `fade` / `dissolve`

---

## Visual Styles（视觉风格）

### 胶片颗粒（Film grain）

`fine` 细颗粒 35mm / `coarse` 粗颗粒 16mm / `clean` 数字无颗粒 / `halation` 胶片光晕

### 调色（Color palette）

`teal_orange` 青橙互补 / `desaturated` 低饱和 / `warm_amber` 暖琥珀 / `cool_steel` 冷钢蓝 / `high_contrast` 高反差 / `pastel` 柔和粉彩

### 布光（Lighting）

`rembrandt` 伦勃朗光 / `backlight` 逆光 / `practical` 现场光 / `low_key` 低调光 / `high_key` 高调光 / `neon` 霓虹光 / `golden_hour` 黄金时刻 / `blue_hour` 蓝调时刻

---

## 场景策略（Scenario strategies）

Seedance 场景 prompt 适配，按 genre 选运镜/布光/调色/节奏：

| scene_type | 标签 | 运镜偏好 | 布光 | 调色 | 节奏 |
|------------|------|----------|------|------|------|
| `short_drama` | 短剧 | dolly_in / ecu_hold / low_lean / pan_with | low_key / practical | teal_orange / high_contrast | fast |
| `ecchi_romance` | 成人向情感 | dolly_in / push_pull_breath / ecu_hold / tracking | warm_amber / backlight / golden_hour | warm_amber / pastel | slow |
| `ecommerce` | 电商广告 | orbit / tracking / crane_up | high_key / practical | clean / pastel | medium |
| `xianxia` | 仙侠奇幻 | crane_up / orbit / tracking / push_pull_breath | backlight / golden_hour / blue_hour | pastel / cool_steel | slow |
| `science` | 科普 | dolly_in / tracking / tilt_down | high_key / clean | cool_steel / desaturated | medium |
| `music_video` | 音乐MV | handheld / orbit / tracking / dolly_in | neon / low_key | high_contrast / teal_orange | fast |

---

## dramatic_function → 运镜映射

替换 `story_plan._camera_axis` 的固定 enum 轮转：

| df | 运镜 | 节奏 | 焦点 |
|----|------|------|------|
| hook | dolly_in | fast | shallow |
| approach | pan_with | medium | shallow |
| sensory | low_lean | slow | shallow |
| reaction | ecu_hold | hold | shallow |
| action | dolly_in | fast | deep |
| afterglow | pull_back | slow | shallow |
| bridge | locked | medium | deep |

`idx % 3 == 1 and base == dolly_in → ecu_hold`（保留 story_plan 的 idx 调制逻辑，向后兼容）。

## heat_phase → 强度调制

| heat_phase | 节奏 | 调色 |
|------------|------|------|
| warmup | medium | warm_amber |
| rising | slow | warm_amber |
| peak | slow | warm_amber |
| climax | hold | high_contrast |
| cooldown | slow | cool_steel |

---

## Agent 决策

```
shots 环 → cinema_prompt.inject_camera_prompts(root)
  ├─ 读 film-spec.json 每个 shot
  ├─ 按 df + idx + heat_phase + scene_type 选词
  └─ 写 dsl.camera_prompt + 结构化字段
write-spec 环 → prompt_injector 把 camera_prompt 写进 prompts/*.txt
I2V 环 → provider 读 camera_prompt 作为运镜指令
```

## 相关

- [directors-lens.md](directors-lens.md) — 导演镜头语法
- [shot-motion.md](shot-motion.md) — 运镜关键词表（旧，保留兜底）
- [genre-migration-test.md](genre-migration-test.md) — genre 分支
