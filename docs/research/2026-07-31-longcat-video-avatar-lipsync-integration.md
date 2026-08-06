# LongCat-Video-Avatar 1.5：短对白 lip-sync 接线研究

> 状态：研究完成，未安装模型、未改动节点、未排队 GPU。
> 目标：把 LongCat 的“音频驱动整段表演”能力接入 ai-film-grok，同时保留短版后制 lip-sync 的像素保真承诺。

## 结论

LongCat-Video 的基础 T2V/I2V/Continuation 不应直接接到 lip-sync 服务；真正相关的是 **LongCat-Video-Avatar 1.5**。它输入最终语音、提示词和（可选）状态图，直接生成带嘴型、表情、头部与身体运动的新影片。它并不是 LatentSync 的替换品：

| 线路 | 正确用途 | 画面承诺 | 目前状态 |
| --- | --- | --- | --- |
| `latentsync` | 短台词、近景、已有合格动态片的后制对嘴 | 尽量保留原片，只调整口部 | 已批准、当前唯一 production-ready backend |
| `longcat-avatar-1.5` | 短对白“整段表演”、I2I 状态图直接生成讲话镜 | 整张画面会重生，可能带来身份/衣物/背景漂移 | 新增 pilot candidate，绝不加入 `final --lipsync auto` |
| `infinitetalk` | 现有整段表演候选 | 整张画面会重生 | 已是 explicit pilot；LongCat 应与它并列竞争，不能静默取代 |

因此要“赶快打通”的 P0，不是把 LongCat 塞进 `lipsync_backend.py` 的 post-process 优先级；而是新增一个 **`longcat-avatar` 受收据约束的 avatar worker**，接在 dialogue competition 的 `face_animation_to_audio` lane。短版继续优先 LatentSync，必要时才用 Avatar 生成候选。

## 官方技术中值得借镜的部分

1. **端到端音频条件，而非只修嘴。** Avatar 1.5 在每个 DiT block 加音频 cross-attention，驱动口型、表情、头势和身体运动；其输入既支持 audio+text，也支持 audio+text+image，以及续写。我们应把它用于“说话表演镜”，而非对任何成片补嘴。[技术报告](https://arxiv.org/html/2605.26486#S3)
2. **Whisper-large-v3 语音表征。** 官方以 Whisper-large 取代 Wav2Vec2，并为超过 30 秒音频使用滑动窗；25 fps 时把 50 Hz 特征重采样为逐帧条件。我们的 adapter 必须只接收已经锁定 SHA-256 的最终 TTS，不允许生成后更换音轨。[技术报告](https://arxiv.org/html/2605.26486#S3.SS2)
3. **续写的重叠条件。** 单人 demo 以 93 帧片段、13 帧条件帧续写，保存前段 latent/参考 latent，接续时仅追加非重叠帧。这值得借镜为 `segment_plan` 及 overlap QA；短版 P0 限制为单段，不先承诺长片。 [官方 demo](https://github.com/meituan-longcat/LongCat-Video/blob/main/run_demo_avatar_single_audio_to_video.py)
4. **多说话者必须有归属与静音轨。** 官方多音频路线可传两条声轨、人物 bbox，并为背景人物加入 silent condition，防止配角被主角语音带动。我们已经有 `line_id`、speaker、listener；应补 `speaker_regions`、`background_regions` 与 `silent_background_track`，不接受“两个脸但没有 bbox”的请求。 [技术报告](https://arxiv.org/html/2605.26486#S3.SS5)
5. **评审标准可直接复用。** Rationality（物理合理）、Harmony（音画一致）、Stability（时间稳定）、Consistency（身份一致）四维；口型要以 0.5x 观看。它正好扩充我们现有逐镜人工 review，不应只看 ffprobe 成功。 [技术报告](https://arxiv.org/html/2605.26486#S5)

## 与现有服务的差距与可直接复用处

现有 `lipsync_node_service.py` 已有认证、单 GPU lock、队列、输入/输出 SHA-256、FFmpeg/ffprobe 验证、backend fingerprint 和人工批准闸门；这些无需重造。它当前仅允许 `latentsync` / `musetalk`，而 `lipsync_backend.py` 也正确地把此类“保真后处理”优先级限定为 LatentSync→MuseTalk。

LongCat 的 adapter 需要新 lane，原因是它的接口是：

```text
approved state image + final dialogue audio + performance prompt
  -> LongCat Avatar inference (ai2v, single/multi, optional continuation)
  -> generated MP4 + original final dialogue audio
  -> full decode + provenance receipt + 0.5x human review
  -> explicit candidate promotion only
```

绝不能宣称输出为原 I2V 的“lip-sync 修正”。候选失败（脸漂、衣物背景漂、质量不佳）也不能自动退回其他 provider；只有分类为技术失败才能按已批准的显式规则切换。

## 最短 P0 接线规格

### 1. 独立 worker 与启动门槛

在 RTX 5090 另建 `longcat-avatar-node`，沿用现有 loopback + SSH tunnel + Bearer token 模式，但 **不要** 与 `:8790` 的 post-lipsync node 混成一个 backend。启动前必须真实验证：

- 5090 identity、无未知 job、queue idle；至少 24 GiB free VRAM、12 GiB free RAM、足够权重磁盘空间。
- `hf auth whoami` 与一次实际 Avatar 权重文件读取；下载完成/文件存在不算授权或可运行。
- 官方要求 Python 3.10、PyTorch 2.6 CUDA 12.4、FlashAttention 2；这和本仓 Python 3.11 及现有节点 PyTorch 2.7.1 CUDA 12.8 不同，必须隔离环境，不能污染现行 LatentSync node。[官方 README](https://github.com/meituan-longcat/LongCat-Video#quick-start)
- 先用 `avatar-v1.5 --use_distill --use_int8` 的 480p、single-audio、single-segment canary；官方的 1.5 蒸馏模式为 8 steps，INT8 仅 1.5 支持。

### 2. 请求合约（新增 `avatar`，不是 `lipsync`）

```json
{
  "kind": "aifilm-avatar-render-request/v1",
  "route": "longcat-avatar-1.5",
  "mode": "single_ai2v",
  "line_id": "sc01-sh03-ln01",
  "state_image_sha256": "...",
  "dialogue_audio_sha256": "...",
  "dialogue_language": "ja",
  "prompt": "physical performance and scene context only",
  "performance_hash": "...",
  "resolution": "480p",
  "segments": 1,
  "speaker_regions": [{"speaker": "character_a", "bbox": [0, 0, 0, 0]}],
  "production_promotion": "forbidden_pending_human_review"
}
```

请求必须拒绝：无最终音频 hash、无 approved state image、超过短版时长上限、多人无 bbox、音频与字幕/`line_id` 不一致、或请求使用未经批准的 model/repo fingerprint。

### 3. 输出收据与晋升

回执在现有字段上增加：`route=avatar_generation`、LongCat git commit、全部 checkpoint/LoRA/Whisper SHA-256、Torch/CUDA/FlashAttention、输入/输出 hash、seed、resolution、steps、CFG、`ref_img_index`、`mask_frame_range`、segment overlap、峰值 VRAM、wall time 和完整 ffprobe/decode 结果。

评审必须逐句检查：

1. 0.5x 口型与日文最终音频一致；
2. 是否只让目标 speaker 开口，listener/background 是否保持合理静止；
3. 身份、发型、衣服、道具、色调和人物关系是否保持状态图约束；
4. 肢体、手与背景是否有形变、跳帧、闪烁；
5. 输出可完整 decode，字幕 cue 与同一 `line_id` 对齐。

只有人工 `approved` 的单镜候选才可登记为 `longcat_avatar` clip；不能让 `final --lipsync auto` 自动调用或自动晋升。

## 执行顺序

1. **P0-a（先恢复容量）**：不碰现有未知 GPU 工作；等 5090 达到 24 GiB free VRAM / 12 GiB RAM 后再允许 canary。
2. **P0-b（环境可复现）**：在隔离目录建立 LongCat Avatar 1.5 环境与权重清单，输出只读 `doctor` / fingerprint，不改现有 production route。
3. **P0-c（单镜 canary）**：同一张已批准状态图、同一条日文最终 TTS，同时跑 LatentSync baseline、InfiniteTalk（若可用）与 LongCat Avatar；每路各一次，不重试未知失败。
4. **P0-d（评分与选择）**：按四维人工评分、0.5x 嘴型、完整 decode 与 lineage receipt，选出各自适用范围。只在 LongCat 通过三类近景（正脸、微侧、带动作）后把它登记为 explicit pilot。
5. **P1（两人对话）**：仅在单人已通过后接多音轨+bbox+background silent condition；禁止先上双人全身复杂镜。
6. **P2（续写）**：在连续三段稳定后才开放 `num_segments > 1`，逐段做 overlap/identity/色调 QA。

## 今天的实际 readiness

`aifilm doctor` 的 GPU 遥测会随现有工作即时变化，不能写成稳定容量。最后一次 read-only 检查时，lip-sync node 是 `running=0, queued=0`、LatentSync `ready=true, approved=true`，并回报 **30898 MiB / 32607 MiB** free VRAM；这次读数满足 LongCat canary 的显存闸门，但执行前仍须再查一次 identity、queue、VRAM/RAM、disk、权重授权与 fingerprint。

不过此刻 `doctor` 整体为 `strict_status=blocked`：`runtime_lock` 指向既有的 `aifilm_grok.py`、`shortform_director.py`、`shortform_motion.py` 漂移。这是本研究以外的工作树状态，我没有修改或绕过它；在 lock 恢复且复查容量之前，不得启动 LongCat canary。音频节点的显存读数也不能替代 lip-sync node 的容量证据。

## 明确不做

- 不把 LongCat 写进 `BACKEND_PRIORITY`，不伪装为保真 lip-sync。
- 不用 `final --lipsync auto` 静默重生整张镜头。
- 不在当前显存不足时下载、安装或启动模型；不取消/重启任何未知 GPU job。
- 不将模型下载完成、HTTP health 成功或单次 API 返回，当作 production approval。

## 2026-07-31 实作准备回执

已在私有 Windows RTX 5090 建立隔离目录 `C:\AI_Models\LongCat-Video`，不触碰既有
LatentSync node 环境：

- LongCat 源码 commit：`6b3f4b8582a8bc3f20f795735f5383716c4ba794`。
- `uv` 建立 Python 3.10.19 venv；Hugging Face 已认证并实际下载 Avatar 1.5 的
  `config.json` 探针。
- RTX 5090 已验证 `torch 2.7.1+cu128`、CUDA 12.8、`torch.cuda.is_available()=True`。
- 官方源码含 `enable_xformers` 分支，已安装 `xformers 0.0.30`；不用在 Windows
  编译 FlashAttention 2。
- 上游 pip 清单中的 `libsndfile1==0.0.1` 与 `tritonserverclient==0.0.6` 在该平台
  不可解析，且源码无运行时引用；隔离环境排除两项。官方清单会把 CUDA torch 覆盖成
  `2.6.0+cpu`，故已在其余依赖完成后重新锁回 CUDA torch。

**尚未开始 74.9 GB 权重下载或任何推理。** 原因不是权限、磁盘、RAM 或 HF 授权，而是
GPU 空显存持续在 15.8–23.1 GiB 间波动，尚未通过 24 GiB 启动闸门。下一次同时满足
`queue idle + free VRAM >= 24576 MiB + free RAM >= 12288 MiB` 时，先做 xFormers 小型
CUDA kernel canary；仅成功后下载完整权重并跑单人、480p、单段、8-step INT8 canary。
