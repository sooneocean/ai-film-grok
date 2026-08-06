# Keyframe-First · 状态照索引（检查门 + 可补生成）

> **用户意图（2026-07-21）**：  
> 1) 从生成逻辑回头改 keyframes / 角色状态照，让视频**有所参考**  
> 2) **这是检查机制**：本阶段若有缺口可再生成，目的是 **运镜 / 转场流畅**  
> **P 码**：P0 交付 · P1 身份 · P2 时空  
> **互补**：  
> - [wardrobe-no-redress-still](lessons-2026-07-21-wardrobe-no-redress-still.md)  
> - [first-last-gen](lessons-2026-07-21-first-last-gen.md)  
> - [consistency.md](consistency.md) §1 / §1e  
> - [sex-undress-ladder](lessons-2026-07-21-sex-undress-ladder.md)

---

## 0 · 一句话

**不是「文档建议」，是生产检查门（checkpoint）**：  
先查状态照 / keyframe / promote 是否齐 → 有缺口**就在本阶段补生成** → 再 bulk I2V。  
目的：衣着不跳、首尾接戏、运镜转场顺。

白话类比：  
状态照 = 衣柜证件照；keyframe = 场记板；I2V = 开拍。  
开拍前场记会检查：服装对不对、上一场末尾接不接得上——不对就先补拍证件照/场记板。

---

## 0b · 检查门 CLI（必跑）

```bash
# 检查 + 写 receipts/state-index.json
"$AIFILM" state-index check --root "<film>"

# 只看「本阶段该补生成什么」（状态照 / keyframe / promote）
"$AIFILM" state-index plan --root "<film>"

# 也会并入 preflight / dispatch（soft + generate_plan）
"$AIFILM" preflight --root "<film>"
"$AIFILM" dispatch --root "<film>"
```

| 字段 | 含义 |
|---|---|
| `ok` | hard 空则为 true |
| `generate_plan[]` | **本阶段可执行的补生成清单** |
| `fluency_issues[]` | 转场/接戏风险（缺 promote、衣着 rank 掉） |
| `agent_do[]` | 本回合 checklist |
| `undress_anchor` | 卸装峰值锚是否存在 |

**执行顺序（plan 默认）**：  
(1) 缺的状态照 → (2) undress-anchor → (3) 缺 keyframe（从状态照 edit）→ (4) continue 缝 `extract-frame --promote-keyframe`  
做完再 `state-index check` 直到 `generate_plan` 空或只剩可选 soft。

---

## 1 · 资产索引层级（Index Ladder）

从稳到动，**下层只能引用上层，不得跳回更「穿好」的上层**：

| 层 | 资产 | 路径约定 | 管什么 |
|---|---|---|---|
| L0 | Style master | `canonical/style-v1.*` | 介质/色/光 |
| L1 | Cast master（定妆 · 通常 full） | `canonical/cast/<id>-v1.*` | 脸/发/瞳/**默认全装** |
| L2 | **状态照 State photos** | `canonical/cast-states/<id>/{full,partial,undressed,bare}.*` | **衣着状态真相** |
| L2b | undress-anchor（本片峰值） | `canonical/wardrobe/undress-anchor.png` | 本片卸装峰值快照（可 = L2 undressed/bare） |
| L3 | **Shot keyframe** | `keyframes/shotXX.*` | 本镜 t=0 构图+姿势+**已定状态** |
| L4 | I2V clip | `clips/shotXX.mp4` | 从 L3 演动 |
| L5 | promote 末帧 | 下镜 L3 候选 | 接戏 |

```text
L1 cast full ──edit──► L2 state photos (full/partial/undressed/bare)
                              │
                              ▼ 按 film-spec wardrobe_state 选索引
                         L3 keyframe (image_edit 主 ref = L2 对应状态)
                              │
                              ▼
                         L4 I2V (input = L3 only)
                              │
                              ▼ register → promote last → 下镜 L3
```

**禁止**：L4 的输入直接用 L1 全装（除非本镜 `wardrobe_state=full` 且 setup）。

---

## 2 · 角色状态照（State Photos）

### 2.1 是什么

每个主角在本片可能出现的 **衣着/身体状态** 各一张（或一套）**站桩证件照**：

| state | 画面最低要求 |
|---|---|
| `full` | 定妆完整（可与 cast-v1 相同或拷贝） |
| `partial` | 半脱/失序可读（肩带崩、扣解开、裙掀…） |
| `undressed` | 主装已卸、大面积裸/半裸可读 |
| `bare` | 顶格暴露（双轨可 suggestive，但**不得**画回 full） |

脸/发/瞳必须与 L1 cast **同一人**。状态照 **只变衣着状态**，不换脸。

### 2.2 落盘与 bible

```text
canonical/cast-states/
  xide/
    full.png
    partial.png
    undressed.png
    bare.png
  partner/   # 可选
    full.png
```

`style-bible.json`：

```json
{
  "cast_state_masters": {
    "xide": {
      "full": "canonical/cast-states/xide/full.png",
      "partial": "canonical/cast-states/xide/partial.png",
      "undressed": "canonical/cast-states/xide/undressed.png",
      "bare": "canonical/cast-states/xide/bare.png"
    },
    "hero": { "...": "可与 xide 同路径别名" }
  }
}
```

`wardrobe_variants` 仍写**文字**描述；`cast_state_masters` 写**像素路径**。两者一起才算状态可索引。

### 2.3 如何生成状态照

1. 以 L1 cast 为 ref → `image_edit` 得到 partial → undressed → bare（**串行**，每步保存）  
2. 审核双轨：bare 可 soft，但**状态标记**仍是 bare 档，禁止再引用 full 图  
3. heat max 建议至少：`full` + `partial` + `undressed`（bare 可选与 undressed 共用一图）  
4. 本片卸装峰值 still 另存 `undress-anchor`（与 ladder 一致）

---

## 3 · Keyframe-First（倒推生成）

### 3.1 正向误解（旧·易回穿）

```text
cast full → 每镜 image_edit(cast) → I2V
```

结果：文字写 bare，像素回 full。

### 3.2 正确倒推

```text
film-spec 定 wardrobe_state + pose
        ↓
查索引：state_photo = cast_state_masters[id][wardrobe_state]
        若无 → undress-anchor（若 ≥partial）→ 禁止 silent 用 full
        ↓
keyframe = image_edit(state_photo 为主 ref；cast 仅脸辅可选)
        ↓ 审 keyframe（结构/衣着/脸）
I2V(image=keyframe, motion=相对本帧变化)
        ↓ 坏了？
只修 keyframe 或换状态照再 I2V —— 不从 cast full 平行重抽
```

### 3.3 Agent 检查表（每镜 still 前）

- [ ] 读 `shot.wardrobe_state`  
- [ ] 解析 `state_photo` 路径（bible `cast_state_masters` 或 undress-anchor）  
- [ ] `image_edit` **主图** = state_photo，**不是** full cast（除非 state=full）  
- [ ] prompt 含 `State photo continuity: wardrobe=<state>`  
- [ ] keyframe 过结构门 + 衣着门 → 才 I2V  
- [ ] I2V prompt：`Keep first-frame clothing; never re-dress`  

### 3.4 与 first/last 接戏

| 情况 | keyframe 来源 |
|---|---|
| `chain_mode: continue` 且上镜已批 | **promote 上镜 last**（字节相同）优先于重画状态照 |
| `chain_mode: cut` 换景别 | 可用状态照重构图，**衣着 state 不降 rank** |
| 上镜 last 衣着漂了 | 先用状态照 **修** promoted 帧，再 I2V |

详见 [first-last-gen](lessons-2026-07-21-first-last-gen.md)。

---

## 4 · write-spec / Prompt Injector 契约

`write-spec` 后 `prompts/<shot>.txt` 与 `receipts/prompt_assembly_*.json` 应含：

| 字段/行 | 含义 |
|---|---|
| `wardrobe_state=…` | 文字阶梯 |
| `State photo ref: <path>` | **像素索引**（有则 agent 必须吃） |
| `Costume continuity HARD` | 禁回穿 |
| `Start already: …` | 从已脱姿势开场 |

Agent **不得**忽略 `State photo ref` 行另起 full cast。

---

## 5 · 验收

| 检查 | pass |
|---|---|
| 索引存在 | heat max：至少 full+partial+undressed 状态照或 undress-anchor |
| keyframe 溯源 | 每镜 still 主 ref ∈ {state_photo, undress-anchor, promote 末帧} |
| 视频可参考 | I2V input 文件 = 该镜 keyframe；QA 抽 t=0 对齐 keyframe |
| 回穿 | peak 后无 full cast 主 ref；抽检半脱标记连续 |

用户说「回穿 / 没参考 / 乱跳」→ 先查 **L2 状态照是否齐**、**L3 是否从 L2 来**，再查 L4。

---

## 6 · 最小命令心智

```bash
# 1) 定妆
canonical/cast/xide-v1.jpg

# 2) 状态照串行（从 full 改 partial → undressed → bare）
canonical/cast-states/xide/{full,partial,undressed,bare}.png
# 写进 style-bible cast_state_masters

# 3) 每镜
#    ref = cast_state_masters[hero][wardrobe_state] 或 undress-anchor
#    → keyframes/shotXX.png → image_to_video(shotXX.png)

# 4) register-clip → auto promote last → 下镜 keyframe
```
