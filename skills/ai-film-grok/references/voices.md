# 旁白与声线一致性

“更像真人”与“每镜是同一个人”是两个指标。生产中先锁定身份，再比较自然度。

## 场景路由（2026-07-21 · 声网开源横评对照）

**默认不变：中文量产仍用 `edge`。** 开源/克隆是质量档，不是静默替换。

| 场景 | 推荐后端 | 说明 |
|---|---|---|
| 日常中文说书量产 | **`edge`** | 零依赖、可复现；Neural 已锁 |
| 本机克隆、不装重模型 | **`voicebox`** | 一等后端；固定 `VOICEBOX_PROFILE` |
| 中文最高自然度（本地） | **CosyVoice 2** → `external` | 评测中文 MOS 第一；见 [opensource-tts.md](opensource-tts.md) |
| 高情感 / 色气语气精修 | **Higgs Audio V2**（候选）或 **`minimax`** | Higgs 情感最强；先 `tts-ab` 再锁 |
| 无网 / CPU-only 轻量 | **Kokoro-82M**（可选）或 edge 空流重试 | 中文弱于 edge，只作后备 |
| 在线克隆 | **`fish`** API | 固定 `FISH_VOICE_ID`；**自托管 Fish Speech 权重 NC 不可商用** |

评测来源：[声网 2026-05 开源 TTS 横评](https://www.shengwang.cn/blog/blogdetail/2026-TTS-evaluation/)（MOS 为文中数字，上线前本机 `tts-ab` 实听）。  
详表与不推荐项：[opensource-tts.md](opensource-tts.md) §声网横评对照。

## 后端与 auto 顺序

| 后端 | 适用 | 生产要求 |
|---|---|---|
| `external` | 本地 CosyVoice 2 / Higgs / IndexTTS 等 | 结构化 argv，固定 ref/voice，代码可信 |
| `voicebox` | 本机 Voicebox 工作室（克隆/多引擎） | App 在跑 + 固定 `VOICEBOX_PROFILE` |
| `minimax` | 在线情感声线 | 固定 `MINIMAX_VOICE_ID` |
| `fish` | 在线克隆/自然旁白 | 严格模式下必须固定 `FISH_VOICE_ID` |
| `edge` | 免费、可复现旁白 | 固定 Neural voice，可明确选用 |

`auto` 顺序是 **external → voicebox（若就绪）→ MiniMax → 已固定 voice ID 的 Fish → Edge**。  
Voicebox 只有本机 API 通、且至少有一个 profile 时才参与 auto。Fish 只有 key 但没有 voice ID 时不参与 auto。

**机位 / 试听（2026-07-21）**

```bash
"$AIFILM" capability                 # TTS·runtime·工具一页
"$AIFILM" tts-ab --root "<film>" --shot shot01 --backends edge,voicebox
# CosyVoice HTTP 就绪后也可：
# "$AIFILM" tts-ab --root "<film>" --shot shot01 --backends edge,external
```

Voicebox 未开时 `tts-ab` 会 skip 该后端，不崩；不修改 film-spec。

## 失败策略

- `tts_allow_network_fallback: false` 是默认。
- 显式指定 `fish | minimax | external | voicebox` 时，后端错误必须直接暴露，不得偷换音色。
- 只有使用者已接受 provider/声线可能改变，才在 film-spec 设 `tts_allow_network_fallback: true`（auto 失败链：**voicebox → edge**）。
- **Voicebox 语音兜底（opt-in）**：`AIFILM_TTS_VOICEBOX_FALLBACK=1` 时，显式 `edge|minimax|fish|external` 失败会再试本机 Voicebox 一次（仍不静默；需 App 就绪 + profile）。
- 严格声线锁默认开：`AIFILM_TTS_STRICT_VOICE=1`。不要为了“先出声”关掉它。

## 角色映射

```json
{
  "vo_mode": "storyteller",
  "tts_backend": "edge",
  "vo_voice": "zh-CN-YunxiNeural",
  "cast_voices": {
    "storyteller": "zh-CN-YunxiNeural"
  },
  "tts_allow_network_fallback": false
}
```

`storyteller`：只有一条旁白声线。`character | hybrid`：每个 cast ID 都需要固定 voice/ref，不得让 provider 每镜随机抽样。

## 人物对白日文（P0 · 2026-07-23）

**角色开口用日文 TTS；说书旁白用中文；烧字字幕默认中文。**  
详见 [lessons-2026-07-23-character-dialogue-ja.md](lessons-2026-07-23-character-dialogue-ja.md)。

| 轨 | 默认语言 | edge 声线 |
|----|----------|-----------|
| 女主 / heroine 对白 | **ja** | `ja-JP-NanamiNeural` |
| 男主 / partner 对白 | **ja** | `ja-JP-KeitaNeural` |
| 说书 storyteller | **zh** | `zh-CN-XiaoxiaoNeural`（或 Yunxi） |
| 字幕 caption | **zh** | （不走 TTS；用 `nar`/`nar_zh`） |

```json
{
  "vo_mode": "hybrid",
  "tts_backend": "edge",
  "dialogue_spoken_lang": "ja",
  "narration_spoken_lang": "zh",
  "caption_lang": "zh",
  "vo_voice": "zh-CN-XiaoxiaoNeural",
  "cast_voices": {
    "storyteller": "zh-CN-XiaoxiaoNeural",
    "heroine": "ja-JP-NanamiNeural",
    "partner": "ja-JP-KeitaNeural"
  }
}
```

- 角色镜：`speaker` + **`nar`（中文观众字幕）** + **`nar_ja`（日文成片 TTS）**
- 用户强制中文对白：`dialogue_spoken_lang: "zh"`
- **禁止** 用 `zh-CN-*` 名塞进 ElevenLabs / CosyVoice；日文对白也不要混中文 Neural

## External TTS

`AIFILM_TTS_CMD` 已禁用。使用 JSON argv，支持 `{text}`、`{text_file}`、`{out}`、`{voice}` 完整参数占位：

```bash
export AIFILM_TTS_ARGV='["python","/trusted/tts_adapter.py","--text-file","{text_file}","--out","{out}","--voice","{voice}"]'
```

子进程不继承 API key、token、SSH agent 或 proxy；适配器需自行从它的受控配置读取必要凭证。

### CosyVoice 2（中文质量档 · external · P0）

适配器：`scripts/adapters/cosyvoice_tts.py`（HTTP → 本机/远程 CosyVoice 服务）。  
**不改默认**；仅当要「比 edge 更自然的中文」且服务已起时显式使用。

```bash
# 1) 另开终端启动 CosyVoice API（示例端口 9880；以官方/你的部署为准）
# 2) skill config.env：
AIFILM_TTS_BACKEND=external
COSYVOICE_BASE_URL=http://127.0.0.1:9880
COSYVOICE_REF_WAV=/path/to/storyteller-ref.wav   # 一角一声；10–30s 干净人声
# COSYVOICE_PAYLOAD_STYLE=shengwang   # 或 funaudio / openaiish
AIFILM_TTS_ARGV=["python3","$HOME/.grok/skills/ai-film-grok/scripts/adapters/cosyvoice_tts.py","--text-file","{text_file}","--out","{out}","--voice","{voice}"]

# 3) 体检 + 试听
python3 "$HOME/.grok/skills/ai-film-grok/scripts/adapters/cosyvoice_tts.py" doctor
python3 "$HOME/.grok/skills/ai-film-grok/scripts/adapters/cosyvoice_tts.py" \
  --text "话说那天夜里……" --out /tmp/cv-test.wav
"$AIFILM" final --root "<root>" --tts-backend external --music-mood rnb
```

film-spec：`"tts_backend": "external"`，`vo_voice` 用 speaker id / 逻辑名（**禁止** `zh-CN-…Neural`）。  
Mac 无独显时优先 Voicebox；CosyVoice 可放 GPU 机只暴露 HTTP。详见 [opensource-tts.md](opensource-tts.md)。

### Voicebox（本机开源 · 一等后端 · 语音兜底）

项目：[jamiepine/voicebox](https://github.com/jamiepine/voicebox) — 本地 AI 语音工作室，loopback REST `http://127.0.0.1:17493`。  
适配器：`scripts/adapters/voicebox_tts.py`（也可由 `tts_backend` 内联调用）。

**前置**

1. 安装并启动 Voicebox 桌面版（或 `docker compose up` / dev backend）。
2. 在 App 里建好 **固定** 旁白 profile（克隆或 preset），记下名称。
3. 试听：

```bash
python3 "$HOME/.grok/skills/ai-film-grok/scripts/adapters/voicebox_tts.py" doctor
python3 "$HOME/.grok/skills/ai-film-grok/scripts/adapters/voicebox_tts.py" \
  --text "话说那天夜里……" --out /tmp/vb-test.wav --voice "my-storyteller"
```

**config.env**

```bash
AIFILM_TTS_BACKEND=voicebox
VOICEBOX_BASE_URL=http://127.0.0.1:17493
VOICEBOX_PROFILE=my-storyteller    # 名称或 id；一角一声
VOICEBOX_LANGUAGE=zh
# VOICEBOX_ENGINE=qwen             # 可选
# 主路径 edge 失败时再试 Voicebox：
# AIFILM_TTS_VOICEBOX_FALLBACK=1
```

**film-spec**

```json
{
  "tts_backend": "voicebox",
  "vo_voice": "my-storyteller",
  "tts_allow_network_fallback": false
}
```

```bash
"$AIFILM" final --root "<root>" --tts-backend voicebox --lipsync off --music-mood rnb
```

**行为要点**

| 项 | 说明 |
|---|---|
| 合成路径 | 优先 `POST /generate/stream`（直出 WAV）；失败再 `/generate` + poll + `/audio/{id}` |
| 一角一声 | 固定 `VOICEBOX_PROFILE` / `vo_voice`；禁止每镜换 profile |
| 中文 | `VOICEBOX_LANGUAGE=zh`；引擎建议 `qwen`（多语克隆） |
| 与 Edge | 中文量产默认仍可 `edge`（不依赖本机 App）；要克隆声/更自然 → voicebox |
| 勿混 | 不要把 `zh-CN-*Neural` 当 Voicebox profile 名 |

### ElevenLabs（已封装）

适配器：`scripts/adapters/elevenlabs_tts.py`。

```bash
# 写入 skill config.env（chmod 600），勿 commit、勿贴聊天
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=cgSgspJ2msm6clMCkdW9   # Jessica young cute；可换
ELEVENLABS_MODEL=eleven_multilingual_v2
AIFILM_TTS_BACKEND=external
AIFILM_TTS_ARGV=["python3","$HOME/.grok/skills/ai-film-grok/scripts/adapters/elevenlabs_tts.py","--text-file","{text_file}","--out","{out}","--voice","{voice}"]
```

`film-spec.json`：

```json
{
  "tts_backend": "external",
  "vo_voice": "cgSgspJ2msm6clMCkdW9",
  "tts_allow_network_fallback": false
}
```

适配器会自行 load `config.env` 读 key（因 `minimal_subprocess_env` 不传密钥）。一角一声：整片固定同一 `voice_id`。

### 中文旁白选型（2026-07-16 教训 + Voicebox + CosyVoice）

| 场景 | 推荐 | 勿用 |
|------|------|------|
| 中文说书 / 傲娇幼女**听感**（零依赖） | **Edge**：`zh-CN-liaoning-XiaobeiNeural`（幼、有性格）或 `zh-CN-XiaoyiNeural`（软）；可 `vo_rate +6~10%`、`vo_pitch +12~18Hz` | 免费 ElevenLabs 英文声（Jessica 等）硬读中文 |
| 中文**更高自然度**（本地服务） | **CosyVoice 2** + 固定 `COSYVOICE_REF_WAV`；`--tts-backend external` | 未起 API 就硬指定 external；Neural 名当 voice |
| 中文**克隆声 / 更自然**（本机 App） | **Voicebox** + 固定 profile；`--tts-backend voicebox` | App 没开就硬指定 voicebox（会 fail closed） |
| 高情感镜精修 | MiniMax 或 Higgs（候选）+ 固定 voice/ref；先 `tts-ab` | 半片 edge 半片克隆（声线跳） |
| edge 失败时的本地兜底 | `AIFILM_TTS_VOICEBOX_FALLBACK=1` + 已锁 profile | 未 opt-in 就静默换 provider |
| 必须 ElevenLabs 中文 | Creator 档以上 + **中文 library voice_id**；试听通过再锁 | 共享库声线在 free 会 402；edge Neural 名塞进 EL → 400（**preflight hard / synthesize 直接失败**） |

**Hard gate（2026-07-20）**：`tts_backend=external|auto` + `AIFILM_TTS_ARGV`（ElevenLabs 等）时，`vo_voice` 不得为 `zh-CN-…Neural`。中文说书请用 `--tts-backend edge`。
| film-spec | `"tts_backend": "edge"` 或 `"voicebox"` + 上表 voice | `"tts_backend": "auto"` 且全局 `AIFILM_TTS_ARGV` 指向 EL |

**密钥**：只进 `config.env`（chmod 600）；禁止贴聊天/写进 film-spec/commit。Voicebox 本地无需 API key。

## 试音与混音

1. 用同一段 8–12 秒中文对比候选后端，包含叙述、停顿、轻情绪和专有名词。
2. 确认声线 ID/ref 后锁定，不在镜头间更换。
3. 检查断句、数字、英文、儿化和连读。
4. 混音中旁白是主体；BGM 与生成片原生音轨在旁白期间让位。
5. 最终声线一致性必须通过完整观看，技术 probe 不能代替听感验收。

本地开源方案与参考音管理：[opensource-tts.md](opensource-tts.md)。
