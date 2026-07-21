# 角色立场 / 多 POV 剪辑（Character Stance）

> 映射 **P1 身份 · P2 时空 · P3 动能 · P4 语义 · P5 分层**  
> 目标：剪辑不只「好看接缝」，还要回答——**这一镜站在谁的立场？权力在谁手里？观众该跟谁呼吸？**  
> 代码：`edit_policy.suggest_focal_character` / `suggest_viewpoint` / `lint_character_stance`；write-spec 注入 `dsl.focal_character` · `viewpoint` · `look_axis`。

---

## 一句话

**换立场 = 换世界。**  
同一事件，从女主 OTS 切到男主 reaction，比多叠一个 dissolve 更「电影」。

---

## 女主弹性（与 ecchi 联动 · 2026-07-21）

| 模式 | 做法 |
|---|---|
| **single（默认）** | 一女主；不要求 dual；focal 可固定 |
| **multi（证据触发）** | Prompt/多图/`heroine_ids≥2`；每 id cast master + ≥1 focal + ≥1 dual |
| 换女主 | **cut 缝**；新镜从该女主 cast 起 still |
| lint | single 跳过 multi 检查；见 [ecchi-story.md](ecchi-story.md) §女主弹性 |

---

## 三个字段（每镜）

| 字段 | 含义 | 值 |
|---|---|---|
| `dsl.focal_character` | 本镜**共情归属**（谁的戏） | `hero` / `partner` / cast id… |
| `dsl.viewpoint` | 机位语法 | 见下表 |
| `dsl.look_axis` | 屏幕方向（180° 轴线） | `left` \| `right` \| `center` |

### viewpoint 菜单

| viewpoint | 白话 | 典型 beat |
|---|---|---|
| `objective` | 中立观察 | hook 建立 |
| `subjective_pov` | 角色主观眼 | action 沉浸 1 镜 |
| `ots` | 过肩，偏 focal | approach / 对话 |
| `reverse` | 反打 / 正反打回答 | focal 切换后 |
| `reaction_to` | 反应脸 | reaction |
| `dual` | 双人同框 | afterglow / 关系定格 |
| `insert_object` | 物件特写（立场靠「谁的物件」） | sensory |

---

## 与剪辑 craft 的联动

| 立场变化 | 优先 craft |
|---|---|
| focal 切换 + reverse | `contrast_cut` |
| focal 切换 + reaction_to | `smash_cut` |
| 进 insert_object | `insert_cut` |
| 同 focal 场内连续 | soft_glue / cut_on_action（continue） |

continue 缝仍 **hard 家族**——立场标签改变的是**语义与构图**，不是 dissolve。

---

## 正反打与 180°

```text
shot A: focal=hero  viewpoint=ots      look_axis=left
shot B: focal=partner viewpoint=reverse look_axis=right   ← 轴线对翻
```

- `reverse` 时 look_axis 自动对翻（prev left→right）。  
- lint：`REVERSE_WITHOUT_FOCAL_SHIFT`（反打却不换 focal）soft 警告。

---

## 说书人片怎么用（单主角色气）

即使只有一个脸：

| beat | 建议立场 |
|---|---|
| hook | hero + objective |
| approach | hero + ots（想象「你」在肩后） |
| sensory | hero + insert_object |
| reaction | **partner 或 audience 感** + reaction_to（权力翻面） |
| action | hero + ots/objective；偶发 subjective_pov |
| afterglow | dual 或 reaction_to |

`director_intent.cast`: `["hero","partner"]` 帮助 suggest 换立场。

---

## write-spec 行为

1. 缺省注入 focal / viewpoint / look_axis（作者优先）。  
2. viewpoint 影响默认 angle / shot_size / framing 提示。  
3. 产出 `_character_stance` soft lint：  
   - `VIEWPOINT_FLAT` — 全 objective  
   - `FOCAL_STANCE_FLAT` — reaction 从不换 focal  
   - `REVERSE_WITHOUT_FOCAL_SHIFT`  
4. `stance_strict: true` → 升 hard fail。

---

## Agent 清单

- [ ] 10 镜片至少 **3 种 viewpoint**  
- [ ] 至少一次 **focal 切换**（含 reaction / reverse）  
- [ ] reverse 必带 look_axis 对翻  
- [ ] I2V prompt 含 focal + viewpoint 语义（framing 已注入）  
- [ ] 改立场构图 → re-I2V；只改接缝 craft → re-final  

## 不可宣称

- 只写了 soft 转场 = 有立场剪辑  
- 全片 objective hero = 多角色电影感  
- reverse 不换人 = 正反打  

相关：[editorial-craft.md](editorial-craft.md) · [directors-lens.md](directors-lens.md) · [shot-motion.md](shot-motion.md)
