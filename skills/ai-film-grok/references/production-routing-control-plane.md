# 镜头级生产路由控制层

`route explain` 只回答一件事：基于当前 `film-spec.json` 镜头约束和一份有时效的能力快照，哪条路线现在可用，以及其他路线为什么被淘汰。

它不会探针、写回执、提交任务、切换 provider 或消耗额度。

## 输入真相

| 输入 | 责任 |
|---|---|
| `film-spec.json` | 镜头角色、连续性、身份、内容边界和 provider lock |
| `receipts/capability-snapshot.json` | 模型、操作、授权、pilot、资源、并发和到期时间 |
| `--quality-tier` | `draft`、`select` 或 `hero` |

能力快照必须符合 `schemas/capability-snapshot.schema.json`。模板位于
`templates/capability-snapshot.example.json`。历史成功不能自动变成当前可用；
`expires_at` 到期后会返回 `CAPABILITY_STALE`。

## 使用

```bash
AIFILM="skills/ai-film-grok/scripts/aifilm"

"$AIFILM" route explain \
  --root "<film-root>" \
  --shot-id "shot01"

"$AIFILM" route explain \
  --root "<film-root>" \
  --shot-id "shot01" \
  --capabilities "<snapshot.json>" \
  --quality-tier select
```

实验能力默认返回 `EXPERIMENTAL_NOT_ALLOWED`。`--allow-experimental` 只允许它进入
只读比较；选中结果仍带 `requires_human_approval=true`，且 `auto_execute=false`。

## 选择顺序

1. 硬约束：状态、时效、授权、pilot、操作、镜头角色、内容类别、身份锁、provider lock。
2. 最弱质量门 `quality_floor`。
3. 总体 `quality_score`。
4. 镜头角色专用度。
5. 人工配置的 `priority`。
6. 相同条件按 capability id 稳定排序。

不以平均分覆盖硬失败；不存在合格能力时返回 `NO_VIABLE_CAPABILITY`。

## 当前边界

- 本增量不生成 capability snapshot；快照必须来自后续的无费用探针聚合器或人工导入。
- 本增量不建立执行 DAG；`execution-plan.schema.json` 仅先固定未来授权、资源锁、依赖和幂等键的公开合约。
- `route explain` 的输出不等于 provider 授权、pilot 批准或最终成片证据。
