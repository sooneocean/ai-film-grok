# Memory · 2026-08-04 · 剧本呈现价值拆解

**完整规则**：[script-value-debrief.md](../references/script-value-debrief.md)

## 用户原话
> 帮我思考如何拆解输入的剧本能够让影片完成呈现价值 导入更多导演思维还有编剧跟用户思维 用多角度来思考这个影片剧本的环节优化

## 三句话
1. 缺口不是再写方法论，而是 lock 前强制 **script-value-debrief**（独立收据）。
2. 五层：用户契约 → 编剧骨架 → Beat Value Card → 观众旅程 → 生产/pilot 映射。
3. **v2.38.8**：`next` 在 story intake 后强制 `plan debrief`；seed 自动标 climax/ending + needs_agent_fill。

## 检查清单
- [x] `story.receive` 后写 `receipts/script-value-debrief.json`（`plan debrief --action seed`）
- [x] `next_actions` 先 `plan-debrief` / `plan-debrief-confirm`（过 pilot 后跳过）
- [ ] 回显 promise / must_have / must_not / 不可砍 beat → 用户 `--action confirm`
- [x] seed 每 beat 有 `visual_event` + 启发式 `value_rank`
- [x] pilot 优先 rank≥4
- [x] 不覆盖 `source.raw_text`


## 模板
- [script-value-debrief.example.json](../templates/script-value-debrief.example.json)
- [script-value-debrief.adult-max.example.json](../templates/script-value-debrief.adult-max.example.json)
