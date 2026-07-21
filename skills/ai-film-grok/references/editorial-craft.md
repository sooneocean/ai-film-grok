# 资深剪辑语法（Editorial Craft）

> 映射 **P2 时空连续 · P3 动能连续 · P4 语义绑定 · P5 分层表达**  
> 目标：短片**不是**镜 1→2→3 的呆板线性幻灯片，而是用**剪辑句法**制造节奏、对比、冲击与余韵。  
> 实现层：每条接缝一个 **edit craft** → 映射 `transition_intents` + `transition_styles`（FFmpeg xfade / hard concat）。  
> 代码：`scripts/edit_policy.py` · write-spec 写入 `edit_craft` + `_edit_craft_plan`。

---

## 一句话

**戏在镜头里演完一半，另一半在剪辑点上完成。**  
continue 缝用 match-cut 接戏；场景缝用 glue/bridge；冲击用 smash；细节用 insert——**禁止全片 soft dissolve 糊成一锅**。

---

## 本管线能做什么 / 不能做什么

| 能（有代码） | 不能（勿宣称） |
|---|---|
| 每缝 craft 不同（smash / insert / hold…） | 真·非线性时间线（闪回时间轴重排需手改镜序） |
| hard match-cut + cut-on-action | 用 dissolve 盖 continue 字节缝 |
| soft 样式轮转（hblur / smooth* / fadeblack） | 每缝都用同一种 dissolve |
| 跨 scene 自动 scene_bridge | 任意花哨 xfade 名（仅 SOFT_XFADE 白名单） |
| 连续 mixed.wav 天然 **L/J-cut** | 分轨手工 L-cut 时间码编辑 |
| 蒙太奇语感：action→action hard 跳切 | 多屏 split 同时戏 |
| 设计后期统一 grade/字幕胶水 | 用 HF Ken Burns 冒充剪辑 |

**闪回 / 平行剪辑**：在 Director’s Lens 阶段把镜序**写成交错**（A1 B1 A2 B2），不要指望 final 自动重排。

---

## Craft 菜单（agent 必会）

| craft | 白话 | 画面 intent | 典型时机 |
|---|---|---|---|
| `match_cut` | 接戏硬切 | hard | `chain_mode: continue` |
| `cut_on_action` | 动作中切 | hard | continue + `cut_on: mid_motion` |
| （continue 上的 smash/insert/montage） | **仍是 hard** | hard | 只改**语义标签**防扁平；**绝不**改成 dissolve |
| `smash_cut` | 砸切 | hard | action→reaction、hook 冲击 |
| `contrast_cut` | 对比切 | hard | 景别/权力突然翻面；soft 跑太久时强制打断 |
| `insert_cut` | 插入特写 | hard | approach/action → sensory 物件 |
| `montage_jump` | 蒙太奇跳切 | hard | action→action 连打 |
| `soft_glue` | 场内胶水 | soft | 同场景情绪连续 |
| `whip_soft` | 方向能叠 | soft + hblur/smooth* | 靠近→行动的能量滑动 |
| `mood_hold` | 余韵着陆 | hold + fadeblack/dissolve | 进 afterglow |
| `scene_bridge` | 场景桥 | soft + fadeblack | **跨 scene** 边界 |

声轨：全片 `audio/mixed.wav` underlay = **默认 L/J-cut**（画面 hard 时旁白/BGM 不断）。

---

## 节奏纪律（反呆板线性）

1. **继续缝永远 hard**（match_cut / cut_on_action）——作者写 soft 也会被改掉。  
2. **soft 连跑 ≤3**（punchy ≤2）——超出把 `soft_glue` 升为 `contrast_cut`（`_punctuate_soft_run`）。  
3. **冲击要硬、着陆要软**：smash 在高潮前；mood_hold 只给余韵，勿全片 hold。  
4. **景别/机位轴与剪辑同步**：insert 前后最好有 size 跳变；contrast 最好有 `camera_axis` 变化。  
5. **角色立场**：`focal_character` 切换 + `viewpoint`（ots/reverse/reaction）驱动 contrast/smash；见 [character-stance.md](character-stance.md)。  
6. **改剪辑只 re-final**；改动作/立场构图像素 **re-I2V**。

推荐 10 镜色气脊柱（示例 craft 串，非死模板）：

```text
cut_on_action → whip_soft → insert_cut → smash_cut → cut_on_action
→ whip_soft → montage_jump → insert_cut → mood_hold
```

### 资深 / 重口男向强制（2026-07-21）

用户嫌「剪辑差 / 像幻灯片 / 要蒙太奇」或「重口男向」时：

| 强制 | 规则 |
|---|---|
| craft 种类 | **≥4** 种；禁全 `cut_on_action` |
| insert | 60s **≥2** 缝 `insert_cut` |
| smash | 高潮前 **≥1** `smash_cut` |
| montage | **≥1** 段 `montage_jump`（连续 ≥2 缝动作连打） |
| 验收 | 写进 `receipts/editor-cut.md`「蒙太奇设计」；不达标 = Picture/Action fail |

完整课：[lessons-2026-07-21-montage-hardcore-male.md](lessons-2026-07-21-montage-hardcore-male.md)。

---

## film-spec 字段

```json
{
  "transition_fluency": "cinematic",
  "edit_craft": [
    "cut_on_action", "whip_soft", "insert_cut", "smash_cut",
    "match_cut", "soft_glue", "montage_jump", "contrast_cut", "mood_hold"
  ],
  "transition_intents": ["hard", "soft", "hard", "hard", "hard", "soft", "hard", "hard", "hold"],
  "transition_styles": ["fade", "hblur", "fade", "fade", "fade", "dissolve", "fade", "fade", "fadeblack"]
}
```

| 字段 | 说明 |
|---|---|
| `edit_craft` | 长度 **n−1**；作者可手写；不写则 write-spec **craft_suggest** |
| `_edit_craft_plan` | 只读回执：join_index / craft / why / intent |
| `transition_fluency` | `auto`→silk；`silk`；`punchy`；**`cinematic`**（craft 丰富 + 节奏断点） |
| `transition_intents` / `styles` | 可由 craft 导出；continue 仍强 hard |

---

## 与 Editor’s Cut 的关系（2026-07-20）

本文件管 **接缝 craft 菜单**（写进 film-spec 的句法）。  
**素材齐了之后**的剪辑师过片（画面·动作·声音·剧情四轴、是否 re-I2V、是否加镜）见权威：

→ **[editor-cut-pass.md](editor-cut-pass.md)**  
→ 案例 [lessons-2026-07-20-editor-cut-ecchi-scale.md](lessons-2026-07-20-editor-cut-ecchi-scale.md)

**生成规划**写 craft 草案；**Editor’s Cut** 可改 craft 后只 re-final，或点名重渲弱镜。

## Agent 工作流

```text
Director’s Lens（故事弧 + 可选交错镜序）
  → film-spec shots（dramatic_function / chain_mode / cut_on / scene）
  → write-spec
       · suggest_edit_crafts
       · edit_craft → intents + styles
       · enforce continue hard
  → I2V / final
  → 用户说「剪得呆」→ 改 edit_craft / fluency 后 **只 re-final**
  → 用户说「动作慢」→ re-I2V（不是再叠 dissolve）
```

### 检查清单

- [ ] `edit_craft` 种类 ≥ 4（10 镜片）  
- [ ] continue 缝全是 match_cut 或 cut_on_action  
- [ ] 无 4+ 连续 soft_glue  
- [ ] 至少一个 smash 或 contrast 作标点  
- [ ] afterglow 前有 mood_hold 或 soft 着陆  
- [ ] 跨 scene 为 scene_bridge  
- [ ] `_edit_craft_plan` 可读（给导演过目）

---

## 与旧规则关系

| 旧 | 新 |
|---|---|
| 仅 hard/soft/hold | craft 是**上层语义**，仍落到 hard/soft/hold |
| silk 多 soft | cinematic/silk + craft 轮换 + soft 跑断点 |
| STYLE_SOUP lint | craft→styles 天然多样 |
| 男娘 continue=hard | **不变**，craft 强制 match 家族 |

相关：[transition-motion-v2](lessons-2026-07-20-transition-motion-v2.md) · [cut-silk-bilingual](lessons-2026-07-20-cut-silk-bilingual.md) · [shot-motion](shot-motion.md) · [directors-lens](directors-lens.md) · [vo-drag-motion-snap](lessons-2026-07-20-vo-drag-motion-snap.md)
