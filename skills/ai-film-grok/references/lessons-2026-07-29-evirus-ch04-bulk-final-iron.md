# Lesson · E病毒 ch04 bulk→final IRON（P0 · 2026-07-29 · 后面不要再犯）

> 片例：`AI FILM SPACE/0729/e-virus-ch04-shelter` · 用户句「all ok 直接出片」  
> 挂：`hard-defaults` · `SKILL.md` §17 · `Agents.md` · `memory/2026-07-29-evirus-ch04-bulk-final-iron.md`

## 用户信号
「all ok 直接出片」= pilot 已批 → bulk I2V/register → TTS+rnb → final 交付。  
「把这些经验写回去」= 本场坑必须落 lesson，禁止下轮重踩。

---

## 1. Imagine 拦 bare I2V（诚实 PARTIAL）

| 现象 | 规则 |
|---|---|
| bare still / 明示 genitals 词 → `imagine:content-moderated` | **禁止**内衣/军裤 still 冒充插入 |
| soft 提示能过审核但 **mean 极低** | soft-pass **≠** 可装片；须 HIGH MOTION 重拍 |
| Comfy Wan 空档 | capacity 过再补真 bare；未补则 **PARTIAL 收据** |

**可过审 + 高动提示模板（首段必 MEDIUM LOCK cel）：**
```text
MEDIUM LOCK polished 2D anime cel manhua clean lineart style-v1.
HIGH MOTION ONLY: rapid continuous body thrash hip rock hair whipping
camera handheld whip-pan aggressive push-in no freeze full head shoulders
keep wardrobe from source. Adult. Cel only.
NEGATIVE: photoreal 3D static Ken Burns futa milk neon head crop redress underage
```

**禁止** I2V 首段写 photoreal / natural skin（prompt_assembly 默认坑）。

**续接链（bare 源被拦时）：**
1. 用 **已批 undress 镜末帧** 作 `keyframes/<next>.png`（continue）  
2. 串行 `image_to_video`（防 429）  
3. 收据 `receipts/bare-i2v-partial.json` 写清 moderated 尝试 + 实际路径  
4. **不得**用 Ken Burns 过 motion gate

---

## 2. 高动态门（装片前）

| 项 | IRON |
|---|---|
| 指标 | 本地 `mean_absdiff`（fps=5, 140×248 gray）写 `--rows`；**勿**只信 technical_qa.motion_score 当 final 数 |
| 平常 | mean≥**18** |
| 肉戏 act/climax | mean≥**20**（目标≥24） |
| 流程 | 测 mean → 低动多 take 取 max → `aifilm i2v-motion-gate --root … --write --rows <file>` |
| 桌面 final | 仅 `i2v-final-gate.ok=true` |

`i2v-motion-gate --rows` 参数是 **JSON 文件路径**，不是内联超长 JSON（路径过长会 Errno 63）。

---

## 3. register / 证据链（改 take 后必做）

| 坑 | 铁律 |
|---|---|
| 重拍后 `approved_clip_record` 假失败 | `quality_evidence_is_current` 校验 **邻接镜 clip_sha256**；旧 review 的 neighbours 过期 |
| 只 re-register 不够 | **整轨按时间序 review-shot --approve + register-clip 两轮**（pass1 刷新己镜；pass2 邻接 hash 对齐） |
| act/climax 审 | `--score-coitus` **≥4** 才能 `--approve`（mute-frame 硬拦） |
| pilot 多出来的镜（如 s03） | **移出** `manifest.clips` + `clips/` + `receipts/takes|quality`（否则 inventory `extra=` 拦 final） |

路径：`canonical/cast-states/<char>/{undressed,bare}.png`  
+ `canonical/wardrobe/undress-anchor.png`（max 片 hard）

---

## 4. final / 混音 / 字幕

| 坑 | 铁律 |
|---|---|
| `aifilm final` 默认 **1200s** 杀 plate | 长片/成人 **直调** `scripts/render_final.py`；超时 ≥**1800s**；可用 `--resume` |
| sidechaincompress 混音 **假死**（mixed.wav 大小不动） | 等 >2min 无增长 → **kill** → 简化 `amix`：narr+bgm+native（volume≈1.32/0.56/0.55） |
| `--music` 须 license | 旁挂 `*.license.txt` 或 `--music-license` |
| ffmpeg `subtitles=` / `ass=` 路径空格 / force_style 解析炸 | SRT/ASS 拷 **无空格路径**（如 `/tmp/…`）；失败则 **PIL 逐帧烧字**（本场验证可用） |
| 字幕完成定义 | 抽帧 **像素可见中文**；有 SRT 无烧字 = 未完成 |

BGM：色气 `rnb` volume≈0.55–0.58；显式 `--music`。

---

## 5. 串行纪律

1. I2V **一次一件**（429 resource-exhausted）  
2. 失败 moderated → 改提示重试，**勿**连发 4 路  
3. 429 → sleep 20–40s 再单发  
4. Comfy capacity blocked 时 **勿**假称已走 5090

---

## 6. 完成 / PARTIAL

```text
DONE = film_final.mp4 + ffprobe 时长/分辨率 + 抽帧字幕可见 + motion gate ok
PARTIAL = bare Imagine 拦 / 简化混音 / 未 review-final master_lock
禁止 = 内衣当插入 · 弱动装片 · inventory 多 orphan · 假 DONE
```

---

## 速查命令

```bash
# motion rows 文件
aifilm i2v-motion-gate --root "$ROOT" --write --rows /tmp/i2v-rows.json

# 直调 final（长超时）
python3 "$SKILL/scripts/render_final.py" --root "$ROOT" --out-name film_final.mp4 \
  --tts-backend edge --music "$ROOT/audio/bgm/rnb-primary-ace-step.wav" \
  --music-license "$ROOT/audio/bgm/rnb-primary-ace-step.license.txt" \
  --music-volume 0.56 --music-mood rnb --lipsync off --subs off --plate-cards blank --resume

# 简化混音
ffmpeg -y -i audio/narration.wav -i out/_final_work/bgm_stereo.wav -i audio/native_track.wav \
  -filter_complex "[0:a]volume=1.32[a0];[1:a]volume=0.56[a1];[2:a]volume=0.55[a2];[a0][a1][a2]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.95[a]" \
  -map "[a]" -ar 44100 audio/mixed.wav
```

## 关联
- [high-motion-style-lock](lessons-2026-07-27-high-motion-style-lock-final.md)
- [adult-scale-max-sex-arc](lessons-2026-07-27-adult-scale-max-sex-arc.md)
- [anatomy-milk-futa](lessons-2026-07-29-anatomy-milk-futa-comfy-batch.md)
- [shot-variety-anti-boring](lessons-2026-07-29-shot-variety-anti-boring.md)（观感：重复/无聊 → motion·景别·时长）
- [subs-always-burn-hard](lessons-2026-07-23-subs-always-burn-hard.md)
- [wardrobe-no-redress](lessons-2026-07-21-wardrobe-no-redress-still.md)
- memory: `memory/2026-07-29-evirus-ch04-bulk-final-iron.md`
