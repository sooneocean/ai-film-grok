---
name: ai-film-grok
description: 启动 AI 短片/漫剧七段成片主流程（Imagine I2V + edge TTS + final）
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
- `phase` 是对外唯一进度：定义故事→设计演出→Pilot→批量制作→选片与粗剪→后期母版→审片与交付
- 每步结束后再 `dispatch`，只执行结构化 `next_action`；先解除 `blocked_by`，以 `required_proof` 决定过关（`next_cmd` 兼容显示）
- Professional Director 11 阶段与八环保留为相容／诊断字段，不能形成第二套入口
- 可用 `advance --root …` 执行 allowlist 内本地步骤；human/paid/external 必停
- pilot 须用户批准才 bulk；中文 final TTS 用 **edge**；BGM 默认 **rnb**（dark 仅恐怖）
- I2V 默认 `ltx23_primary`：FRW LTX 2.3 → FRW API I2V → Grok Video 1.5；每路须当前影片 approved canary，`grok_primary` 仅供旧项目显式锁定
- 只读返回的 `context_refs`；完整导航见 `references/INDEX.md`
