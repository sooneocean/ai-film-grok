# Adult Max Playbook · 办事剧 Grok Build 单入口（2026-07-22）

> 把「尺度拉满」从 lessons 自觉，收成 **plan → write-spec → still/I2V → review** 可执行路径。  
> 互补课：sex-duration / undress / vo-spice / intercourse-impact / size-ladder。

## 一句话

**秒数够 + 衣服卸了不回穿 + 耳朵荤 + 性交六拍可读 + 景别加压** = 办事剧标竿。  
Grok SDK 拉满画面顶格 suggestive；审核软化时 **VO/SFX/insert 双轨补**，禁止降 `heat_scale`。

## 触发

| brief 信号 | 结果 |
|---|---|
| 成人 / 办事 / 性爱 / 里番 / 尺度拉满… | `heat_scale=max` + `ADULT_MAX` 脊柱 |
| 重口 / 男向 / 尺度太小… | + `audience_profile=hardcore_male` + 六拍/景别 **strict** |

`story_plan.detect_heat_signals` · **无证据不钉 max**。

## 八环 × 工具

| 环 | Grok / aifilm | 验收 |
|---|---|---|
| Idea | 命题必须性驱动 | brief 有办事动机 |
| Story/Beats | `plan run` 成人脊柱 | `heat_phase` + `coitus_beat`；**用户句优先**（禁整句盖「展厅落锁」） |
| Shots | `write-spec` | `_heat_arc` 全绿 / `aifilm heat check` |
| Media still | `image_edit` 状态照/undress-anchor | Mute Frame：静音能读结合 |
| Media I2V | `image_to_video` + coitus motion | hips-sink/grind 非 soft lean |
| Selects | `review-shot` | coitus 证据建议填 |
| Rough/Final | montage hard + rnb | escalation 可勾 |

## 机器闸（write-spec · v1.10）

| 闸 | 字段 | max 默认 |
|---|---|---|
| 性爱秒数 | `sex_floor_strict` | hard **≥30%**（hardcore **≥40%**） |
| 卸装 | `sex_wardrobe_strict` | hard |
| 荤 VO | `sex_vo_strict` | hard；`spice_level` explicit\|**extreme** |
| 声画同动词 | `sex_vo_motion_strict` | hardcore hard |
| 性交六拍 | `coitus_strict` | hardcore 或 `coitus_grammar.enabled` |
| 景别 | `size_ladder_strict` | hardcore |
| 蒙太奇 | `montage_strict` | hardcore（inject craft 脊柱） |
| 多体位 | `pose_strict` | hardcore（`SEX_POSE_STALE`） |

```bash
"$AIFILM" heat check --root "<root>"
"$AIFILM" heat vo-suggest --root "<root>" [--shot id]
"$AIFILM" heat soften-log --root "<root>" --note "I2V soft"
"$AIFILM" write-spec --root "<root>"
```

## 声轨（v1.10+）

- **非成人**：`vocal_color` 仍默认关  
- **hardcore / spice=extreme**：建议开娇喘轨 + `auto_vocal_color`（gain≈0.52）  
- **act/climax**：自动 `sound_cues=impact,breath,leather`（`auto_sex_sfx:false` 可关）  
- **write-spec**：自动把 act/climax 肉体 accent **写入 `sound_plan.events`**（`sex_sfx:true`）

## Pilot（成人）

`pilot pick` 在 heat=max 时优先：**undress → union → rhythm**（验卸装 + Mute Frame + 节奏），不是空台口 hook。

## 双高潮 / premise

- brief 含 **双高潮 / 两轮 / 再来一轮** → `dual_climax` 脊柱（~100s）  
- 种子：`templates/premises-adult.md`

## 性交六拍（必见）

ENTRY → UNION → RHYTHM → LOCK → FINISH → HOOK  
镜字段：`coitus_beat` · 片字段：`coitus_grammar.beats`  
主动词：`straddle-seat` `hips-sink` `grind` `pelvis-lock` `arch-finish`…

## Motion 模板键

`undress_slide` `entry_pin` `union_settle` `rhythm_hips` `lock_clutch` `finish_arch` `hook_whisper`  
→ `edit_policy.i2v_motion_templates` / `coverage_defaults_for_heat`

## 脚手架

- 模板：`templates/film-spec.adult-max.example.json`
- plan：brief 含成人词 → 自动成人脊柱 + spicy `nar` 种子

## 审核软化

1. 画面改顶格 suggestive（骨盆咬合 + 衣失序）  
2. **加重** VO 办事动词 + SFX impact/breath  
3. 加 L4 insert  
4. **禁止** `heat_scale` 降 medium  

## 相关

- [ecchi-story.md](ecchi-story.md)  
- [lessons-2026-07-21-intercourse-impact-benchmark.md](lessons-2026-07-21-intercourse-impact-benchmark.md)  
- [lessons-2026-07-21-size-ladder-hardcore-stack.md](lessons-2026-07-21-size-ladder-hardcore-stack.md)  
- [grok-build-sdk.md](grok-build-sdk.md)  
