# 武器库双车道矩阵（Grok Video 1.5 + 5090 H3）

> 2026-08-03 · 运营真相。类比：**Grok = 量产流水线**；**H3 = 重工车间**；**LTX = 对白棚**；**Qwen = 本地修片台**。

## 对白优先（v2.34 新）

- **对白镜画面必须可见「人在讲」**（on_camera>嘴动+近景；肉戏对白→H3 i2v/r2v 注入 Mandarin 台词）。
- **禁全场纯 silence/action_cover 或纯 nar**：每场 ≥1 条 on/off_camera 对白；逃生 `narration_reason`（见 [hard-defaults](hard-defaults.md) 对白场景级规）。
- 工具组 = `grok i2v`（安全 setup/只做 bulk） · `5090 H3 i2v/r2v`（restricted/肉戏/对白restricted） · `FRW LTX`（安全对白棚） · `Qwen`（状态照）。

## 默认

| 片型 | Profile / H3 |
|------|----------------|
| `genre=adult` 或 `heat_scale=max/hot/extreme` | 自动 `h3.enabled=true`，片级 `_i2v_profile→hybrid_h3`（Grok bulk + H3 meat） |
| 非成人 / `heat soft` / `adult_max_iron:false` / `h3.enabled=false` | 保持 `grok_primary`，不锁 H3 |
| 显式 `AIFILM_I2V_PROFILE=hybrid_h3` | 始终 dual-lane |

## 镜头路由

| 类型 | Still | Motion | Audio |
|------|-------|--------|-------|
| Setup / 非敏感 hero | Grok `image_edit(cast)` | Grok Video 1.5 `media-queue` | Edge TTS + BGM |
| Foreplay soft clothed | Grok | Grok 优先；moderation → 签名切 H3 | 同上 |
| Act / climax / bare / undressed | Qwen Edit / undress-anchor | **H3 I2V**（queue 硬拦云 bulk） | H3 `prefer_native` |
| 高难（deep_thrust / creampie / L4+contact / force_local_h3） | 本地状态照 | **H3** | 同上 |
| 对白近景（非敏感） | Grok face | FRW LTX 2.3 | 原生有声（中文） |
| **对白近景（restricted / bare）** | Qwen 状态照 | **5090 H3 i2v**（台词注入）；有状态照链 → **H3 r2v** | H3 原声 spoken Mandarin |
| Env / bridge | 可选 | FRW env 或 H3 T2V（低优先） | 环境 |
| 毒镜 | Qwen 解剖修 | **禁 I2V** | — |

## CLI

```bash
aifilm h3 list --root "<film>"     # 应走 H3 的镜
aifilm h3 plan --root "<film>" --shot-id shot03
aifilm h3 run  --root "<film>" --shot-id shot03 --register
# restricted 误入 Grok queue → QueueError；逃生 AIFILM_ALLOW_CLOUD_RESTRICTED=1
```

## 产能日历

1. 云：Grok setup + 非敏感 pilot  
2. 本地：Qwen 卸装 / bare state masters  
3. **5090 独占**：H3 meat 串行（`gpu-lease` + 单 comfy client）  
4. 云：桥接 / 对白 LTX  
5. select → final（HyperFrames）

## 质量门分车道

- Grok：mean ≥18/20 + MEDIUM LOCK cel  
- H3：解剖安全 + 接触可读 + 几何 ≥704×1280（run 时自动 upscale）+ 原声可用性  
- 毒 still：禁任何 I2V  

## 代码入口

- `production_router.build_shot_intent` / `classify_shot_content`  
- `film_spec.resolve_h3_config`（成人自动 dual-lane）  
- `media_queue.add_job`（restricted → 硬拦云）  
- `h3_workflow.ensure_h3_delivery_geometry`  
