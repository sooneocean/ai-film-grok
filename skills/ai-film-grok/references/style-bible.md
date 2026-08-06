# Style Bible（全片视觉语法）

全片只认一份 bible。禁止每镜重发明 medium / palette / 线稿语言。

## 必填字段

| Field | 含义 | 锁定前要求 |
|-------|------|------------|
| `medium` | photoreal / **anime** / illustration… | 不得残留 init 默认「photoreal…」若主题是漫剧/同人 |
| `palette` | 主色 + 对比 | 具体色名/关系，禁止 `to be filled` |
| `lighting` | 主光气质 | 与主题一致（夜雨 / 纪律室荧光 / 低关键后宫…） |
| `lens` | 景深与竖屏构图习惯 | 可写 push-in / CU 偏好 |
| `rendering` | 皮肤/布料/粒子/线稿密度 | anime 要写 clear line / cel-shade 等 |
| `signature_block` | **英文**短段，贴进**每一** still/I2V prompt 前缀 | ≥48 字符，描述介质+色+身份稳定 |
| `identity_lock` | **英文**角色锁句（脸/发/瞳/服） | 主角必填；多主角用 `cast_locks` 对象 |
| `cast_locks` | 每角**结构化**锁对象（P1-1）：`{face_ref_path, identity_lock_tokens, never_tokens, hair_lock, makeup_lock}` | multi 必填；prompt_injector 优先使用此结构，注入 Hair lock 行与 Makeup 行 |
| `hair_swatches` | `{ "<char_id>": {color_name, hex, description} }` | P1-2 发型参数化；独立字段脱离 identity_lock 自由文本；prompt_injector 自动构建 Hair lock |
| `makeup` | `{ "<char_id>": {name, ref_path, lock_tokens, cross_scene_consistency} }` | P1-3 妆造参数化；prompt_injector 注入 Makeup 行；cross_scene_consistency=true 时全片妆造锁定 |
| `negative_hints` | 禁换脸、禁换发色、禁换介质、禁未成年… | 必填；须含「do not recolor hair」 |
| `canonical_style_path` | style-v1 路径 | lock-style 写入 |
| `cast_masters` | `{ "kei": "canonical/cast/kei-v1.png" }` | 至少一名主角；**一角一路径**（默认 full 定妆） |
| `cast_state_masters` | `{ "kei": { "full": "…", "partial": "…", "undressed": "…", "bare": "…" } }` | **状态照索引**（2026-07-21）；keyframe 按 `wardrobe_state` 查此表；见 [keyframe-first-state-index.md](keyframe-first-state-index.md) |
| `wardrobe_variants` | 每角每 state **文字**衣着描述 | 与状态照像素配套；undressed **勿**写回 full 句 |

## 状态照（State photos）· 必做心智

1. cast-v1 = L1 全装证件照。  
2. 串行 `image_edit` 产出 L2：`canonical/cast-states/<id>/{full,partial,undressed,bare}.*`  
3. 写入 `cast_state_masters`；heat max 至少 full+partial+undressed。  
4. 每镜 keyframe **主 ref** = `cast_state_masters[id][wardrobe_state]`（缺则 undress-anchor；**禁止** silent 回 full cast）。  
5. I2V **只**吃 keyframe；坏了回头改 keyframe/状态照。

## 从主题推断 medium（init / 人工）

| 主题关键词 | medium |
|------------|--------|
| anime, doujin, 漫剧, 同人, 里番, 二次元 | `high-quality anime illustration` |
| photoreal, live-action, cinematic real | `photoreal cinematic short` |
| 不确定 | **问用户一句**，禁止默认 photoreal 硬盖漫剧 |

## Lock 流程

1. 初始化 v2 結構: `aifilm bible init --root <root>`
2. 編輯 `style-bible.json`，寫滿 bible 字段（含 `characters`, `wardrobe_variants`, `continuity_states` 等）。  
3. 生成 **style-v1**（介质样张）+ **cast/\<id\>-v1**（主角定妆）。  
4. 生成 lookbook 3 张并人工批。  
5. 鎖定並過渡到 Approved 狀態:

```bash
"$AIFILM" bible lock --root <root>
# 或者手動更新
"$AIFILM" bible state --root <root> --set Approved
```

6. 中途不得随意 unlock；大改画风 → rollback 或建立新 film root。

## Prompt 前缀模板（由 Prompt Injector 自動注入）

執行 `aifilm write-spec` 時，內建的 Prompt Injector 會自動讀取 `style-bible.json` 並按以下優先級將 prompt 寫入 `receipts/prompt_assembly_[shot].json` 與 `prompts/[shot].txt`：

1. Signature / Visual Style
2. Location / Lighting
3. Character Lock & Wardrobe Lock
4. Continuity State
5. Shot-Specific Action
6. Negative Constraints

**無需在 agent 階段手動組裝長字串，Injector 具備防衝突檢測（例如角色鎖定與分鏡動作矛盾時報錯）。**

- `focal_character` / `viewpoint` / `look_axis` 来自 film-spec `dsl`（write-spec 可注入）；见 [character-stance.md](character-stance.md)。  
- 缺省可写 `focal=hero; viewpoint=objective; look_axis=center`，但 **≥4 镜片应轮换 viewpoint**。  
- **发色**：见 [lessons-2026-07-21-hair-color-lock.md](lessons-2026-07-21-hair-color-lock.md)；双人镜每位 cast 都进 `image[]`。

## Signature 示例（anime 暗黑同人）

```text
Vertical 9:16 high-quality dark anime doujin short, clean linework, soft cel shading,
coherent night academy palette (cold fluorescents, rain neon, violet rim),
stable heroine identity and wardrobe, consistent grade across all shots.
```

## Identity lock 示例

```text
Adult anime woman Kei: long silver-white wavy hair, black headband, pink geometric halo antenna,
large purple-red eyes, fair android-like skin, white oversized jacket with black panels and pink accents,
black vest, cyan blue tie, short black skirt, long black thigh-high socks, black boots.
```
