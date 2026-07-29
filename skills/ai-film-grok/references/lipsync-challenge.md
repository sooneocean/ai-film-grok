# 开源唇同步挑战赛

挑战赛是独立的证据控制面，不执行模型、下载权重或修改 RTX 节点。生产默认仍是
LatentSync 1.6；任何报告都只能把方案标成 `production_candidate`，不能自动改
`final --lipsync auto`。

## 固定赛道

- 原视频保留评测：LatentSync 1.6、MuseTalk 1.5、LTX-2.3 LipDub。
- 整帧表演生成：EchoMimicV3 Flash、LongCat-Video-Avatar 1.5。

“原视频保留”是评测目标，不是像素不变声明。所有后端都必须用
`outside_mouth_similarity` 与原尺寸人工观看证明嘴部以外没有外溢。
EchoMimicV3 与 LongCat 永远登记为 `face_animation_to_audio`，只允许 pilot，
不能进入 `final --lipsync auto`。

## 创建无执行计划

四个输入均须为 3–5 秒，使用同一条已批准的日文角色对白。批准收据必须逐一绑定
输入与音频 SHA-256。

```bash
aifilm lipsync-challenge create \
  --root "<challenge-root>" \
  --front-closeup "<front.mp4>" \
  --three-quarter "<three-quarter.mp4>" \
  --occlusion-motion "<occlusion-motion.mp4>" \
  --anime "<anime.mp4>" \
  --japanese-audio "<dialogue-ja.wav>" \
  --approval-receipt "<approval.json>"
```

输出 `challenge.json` 固定 `auto_execute=false` 与
`gpu_work_authorized=false`，包含 4 × 5 共 20 个待外部执行单元。

## 导入外部结果

```bash
aifilm lipsync-challenge register-result \
  --root "<challenge-root>" \
  --fixture-id front_closeup \
  --backend-id ltx-2.3-lipdub \
  --output "<output.mp4>" \
  --metrics-receipt "<metrics.json>" \
  --runtime-receipt "<runtime.json>"
```

指标收据必须绑定 backend、输入视频、日文音频与输出哈希，并提供评估器名称、
版本和模型 SHA-256。必填指标：

- 口型分数、偏移帧数、置信度；
- 身份相似度、嘴部时间稳定度；
- 嘴部以外相似度、牙齿/嘴唇颜色稳定度。

运行收据必须记录 executor、GPU 型号/数量、峰值显存、耗时与完成状态。
导入时会重新哈希输出、完整解码，并核对原始几何、FPS 与时长。

## 盲测与报告

```bash
aifilm lipsync-challenge blind-package --root "<challenge-root>"
aifilm lipsync-challenge review \
  --root "<challenge-root>" \
  --reviewer "<name>" \
  --review-json "<completed-review.json>"
aifilm lipsync-challenge report --root "<challenge-root>"
```

公开盲测模板只出现随机候选标签；后端映射单独保存在 private mapping。审片人必须
确认以原尺寸完整观看。人物拉伸、强压方形、遮挡物被脸覆盖、牙齿/嘴色漂移、
嘴部外溢、身份失败或解码失败均是硬失败。

晋级至少需要 4 类中的 3 类盲测获胜、4 个通过的结果，且零硬失败。LTX 另外需要
许可证审查收据和四类 5090 单卡证据。MuseTalk 只能成为候选，不能自动改默认。
即使报告出现 `route_change_submission_ready=true`，
`default_route_change_authorized` 仍固定为 `false`。
