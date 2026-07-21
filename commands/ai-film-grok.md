---
name: ai-film-grok
description: 启动 AI 短片/漫剧成片管线（dispatch 八环 + Imagine I2V + edge TTS + final）
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

- 每步结束后再 `dispatch`，只执行 `next_cmd`
- pilot 须用户批准才 bulk；中文 final TTS 用 **edge**；BGM 默认 **rnb**（dark 仅恐怖）
- I2V 默认 `grok_primary`；出图前加载 `/imagine`
- 完整主脊见 skill 内 `SKILL.md` 与 `references/craft-spine.md`
