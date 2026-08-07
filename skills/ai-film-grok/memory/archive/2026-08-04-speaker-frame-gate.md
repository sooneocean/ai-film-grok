# Memory · 2026-08-04 · Speaker-frame 门禁

## 用户原话
> 做完（speaker-frame 整包 / Fill-Idle 调度 / 跨集胜率）

## 三句话
1. **on_camera 台词镜**：speaker = 画面主体（dsl.subject/cast）= audio_cues.speaker。
2. **热窗同 beat** 相邻 on_camera 禁 speaker 翻转（dialogue_window_strict）。
3. preflight soft；max dialogue_drama 或 `speaker_frame_strict` → hard。

## 检查清单
- [x] `dialogue_speaker_frame_gate.py` + preflight
- [x] tests
- [x] hard-defaults 行

## 链
- huangdao §H · hard-defaults · preflight
