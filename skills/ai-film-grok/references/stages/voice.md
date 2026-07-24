# Voice 阶段卡

- 角色对白默认日文 Edge，中文字幕；说书旁白默认中文 Edge。
- `nar` 是字幕/中文语义，`nar_ja` 是角色日文口语，不得互相覆盖。
- 色气或亲密段落 BGM 默认 rnb；dark 只用于恐怖，曲库缺失才走程序生成。
- dialogue、SFX、BGM 与 mixed 各自保留来源、hash 和 mix evidence。
- 外部 TTS、克隆声线与 lipsync 不静默启用，也不把普通 I2V 口部运动宣称为真实口型同步。

深入资料：[voices.md](../voices.md) · [audio-recipe.md](../audio-recipe.md)
