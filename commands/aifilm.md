---
name: aifilm
description: ai-film-grok 短别名——dispatch / doctor / 成片管线入口
---

# /aifilm

`/ai-film-grok` 的短别名。加载 **ai-film-grok** skill，对当前或用户指定的 film root 跑：

```bash
SKILL_DIR="${HOME}/.grok/plugins/ai-film-grok/skills/ai-film-grok"
[ -d "$SKILL_DIR" ] || SKILL_DIR="${HOME}/.grok/skills/ai-film-grok"
"$SKILL_DIR/scripts/aifilm" dispatch --root "<root>"
```

无 root 时先问用户或 `aifilm init`。
