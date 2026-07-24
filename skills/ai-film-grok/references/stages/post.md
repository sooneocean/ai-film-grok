# Post 阶段卡

- `stage_plate` 只做 clips、VO、BGM；HyperFrames/Remotion 负责 designed post。
- 字幕必须真正进入交付 MP4 像素；外挂 SRT 或抽帧存在不等于可读。
- HyperFrames 未烧字时显式进入 `stage_caption` recovery，禁止清空 `final.srt` 过关。
- title、subtitle 与 end card 只允许一个 owning post engine，避免双烧。
- `final` 技术成功不等于 `final_complete`；仍需 post audit、caption attestation 与完整观看。

深入资料：[post-compose.md](../post-compose.md) · [postproduction.md](../postproduction.md)
