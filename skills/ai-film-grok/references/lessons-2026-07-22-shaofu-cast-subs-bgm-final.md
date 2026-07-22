# Lesson 2026-07-22 · 少婦多情案：脸锁 / HF 字幕空窗 / 色气 BGM / final 超时

> **触发原话**：「人物跑掉了」「hypeframes 的字幕又不见了」「背景音乐要诱惑色气」「直接推进到出片」「记取教训沈淀进 plugins」  
> **P 码**：P0 交付 · P0 身份 · P2 后处理 · P3 音频  
> **片例**：`shaofu-duoqing-xiandai`（少婦多情·现代偷情篇）— 2026-07-22  

---

## 失败解剖

| 用户感受 | 工程事实 | 根因 |
|---|---|---|
| 人物每镜换脸 | pilot still 用纯 `image_gen` / 审核挡后软文生图 | **未 `image_edit(cast master)`**；审核失败后改用 t2i「绕」= 必漂 |
| 给了角色表仍漂 | sheet 整页 letterbox 当 9:16 master | multi-panel sheet 须 **裁 FRONT/脸** 再 lock；整表不能当 I2V 脸锁 |
| HF 字幕不见了 | `final --post-engine hyperframes` 默认 plate **`subs=off`** | 设计路径假设 HF 会烧字；**HF 未完成 = 零字幕**；再手清 `final.srt` 更惨 |
| BGM 不够色气 | delivery 记 `mood=warm` / procedural velvet | 色气应用 **`assets/bgm/rnb/*` 曲库** 或 `--music-mood rnb` + 显式 `--music`；勿默认可温馨 warm |
| final 总失败 | `aifilm final` 内 `run()` **timeout=60s** | `render_final.py` 常 >2min → TimeoutExpired；须长超时或直调脚本 |
| 硬核 still 全 moderated | heat=max 器官细部 + 公众脸 ref | Imagine 审核硬拦；**软亲密轨可交付**，须对用户诚实尺度落差 |
| export-desktop 不过 | review-final：subtitle 跨 hard cut | 勿用空 SRT 糊弄；burn 后 boundary 或 soft join；桌面可 `cp out/film_final.mp4` |

**一句话**：脸只认 cast 像素；字幕要么 HF 真跑完要么 plate 必 burn；色气 BGM 认 rnb 曲库；final 别 60 秒掐死。

---

## 规则（Agent 硬清单）

### 1 · 脸锁（P0 · 身份）

1. 用户交主角图 / 角色表 → 立刻 `canonical/cast/user-refs/*` + 裁 **FRONT 全身** + **脸特写** → `afang-v1` / `*-face-v1` → `lock-style` / bible  
2. **有角色的 still**：只许 `image_edit(cast|face|上一过审 still)`；**禁止**纯 `image_gen` 抽脸  
3. 审核 400 moderated → **停**；改软提示仍 **edit 已过审 still**，禁止 t2i 绕审核  
4. multi-panel character sheet：`image_edit` 抽单人常失败 → **PIL/sips 坐标裁 FRONT**（少婦案验证）  
5. 过审后仍漂 → 作废 keyframe 入 `keyframes/_drifted_void/`，从 cast 重 edit  

### 2 · 字幕与 HyperFrames（P0 · 后处理）

| 路径 | plate `subs` | 前提 | 失败时 |
|---|---|---|---|
| `post-engine hyperframes` | 默认 **off**（防双烧） | HF compose **真成功**才有字 | **立刻** `render_final --subs burn` 补烧 |
| `post-engine ffmpeg` | 默认 **burn** | 单引擎交付 | — |

**禁止**：为过 `review-final` 把 `out/final.srt` **写空**（少婦案误伤，字幕全灭）。

交付前抽帧验收：

```bash
ffmpeg -y -ss 12 -i out/film_final.mp4 -frames:v 1 /tmp/sub_check.jpg
# 画面底部须有中文字幕条；cue_count>0 且 burned_in=true
```

### 3 · 色气 BGM（P3 · 音频）

- 色气 / 里番 / heat max 亲密：**`--music-mood rnb`**（或 `sensual`/`soul`）；**禁止**对色气用 `dark`  
- **优先** skill 曲库（有 license）：  
  `skills/ai-film-grok/assets/bgm/rnb/rnb_loop_0{1-5}.wav`  
- 推荐显式：

```bash
ffmpeg -y -stream_loop 3 -i "$SKILL/assets/bgm/rnb/rnb_loop_03.wav" -t 90 \
  -c:a pcm_s16le "$ROOT/audio/bgm_seductive_rnb.wav"
# render_final ... --music "$ROOT/audio/bgm_seductive_rnb.wav" \
#   --music-license "CC0 assets/bgm/rnb/rnb_loop_03" --music-volume 0.55-0.58
```

- 仅当曲库缺失才 procedural；报告里 `license_or_source` 须含 `rnb`/`CC0`，勿只看误标的 `mood: warm` 字段  

### 4 · final 超时（P0 · 工程）

- `aifilm final` 经 `run(timeout=60)` 调 `render_final` → **易杀**长片  
- **正确**：`python3 scripts/render_final.py --root …` 无短超时；或 `run(..., timeout=600)`  
- 已成功 plate 后 HF 可另开；HF 失败不删 plate  

### 5 · 尺度诚实

- heat_scale=max **文案/VO** 可硬；**像素**以审核通过为准  
- 禁止向用户宣称「硬核成片」若仍是软亲密轨；交付时写明尺度落差  

---

## 代码 / 配置落点（本轮优化）

| 项 | 动作 |
|---|---|
| `aifilm_grok.run` | `timeout` 可覆盖；`cmd_final` 调 render_final 用 **600s** |
| `cli/review.create_shot_review_report` | 只强制 CORE 五维；`coitus` 可选，避免 `score_coitus` AttributeError |
| SKILL.md | 硬门禁 + 按需表链本 lesson |
| BGM 默认纪律 | 色气 → rnb 曲库优先（见上） |

---

## 验收

```bash
# 1) cast 存在且非整页 sheet 糊脸
test -f "$ROOT/canonical/cast/afang-v1.jpg"
# 2) 成片字幕 burned
python3 -c "import json;d=json.load(open('$ROOT/out/final-delivery.json')); assert d['subtitles']['burned_in'] and d['subtitles']['cue_count']>0"
# 3) BGM 色气源
python3 -c "import json;d=json.load(open('$ROOT/out/final-delivery.json')); s=str(d.get('music',{}).get('license_or_source','')); assert 'rnb' in s.lower() or 'CC0' in s"
# 4) final 不 60s 死
# 直调 render_final 应 exit 0 且 out/film_final.mp4 mtime 新
```

---

## 相关

- [consistency](consistency.md) · 身份锁  
- [bgm-generation](bgm-generation.md) · [lessons-2026-07-21-bgm-instrumental-fallback](lessons-2026-07-21-bgm-instrumental-fallback.md)  
- [lessons-2026-07-20-title-double-burn](lessons-2026-07-20-title-double-burn.md) · plate subs off 仅当 HF 真烧字  
- [verify-before-generate](lessons-2026-07-22-verify-before-generate.md) · 坏 still 不进 I2V  
- [wardrobe-no-redress-still](lessons-2026-07-21-wardrobe-no-redress-still.md)  
- 片根：`AI FILM SPACE/0722/shaofu-duoqing-xiandai`  
