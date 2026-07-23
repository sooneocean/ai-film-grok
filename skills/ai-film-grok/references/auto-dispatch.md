# 自动调配 · `aifilm dispatch`

> Agent 主入口：把八环 craft + 机位 capability + next 收成**一回合一步**。
> 不替代硬门禁；只负责「现在该干什么」。

## 一句话

```bash
aifilm dispatch --root "<film>"
```

读返回 JSON 的 `next_cmd` 与 `agent_instruction`，做完再跑一次，直到 `craft_stage=verified` 且已 export。

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
- `~/.grok/hud/aifilm-dispatch.json` / `.txt` — HUD 短行

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
