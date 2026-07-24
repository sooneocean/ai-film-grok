# 自动调配 · `aifilm dispatch`

> Agent 主入口：把八环 craft + 机位 capability + next 收成**一回合一步**。
> 不替代硬门禁；只负责「现在该干什么」。

## 一句话

```bash
aifilm dispatch --root "<film>"
```

默认只读 compact JSON 的 `next_cmd`、`next_action`、`hard_gate_codes` 与
`context_refs`；做完再跑一次，直到 `craft_stage=verified` 且已 export。
完整审计包始终写入 `receipts/dispatch.json`。

## 会自动帮你调什么

| 维度 | 行为 |
|------|------|
| 工序环 | 推断 idea…verified，优先 craft 缺口 |
| 工具层 | 对齐 agent/visual/voice/design/post |
| **Grok Build** | `routing.grok_build`：Imagine 静帧/I2V、推理、检索、记忆（见 [grok-build-sdk.md](grok-build-sdk.md)） |
| FRW | Media 前无 canary → 插入 `frw canary` |
| I2V | 有 canary → 提示 `capability --suggest-i2v`（改 spec 须 `--apply`） |
| TTS/BGM/Lipsync | `routing` 摘要；默认 edge + 程序化/库 rnb + lipsync off |
| Selects | selects 环插入 `selects report` |
| Rough/Verified | 插入 `audio-plan` 再 final |

## 不会自动做（刻意）

- 不自批 pilot / review-final
- 不静默改 `i2v_provider` / `tts_backend`
- 不默认 lipsync
- 不跳过 write-spec / VO 预算
- 不代替用户说「可以」

## 回执

- `receipts/dispatch.json` — 完整包
- `receipts/orchestration-usage.jsonl` — 调度 bytes、估算 Token、耗时、cache hit 与引用数；不含 prompt、凭据或供应商生成成本
- `~/.grok/hud/aifilm-dispatch.json` / `.txt` — HUD 短行

## 输出与缓存

```bash
aifilm dispatch --root "<film>"                  # compact（默认）
aifilm dispatch --root "<film>" --full           # 完整旧格式
aifilm dispatch --root "<film>" --format full    # 同上
aifilm dispatch --root "<film>" --refresh-capability
AIFILM_DISPATCH_FORMAT=full aifilm dispatch --root "<film>"
```

- capability 缓存为十分钟指导性缓存；付费、外部服务、人审动作与显式 refresh 强制实时探测。
- `state_hash` 未变时可复用 Graph、Production Book、quality 与 evidence 的完整包；输入变化立即失效。
- 普通步骤 `context_refs` 最多三份、合计不超过 8KB；异常按 issue code 精确扩展。

## 安全本地推进

```bash
aifilm advance --root "<film>" --max-local 3
```

`advance` 只执行固定白名单内的 `approval_class=none`、`spend_class=local`
动作，并在每一步验证 state/transaction、运行对应 verification、重新
dispatch。遇付费、外部服务、pilot、人审、重复、状态过期或失败立即停止。

## 与 next / craft / capability

| 命令 | 用途 |
|------|------|
| **dispatch** | 自动调配总包（推荐） |
| next | 仅工具 next_actions |
| craft | 仅八环进度 |
| capability | 仅机位/FRW 建议 |

## 用户口令

- 「继续 / 下一步」→ `dispatch` → 执行 `next_cmd`
- 「一路做完」→ `run_to_completion`：仍每步 dispatch，遇 pilot/十一维等人审点暂停
- 「停」→ 停止 bulk

见 [craft-spine.md](craft-spine.md) · [audio-fallback.md](audio-fallback.md)
