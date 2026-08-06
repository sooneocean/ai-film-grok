# 8–15 分钟竖屏剧情长片 v1

## 边界

- `production_mode=longform`；目标 480–900 秒；只支持 9:16。
- 通用主链固定为 story→editorial→visual→performance→sound→post→delivery；题材差异由 production-book 的 `genre` pack 承担。
- v1 不新增模型、不静默换 I2V provider、不扩 16:9。Mac 负责编排；5090 只在既有资源与队列健康时执行媒体任务。

## 建立项目

```bash
aifilm plan receive --root "<film>" --file "<story>"
aifilm plan run --root "<film>" --received \
  --production-mode longform --target-duration 600
# 人审补齐并锁定 drama-graph
aifilm plan project --root "<film>"
aifilm write-spec --root "<film>"
aifilm longform status --root "<film>"
```

`write-spec` 生成 hash 绑定的 `receipts/longform-production-plan.json`。三幕内按 beat 分成最长 90 秒的连续生产单元；第一单元是代表性 pilot。

## 三道人工闸

1. 故事与 animatic 锁定后，才进入媒体生产。
2. 代表性 pilot 必须由用户批准，才可 bulk。
3. 最终母版必须完整观看并完成现有 review/audit/export 门禁。

自动化不得代批任何一道闸。

## 恢复与证据

- `aifilm longform status` 读取 graph/spec/timeline hash、单元 checkpoint 与最终母版来源，不写项目。
- `aifilm longform resume --unit lf-unit-NNN` 只返回一个受限恢复动作；不自行发起生成。
- final 技术 QA 通过后，系统从真实成片切出 `out/units/*.mp4`，逐个完整解码并写 checkpoint v2。
- final 或任一源合约 hash 改变，旧单元完成态失效；执行路径会保留损坏 checkpoint 为 `.corrupt.*`，只读 status 仅 fail-closed 回报，不写盘。
- `receipts/project-state.json` 是 dispatch 写入的统一状态快照；普通 `status` 保持只读。

## 长任务

final 的 plate timeout 由总时长、镜数与 lipsync 工作量动态估算：短片 floor **1200s**；片板≥480s 或 `production_mode=longform` floor **1800s**（cap 21600）。事件写入 `receipts/pipeline-events.jsonl`；超时明确失败并提示直调 `render_final` / 加大 `--plate-timeout`，不自动改 provider。sidechain 混音失败会 amix 降级并写 `receipts/final-mix-partial.json`（PARTIAL）。
