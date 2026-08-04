# Script Value Debrief · 剧本呈现价值拆解

> **位置**：`story.receive` 之后、story / graph **lock 之前**。  
> **产物**：`receipts/script-value-debrief.json`（独立收据，不塞进 reception 胖 schema）。  
> **链**： [story-reception](story-reception.md) · [directors-lens](directors-lens.md) · [stages/agent](stages/agent.md) · 模板 [script-value-debrief.example.json](../templates/script-value-debrief.example.json)

## 一句话

原文保全之后，用 **用户 / 编剧 / 导演 / 观众 / 生产** 五层把「这部片为什么值得看」拆成机读字段；用户确认 `viewer_promise` 与不可砍 beat，才允许 lock 进媒体。

类比：摄影棚开工前的剧本分析会 + 看片测试卡，不是再润色一版散文。

## 强制顺序

```text
用户剧本/小说
  → story.receive（原文 + sha + 导演处理包）
  → script-value-debrief（本档 · L0–L4）
  → 用户确认 promise + must_have / 不可砍 beat
  → plan run / normalize / graph / write-spec
  → workshop diagnose（台词第二道）
  → pilot（优先 value_rank≥4）
```

## CLI

```bash
aifilm plan debrief --root "<film>" --action status
aifilm plan debrief --root "<film>" --action seed          # 从 story-reception 草稿
aifilm plan debrief --root "<film>" --action write --file debrief.json --force
aifilm plan debrief --root "<film>" --action confirm --user-phrase "确认 promise 与不可砍 beat"
aifilm plan validate --root "<film>" --strict              # 缺 debrief hard-fail
aifilm plan lock --root "<film>" --scope story --strict --user-phrase "…"
# 或: AIFILM_DEBRIEF_STRICT=1
```

- Agent **不得**代签确认。  
- 缺 debrief 时：新片默认 **warn**；`aifilm plan validate --strict` 对缺失或结构错误 **hard**。
- CLI：`aifilm plan debrief --root … --action status|seed|write|confirm|validate`
- story lock：`--strict` 或 `AIFILM_DEBRIEF_STRICT=1` 时要求 debrief 存在且 `confirmed_by_user`
- 机读：`scripts/script_value_debrief.py` · `story_quality` 折叠 promise/beat_value/setup_payoff/dead_air；`pilot pack` 优先 value shortlist  
- 禁止用 debrief 覆盖 `source.raw_text` 或静默改用户保护台词。

## 三视角冲突仲裁

优先级从高到低：

1. **用户 `must_have` / `must_not`**（订片契约）  
2. **原文事实与保护台词**（`source_supported`）  
3. **可拍性改造**（只能标 `creative_suggestion`，回显后采纳）  
4. **Agent 润色 / 结构补全**（不得伪装成原文）

对白主链 / 零旁白 IRON：编剧层的「说明」→ 改写成可演对白或道具事件，**不进 `nar`**（`dialogue_drama`）。

## 呈现价值验收句（lock 前）

用户须能：

1. 用**一句话**复述 `viewer_promise`；  
2. 指出 **≥2** 个绝不能砍的 beat（`must_keep_beat_ids`）；  
3. 确认 `must_not` 未越界。

## L0 · 用户契约（订片人 + 受众）

| 字段 | 说明 |
|------|------|
| `user_brief.audience_profile` | 如 `hardcore_male` / general / serial |
| `user_brief.must_have[]` | 看完必须留下的画面/台词/尺度 |
| `user_brief.must_not[]` | 禁忌（毒镜、旁白、声线、画风） |
| `user_brief.success_looks_like` | 成功长什么样（人话） |
| `user_brief.platform` | 竖屏短剧 / 连载等 |
| `user_brief.target_duration_sec` | 目标时长 |

每片最多 **1** 个关键追问；能默认则默认并写进 `assumptions[]`。

## L1 · 编剧骨架

沿用 reception / story_contract 五件套，debrief **引用或回填**并加 provenance：

- `protagonist_goal` · `opposition` · `stakes` · `climax_choice` · `ending_hook`

增强（建议必填）：

| 字段 | 说明 |
|------|------|
| `information_state` | 观众知 / 角色知（反转类） |
| `theme_one_line` | 主题一句（可 suggestion） |
| `setup_payoff_pairs[]` | `{setup_ref, payoff_ref, note}` |
| `scene_necessity` | 每场：删掉故事是否断（`hard`/`soft`） |

## L2 · 导演可拍性 · Beat Value Card

每个 beat（或每组连续同功能镜）一张卡：

| 字段 | 说明 |
|------|------|
| `beat_id` | 稳定 id（可后对齐 graph） |
| `objective` | 戏剧目的 |
| `state_in` / `state_out` | 进/出状态须不同 |
| `visual_event` | **唯一**主视觉动词事件 |
| `visible_change` | 一镜世界变化（对齐 film-spec dsl） |
| `audio_load` | `dialogue` / `foley` / `silence` / `mixed` |
| `coverage_min` | 最少景别覆盖，如 `wide→cu` |
| `performance_beat` | `pre` / `peak` / `afterglow` |
| `join` | 接下一镜 |
| `poison_risk` | none / anatomy / headroom / … |
| `value_rank` | 1–5（5=全片灵魂） |
| `dramatic_function` | 与 enum 对齐 |
| `dialogue_function` | 推进/关系/潜台词/钩子（若有词） |

**禁**：无 `visual_event` 的纯内心独白 beat；无 `state_out` 变化的空转场。

## L3 · 观众旅程

| 字段 | 说明 |
|------|------|
| `viewer_promise` | 3 秒内可懂的观看承诺 |
| `open_hook` | 开场钩（画面优先，不是 logline 复读） |
| `audience_journey[]` | 时段：`0_3s` / `first_20pct` / `mid` / `climax` / `end` |
| `retention_hooks[]` | 中段防划走的微转折 |
| `dead_air_risks[]` | 无聊预警（对齐 anti-boring） |
| `must_keep_beat_ids[]` | 不可砍（≥2） |

时间轴硬问：

- 0–3s：promise 是否**像素级**可懂  
- 前 20%：欲望 + 具体障碍（成人 setup 仍服从 hard-defaults 比例）  
- 中段：每约 15–20s 至少一个微转折  
- 高潮：选择**可见**  
- 结尾：`ending_hook` 有可拍末帧  

## L4 · 价值 → 生产映射

| 字段 | 说明 |
|------|------|
| `pilot_shortlist_beat_ids[]` | 默认 `value_rank≥4` |
| `weapon_bias[]` | 每项：`beat_id`, `suggest`（i2v/r2v/t2v/h3…）, `why` — **只建议不自动改 provider** |
| `compress_candidates[]` | rank≤2 且 soft necessity → 可压时长/合并 |

## Provenance

每个非空创意字段：

```json
"provenance": {
  "viewer_promise": "source_supported | creative_suggestion | user_choice"
}
```

- `user_choice`：订片人原话或确认  
- `source_supported`：原文可回指  
- `creative_suggestion`：未确认前不得当事实锁  

## 回显给用户（中文一页，禁 dump 全文 JSON）

1. **本片承诺**（viewer_promise）  
2. **不可砍** 2+ beat（人话）  
3. **必须有 / 禁止**  
4. **开放问题 / unknowns**  
5. 请用户：`确认 / 改 promise / 改 must_*`

## 与现有系统边界

| 系统 | 关系 |
|------|------|
| story-reception | 上游原文+导演处理；debrief 不替代 |
| directors-lens | L2 执行细则；debrief 提供 value_rank 与 promise |
| story_quality | 可对 debrief/graph 打分（P2 扩展维度） |
| workshop | 台词七维在 graph 后；debrief 在 lock 前 |
| adult-max / hard-defaults | 比例与毒镜仍唯一机读正文；debrief 只对齐检查 |
| weapon-lane | L4 只写 suggest |

## 完成定义（机读已落地 · 2026-08-04）

- [x] 模块 `script_value_debrief.py` + `plan debrief` CLI  
- [x] `plan validate` 挂载 soft/strict 检查  
- [x] `story_quality` 折叠呈现价值维度（缺 debrief 中性 0.5）  
- [x] `pilot pack` 优先 value shortlist → shot map  
- [x] `plan lock --scope story --strict` 可硬拦未确认  
- [ ] 每片实例：`receipts/script-value-debrief.json` 存在且用户确认后才 media  

离线回放：可对既有 `drama-graph` 事后填 rank，验证高 rank 是否=成片高光。
