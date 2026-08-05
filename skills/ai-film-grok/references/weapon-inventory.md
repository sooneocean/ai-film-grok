# 武器库全模态盘点（文 · 图 · 影 · 声音）

> 2026-08-05 · **单一真相（机读）**：`registry/weapon-inventory.json`  
> 代码：`scripts/weapon_inventory.py` · 本地 Comfy 细表：`registry/comfy-weapons.json`  
> 运营矩阵：[weapon-lane-matrix.md](weapon-lane-matrix.md) · 臂章：[comfy-weapon-armory.md](comfy-weapon-armory.md)

## 分层

| tier | 含义 |
|------|------|
| **primary** | 默认首选；与 hard-defaults / select_weapon / ship 一致 |
| **secondary** | hybrid / 云 escape / free tier |
| **experimental** | pilot only；禁静默 production |
| **retired** | 不得再当默认 |

## 5090 主产线 primaries

| 模态 | Primary | 入口 |
|------|---------|------|
| 文 prompt | motion_prompt_spine + prompt_injector | GenerationRequest 自动 |
| 图 T2I | qwen-image-2512-quality | `aifilm comfy route --intent text-to-image` |
| 图 修片 | qwen-image-edit-2511-local | local-image-edit --identity-lock |
| 影 I2V/FLF/R2V/T2V | MiniMax H3 | `aifilm h3 plan\|run` |
| 声 中文 VO | **Edge** zh-CN-*-Neural | `final --tts-backend edge` |
| 声 BGM | recipe **rnb** | `final --music-mood rnb` |

Profile：有 5090 → `AIFILM_I2V_PROFILE=h3_primary`。

## 防转换流失

```text
StillSource → GenerationRequest (text_sha + image_refs.sha) → H3 / media-queue
```

详：[material-fidelity-loop.md](material-fidelity-loop.md)

## 校验 / CLI

```bash
aifilm weapon inventory                 # 全表 + line
aifilm weapon inventory --tier primary  # 仅 primary
aifilm weapon inventory --primary-for image-to-video --validate
aifilm doctor                           # soft 字段 weapon_inventory.line
pytest skills/ai-film-grok/tests/test_weapon_inventory.py skills/ai-film-grok/tests/test_cli_weapon.py -q
```

## 接入（round 3）

- `generation_ready` → `weapon_inventory` / `inventory_line` / hints
- `next_actions` H3 why → `wp=minimax-h3-i2v-pilot` 等 primary 标签
- `aifilm dispatch` compact → `weapon_inventory_line` + motion/still_primary

## bulk-preflight（round 4）

失败时 `receipts/bulk-preflight.json` 带 `weapon_inventory` + `next_why`，点名 still/edit/motion primary：

```bash
aifilm bulk-preflight --root "<film>" --no-tunnel
# failed → next_cmd names Qwen edit / H3 motion
```
