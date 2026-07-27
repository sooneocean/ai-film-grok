# 正式后期与交付

本管线从已审批的动态镜头出发，生成旁白、音乐/音效、字幕和最终 MP4。渲染成功不等于交付完成；还需要完整观看与 `review-final`。

**后期双轨（2026-07-17 闭环）**

| 路径 | 命令 | 何时用 |
|---|---|---|
| **默认交付** | `aifilm final`（=`--post-engine ffmpeg`） | 色气/漫剧说书人、要稳要快 |
| **设计成片一键** | `aifilm final --post-engine hyperframes` | 设计字幕/片头 + 仍用 aifilm VO/BGM |
| **分步设计** | `export-compose` → `compose-render` | Studio 先预览再渲 |
| **外部成片** | `register-final --source …` | Remotion / 手工导出接入门禁 |

设计后期**不**替代 I2V，**不**跳过 scorecard。详见 [post-compose.md](post-compose.md)。

## 固定入口

```bash
SKILL_DIR="$HOME/.grok/skills/ai-film-grok"
AIFILM="$SKILL_DIR/scripts/aifilm"

"$AIFILM" doctor
"$AIFILM" status --root "<root>"
```

`doctor` 检查 Python/FFmpeg、精确依赖、运行指纹、Schema、后端锁和安全态势。运行时发生了经审查的变化，执行 `"$AIFILM" lock-runtime`，再次检查。

## 组装与渲染

```bash
"$AIFILM" assemble --root "<root>"
"$AIFILM" final --root "<root>" \
  --lipsync off \
  --music-mood rnb \
  --music-volume 0.52 \
  --native-audio-volume 0.16
```

`final` 默认从 film-spec 读取 `tts_backend`、`vo_voice`、`transition_sec` / **`transition_intents` / `transition_styles`**、`native_audio_volume`。命令行只用于这次有意覆盖。

**转场 / BGM 换 take**：改 `transition_*` 或 `--music-seed` 后 **只 re-final** 即可；不必重 I2V。设计后期成片音轨优先 **`audio/mixed.wav`**（见 compose_render）。

TTS 后端：`auto | external | voicebox | minimax | fish | edge`。本机 [Voicebox](https://github.com/jamiepine/voicebox) 就绪时可 `--tts-backend voicebox`（固定 `VOICEBOX_PROFILE`）；`auto` 会在 external 之后优先 Voicebox。见 [voices.md](voices.md)。

**preflight 默认前置（2026-07-17）**：`final` 先跑教训体检——**hard**（loop_risk、色气 dark BGM 等）直接失败；**soft** 打到 stderr 不拦。  
应急：`--skip-preflight`；更严：`--preflight-strict`（soft 也拦）。单独体检：`aifilm preflight --root …`。

### 设计后期（可选 / 已闭环）

```bash
# 一键
"$AIFILM" final --root "<root>" --post-engine hyperframes --tts-backend edge --music-mood rnb

# 分步
"$AIFILM" export-compose --root "<root>" --engine both --layout auto --force
"$AIFILM" compose-render --root "<root>" --engine hyperframes
"$AIFILM" register-final --root "<root>" --source "<mp4>" --post-engine remotion  # 外部
```

- 门禁：`clips_complete`；注册时技术 QA（音轨+运动）；`review-final` 才 `final_complete`。
- `--post-engine hyperframes|remotion` 时 FFmpeg 默认：
  - **`--subs off`**（只写 SRT，避免与设计字幕双烧）
  - **`--plate-cards blank`**（片头/片尾只留 pad、不烧字，避免与设计片头双烧）  
  详见 [lessons-2026-07-20-title-double-burn.md](lessons-2026-07-20-title-double-burn.md)。纯 `ffmpeg` 交付仍默认烧字（`plate-cards text`）。
- layout：`auto` = 有 film_final 则 underlay，否则 multiclip。
- 完整边界：[post-compose.md](post-compose.md)。

### 防炸纪律（2026-07-16 实战）

1. **全局串行 final**：禁止并行两个 `final` / 直接调 `render_final.py` 抢 `out/_final_work`（会 rmtree 互删 → 丢 title/video_silent）。  
2. **FRW/外源 clip 入组前**：优先一键  
   `"$AIFILM" reencode-clips --root <root>`（clean h264 + 自动 re-register）。  
3. **改了 clips 文件后必须 re-register**（否则 manifest sha 与磁盘不一致 → `review-final` 假失败）。手动改文件后也再跑 `reencode-clips` 或 register-clip。  
4. **镜数 ≥16 或大量段 <4s**：优先 `--transition-sec 0` 硬切，或 0.12–0.18 小 xfade；26 段 soft xfade 易失败。  
5. **禁止**手改 `clips/*.mp4` 覆盖后不 re-register。  
6. final 失败时：先 `rm -rf out/_final_work`，确认无其它 final 进程，再单次重跑。  
7. 确认 `_vo_budget.loop_risk_shots` 为空；有则先拆旁白，再 final。  
8. **中文旁白默认** `"$AIFILM" final ... --tts-backend edge`（避免 auto 走 ElevenLabs 却塞 edge voice id → 400）。  
9. `assemble` 若报 tpad `stop_duration` 极小浮点错误：可跳过 assemble，直接 **final**；或硬切 `--transition-sec 0`。  
10. 用户一句话要「整集成片」时：pilot-approval 写 `approved_by:user` + `user_phrase` 引用原话，再量产。

内部阶段：

1. 严格验证 film-spec 与每镜 approval receipt。
2. 逐镜生成旁白；显式后端失败时不暗中改 provider。
3. 按 VO 长度 stretch 镜头；**优先 loops=0**（短旁白）。loop 多 = 观感重播，应回改 spec。
4. 按 `transition_sec` 进行 xfade；0 为硬切。
5. 混合旁白、程序化 BGM 或用户音乐；若 I2V 有自带音乐／环境声，保留其原生音轨作为主视频声，并在旁白／角色对白期间自动闪避。
6. 用 PIL 绘制字幕并烧录，避免系统 libass 差异。  
   - **交付判定**：用户播放时画面底部必须有字；只有 `final.srt` **不算**字幕完成。  
   - 本机 brew ffmpeg 常**无** `ass`/`subtitles` 滤镜 → 用 **半透明底条 PNG + overlay enable=between(t,...)**。  
   - 路径含空格时先 `cp` 到 `/tmp/...` 再进 filter_complex。  
7. 对最终视频完整解码，检查时长、连续运动和音轨；单个硬切不算真实动态，结果写入 QA report。  
8. **目标≈60s 快片**：优先 `film_silent`（10×6s）+ 每镜 VO 后 pad 静音到 6s 再混 BGM，再烧字幕；不要指望短 VO + stream_loop 凑时长。

## 声音策略

- 默认 `storyteller`，lipsync 关闭。
- auto 顺序：结构化 external → MiniMax → 已固定 voice ID 的 Fish → Edge。
- Fish 严格声线锁默认开启；没有固定 ID 时不调 Fish。
- `tts_allow_network_fallback: false` 是生产默认。只有已接受 auto 模式的声线/服务商变化时才改为 true；显式后端仍不跨 provider。
- `AIFILM_TTS_CMD` 已禁用。本地 CosyVoice/IndexTTS 用 `AIFILM_TTS_ARGV` JSON 数组，参考 [opensource-tts.md](opensource-tts.md)。

## 字幕与混音检查

- 字幕只在对应语音时出现，不覆盖脸/重要道具，不截断中文词组。
- 旁白始终清晰；BGM 停顿时可听见，说话时自动让位。
- I2V 原生音轨默认 0.72，是主视频声（高于额外 BGM）；旁白／角色对白期间自动闪避。交付审计会核验保存的 stem、SHA-256 与来源镜头；没有可用 stem 时不得标称为主声。
- 自带音乐时记录 `--music-license`，不得默认认定可商用。

## 完整观看门禁

`final` 使用 film-spec 的 `transition_intents`（硬/软/hold 分镜接缝）与 `sound_plan`（mood/mute/duck/accent）。  
**色气片 BGM**：`sound_plan.mood` 优先于 CLI；默认 **`rnb`**（R&B/Soul 诱惑）。`dark` 仅恐怖——写错会被 write-spec 在色气 tone 下自动改回 rnb。  

### sound_plan 事件（已真正叠入 bed）

| type | 作用 |
|---|---|
| `mute` | 时间窗内 BGM 归零 |
| `duck` | 时间窗内 BGM 衰减（`depth`） |
| `sfx_accent` | 叠程序化点缀：`heartbeat` / `whoosh` / `chime` / `impact` / `breath` / `generic` |

- **auto_sfx**（默认 true）：未手写 `sfx_accent` 时，按 `dramatic_function` 自动一镜一点缀（hook→whoosh，sensory→heartbeat，action→impact…）。关：`"auto_sfx": false`。
- **用户 `--music` 文件**：mute/duck/sfx 同样作用在 bed 上（再与 VO 侧链混音）。
- **侧链 duck**（说话时 BGM 让路）：FFmpeg `sidechaincompress`；**rnb 默认更长 release（720ms）**，停顿时 groove 回来更「呼吸」。
  - film-spec：`sound_plan.sidechain: {threshold, ratio, attack_ms, release_ms}`
  - CLI：`--sidechain-threshold/ratio/attack/release`
  - 参数写入 `audio/mix_report.json` → `sidechain`

### TTS 防呆（Phase E hard + Phase F 默认）

- **禁止**把 `zh-CN-…Neural` 塞进 external/ElevenLabs（`AIFILM_TTS_ARGV`）。
- 中文说书：**`--tts-backend edge`** + Edge Neural 名；或 provider 原生 voice id。
- `write-spec`：`vo_mode=storyteller|hybrid` 且 `tts_backend=auto` → **自动钉 edge**（`_tts_notes`）。
- `preflight` hard：`tts_neural_on_external`；soft：`tts_external_risk`、`tts_storyteller_not_edge`。
- **status 音频摘要**：`aifilm status` → `audio` 字段（tts_backend / mood / sidechain / mix_report / loudness）。
- **响度**：final 混音后写 `audio/mix_report.json` → `loudness.integrated_lufs`（ffmpeg ebur128）。
- **loudnorm（Phase G）**：默认 **`auto`**——仅当 LUFS 过响（>-12）或过轻（<-22）时拉到 `target_lufs`（默认 **-16**）。
  - CLI：`--loudnorm auto|on|off` · `--target-lufs -16`
  - film-spec：`sound_plan.loudnorm` / `target_lufs`
  - `status.audio` 可见 `loudnorm_applied` / `loudness_before` / `loudness`

### 本地 BGM 模板曲（Phase H）

Skill **不附带**版权曲库。你把**自己有权使用**的 rnb/许可文件放进 film root，final 会自动挂上：

```
<audio>/
  bgm.wav                 # 优先
  music.mp3
  templates/rnb.wav       # 按 --music-mood / sound_plan.mood
  templates/sensual.wav
  templates/default.wav
  bgm.license.txt         # 推荐：许可说明（或 --music-license）
```

```bash
# 有 audio/bgm.wav 时自动用（默认 --music-template auto）
"$AIFILM" final --root "<root>" --tts-backend edge --music-mood rnb

# 强制只要本地模板（没有就失败）
"$AIFILM" final --root "<root>" --music-template on

# 只要程序化 rnb
"$AIFILM" final --root "<root>" --music-template off

# 显式路径
"$AIFILM" final --root "<root>" --music "/path/to.rnb.wav" --music-license "Epidemic …"
```

`status.audio.local_music_available` / `mix_report.music_template` 可查是否命中。  
输出 `audio/mix_report.json` 列出 `applied_events`。

`final` 结束后，`final_complete` 仍为 false。完整播放当前成片，并完成**导演评分卡**（**十一维**全 pass）：

| 维度 | CLI | 含义 |
|---|---|---|
| identity | `--score-identity` | 角色脸/服一致 |
| style | `--score-style` | 介质/色板/线稿全片一致 |
| motion | `--score-motion` | 真实动态，非静图 |
| escalation | `--score-escalation` | 情绪/距离有升级 |
| audio | `--score-audio` | VO/BGM 可读可听 |
| subs | `--score-subs` | 字幕同步可读 |
| dead_air | `--score-dead-air` | 无明显拖沓/黑帧死气/**同画面 loop 重播** |

任一 `fail` 或漏填 → `review-final` 拒绝，`export-desktop` 不可用；  
同时写入项目根 **`director_notes.json`**（开放重拍清单）。可用：

```bash
"$AIFILM" director-notes list --root "<root>"
"$AIFILM" director-notes add --root "<root>" \
  --action reshoot --reason motion --shot-id shot03 --note "嘴型乱"
"$AIFILM" director-notes resolve --root "<root>" --shot-id shot03 --note "已重生成"
```

`review-final` 评分失败时可附 `--reshoot-shots shot01,shot03`，把 identity/motion/escalation 失败挂到具体镜头。  
`status` 会输出 `open_reshoots` / `gates.reshoots_clear`。

完整播放时还要检查：

- 开头/结尾无黑幕、花屏或意外静帧。
- 每镜脸、发型、服装、道具与场景连续。
- 每镜有可观察的相机/主体/环境运动。
- 声线稳定，无断句、重复、爆音；字幕与声音对齐。
- 转场没有视频/音频跳点，结尾完整。

```bash
"$AIFILM" review-final --root "<root>" --approve \
  --score-identity pass --score-motion pass --score-escalation pass \
  --score-audio pass --score-subs pass --score-dead-air pass \
  --reviewer "<reviewer>" --notes "已完整观看，身份/运动/音画/字幕通过"
"$AIFILM" status --root "<root>"
"$AIFILM" export-desktop --root "<root>" --name "<中文名>"
```

审批绑定最终视频 SHA-256。重渲染后必须重看、重批。
