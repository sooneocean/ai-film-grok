# Migration governance

`ai-film-project` 是新建的 draft skill，目前不替代既有 skill。任何 portfolio 变化都必须保留证据。

## Rename

记录旧名称、新名称、触发兼容期、安装路径变化、引用更新与回滚方式。

## Deprecate

记录弃用原因、替代 skill、有效日期、移除日期、旧项目 fallback 和用户通知。

## Merge

记录来源 skill、目标 skill、边界理由、触发冲突解决、handoff 合并和 eval 迁移。

## Split

记录拆分目标、每个 skill 的唯一 primary job、旧触发语句分配、共同 schema 与 wrapper 变化。

## Compatibility

禁止直接重命名 `project_id`、`character_id`、style lock hash 或 episode ID；必须保留 adapter 或
一次性迁移报告，使旧 blueprint 仍可验证。

## Migration Evidence

迁移完成前必须有旧/新 skill 的 structure、semantics、trigger、workflow、lifecycle 与 release
gate 结果，并注明 schema version、git commit、host、model、timestamp 和回滚条件。
