# BGM 生成与抗疲劳（2026-07-21 沉淀）

> 嵌在 craft **Media → Verified**。  
> **硬兜底**：程序化 rnb v3（零依赖、必无人声、永不假静音）。  
> **听感兜底**：纯乐器曲库池（人工或 AI 预生成 → 多文件 seed 轮换）。

## 为什么会「重复听腻」

| 根因 | 说明 | 已做 |
|---|---|---|
| 音色族单一 | 旧程序床 ≈ 同一 Rhodes+鼓 | **v3 multi-style**（velvet/pulse/ambient/lofi/glitter） |
| 曲库空 | 无 wav → 永远 procedural | 池目录 + seed 轮换 |
| 同 seed 可复现 | 同 title+mood+时长 → 同 take | `--music-seed` / `audio_policy.music_seed`；路由 counts 参与 hash |
| 歌模型当 BGM | HeartMuLa 带人声抢旁白 | **不当纯 BGM 硬兜底**；歌/唱段另路 |
| 全片一床 | 说书厚薄未调 | **audio_recipe** 调 bed_gain（thin/focus） |

## 纯乐器兜底阶梯（研究结论 · 定稿）

```text
① 曲库池 · 纯乐器 wav（最推荐听感兜底）
     assets/bgm/rnb/*.wav  或  <film>/audio/templates/rnb/*
     → seed % pool 轮换；须无人声、可写 .license.txt

② 程序化 rnb v3（工程硬兜底 · 永远有）
     无曲库 / final 失败回落；换 --music-seed 换 style 族

③ 离线 AI 灌库（可选 · 不进 final 热路径）
     ACE-Step lyrics=[inst]  ·  Stable Audio Open 短床
     · MusicGen（权重常 CC-BY-NC → 商用慎）
     听审无人声 → 丢进 ①

④ HeartMuLa / 成歌模型
     仅 sung_beat / 实验；禁止当默认无人声 BGM
```

| 来源 | 纯乐器？ | 商用注意 | 技能位置 |
|---|---|---|---|
| **程序化 v3** | 是 | 自有生成 | hard fallback |
| **自备/订阅曲库** | 人工保证 | 看授权页 | 池 ① |
| **ACE-Step `[inst]`** | 强（需实听） | 核权重/ToS | 灌 ① |
| **Stable Audio Open** | 强（短氛围） | Community 条款 | 灌 ① |
| **MusicGen** | 强 | **常 NC 非商用** | 仅自用实验 |
| **HeartMuLa** | 弱 | Apache | 不进 BGM 默认 |

**色气说书灌库 prompt 示例（ACE / MusicGen 类）：**

```text
late night neo-soul instrumental, soft electric piano, warm sub bass,
slow groove 72 bpm, no vocals, no singing, background for narration
```

ACE-Step 歌词侧可用：`[inst]` 或空结构标记（以官方/社区文档为准，出库前听审）。

### 5090 私有 ACE-Step 候选曲库（正式插件选项）

`aifilm bgm-candidate` 是 5090 局域网节点的离线灌库入口，可在开拍前建立曲库，
也可在剪辑或混音阶段按实际镜头补一首；两种时机的产物完全相同。它绝不在
`final` 热路径现生成，也不会自动替换既有 BGM。

```bash
# 生成：只写入 pending，保留 seed、模型/node job、hash；不会进入 final
"$AIFILM" bgm-candidate generate --root "<film-root>" \
  --mood rnb --duration 30 --seed 5101 \
  --prompt "late-night neo-soul instrumental, no vocals"

# 人工完整听审后才批准；批准后才进入 audio/templates/<mood>/
"$AIFILM" bgm-candidate approve --root "<film-root>" --asset-id "<candidate-id>"
```

候选必须是无歌词/无演唱的 WAV，插件会核验 MIME、WAV、44.1 kHz、时长与 SHA-256。
节点不可用、超时、坏档或 hash 不符均失败关闭；已批准曲库和程序化 rnb 维持原有可用性，
不会静默换源。每首进入曲库前仍须记录实际模型版本与权利/许可，私有本地推理不自动取得公开发行授权。

### 共享批准库（library-first）

新片的正式路径是 `aifilm bgm-library`。共享资产默认落在
`~/.grok/ai-film-grok/bgm-library/`，不进入插件 Git；`catalog.json` 原子更新，
`usage.jsonl` 只在成片成功后追加。节点 receipt 只保留抽象配方、prompt hash、seed、
模型与 checkpoint 指纹，不保留剧情 prompt 或 token。

```bash
# 只读检查节点与曲库；输出不会显示 token
"$AIFILM" bgm-library doctor
"$AIFILM" bgm-library status
"$AIFILM" bgm-library audit

# 20 个基准配方槽，每槽默认批量 4 个 pending 候选
"$AIFILM" bgm-library generate --recipe-pack baseline-v1 --batch-size 4

# 首次接真实 5090 时只跑一个 4×30 秒 canary；仍只进入 pending
"$AIFILM" bgm-library canary --slot baseline-v1-rnb-pad \
  --duration 30 --batch-size 4

# 生成本机 HTML 审听页；听完后逐首批准或拒绝
"$AIFILM" bgm-library review-pack
"$AIFILM" bgm-library approve --asset-id "<id>" \
  --reviewer dex --license-note "local ACE-Step generation; release rights reviewed" \
  --instrumental-confirmed
"$AIFILM" bgm-library reject --asset-id "<id>" \
  --reviewer dex --reason "melody too close to an approved asset"

# 先预演，再把确定性选曲写入片级 receipt
"$AIFILM" bgm-library plan --root "<film-root>"
"$AIFILM" bgm-library select --root "<film-root>"

# 从已批准主题 master 派生主角/关系/威胁 low-mid-high，共 9 个 pending
"$AIFILM" bgm-library series-pack --root "<film-root>" --series-id "<series-id>"
```

批准时会拒绝完全相同 SHA-256；标准化 PCM 相似度 `>=0.98` 也拒绝，只有明确的
同 motif 父子变奏可保留 lineage。`0.90–0.98` 会归入同一声音簇，因此相邻 cue
仍不能连续使用。选择器硬过滤批准、纯器乐、许可、mood 与技术检测；同片不重复资产，
相邻不重复声音簇。存在替代时避开最近 5 部或 30 天用过的曲；候选不足只放宽跨片窗口，
并把 `diversity_relaxed` 和原因写入 receipt。

曲库达到 20 首且五类 mood 各至少 4 首后，新项目才默认
`audio_policy.bed_source=approved_library`。旧项目继续保持原来的 `auto` 逻辑。
`final` 不调用 ACE 临时生成；缺匹配曲会写入待生成队列并阻塞。成功完成混音后，
才把资产 ID、checksum、catalog revision、motif lineage、声音簇与选择理由提交到
`usage.jsonl` 和 `mix_report.json`。

canary 会回读候选数量、时长、技术检测、唯一 checksum 与唯一 PCM 指纹；任何候选
仍保持 `pending_human_review`，不能替代人工完整听审。

### ACE-Step Music Editor v2

共享 master 不再由 `final` 直接截断。片级 `music_cue` 先生成 checksum 绑定的
`receipts/music-edit-plan.json`；选择器优先匹配准确时长、对白安全版本、
`motif_role`（动机在剧情中的作用）、相邻调性与 BPM。缺少已批准 edit 或转场桥时，
`final --music-template approved_library` 会列出需求并阻塞，ACE 仍只在离线策展阶段运行。

```bash
# 查看本片每个 cue 需要哪种离线编辑
"$AIFILM" bgm-library edit-plan --root "<film-root>"

# 从已批准 master 生成准确时长／对白安全／无缝循环候选；全部保持 pending
"$AIFILM" bgm-library edit-pack --asset-id "<approved-id>" \
  --duration 18 --variant exact --variant dialogue-safe --variant loop

# 修复尾奏（ACE repaint）；只重绘最后 8 秒
"$AIFILM" bgm-library edit-pack --asset-id "<approved-id>" \
  --duration 60 --variant outro

# 把一个剧集主题发展为 statement/fragment/tender/corrupted/reveal/loss/reunion/climax
"$AIFILM" bgm-library motif-development --root "<film-root>" \
  --asset-id "<approved-series-motif-id>"

# 为两首调性或速度不兼容的批准曲生成过桥；生成后仍须 review-pack 听审并批准
"$AIFILM" bgm-library bridge-pack \
  --from-asset-id "<approved-outgoing-id>" \
  --to-asset-id "<approved-incoming-id>" --duration 10
```

所有 edit/bridge 会保存父资产、目标资产、配方、seed、checkpoint 和技术检测，但不保存
剧情原始 prompt。审听页同时显示 loop seam、结尾活跃度、对白频段占比和目标时长。
配方另会记录可审计的配器意图（鼓、低音、和声密度、明亮度、主旋律存在感）；它们会编入
ACE cover/repaint 的抽象提示词，不声称 ACE 已输出可独立交付的 stems。
转场桥只有在批准、checksum 校验通过且父子绑定吻合时才实混；成片成功后，cue 和 bridge
分别追加 usage 事件。`final` 不允许把“计划中会生成”当成“已经存在”。

ACE-Step cover 会以参考音长度为准。因此当 edit 目标时长不同于批准 master，客户端只会在
临时目录制作带淡出的 target-length reference 并上传给节点；批准 master 从不改写，临时参考
不进 catalog，最终仍只允许人工批准的 ACE 输出进入 final。这个规则同样适用于 series pack 与
transition bridge，不能让 30 秒母带伪装成 10 秒过桥。

### Audio armory（已收编的 5090 音乐武器）

`aifilm bgm-library doctor` 会输出 `audio_armory`：只有节点健康、reference upload 可用且存在
checksum 绑定、技术通过的真实候选时，才把 `scene_edit`（对白安全／尾奏修复）或
`transition_bridge` 标为 `verified`。所有武器都只能离线策展、必须人审、不能直接进入 final。
`motif_development` 在有剧集主题母带和真实候选前保持 `conditional`；Foley／逐帧 SFX 与无缝
循环不属于 ACE 的自动武器，后者在 live seam 测试通过前也不会自动路由。

## 三阶梯 · 立刻换口味（操作）

```text
1. 换 take（零依赖）
   --music-seed <新数字>
   或 film-spec: "audio_policy": { "music_seed": 42 }
   → style 族 + 和声重排

2. 曲库池 ≥3 首纯乐器
   assets/bgm/rnb/01.wav … 03.wav
   → 片与片之间不再同一首

3. 场景厚薄（write-spec 已自动）
   audio_recipe: narrate_bed / narrate_thin / bed_focus
   → mean bed_gain 调节床响度（非换曲时也减「糊成一片」）
```

```bash
# 预听程序床
python3 "$HOME/.grok/skills/ai-film-grok/scripts/make_sfx_bed.py" \
  --duration 24 --shot-starts 0 --mood rnb --seed 42 --out /tmp/bgm.wav

# 成片
"$AIFILM" final --root "<root>" --tts-backend edge --music-mood rnb --music-seed 42

# 看路由
"$AIFILM" write-spec --root "<root>"
"$AIFILM" audio-plan --root "<root>"
```

## 程序化 v3 风格

| seed % 5 | style | 听感 |
|---|---|---|
| 0 | velvet | 亲密晚间 R&B |
| 1 | pulse | 更快、kick 前 |
| 2 | ambient | 厚 pad、少鼓 |
| 3 | lofi | 闷 + swing |
| 4 | glitter | 亮 Rhodes |

## 本地曲库池

```bash
mkdir -p ~/.grok/skills/ai-film-grok/assets/bgm/rnb
# 只放纯乐器；带人声的不要进 rnb 默认池
# cp ~/Music/licensed/soft-rnb-01.wav ~/.grok/skills/ai-film-grok/assets/bgm/rnb/
# echo "许可说明" > ~/.grok/skills/ai-film-grok/assets/bgm/rnb/soft-rnb-01.license.txt
```

`resolve_music_template`：`seed % pool_size`；mix_report 记 `pool_index` / `pool_size`。

## AI 接入（可选 · 失败回落程序床）

```bash
AIFILM_MUSIC_ARGV=["python3","$HOME/.grok/skills/ai-film-grok/scripts/adapters/music_external.py","--out","{out}","--duration","{duration}","--mood","{mood}","--seed","{seed}","--prompt","{prompt}"]
MUSIC_GEN_BASE_URL=http://127.0.0.1:7860
# AIFILM_MUSIC_REQUIRE=0  默认失败→procedural
```

生产更稳：**离线生成 → 池**，不要每 final 现跑。

## 镜头级情绪音乐（music_cue）

每个 shot 可独立指定 `music_cue`，让同一主题在不同情绪中换密度与力度，而不是只换一个随机 seed：

```json
{
  "mood": "dark",
  "energy": 0.72,
  "density": 0.48,
  "bass_presence": 0.7,
  "brightness": 0.25,
  "stem_profile": "pulse",
  "motif_id": "secret-theme",
  "transition": "crossfade",
  "duck_db": -2
}
```

缺少 cue 时，会按 `dramatic_function` 推导：危机偏 dark/pulse，高潮偏 rnb/full，铺陈偏 ambient/pad，余韵偏 warm/thin。`music_timeline` 还会从镜头 cast 推导角色或双人关系动机：同一角色跨段重现同一动机，剧情功能只改变其纯器乐配器（例如钢琴/弦乐/低音提琴/刷鼓）与张力；明确的 `motif_id` 始终优先。程序 BGM 会按镜头切段，确定性地变更动机 seed、能量、鼓组密度、低频与高频层，以及 stem profile；外部曲库则保留原曲，仅施加可解释的镜头级 gain/duck 自动化。对白 cue 未明确写 `duck_db` 时，先减 3 dB，再交给实时 sidechain 做细部闪避。实际路由会写入 `mix_report.json.music_cue_routing`，包含 `instrument_palettes` 与 `instrumental_only=true`，不会把“seed 不同”当作音乐变化的证明。

`mix_report.json.music_mix_review` 是成片听审地图：记录每个切点相对于 downbeat 的偏差、对白保护是否有静态与动态两层、成片响度和需要回听的时间点。它绝不为追拍而移动已批准的画面切点；出现 `needs_attention` 时须先修正对白保护再 final review。

旁白仍为中文、角色对白仍为日文，字幕仍为中文；`music_cue` 只控制音乐层，不会改变语言分轨。若启用 `--music-template timeline`，则每个 cue 会从 `audio/templates/<mood>/`（或共享曲库）选择一首授权纯音乐并实混到 BGM stem；任一目标 mood 缺曲即 fail-closed，不会用 default 或全片 `audio/bgm.wav` 偷换。mix report 只记录 `audio/templates/...` 或 `skill_library/...` 逻辑路径。

## 场景自适应（相关）

- [audio-recipe.md](audio-recipe.md) — 说书厚薄 / bed_focus  
- [audio-fallback.md](audio-fallback.md) — TTS/BGM/Lipsync 阶梯  
- seed 优先级：`--music-seed` → `audio_policy.music_seed` → hash(title+mood+dur+recipe counts)

## 代码入口

- `scripts/make_sfx_bed.py` — `rnb_bgm` multi-style  
- `scripts/sound_plan.py` — 曲库池轮换  
- `scripts/render_final.py` — seed / bed_gain / external  
- `scripts/audio_recipe.py` — 镜级配方  
- `scripts/adapters/music_external.py` — AI HTTP  

## 法务

- 程序床：自有  
- 曲库：以 license 文件为准  
- MusicGen 权重常 **NC** → 商用片勿默认  
- 商业站 / ACE / Stable：以**当前** ToS 为准  

## 验收（抗重复）

1. 换 seed → 听得出 style 或编排不同  
2. 池 ≥3 首 → 不同 seed 可能不同文件（pool_index）  
3. 无曲库时仍有程序床（非静音）  
4. 旁白清晰；床无人声抢麦  

---

## 色气成片 BGM（2026-07-22 · 少婦案）

- **色气 / heat 亲密**：优先 `assets/bgm/rnb/rnb_loop_0{1-5}.wav`（各有 `.license.txt`，CC0）。
- 推荐 80bpm 偏闷骚：`rnb_loop_03`；loop 至片长后 `--music` 显式传入。
- `render_final --music-mood rnb --music-volume 0.55–0.58`；**禁止**色气用 `dark`。
- 报告字段 `music.mood` 偶发显示 warm——以 `license_or_source` 含 `rnb`/`CC0` 为准。
- 详：[lessons-2026-07-22-shaofu-cast-subs-bgm-final.md](lessons-2026-07-22-shaofu-cast-subs-bgm-final.md)
