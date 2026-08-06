# Project Blueprint Contract

`project-blueprint.json` 是项目级唯一配置；它不是每集 prompt，也不是生成结果。

## 四层锁

| 层 | 固定什么 | 必须有的证据 | 什么时候允许改 |
|---|---|---|---|
| Project | project_id、画幅、系列规则、语言 | blueprint hash | 新项目版本或明确解锁 |
| Character | stable character_id、多视图、canonical master、脸/发/妆/服锁 | 每张参考图 SHA-256 + 人工 review | 新版角色资产，不能静默覆盖 |
| Style | medium、palette、lighting、rendering、signature、negative | style sample + style lock receipt | 新版 style bible |
| Story/State | 原文 hash、graph IDs、上一集状态、continuity chain | story/graph/state receipts | episode-level edit 或显式 replan |

多视图是“身份证据集合”，不是自动锁定。真正进入 Approved 前，必须选一张
`canonical_master`，并让用户确认它与多视图属于同一角色；侧面/背面图仍保留给审计与后续
状态/构图参考。角色相似度也不能由 SHA-256 证明，仍要人工看图或运行真实 face/identity
审查。

## 每集只允许新增的栏位

```json
{
  "episode_id": "ep02",
  "previous_episode_id": "ep01",
  "story_change": "本集新增剧情或用户确认的改动",
  "new_characters": [],
  "new_locations": [],
  "state_changes": [],
  "shot_constraints": [],
  "audio_language": {"dialogue": "ja", "narration": "zh", "captions": "zh"},
  "approval_required": ["story_lock", "pilot"]
}
```

不得在 episode brief 里重写 project-level `identity_lock_tokens` 或 `signature_block`；若确实
要变更，先建立新版本、记录原因、使旧 projection stale，再走人工 review。

## ai-film-grok 交接顺序

```text
project blueprint
  → intake-manifest / intake-report
  → story.receive / plan run
  → plan validate --strict
  → lock story/beats/shots/panels
  → graph project → write-spec
  → assets sync → state-index check
  → pilot approval → media queue → dailies/post
```

蓝图验证通过只代表资料契约完整；它不代表 pilot 通过、供应商真的遵守了提示词，或最终
视频已经完成。
