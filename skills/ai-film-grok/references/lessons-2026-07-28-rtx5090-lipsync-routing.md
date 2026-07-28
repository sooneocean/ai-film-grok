# Lessons · RTX 5090 剧情对白口型路由

> 2026-07-28 · **P0 / Voice→Post**
> 状态：**PARTIAL：LatentSync 1.6 已通过 RTX 5090 技术 canary；尚未通过生产晋升矩阵与人工完整观看批准**。
> 目标：让 Grok/I2V 已有剧情镜头中的角色按最终对白开口，同时尽量保留原表演、身份、背景与摄影运动。

## 一句话

**Wav2Lip 可移植到 RTX 5090，但只当应急基线；后期保原镜头优先验证 LatentSync 1.6，其次 MuseTalk 1.5。**
若需要嘴、表情、头部与身体一起重演，先以 EchoMimicV3-Flash 做低成本 canary，再评估 Wan2.2-S2V / OmniAvatar / FantasyTalking / LTX LipDub / InfiniteTalk / LongCat Avatar；不把“重新生成表演”冒充“只修嘴”。

## 证据边界

- RTX 5090 是 Blackwell 32GB；PyTorch 2.7 才正式提供 Blackwell + CUDA 12.8 预编译支持。
- 上游旧环境不能原样照装：
  - Wav2Lip：`torch==1.1.0`，开源推理脸区为 96×96。
  - MuseTalk 1.5：文档固定 PyTorch 2.0.1 / CUDA 11.8，脸区 256×256。
  - LatentSync 1.6：文档固定 PyTorch 2.5.1 / CUDA 12.1；推理最低显存 18GB，模型以 512×512 训练。
- 因此“5090 显存够”不等于“上游环境直接可用”。5090 节点必须用隔离的 Python 环境、PyTorch 2.7+、CUDA 12.8，并重新验证 face detector、ONNX Runtime、xformers/attention 与 FFmpeg。
- 2026-07-28 已在私有 RTX 5090 节点真实运行 LatentSync 1.6（repo `a229c3948406bc2cf6eaf4873e662e70c6a04746`，PyTorch `2.7.1+cu128`）：
  - 当前剧情 I2V 镜头 + 最终日语 TTS：输出 MP4 可解码，但原片是全身运动镜、脸太小，只能证明管线能跑，不能评价口型质量。
  - 单人近景受控样本 + 同一条最终日语 TTS：输出 720×1280、25 fps、1.84 秒，嘴形有可见变化，脸外区域目视保持稳定。
  - 受控样本 wall time 110 秒，峰值显存 **31,813 MiB / 32,607 MiB**；仅余约 794 MiB，属于能跑但余量危险，不能与 ComfyUI 或其他 GPU 工作并发。
- 上述仍不是生产通过：尚缺微侧脸、遮挡、真实近景运动保留、自动同步辅助指标，以及使用者对完整视频的逐帧/逐句批准。
- EchoMimicV3-Flash 官方权重已完整准备，但当前节点未进入推理：
  - WSL 只有 15 GiB RAM + 8 GiB swap；最新版依赖令上游低内存 loader 失效，Python 在约 15.5 GiB RSS 被 OOM killer 杀死。
  - 固定 Diffusers 0.33.1 / Transformers 4.48.3 后虽恢复旧 loader 符号，却出现 meta 参数复制 no-op 警告；进程随后退出，远端 output directory 快照为空。
  - 因此“官方写 12GB VRAM”不能推出“这台 5090 节点可用”；主机 RAM、loader 与权重真正落入参数同样是硬门槛。

## 方案分层

### A. 已有镜头，后期尽量只改嘴

| 顺序 | 方案 | 用途 | 已知限制 |
|---|---|---|---|
| 1 | **LatentSync 1.6** | 重要近景、清晰度优先 | 18GB VRAM；扩散推理较慢；5090 CUDA 12.8 兼容须实测 |
| 2 | **MuseTalk 1.5** | 快速 canary、批量对白 fallback | 256×256 脸区；官方列出胡须/唇形/唇色损失与单帧抖动 |
| 3 | **Wav2Lip** | 最小基线、紧急抢救 | 96×96；老依赖；开源权重仅研究/学术/个人用途，禁当商业默认 |
| 4 | **Sync 云端** | 本地全失败后的英雄镜头 | 付费、外传素材、隐私与成本；调用前须用户批准 |

### B. 需要重新生成整段表演

| 方案 | 能力 | 5090 / 使用边界 |
|---|---|---|
| **EchoMimicV3-Flash** | 图+音频+prompt；嘴、表情与身体；中文音频；最长片段可续接 | 官方写 12GB、8-step、最高 768×768、Apache 2.0；当前最适合先做 5090 低成本整段表演 canary |
| **Wan2.2-S2V-14B** | 图+音频+prompt，可选 pose video；480p/720p；时长跟随音频 | 官方单 GPU 命令要求至少 80GB，5090 不能照搬；只有独立 ComfyUI/量化路径 canary 通过后才可晋升 |
| **OmniAvatar 1.3B / 14B** | 图+音频+prompt，带自适应身体动作；480p | 官方 A800 表显示 14B 全 offload 可降至 8GB、约 22.1s/step；上游固定 Torch 2.4/cu124，Apache 2.0；先卡 5090 兼容与实片质量 |
| **FantasyTalking** | Wan2.1 I2V + 音频条件；手势/表情可由 prompt 控制 | A100 官方表：512²×81 帧，full offload 5GB、约 42.6s/step；Apache 2.0；适合画质对照，不适合快速批量 |
| **FantasyTalking2** | 以偏好优化改善自然度、口型和画质 | 当前官方仓库只有论文说明，未见推理代码、权重或 license；列观察名单，不能进 canary |
| **LTX-2.3 LipDub** | 视频+音频联合控制；参考分辨率等于输出分辨率 | 22B；会重新扩散画面；社区许可证与显存/速度须单独审查 |
| **InfiniteTalk** | V2V/I2V；嘴、表情、头、身体联动；多人 | 摄影运动只模仿、不保证完全保留；长段可能色漂 |
| **LongCat Avatar 1.5** | Whisper-Large、多音频、480p/720p、INT8、8-step | 官方 Avatar 范例以双 GPU 为主；单张 5090 仍需实片验证 |
| **Runway Act-Two** | 用真人 driving performance 转移口型、表情与动作 | 需要表演驱动视频；多人要逐角色裁切/合成；属于重演而非补嘴 |

### C. 方案选择，不按一个排行榜硬排

```text
已有 Grok/I2V 镜头已经满意，只缺嘴
  → LatentSync → MuseTalk → Wav2Lip

对白镜还没生成，希望角色整个人按声音演
  → EchoMimicV3-Flash 低成本 canary
  → 重要镜再比较 Wan2.2-S2V / FantasyTalking / OmniAvatar

已有镜头但愿意接受重扩散，以换表情和身体联动
  → LTX LipDub / InfiniteTalk / LongCat

需要真人表演控制
  → Runway Act-Two；逐角色处理再合成
```

LivePortrait、AniPortrait 主要吃 driving video / landmark，不是“最终音频直接对嘴”的完整后端；可作动作转移组件，但不进入本轮音频口型主梯队。SadTalker 与 EchoMimicV2 可保留为低端 talking-head 备援，剧情近景优先级低于 EchoMimicV3。

## 当前 plugin 真相

1. `lipsync_backend.py` 现有可执行 registry 只有 `musetalk → wav2lip → external`；**没有 LatentSync provider**。
2. 当前 `AIFILM_LIPSYNC_BACKEND=off`，capability probe 的 `ready=[]`。
3. 本机已有 Wav2Lip repo 与权重，但 repo 有未提交兼容补丁且尚未 backend lock；不能称为 production ready。
4. Grok OAuth 的 I2V 是静音视频，`native_lipsync=false`；后贴 VO 不能冒充原生音画同步。
5. FRW 口型有独立 `frw-lipsync` 接口，但历史 403/502 不是当前 live 证据；每次使用前都要 probe。
6. `should_lipsync_shot()` 对未写 `lipsync` 的镜头仍会按景别/标题启发式推断；`render_final.py` 也只有 `--lipsync require` 才在逐镜失败时中止。稳定政策要求显式标记，但当前实现尚未完全兑现。

## 稳定路由

```text
Grok primary / 已批准 I2V clip
  → 只处理 lipsync:true 的正脸或微侧近景
  → 已通过 5090 canary 且有 fingerprint receipt 的本地后端
      target: LatentSync 1.6
      fallback: MuseTalk 1.5
      emergency baseline: Wav2Lip
  → 本地明确技术失败，且用户批准外传/成本
      cloud: Sync / FRW
  → 质量差、人工拒绝、未知错误：停，不静默切 provider
```

- 说书镜、中远景、快速转头、严重遮挡默认 `lipsync:false`。
- 双人镜必须有 speaker/face target；不能让两个人同时按同一条音频动嘴。
- 生成式重演路线必须登记为 `face_animation_to_audio` 或等价真实方法，不得标成原镜头像素保留。
- 当前 `auto` 有启发式补标行为；生产前必须审阅目标镜清单。要求“失败即停”时使用 `--lipsync require`，不能只靠显式 backend 名称。

## RTX 5090 canary

### 2026-07-28 首轮实跑回执

| 项目 | 结果 |
|---|---|
| 节点 | RTX 5090 32GB；driver 595.79 |
| LatentSync | 1.6；repo `a229c3948406bc2cf6eaf4873e662e70c6a04746`；checkpoint SHA-256 `0a478e89eb660f82da4c35dbdde8a5adfb27f99d1b4e50edd03729e1e98316d3` |
| Runtime | Python 3.10；PyTorch 2.7.1+cu128；CUDA runtime 12.8 |
| 原剧情镜头输出 | SHA-256 `1d0d09a16cfa248067169d6dea474fff05ff28a3b84ef0948231dad99d478bc6`；1.84 秒；25 fps；峰值 29,493 MiB |
| 受控近景输出 | SHA-256 `995a0bd32b67ea441533856bb195d3ccba76624595f76676544007f6ad82802f`；1.84 秒；25 fps；wall 110 秒；峰值 31,813 MiB |
| 技术结论 | 两份 MP4 均通过 `ffmpeg -f null -` 完整解码；输入/输出 hash 与 GPU 采样已落回执 |
| 质量结论 | 原剧情镜脸太小；受控近景可见嘴形变化，但不是原运动镜头。状态保持 PARTIAL |
| EchoMimicV3-Flash | repo `7e89489ca51c0d008fc1963ec6c03fc5bd0b9397`；官方权重已下载；15 GiB WSL RAM 下装载失败，未取得输出 MP4，禁用 |

首轮还暴露了三条生产风险：

1. EP3 的 review contact 与当前 active clip hash 已漂移；选 canary 前必须对 review source hash 与实际 clip hash 做 read-back，不能只看旧缩略图。
2. LatentSync 官方脚本依赖 `ffmpeg` 命令；隔离环境起初缺少命令而失败。已用隔离环境内 `imageio-ffmpeg` 二进制补齐，未改系统套件。
3. EchoMimicV3 requirements 只有下限、没有兼容上限；2026-07-28 解析到 Diffusers 0.39 / Transformers 5.14 会让旧 loader 路径失效。盲目降版也可能产生 meta 参数 no-op，必须以真实首帧和输出 MP4 验证，不能以 import 成功算通过。

同角色、同最终 TTS，选三段 4–8 秒镜头：

1. 正脸静稳近景。
2. 30–45° 微侧脸并转头。
3. 手、头发或另一角色短暂遮嘴。

至少输出：

```text
original
latentsync-1.6
musetalk-1.5
wav2lip
```

另开“整段表演生成”矩阵，不与后期补嘴混算：

```text
echomimic-v3-flash
fantasytalking
omniavatar-1.3b
wan2.2-s2v-14b  # 仅有可复现的 5090 低显存路径时
```

逐份记录：

- backend、repo commit、dirty state、模型/权重 SHA-256。
- Python、PyTorch、CUDA、driver、GPU、FFmpeg 版本。
- 输入/输出 SHA-256、ffprobe、帧数、FPS、时长、峰值显存、wall time。
- 自动音画同步指标只作辅助；必须逐镜完整观看嘴、牙、下巴、肤色接缝、身份漂移、遮挡恢复和句尾闭嘴。
- 后期型方案需检查脸外区域是否被无故改写；生成式重演则另验身份、服装、背景、运镜和动作连续性。

## 晋升条件

只有同时满足才可进入 `auto`：

1. 三类 canary 至少正脸与微侧脸通过。
2. 产物可解码、时长/FPS 合法、回执与输出 hash 绑定。
3. 人工完整观看批准；不能只凭任务成功或 SyncNet 分数。
4. backend lock 或远端服务 fingerprint 可验证，环境变化自动失效。
5. 明确许可可覆盖实际使用场景。

遮挡镜失败不必否决后端，但必须让该镜回原片或转生成式重演；禁止带病进入 final。

## 实作方向

- 短期：用安全的 `AIFILM_LIPSYNC_ARGV` 包装 RTX 5090 客户端，先完成 canary。
- 正式：新增独立 `lipsync_node_client.py` / 5090 video service，并在 `lipsync_backend.py` 注册 `latentsync`。
- 远端回执至少返回 model/checkpoint fingerprint、output SHA-256、ffprobe 摘要、耗时与峰值显存。
- 不复用现有 audio-node 的 WAV-only 交付协议；视频服务必须处理上传、任务轮询、MP4 下载、checksum 与 partial-file 原子发布。

## 来源

- [Wav2Lip](https://github.com/Rudrabha/Wav2Lip)
- [MuseTalk 1.5](https://github.com/TMElyralab/MuseTalk)
- [LatentSync 1.6](https://github.com/bytedance/LatentSync)
- [PyTorch 2.7 / Blackwell](https://pytorch.org/blog/pytorch-2-7/)
- [NVIDIA RTX 5090](https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5090/)
- [LTX-2.3 LipDub](https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-LipDub)
- [InfiniteTalk](https://github.com/MeiGen-AI/InfiniteTalk)
- [LongCat Video Avatar 1.5](https://github.com/meituan-longcat/LongCat-Video)
- [EchoMimicV3](https://github.com/antgroup/echomimic_v3)
- [Wan2.2-S2V](https://github.com/Wan-Video/Wan2.2#run-speech-to-video-generation)
- [OmniAvatar](https://github.com/Omni-Avatar/OmniAvatar)
- [FantasyTalking](https://github.com/Fantasy-AMAP/fantasy-talking)
- [FantasyTalking2](https://github.com/Fantasy-AMAP/fantasy-talking2)
- [Sync lipsync models](https://sync.so/docs/models)
- [Runway Act-Two multi-character dialogue](https://help.runwayml.com/hc/en-us/articles/41748090660499-Creating-Multi-Character-Dialogues-with-Act-Two)
