# Memory · 2026-08-05 · 对白原音 = Grok Video + 5090 H3

## 用户原话
> 帮我优化一下这个流程 有语音的部分以grok video and 5090 h3 去生成 原先的对嘴工具 都先不要用 因为效果都太差了 我们直接用原音来优化

## 三句话
1. **有声镜**只生成在 **Grok Imagine Video**（安全）或 **5090 H3**（restricted / `h3_primary`），混音 **`prefer_native`**。
2. **冻结** LatentSync / MuseTalk / InfiniteTalk / FRW lipsync 等后期对嘴；`final --lipsync off`。
3. Edge TTS 退居字幕时钟；`dialogue_competition` policy → `native_audio_grok_h3_v1`。

## 检查清单
- [ ] 对白路由：`cloud_dialogue_grok` / `local_dialogue_h3`（非 LTX）
- [ ] H3 register → `use_clip_audio`；Grok clip 有声则 prefer_native
- [ ] 不跑 lipsync node / `final --lipsync auto`
- [ ] prompt 注入中文 `spoken_text` + 口型可见
- [ ] pytest：`test_dialogue_competition` + `test_production_router` 讲话镜段

## 链
- hard-defaults「对白原音 IRON」· dialogue-first · lipsync.md · weapon-lane-matrix · SKILL P0#2/#17
