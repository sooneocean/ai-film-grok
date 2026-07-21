# Lesson 2026-07-21 · 发色硬锁（P1 身份连续）

> **片例**：`velvet-stage-dual`（丝绒双姝）  
> **症状**：同一女主跨镜发色漂（Astra 深青 vs 纯黑；双人镜无法辨认同一人）  
> **用户原话**：「发色要稳定 现在颜色不一样 无法辨认是同一位」  
> **映射**：P1 身份连续 · Visualize/Generate 层

## 根因

1. `identity_lock` 只写笼统色名（`dark hair` / `teal`），模型在霓虹/暗红光下改写成黑发。  
2. **双人镜**用 multi-ref 时未把**每位** cast master 都钉在 `image[]` 前位，次要角色发色被场景光吞掉。  
3. Pilot 验人审只看「像不像 anime」，**未强制对照 cast 的发色 swatch**。  
4. I2V 仅吃 keyframe：若 still 已漂，视频必漂——**发色必须在 still 层先锁死**。

## 硬规则（沉入 consistency / style-bible）

| # | 规则 |
|---|---|
| H1 | 每名女主 `cast_locks.<id>` 必须含 **可复述发色句**：色名 + 禁改列表（例：`dark teal cyan-green hair; NEVER pure black; NEVER brown`） |
| H2 | 可选 `hair_swatches`：`{ "astra": "dark teal #0A5C66", "fufu": "golden orange #E8A23A" }` 写入 style-bible |
| H3 | 每镜 `image_edit`：**每个出场角色的 cast master 都进 `image[]`**（双人=两张 cast 在前，场景/style 在后） |
| H4 | Prompt 前缀除 `identity_lock` 外，再加一行 `Hair lock: …`（逐角重复色名 + NEVER…） |
| H5 | Pilot **发色对照**：对照 cast master 发色 fail → identity fail，禁止 `pilot approve` / bulk |
| H6 | 漂了：**只**用 cast master 做 `image_edit` 修 still，禁止从坏 still 平行重抽；修后再 I2V |

## Agent 操作清单（重产时）

```text
1. 从用户 ref / 已批 cast 重出 cast-v2（发色写死）
2. lookbook 近景必须露出发色区域
3. pilot still：每镜 Hair lock 行 + multi cast refs
4. 抽帧目视：发色与 cast 一致才 register-still approved
5. 再 I2V；I2V prompt 重复 Hair lock（视频会吃 still，仍防漂移文案）
```

## 反例 / 正例

| 反例 | 正例 |
|---|---|
| `teal hair` | `long dark teal cyan-green hair (#0A5C66), same as cast master; NEVER pure black` |
| 双人镜只喂一张 cast | `image=[fufu-cast, astra-cast, optional style]` |
| pilot 过「好看就行」 | pilot checklist 含 **hair_color_match** |

## 关联

- [consistency.md](consistency.md) §发色硬锁  
- [style-bible.md](style-bible.md) `cast_locks` / `hair_swatches`  
- [hard-defaults.md](hard-defaults.md) 身份  
- P1 · principles.md  
