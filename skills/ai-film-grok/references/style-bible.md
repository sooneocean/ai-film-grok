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
| `cast_locks` | 每角独立锁句（**必含发色 + NEVER 禁色**） | multi 必填；single 可只填 hero |
| `hair_swatches` | `{ "id": "色名 #hex 或可复述色名" }` | **强烈建议**；防霓虹光改写发色（2026-07-21） |
| `negative_hints` | 禁换脸、禁换发色、禁换介质、禁未成年… | 必填；须含「do not recolor hair」 |
| `canonical_style_path` | style-v1 路径 | lock-style 写入 |
| `cast_masters` | `{ "kei": "canonical/cast/kei-v1.png" }` | 至少一名主角；**一角一路径** |

## 从主题推断 medium（init / 人工）

| 主题关键词 | medium |
|------------|--------|
| anime, doujin, 漫剧, 同人, 里番, 二次元 | `high-quality anime illustration` |
| photoreal, live-action, cinematic real | `photoreal cinematic short` |
| 不确定 | **问用户一句**，禁止默认 photoreal 硬盖漫剧 |

## Lock 流程

1. 写满 bible 字段（含 `identity_lock`）。  
2. 生成 **style-v1**（介质样张）+ **cast/\<id\>-v1**（主角定妆）。  
3. 生成 lookbook 3 张并人工批。  
4. 执行：

```bash
"$AIFILM" lock-style --root <root> \
  --canonical <style-v1.png> \
  --cast-master <cast/kei-v1.png> \
  --signature "<signature_block 最终版>"
```

5. 中途不得随意 unlock；大改画风 → 新 film root 或 `style-v2` 新片。

## Prompt 前缀模板（每镜强制）

```text
{signature_block}
Identity lock: {identity_lock}
Hair lock: {per-character hair from cast_locks / hair_swatches; include NEVER… bans}
Stance: focal={focal_character}; viewpoint={viewpoint}; look_axis={look_axis}
[shot-specific pose / env / camera only after this line]
All characters 18+ adults. Keep exact face, EXACT hair color, wardrobe and medium.
Do not recolor hair under neon or red club light.
```

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
