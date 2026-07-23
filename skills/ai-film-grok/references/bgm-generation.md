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
