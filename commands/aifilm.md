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

默认输出 compact packet；`--full` 读取完整审计包。安全的本地连续步骤可用
`aifilm advance --root "<root>"`，遇付费、外部服务或人审会自动暂停。

无 root 时先问用户或 `aifilm init`。

用户提供小说、剧本或故事文本时，先加载 **ai-film-grok** 的 `story.receive` 接收器，
由 Agent 产出可追溯的 `StoryReception v1`，再运行：

```bash
"$SKILL_DIR/scripts/aifilm" plan receive --root "<root>" --file "story-reception.json"
"$SKILL_DIR/scripts/aifilm" plan run --root "<root>" --received-file "<root>/receipts/story-reception.json"
```
