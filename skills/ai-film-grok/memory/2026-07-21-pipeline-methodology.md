# Memory · 四层流水线方法论沉淀（2026-07-21）

## 用户意图

用清晰产品方法论优化 `ai-film-grok` skill：

```
Prompt → Agent 规划 → 1 视觉 → 2 语音(Edge) → 3 HyperFrames/Remotion → 4 FFmpeg → 交付
```

## 决策

| 项 | 结论 |
|---|---|
| 结论类型 | **PATCH**（结构重组，非砍功能） |
| 主脊文件 | `references/pipeline-methodology.md` |
| SKILL.md | 按 Agent+四层重写生产流程；硬门禁保留 |
| 工程顺序 | 一键 hyperframes 仍是 FFmpeg plate(subs off) → 设计层 → 封装；与方法论「3 设计 / 4 FFmpeg」在文档中显式对齐 |
| 不改 | CLI 契约、Seedance 默认、pilot S3、双烧 blank plate、P0–P5 |

## 备份

`backups/2026-07-21-pipeline-method/{SKILL.md,README.md}`

## 验收

- Agent 读 skill 能按 1→2→3→4 叙事调度
- 不误导成「先 HF 再从零 FFmpeg」破坏 underlay
- description 含四层关键词（视觉/Edge/HyperFrames/FFmpeg）

## 2026-07-21 下一步（已落地）

| 项 | 状态 |
|---|---|
| `docs/architecture.png` 四层重绘 | 已完成（旧图备份在 backups/2026-07-21-pipeline-method/） |
| `detect_pipeline_stage()` | `scripts/next_actions.py` |
| `status` / `next` / `preflight` 输出 `pipeline_stage` | 已挂 |
| `next_actions[]` 带 `stage` / `stage_label` | 已挂 |
| 测试 | `PipelineStageTests` + persist = 14 OK |

## 2026-07-21 再推进（HUD + CLI）

| 项 | 状态 |
|---|---|
| `aifilm stage` | 新增 |
| `next --print-stage` / `--print-stage-only` | 新增 |
| `persist_pipeline_stage` → receipts + `~/.grok/hud/aifilm-stage.*` | 新增 |
| grok-build-hud `loadAifilmStageLine` + 第 3 行展示 | 已补丁并 `npm run build` |
| 关 sidecar | `AIFILM_HUD_STAGE=0` |

## 2026-07-21 收敛

| 项 | 状态 |
|---|---|
| SKILL.md | ~456 行 → ~200 行（主脊 + 阶段路由 + 命令） |
| `references/hard-defaults.md` | 跨层硬默认从主脊抽出 |
| 备份 | `backups/2026-07-21-pipeline-method/SKILL.md.pre-converge-*` |
| 原则 | 细节下沉 reference；硬门禁不删；CLI 契约不变 |
