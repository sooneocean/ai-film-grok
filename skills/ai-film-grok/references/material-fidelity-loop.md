# Material Fidelity Loop（素材保真闭环）

> 2026-08-05 · 生成模型如何**稳定吃对**先验像素。  
> 类比：货架（registry/gates）再全，车间要有**统一领料单**。

## 命名表（勿混）

| 名字 | 是什么 | 不是什么 | 代码 |
|------|--------|----------|------|
| **DocContext** | 给 agent 的文档 refs | 像素 | `context_routing.py` |
| **PixelPack** | first/last/identity 图路径+sha | 部门 hash | `h3_media_pack.py` |
| **StillSource** | 本镜 I2V 首帧唯一决议 | 设定拼图 | `still_source.py` |
| **DeptHashPack** | 部门 bible 节点 hash 契约 | prompt | `shot_package.py` |
| **GatePack** | pilot / bulk / ship 证据 | 生成输入 | `pilot_pack` · `workflow_pack` |
| **GenerationRequest** | 模型消费单：text+refs+sha | 门禁散文 | `generation_request.py` |

## StillSource 优先级（I2V first）

1. explicit override  
2. continue handoff endframe（`chain_mode=continue`）  
3. approved still（manifest → `stills/` / `keyframes/`）  
4. shot 字段 still/keyframe  
5. 对应 wardrobe **state photo**  
6. **禁止** peak（undressed/bare/act）静默回落 full cast master  

## GenerationRequest 回执

```text
receipts/prompts/<shot_id>.request.json
```

字段要点：`text_prompt` · `text_sha256` · `image_refs[{role,path,sha256}]` · `still_source` · `constraints` · `ok`。

- `aifilm h3 plan|run` 写回执  
- `media-queue` 若已有回执：校验 first input sha（逃生 `AIFILM_SKIP_GENERATION_REQUEST=1`）

## 坏 take 怎么办

视频坏 → 先改 L2/L3（state photo / still-challenge），**不要**同 still 盲重烧。  
mean 红 + 脸绿 → 推 still-challenge（人 promote）再 I2V。

## M3 · Registry 进 prompt

`build_asset_prompt_hints`（`asset_registry.py`）→ location structure/lighting/palette/immutableRules/recurringObjects + prop condition/storyFunction。  
缺 `assets-registry.json` 时 soft（提示 `aifilm assets sync`）。

## M4 · 反馈环

| 写入 | 时机 |
|------|------|
| `receipts/shot-evidence/<id>.json` | `write_mean_sidecar` · `register-clip` |
| `PRIOR_EVIDENCE` 行 | 下次 `build_generation_request` 首部（≤3 行） |
| next_actions `still-challenge-weak-mean` | `suggest_still_challenge` |
| pk_score | identity L1 罚分加重（永不 auto-promote） |

## 指针

- 阶段卡：[stages/visual.md](stages/visual.md)  
- 武器盘点：[weapon-inventory.md](weapon-inventory.md) · 双车道：[weapon-lane-matrix.md](weapon-lane-matrix.md)  
- 先验后生：[lessons-2026-07-22-verify-before-generate.md](lessons-2026-07-22-verify-before-generate.md)  
- 状态照：[keyframe-first-state-index.md](keyframe-first-state-index.md)  
- hard-defaults：仅指针行「Material Fidelity」  
