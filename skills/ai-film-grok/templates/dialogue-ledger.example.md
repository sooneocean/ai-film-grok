# Dialogue Ledger — 对白台词库模板

> P1-8 对白台词库 · 独立于 shot.dialogue 的台词表
> 每行一条台词，含 line_id/speaker/emotion/subtext/beat_ref/delivery_note。

| line_id | speaker | text | emotion | subtext | beat_ref | shot_ref | delivery_note | lipsync_anchor | is_key_line |
|---|---|---|---|---|---|---|---|---|---|
| dlg_001 | hero | "你为什么来？" | guarded | 其实想信任他 | bt_001_hook | S01_A | 低声，不看他 | false | true |
| dlg_002 | partner | "因为你需要我。" | earnest | 隐藏自己的伤口 | bt_001_hook | S01_B | 平稳，直视 | true | true |
| dlg_003 | hero | "我不需要任何人。" | defensive | 恐惧被抛弃 | bt_002_approach | S01_C | 快速，偏头 | false | true |
| dlg_004 | partner | "那我等你改变主意。" | calm | 已经看穿她 | bt_003_rising | S01_D | 微笑，后退一步 | false | false |
| dlg_005 | hero | "……谢谢。" | vulnerable | 第一次接受帮助 | bt_005_climax | S02_C | 极轻，几不可闻 | true | true |

## 设计原则

1. **line_id 唯一**：每条对白一个 id，用于 shot.dialogueLineIds 锚定
2. **emotion ≠ subtext**：表面情绪 vs 内在潜台词
3. **delivery_note**：给演员（或 TTS）的表演指示——语速/语调/重音
4. **is_key_line**：关键台词必须被 TTS/表演精准还原
5. **lipsync_anchor**：标记需要口型同步的关键镜头
