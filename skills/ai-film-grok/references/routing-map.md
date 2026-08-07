# Routing map（人读 · agent 索引）

> 一页说清：生产里「往哪走」由谁决定。细节表见 `registry/route-catalog.json`（R1+）。

## Agent 只认这一条

```bash
aifilm dispatch --root <film>
# 读 next_action → blocked_by → required_proof → context_refs / weapon_route
# 失败即停；receipts/dispatch.json
```

不要背 ~131 条 CLI。需要武器/镜头解释时再开 `aifilm route explain`。

## 六层（由外到内）

| 层 | 干什么 | 命令 / 文件 |
|----|--------|-------------|
| **CLI 表面** | 人/脚本敲的子命令 | `aifilm <cmd>` · `scripts/aifilm_grok.py` + `cli/*` |
| **编排 dispatch** | 当前该干什么 | `aifilm dispatch` · `spine/dispatch.py` |
| **next_actions** | 从片根状态列候选步 | `spine/next_actions.py` |
| **skill 注册** | 能力清单 + argv 桥 | `registry/skills.json` · `skill_runner.py` |
| **镜头 capability** | 单镜选 Grok/H3/FRW 等 | `aifilm route` · `plan/production_router.py` · 回执 `layer=capability` |
| **武器 armory** | 本机 Comfy 武器 + provider 锁 | dispatch.`weapon_route` · `media/weapon_router.py` · `layer=weapon` |

### R5 选路三层契约（禁止互抢）

1. **intent**：`build_shot_intent` / `classify_shot_content` — 内容 → lane 需求  
2. **capability**：`explain_route` — 在 capability-snapshot 内排名（不写、不花）  
3. **weapon**：`build_weapon_route` — 本机 armory + film-spec provider 锁  

人读矩阵：`weapon-lane-matrix.md`。改默认 lane 须显式确认，禁止静默切 `i2v_provider`。

支路（不是总控）：`post_route`（字幕路径）、`dialogue_i2i_route`、`frw_dispatch`。

## 三套名字（R2：`spine/stage_model.py` 投影）

| 用途 | 名字 |
|------|------|
| 对外 / SKILL 阶段 | agent → visual → voice → post → deliver（`stage_public`） |
| 内部 pipeline | 同上 + design（≈post）+ done |
| craft 八环 | idea → … → verified（`craft_stage`） |
| workflow 状态机 | 11-stage（`workflow_spine`） |

`design` → 对外算 `post`。新代码只从 `stage_model` 取常量，勿再复制 STAGE 元组。

## 三套 ID（R1 catalog 对齐）

| 空间 | 例 |
|------|-----|
| CLI | `gate-auto`, `h3`, `pilot` |
| next_action id | `gate-auto`, `h3-run-next`, `pilot-pack` |
| skill_id | `projection.verify`, `image.animate`, `quality.inspect` |

## 政策落点

- 花钱 / 人审：`dispatch` policy（将迁 catalog）
- 本地可 auto：`advance` allowlist
- 成人 / 毒镜 / 对白原音：`hard-defaults.md`（不进 catalog 业务字段）

## 维护

- 新 CLI：加 `cli/*` parser + handler，**并**在 route-catalog 加一行（R1+）
- 改选路 lane：先 `weapon-lane-matrix.md` + `production_router` 测，勿只改文档
- 盘点：`python scripts/tools/route_inventory.py`
- **C1 orphan 治理（2026-08-07）：** hub 主路径 CLI（dispatch/doctor/advance/…）→ `canonical`；
  其余仅 CLI 面、不进 next_action 主脊的 → `partial` + tag `cli_only_not_spine`；
  orphan 软顶 **&lt;40 条且 &lt;20%**（`test_route_catalog`）。勿把「没挂 skill」的真实 CLI 长期留 orphan。
