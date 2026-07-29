---
name: ai-film-grok
description: 启动 AI 短片/漫剧成片管线（Professional 11 阶段 + Imagine I2V + edge TTS + final）
---

# /ai-film-grok

按 **ai-film-grok** skill 执行。优先：

```bash
SKILL_DIR="${HOME}/.grok/plugins/ai-film-grok/skills/ai-film-grok"
[ -d "$SKILL_DIR" ] || SKILL_DIR="${HOME}/.grok/skills/ai-film-grok"
AIFILM="$SKILL_DIR/scripts/aifilm"
"$AIFILM" dispatch --root "<film-root-or-ask-user>"
```

规则摘要：

- `dispatch` 默认回 compact packet；完整审计包用 `--full`
- Professional Director 11 阶段已内化为 dispatch 的内部顺序；不是另一套入口
- 每步结束后再 `dispatch`，只执行结构化 `next_action`（`next_cmd` 兼容显示）
- 可用 `advance --root …` 执行 allowlist 内本地步骤；human/paid/external 必停
- pilot 须用户批准才 bulk；中文 final TTS 用 **edge**；BGM 默认 **rnb**（dark 仅恐怖）
- I2V 默认 `grok_primary`；出图前加载 `/imagine`
- 只读返回的 `context_refs`；完整导航见 `references/INDEX.md`
