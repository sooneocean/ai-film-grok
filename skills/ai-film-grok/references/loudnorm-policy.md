# 响度标准（Loudnorm Policy）

> **单一真相**：本文件是 LUFS / true-peak 响度标准的唯一稳定 reference。
> 代码实现：`scripts/sound_plan.py` → `resolve_loudnorm` · `should_apply_loudnorm`。
> 测试：`tests/test_loudnorm_policy.py`。

---

## 背景：三套阈值冲突（已统一）

2026-07-24 扫描发现三套不同 LUFS 阈值散落在模块中（-24..-14 / -18..-14 / -22..-16），
导致同一混音文件可能过 A 失败 B。本次迭代（`lessons-2026-07-24-director-methodology-activation.md` P3-15）
统一为 **目标 -16 LUFS**，auto 触发带 **[-22, -12]**。

> **铁律**：响度标准必须唯一。禁止在新增模块里引入第二套 LUFS 阈值。

---

## 标准（代码真相）

| 项 | 值 | 代码常量 |
|---|---|---|
| **目标 integrated LUFS** | **-16.0** | `DEFAULT_TARGET_LUFS` |
| auto 触发上限（太响 → 拉低） | -12.0 LUFS | `LOUDNORM_LOUD_CEILING` |
| auto 触发下限（太轻 → 抬高） | -22.0 LUFS | `LOUDNORM_QUIET_FLOOR` |
| target 合法范围 clamp | [-24.0, -10.0] | `resolve_loudnorm` 内 clamp |
| 模式枚举 | `off` · `auto` · `on` | `LOUDNORM_MODES` |

### auto 模式判定逻辑

```text
measured_lufs > -12  →  太响，应用 loudnorm 拉向 -16
measured_lufs < -22  →  太轻，应用 loudnorm 抬向 -16
-22 ≤ measured_lufs ≤ -12  →  在带内，不处理
```

`auto` 是默认模式：仅在测量值落在 [-22, -12] 之外时才重写混音。

### `on` / `off` 模式

- `on`：无条件 normalize 向 target_lufs（force）
- `off`：永不重写混音

---

## film-spec / plan 字段

| 字段 | 含义 | 默认 |
|---|---|---|
| `audio_recipe.loudnorm` | `"off"` / `"auto"` / `"on"` / bool | `"auto"` |
| `audio_recipe.target_lufs` | 覆盖目标 LUFS | -16.0 |

CLI 覆盖：`--loudnorm <mode>` · `--target-lufs <float>`（CLI 值优先于 plan）。

---

## 相关文档

- [audio-fallback.md](audio-fallback.md) — 音频三阶梯（TTS/BGM/Lipsync）
- [audio-recipe.md](audio-recipe.md) — 场景自适应声轨配方
- [voice-tracks.md](voice-tracks.md) — 多轨声线
- 统一记录：[lessons-2026-07-24-director-methodology-activation.md](lessons-2026-07-24-director-methodology-activation.md) P3-15
