# Deliver 阶段卡

- 每个批准镜头须有当前 SHA-256 绑定的 review receipt。
- 最终 MP4、字幕、混音、时间线与 screening evidence 必须互相绑定且未 stale。
- 十一维 review-final 全部通过、重拍单关闭、字幕像素可读后，才允许 `final_complete`。
- 自动评分只作 advisory；完整观看、人类批准和盲审不能由模型代替。
- export 后回读文件、hash、ffprobe 与交付 sidecar；“生成过”不等于“交付完成”。

深入资料：[quality-closure.md](../quality-closure.md) · [hard-defaults.md](../hard-defaults.md)
