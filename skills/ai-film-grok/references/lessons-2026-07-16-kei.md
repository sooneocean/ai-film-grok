# 实战复盘：Kei 暗黑同人片 v1 → v2（2026-07-16）

给 agent / 未来自己看：现象 → 根因 → **skill 已写进的规则**。

## 一句话

画风漂移来自**无锚批量 + 混 provider**；无聊来自**长旁白逼 loop**；成片炸来自**并发 final + 脏编码 + hash 不同步**。

## 现象对照

| # | 现象 | 根因 | 规则 |
|---|------|------|------|
| 1 | 镜间画风/质感像换了作者 | style 用设定图裁切；FRW 无固定 model/锚；Grok+FRW still 混用 | 双 master + 单 provider 全程；pilot 后批量 |
| 2 | 同一参考图仍漂（机构戏 vs 色气戏） | still 一半用 cast 锚、一半用 explicit 用户图锚，场景句重写脸服 | **全片同一 still 锚点**（cast master）；服装状态只写在 prompt 后半 |
| 3 | 画面「重播」无聊 | VO 35–50 字 → target>src → `stream_loop` 1–2 次 | 推荐 nar≤28 字；**一镜一句一动作**；宁可加镜也不 loop |
| 4 | 想要 2 分钟却做出 1:42 | 短 VO 正确，但镜数不够 | **时长用镜数堆**，不用拉长单镜 VO |
| 5 | final 报 video_silent / title 丢失 | 并行跑多个 final 抢 `_final_work` rmtree | **全局只允许一个 final**；失败先清 work |
| 6 | moov atom not found | 中间 stretch 文件损坏 / 源片编码怪 | FRW clip **assemble 前统一 re-encode**；再 register |
| 7 | soft xfade 26 段失败 | 滤镜过重 + 极短段 | 镜数≥16 或段长<4s → 优先 `transition_sec=0` 硬切或小 xfade |
| 8 | review-final 过不了 | 重编码改了文件，manifest sha 旧 | **任何改 clips 后必须 re-register** |
| 9 | pilot 形同虚设 | agent 自批 pilot-approval | pilot 须 `approved_by: user` 或用户原话「pilot 过」 |
| 10 | 用户参考图是高色气 naked | 直接当全片 img2img 锚 → 每镜向该构图坍缩 | style/cast 用**着衣定妆**锁脸服；色气只升 soft ladder，不把 naked 当唯一锚 |
| 11 | BGM 像恐怖片，用户要 R&B/Soul 诱惑 | `sound_plan.mood: dark` **覆盖** CLI `--music-mood` | 色气默认 **`rnb`**；`soul/sensual` 别名；tone 色气 + dark → write-spec 自动改 rnb |
| 12 | 静戏 I2V `motion gate failed`（score≈0.76） | still 几乎静、motion 文案太弱 | **微动也要可测**：blink+breath+hair+push-in 写进 prompt；失败后 `fail --reason motion` → 加强动作 re-I2V |
| 13 | `final` TTS 用了 ElevenLabs + `zh-CN-YunxiNeural` 400 | 全局 `AIFILM_TTS_ARGV` 指向 external，中文 Neural ID 无效 | 中文成片 **`--tts-backend edge`**（或改 config 默认 edge）；勿把 edge voice 塞进 ElevenLabs |
| 14 | 并行 `image_edit` 回传文件名顺序 ≠ 调用顺序 | 并发完成乱序 | 映射时按 **tool 返回 path** 记 shot_id，或串行出 still |
| 15 | 系列第二集复用 cast 快且稳 | 新 root + `cp cast/kei-v1` + 新剧情 12 镜 | **同角色多集：复用 cast master**；新剧情重写 film-spec，不必重定妆 |
| 16 | 用户说「产出一个新版本」要不要卡 pilot | S3 门禁要 `approved_by:user` | 用户**明确要求整集生产**时，pilot-approval 可写 `user_phrase` 引用原话；**禁止** agent 空批 |
| 17 | `assemble` 报 tpad `stop_duration=8.88e-16` | 时长差浮点误差 → freeze 成极小正数 | **prefer final 直出**（不必 assemble）；或 `transition_sec 0`；tpad 应 clamp `<1e-3` 当 0 |
| 18 | final TTS 400：ElevenLabs + `zh-CN-YunxiNeural` | `auto` 走了 external/ElevenLabs，Neural ID 无效 | 中文说书片 **强制 `--tts-backend edge`**；film-spec 可写死 `tts_backend: edge` |
| 19 | 新剧情《补课室协议》一次跑通 | 19 镜、短旁白、单 cast 锚、reencode-clips、edge final | **新剧情模板**：新 root + 复用 cast + 短 nar + reencode + edge TTS |
| 20 | 中途取消 get_task 仍可续 | FRW producer 可 resume（进度 JSON） | 断点续作：`frw_produce.py clips` 幂等；勿重开仍 |
| 21 | 用户说「不是正确角色」—无粉光环 | cast/style 简化立绘漏了签名配件 | **签名配件硬锁**（consistency §5b）：identity_lock + cast 可见 + pilot 勾配件 |
| 22 | ElevenLabs 中文「幼女/傲娇」极差 | 免费档**不能用**共享库中文声；Jessica 等英文声读中文口音重 | 中文成片优先 **Edge 女声**（晓北/晓伊/晓晓）；EL 仅 Creator+ 且固定中文 voice_id |
| 23 | API key 贴在聊天里 | 误当参数传递 | key **只写** `config.env` chmod 600；对话里出现后提醒轮换 |
| 24 | 有 `final.srt` 但画面无字幕 | 自定义 60s 槽位混音跳过了 PIL 烧录 | **交付必须画面内字幕**；本机 ffmpeg 常无 libass → 用 **PIL PNG + overlay**，勿依赖 `ass=` |
| 25 | 想 60s 却 final 只出 30s | stretch 跟 VO 走，短 VO→短镜 | 60s = **10×6s 槽位**（silent 对齐 + VO pad 静音），不是「短 VO 硬 loop」 |
| 26 | `vo-pad` 过大 → forbid_loop 失败 | clip≈4.8s 盖不住 target≈7s | 要么升 10s I2V，要么槽位混音；勿无限 pad |
| 27 | `aifilm final --vo-pad` 不生效 | CLI 未转发到 render_final | 用 film-spec / 直接 render 参数；或槽位脚本 |
| 28 | 路径含空格时 `ass=/Users/...` 炸 | filter 解析冒号/空格 | 素材先 **cp 到 /tmp 无空格路径** 再 ffmpeg |
| 29 | 续集「新剧情」无剧本 | 用户只说新版本 | 先确认方向；默认可写续集大纲再生产；**新 root + 复用 cast** |

## 交付物索引（本机，2026-07-16）

| 版本 | 路径 | 剧情 |
|------|------|------|
| v2 后宫线 | `~/Desktop/Kei羞辱崩坏掠夺后宫-v2/成片/` | 拆穿→转学→掠夺后宫 |
| **v3 加强（光环+60s）** | `~/Desktop/Kei极端羞辱精神崩坏掠夺后宫-v3/成片/` | 同主线压至≈62s；粉光环；烧录字幕；晓北 |
| **v4 旧仇反杀** | `~/Desktop/Kei后宫旧仇反杀-v4/成片/` | 续集：教务主任调来→反杀收入后宫 |
| **补课室协议** | `~/Desktop/Kei补课室协议/成片/film_final.mp4` | 诊断异常→强制补课→协议改写→反客为主 |

工程根示例：`/Users/dex/short video 0716/kei-dark-harem-v3`、`.../kei-dark-harem-v4`、`.../kei-remedial-v1`

## BGM 选型（色气片）

| mood | 用途 |
|------|------|
| **`rnb` / `soul` / `sensual`** | **默认** late-night 诱惑 R&B（Rhodes/sub/慢 kick） |
| `warm` | 温柔日常 |
| `playful` | 轻快 |
| `dark` | **仅**恐怖/惊悚；禁止里番默认 |

`final` 混音时 **film-spec.sound_plan.mood 优先于 CLI**；写错 dark 会整片发慌。

## 正确时长设计（类比）

把成片想成**连环画翻页**，不是一张图配长解说：

- 6s I2V ≈ 一页能说 **12–28 个汉字**  
- 多说一句 → **新开一页（新 still + 新 motion）**  
- 禁止：一页解说 50 字，于是把同一页正放倒放两遍  

## Agent 自检清单（final 前）

- [ ] style-bible 已 lock，cast_masters 非空  
- [ ] pilot-approval 含用户批准痕迹  
- [ ] 全部 still 同一 provider + 同一 img2img 锚  
- [ ] 每镜 nar ≤28 推荐 / ≤55 硬限；`_vo_budget.loop_risk_shots` 为空  
- [ ] 每镜 clip `ffprobe` 可解码；必要时 clean re-encode 后 re-register  
- [ ] 只跑一个 `aifilm final`；不要直接调 `render_final.py` 除非懂 manifest  
- [ ] review-final 含 `--score-style`  
- [ ] `sound_plan.mood` 为 `rnb`/`sensual`/`soul`（色气片）；**不是** `dark`  
- [ ] 中文 TTS：`--tts-backend edge`（除非已锁可用的中文 provider voice id）  
- [ ] 静戏 clip 抽帧能感到 blink/breath/push-in（否则 motion QA 易挂）  
- [ ] 系列集：cast 路径可复用；剧情/spec 必须新  
- [ ] 签名配件（halo 等）在 cast + pilot 可见  
- [ ] 中文旁白：edge 中文女声（非免费 ElevenLabs 英文声读中文）  
- [ ] 成片抽帧确认**画面内字幕**（不只 srt 文件）  
- [ ] 目标时长用「镜数×槽位」设计，与 silent 对齐  

## 60s 竖屏快片模板（v3/v4 验证）

1. 新 root（或续集 `cp cast`）→ lock-style（**halo 写进 identity_lock**）  
2. film-spec：**10 镜 × 6s**，nar 约 12–22 字/镜，硬切  
3. FRW：固定 model=qwen、576×1024、cast 锚全程 img2img → I2V  
4. register → assemble（失败则 re-encode concat）→ **槽位混音**（silent + Edge VO pad 到 6s + BGM）  
5. **PIL 字幕条 overlay 烧录** → review-final → export-desktop  

推荐声线：`zh-CN-liaoning-XiaobeiNeural`（幼/有性格）或 `zh-CN-XiaoyiNeural`（软）。

## 本 session 交付物（2026-07-16 夜）

| 片 | 路径 | 备注 |
|----|------|------|
| 羞辱后宫·节奏 RnB | `artifacts/kei-harem-ep01` + Desktop `Kei极端羞辱掠夺后宫_第1集_节奏RnB` | 旧素材 + 短 VO + rnb |
| 辅导室狩猎·新剧情 | `artifacts/kei-counselor-ep01` + Desktop `Kei心理辅导室的狩猎_第1集` | 12 镜新 still/I2V，≈64s，rnb |
| v3 光环加强版 | Desktop `Kei极端羞辱精神崩坏掠夺后宫-v3` | 粉光环 + 烧录字幕 + 晓北 |
| v4 旧仇反杀 | Desktop `Kei后宫旧仇反杀-v4` | 续集，≈62s |

Skill 代码门禁已落地：`vo_pacing`、`hook/action` 禁 loop、pilot 硬门、色气 dark→rnb。  
Skill 文档已补：签名配件、中文 TTS、烧录字幕、60s 槽位模板（本表 #21–29）。  

**续篇（2026-07-17）**：设计后期 HyperFrames + pilot scorecard 闭环 → [lessons-2026-07-17-compose-pilot.md](lessons-2026-07-17-compose-pilot.md)；日常用 `aifilm preflight` / `aifilm next`。  

