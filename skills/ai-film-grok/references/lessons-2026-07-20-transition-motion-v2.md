# Lessons · 转场 + 运镜 v2（男娘咖啡厅沉淀）

> 2026-07-20 · **P2 时空 · P3 动能 · P0 可观测**  
> 样本：`nanniang-cafe-60s`（男娘咖啡厅）交付后优化 skill。

## 一句话

**continue 缝永远 hard（作者写 soft 也强改）**；  
**运镜主轴 `camera_axis` 必须轮换，禁止全片 slow push-in**；  
**转场改 re-final，运镜改 re-I2V**。

---

## 现象 → 规则

| # | 现象（男娘片） | 根因 | skill 落点 |
|---|---------------|------|------------|
| 1 | continue 镜仍 soft dissolve | 作者 `transition_intents` 写 soft，write-spec 不覆盖 | **`enforce_continue_hard_joins`** 强制 hard + `_transition_continue_hard_fixes` |
| 2 | 运镜腻：多镜像同一种推近 | 微动默认后缀全是 `continuous slow push-in` | 微动与 **camera_axis** 解耦；轴轮换注入 |
| 3 | 景别有了仍像「同机位」 | 只轮 shot_size，不轮机位轴 | `dsl.camera_axis` + lint `CAMERA_AXIS_FLAT` |
| 4 | soft 样式全 dissolve | 作者 styles 单一 | lint `STYLE_SOUP`；`suggest_transition_styles` 轮转 |
| 5 | 目标 60s 成片 46s | soft xfade 吃时长 + 镜数不足 | 见下「时长账」；不够就 **加镜** 不拉长 dissolve |
| 6 | 假 continue（每镜 cast 重起） | Grok 独立 I2V 未 promote | 纪律不变：真 continue 必须字节 promote；假 continue 应改 `chain_mode: cut` |

---

## film-spec 字段（运镜）

```json
{
  "dsl": {
    "camera_axis": "pan_with",
    "motion": "tray rises to chest as shield, horizontal pan-with-subject, no push-in, soft breath, idle not speaking",
    "chain_mode": "continue",
    "cut_on": "mid_motion"
  }
}
```

| `camera_axis` | 画面关键词（写入 motion） |
|---------------|---------------------------|
| `dolly_in` | continuous slow dolly-in on subject |
| `pan_with` | horizontal pan-with-subject, no push-in |
| `locked` | camera static locked-off, only body/prop moves |
| `ecu_hold` | tight hold, micro-tremble only, no push-in |
| `low_lean` | low angle lean-in then stop |
| `pull_back` | gentle pull-back then hold |

write-spec：缺省则 **按 beat 建议 + 避开最近 2 轴**；写入 `dsl.camera_axis` 并必要时注入 motion。

---

## film-spec 字段（转场）

| 规则 | 说明 |
|------|------|
| continue → hard | **硬覆盖** author soft/hold |
| silk | 非 continue 偏 soft/hold 胶水 |
| punchy / 惊悚 | 更多 hard |
| styles | soft/hold 轮转；hard 占位 fade |
| 改转场 | **只** `final` re-render |
| 改运镜 | **必须** re-I2V（像素） |

推荐 10 镜色气短片 intents 节奏（n−1=9）：

```text
hard soft hard soft hard soft hard hold hard
```

约每 2 soft 一个 hard；尾 afterglow 可 hold。

---

## 时长账（60s 竖片）

```text
成片秒 ≈ Σ plate_sec − Σ soft_use_t
```

| 做法 | 效果 |
|------|------|
| 10×6s + 全 soft 0.28 | ≈ 60 − 9×0.28 ≈ **57.5s** |
| silk 加长 soft | 更短 |
| 假 60s（镜少） | 加 1–2 镜，不把 dissolve 拉到 0.6 |

Agent：用户要「满 60s」→ 加镜或提高 `duration_sec`，**不要**用更长 xfade 装时长。

---

## Agent 清单

- [ ] write-spec 后看 `transition_intents`：continue 缝全 hard  
- [ ] 看 `_transition_continue_hard_fixes` 是否改过作者 soft  
- [ ] 每镜 `dsl.camera_axis` 三连不重复  
- [ ] `_vo_motion_link` 无 `CAMERA_AXIS_FLAT` / `SOFT_SOUP` / `STYLE_SOUP`  
- [ ] 真 continue：promote 字节 keyframe 再 I2V；否则改 `cut`  
- [ ] 用户说「运镜没变」→ re-I2V；「转场没变」→ re-final  

## 代码入口

| 能力 | 文件 |
|------|------|
| continue 强 hard | `edit_policy.enforce_continue_hard_joins` |
| 轴轮换 / 注入 | `suggest_camera_axis` · `apply_coverage_defaults_to_shot` |
| lint | `CAMERA_AXIS_FLAT` · `STYLE_SOUP` · `SOFT_SOUP` |
| 文档 | 本文 · [motion-transition](lessons-2026-07-20-motion-transition.md) · [shot-motion](shot-motion.md) |

## 不可宣称

- 写了 continue + soft dissolve = 丝滑接戏  
- 只改 film-spec motion 不 re-I2V = 运镜已更新  
- soft xfade 加长 = 片长达标  
