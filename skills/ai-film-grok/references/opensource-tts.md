# 开源 TTS 与一角一声

开源 TTS 的优势是可以用一条固定参考音锁定说话人；代价是模型与权重安装、算力、license 审查和更长的推理时间。不要把“权重可下载”等同于“可商用”。

**中文成片默认仍是 `edge`。** 本节是质量/克隆升级档。

## 声网 2026-05 横评对照（技能滤网）

来源：[2026年5月开源语音合成模型TTS推荐与测评](https://www.shengwang.cn/blog/blogdetail/2026-TTS-evaluation/)。MOS 为文中数字；**上线前必须本机 `tts-ab` 实听**。

| 模型 | 文中亮点 | 协议 | 是否进本技能主路径 | 接入 |
|---|---|---|---|---|
| **CosyVoice 2** | 中文自然度最高（~4.7）；指令语气；3s 零样本 | Apache 2.0 | **P0 推荐** | `external` + `cosyvoice_tts.py` |
| **Higgs Audio V2** | 情感最强（~4.7）；多角色；零样本 | 开源（接入前再核全文） | **P1 情感档** | 待 adapter / 或 Voicebox 内引擎若可用 |
| **Kokoro-82M** | 极轻、CPU 可跑；中文 ~3.9 | Apache 2.0 | **P2 离线后备** | 可选 external；**不**抢 edge 默认 |
| VibeVoice-1.5B | 单次 90 分钟长音频 | MIT | **不优先** | 分镜短 `nar` 用不上长音频优势 |
| Fish Speech **自托管** | 克隆快 | **CC BY-NC-SA 不可商用** | **商用勿默认** | 个人实验可；公开片用 **Fish API**（`tts_backend: fish`） |
| F5-TTS | 部署极简 | MIT | 低优先 | CosyVoice 装不动时的 external 备选 |

### 场景 → 后端（与 [voices.md](voices.md) 一致）

| 场景 | 后端 |
|---|---|
| 日常中文说书量产 | `edge` |
| 本机克隆、不装重模型 | `voicebox` |
| 中文最高自然度本地 | CosyVoice 2 → `external` |
| 高情感镜/色气语气 | Higgs 候选或 `minimax` |
| 无网/CPU-only 兜底 | Kokoro 或 edge 空流重试 |
| 在线克隆 | `fish` + 固定 `FISH_VOICE_ID` |

## 候选方向（工程成本）

| 方向 | 一角一声 | 本地成本 | 使用前检查 |
|---|---|---|---|
| **Voicebox**（推荐接入） | 固定 App profile（克隆/preset） | 中（App + 模型缓存） | 本机 :17493 健康、profile 已建；见 [voices.md](voices.md) §Voicebox |
| **CosyVoice 2**（P0） | 固定 ref audio / speaker | 中等到高（或远程 HTTP） | API 健康、`COSYVOICE_REF_WAV` hash、Apache |
| Higgs Audio V2（P1） | 固定 ref | 高 | license 全文、情感 AB、8GB+ |
| Kokoro-82M（P2） | 固定 speaker preset | 低 | 中文听感是否可接受 |
| IndexTTS / GPT-SoVITS | 固定 speaker/ref | 高 | GPU/MPS、权重 license |
| Fish Speech 自托管 | 固定 speaker/ref | 高 | **NC 条款**；商用改走 Fish API |
| MeloTTS 系 | 固定 speaker ID | 较低 | 中文声线与韵律实听 |

### Voicebox 一键路径（优先于自建 CosyVoice）

[jamiepine/voicebox](https://github.com/jamiepine/voicebox) 已做成 **一等 `tts_backend: voicebox`**，不必再绕 `AIFILM_TTS_ARGV`：

```bash
# 1) 启动 Voicebox App → 建 profile「kei-story」
# 2) config.env
AIFILM_TTS_BACKEND=voicebox
VOICEBOX_PROFILE=kei-story
VOICEBOX_LANGUAGE=zh

# 3) 体检
python3 "$HOME/.grok/skills/ai-film-grok/scripts/adapters/voicebox_tts.py" doctor
"$AIFILM" doctor   # tts probe 含 voicebox_ok

# 4) 成片
"$AIFILM" final --root "<root>" --tts-backend voicebox --music-mood rnb
```

**语音兜底**：主路径仍用 edge 时，可开 `AIFILM_TTS_VOICEBOX_FALLBACK=1`，edge 失败再试本机 Voicebox（需 profile 就绪）。

### CosyVoice 2 生产路径（HTTP 适配器）

适配器：`scripts/adapters/cosyvoice_tts.py`。技能**不内嵌权重**；你自备 CosyVoice 服务。

```bash
# 1) 启动 CosyVoice / CosyVoice2 HTTP（示例）
#    git clone https://github.com/FunAudioLLM/CosyVoice.git  # 固定 commit
#    … 按上游文档装依赖与权重 …
#    python api.py --port 9880

# 2) skill config.env
AIFILM_TTS_BACKEND=external
COSYVOICE_BASE_URL=http://127.0.0.1:9880
COSYVOICE_REF_WAV=/abs/path/storyteller-ref.wav
# 社区 API 形态不同时：
# COSYVOICE_ENDPOINT=/tts
# COSYVOICE_PAYLOAD_STYLE=shengwang   # 或 funaudio | openaiish
AIFILM_TTS_ARGV=["python3","$HOME/.grok/skills/ai-film-grok/scripts/adapters/cosyvoice_tts.py","--text-file","{text_file}","--out","{out}","--voice","{voice}"]

# 3) 体检 + 与 edge 对照
python3 "$HOME/.grok/skills/ai-film-grok/scripts/adapters/cosyvoice_tts.py" doctor
python3 "$HOME/.grok/skills/ai-film-grok/scripts/adapters/cosyvoice_tts.py" \
  --text "话说那天夜里，她推开门……" --out /tmp/cv-test.wav
"$AIFILM" tts-ab --root "<film>" --shot shot01 --backends edge,external

# 4) 成片（显式 external；勿 auto 混 Neural 名）
"$AIFILM" final --root "<root>" --tts-backend external --music-mood rnb
```

**一角一声**：整片同一 `COSYVOICE_REF_WAV`（记 hash）；`vo_voice` 用逻辑 speaker 名，**禁止** `zh-CN-…Neural`。  
**Mac**：无独显时 CosyVoice 可放远端 GPU，只改 `COSYVOICE_BASE_URL`；本机克隆优先 Voicebox。  
**VO 节奏**：开源语速常与 edge 不同 → 必须 `tts-rehearse` measured duration，勿只靠字数估。

具体版本、license 和平台支持会变，安装前要查当前上游文档，不从本文猜。

## 最小可信接入

1. 将 TTS repo 固定到明确 commit，确认工作树 clean。
2. 记录权重下载来源、hash 和 license。
3. 准备 15–30 秒干净、无 BGM、有授权的参考音；同一角色永远使用同一文件 hash。
4. 用独立适配器将上游 CLI/HTTP 收敛为 text file + output path + voice/ref。
5. 先离线生成短试音，实听断句、发音、声线一致性和速度，再用于正片。

## 结构化适配器

优先使用 `scripts/adapters/cosyvoice_tts.py`。设置 JSON argv：

```bash
export AIFILM_TTS_BACKEND=external
export AIFILM_TTS_ARGV='["python3","'"$HOME"'/.grok/skills/ai-film-grok/scripts/adapters/cosyvoice_tts.py","--text-file","{text_file}","--out","{out}","--voice","{voice}"]'
```

`AIFILM_TTS_CMD` 已禁用。argv 不通过 shell；未知占位会被拒绝；子进程不继承 API key、token、SSH agent 或 proxy。适配器需从自己的受控配置读必要凭证。

film-spec：

```json
{
  "tts_backend": "external",
  "vo_voice": "heroine-ref-v1",
  "tts_allow_network_fallback": false
}
```

## 在线 Fish 的严格模式

```bash
export FISH_VOICE_ID="<fixed-voice-or-clone-id>"
export AIFILM_TTS_STRICT_VOICE=1
```

没有 `FISH_VOICE_ID` 时，严格模式拒绝显式 Fish 请求，auto 也不会选 Fish。需要 Edge 时就在 film-spec 明确设 `tts_backend: edge`；不做隐式跨 provider 切换。

**Fish Speech 开源权重**：CC BY-NC-SA，**不可商用**；与 Fish **在线 API** 分开对待。

## 常见失败

| 原因 | 表现 | 处理 |
|---|---|---|
| 没有固定 voice/ref | 每镜像不同人 | 锁定 ID 或 ref hash，重生所有镜头 |
| 参考音带 BGM/混响 | 音色漂、噱声 | 重录干净样本 |
| 中途替换 ref | 角色突然变声 | 将 ref hash 纳入项目记录 |
| 断句/多音字未测 | 意义错或节奏怪 | 先做中文试音清单，再批量生成 |
| 上游更新后直接跑 | 环境漂移/执行风险 | 固定 commit 并重做代码/权重审查 |
| CosyVoice 服务未起 | external 失败 | `cosyvoice_tts.py doctor`；或改回 edge |
| 语速与 edge 差很多 | VO 超时 / 空镜 | `tts-rehearse` 后改 `nar` 或镜长 |
