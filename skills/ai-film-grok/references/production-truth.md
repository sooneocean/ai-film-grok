# 单一生产真相

`aifilm truth audit --root <film-root>` 是生产资料的只读对账入口。它不修复、不迁移、不重投影：审计若能自动把证据补齐，就不再是审计。

## 权威分工

| 事实 | 唯一权威 | 允许的派生物 |
|---|---|---|
| 可执行创作规格 | `film-spec.json` | timeline、prompt、队列工作项 |
| 规范叙事（启用 Graph 时） | `drama-graph.json` | `film-spec.json` 投影；投影须哈希绑定 |
| 素材与交付事实 | `manifest.json` + 本地媒体/回执 | status、quality、delivery package |
| 部门生命周期 | `production-book.json`（存在时） | department Bible、stale reasons |
| 用户项目进度 | Professional 11 阶段的 `project-state` 投影 | dispatch/HUD；不得另造进度条 |

## 审计判定

- `FILM_SPEC_MISSING`：没有可执行创作契约。
- `MANIFEST_TRUTH_INVALID`：manifest 缺失、版本旧、契约 hash 过期，或已批准媒体无法以本地路径、hash、provider 回溯。
- `CANONICAL_PROJECTION_STALE`：canonical `drama-graph.json` 已改动，但 `film-spec.json` 尚未重新投影；禁止继续媒体生产。
- `CANONICAL_GRAPH_NOT_READY`：Graph 的语义验证、锁定范围或投影就绪条件未通过；即使 hash 恰好相同也不能生产。
- `PRODUCTION_BOOK_INVALID`：部门控制册被篡改或无法校验；先恢复可信记录，不能绕过。
- `PROJECT_STATE_CONFLICT`：最终/导出门禁与 Professional 11 阶段或 final receipt 自相矛盾。
- `QUEUE_CONTRACT_STALE`：排队任务冻结的计划或资产版本已经变化，旧任务不得完成或登记为生产证据。
- `CANONICAL_QUEUE_CONTRACT_MISSING`：canonical Graph 项目存在未绑定计划/资产契约的队列任务；须重建该工作项。

Graph 不是每个旧项目的强制前置条件；没有 Graph 的 legacy shortform 项目仍以 `film-spec.json` 为创作真相。只要项目宣告为 canonical graph，Graph → spec 的绑定就必须是当前的。

## 四契约闭环

新建 queue job 会冻结一份 `shot-production-contract`：该镜的 `film-spec`、`drama-graph`、`assets-registry` 的 SHA-256，以及角色状态引用。任务完成时与 queue→clip 的 motion evidence 登记时都会重新验证这份契约；任何计划或资产漂移都会保留任务原状态并拒绝晋级。`production-evidence` 和 `truth audit` 同时汇总所有 queue contract，避免“单镜检查通过、总表仍把旧任务当有效”的分裂。

canonical 项目在 `register-clip --status approved` 时也必须提供 `--queue-job-id`；随后该 job 的输出 hash、端点、QA 与 source contract 都会被 `motion-evidence` 复验。故意先登记 clip、再补 queue 来源的路径不可用。

旧项目没有这份绑定时被标为 `legacy-unbound`，不是被悄悄视为可追溯。canonical Graph 项目必须先完成资产注册与锁定投影，才能创建绑定的 queue job。

## 使用时机

在以下动作前跑一次：bulk、重新接手 legacy 片根、切换 provider、picture/master lock、交付导出。通过审计只代表资料链自洽；它不替代 Pilot 人工批准、素材解码/画面审查，或 final 全片审看。
