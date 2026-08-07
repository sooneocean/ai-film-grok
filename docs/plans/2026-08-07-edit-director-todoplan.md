# 剪辑总监（edit_director）Todo Plan

> 2026-08-07 · 统筹 FFmpeg / HyperFrames / Remotion 最后输出  
> **不**另起第二导演系统；姊妹桌 = `music_director`；兑现 film-OS **P6**。

## 结论

机床齐了（plate / HF / Remotion / editor_cut / picture_lock / post_route），缺**车间主任**：  
`post/edit-director-plan.json` → draft/normalize/status/set/apply/run → receipts。

## 单一真相

| 文件 | 角色 |
|------|------|
| `post/edit-director-plan.json` | 计划（schema `aifilm-edit-director-plan-v1`） |
| `receipts/edit-director-apply.json` | apply 证据 |
| `receipts/edit-director-run.json` | run / dry-run 引擎链 |
| `receipts/post-route.json` | 由 plan 写死 caption_path（禁中途发明） |

## 引擎默认

- plate：**ffmpeg** 永远  
- design：**hyperframes** 默认；**remotion** 仅 explicit  
- caption：`master_hf`（设计路径）/ `ship_hardburn`（ffmpeg 或紧急 ship）  
- continue 缝：hard only；禁 HF 转场盖接戏

## Wave 状态

| Wave | 项 | 状态 |
|------|-----|------|
| E0 | 落档 · schema · hard-defaults 指针 | ✅ |
| E1 | draft/normalize/status/set + CLI + post_route | ✅ |
| E2 | apply + run dry-run；`--execute` shell 既有 `aifilm final` | ✅ |
| E2.5 | dispatch / next_actions / workflow_spine 钩 | ✅ |
| E3 | join_policy · snapshot/activate · audit | ✅ |
| E4 | stages 卡 · memory · tests · bump | ✅ |
| **R2** | ship-prep 自动 draft · post-doctor 路由对账 · final 读 plan · closeout next_cmd | ✅ |

## CLI

```bash
aifilm edit-director draft|normalize|status|set|apply|run --root <film>
# run 默认 --dry-run 安全；真跑须 --execute
```

## 反模式

- 禁第二 DirectorAgent 绿地  
- 禁双 owner 正式 final  
- 禁用剪辑「修好」未 approved take  
- 只编排，不复制 `render_final` 巨石  

## 交叉引用

- film-OS P6：`docs/plans/2026-08-07-film-production-os-todoplan.md`  
- post-compose / hf-remotion-capability-matrix  
- music_director · hard-defaults「后期」· stages/post.md  
