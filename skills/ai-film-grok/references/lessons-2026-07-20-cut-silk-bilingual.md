# Lessons · 转场丝滑 + 中英双字幕（剪辑语法 × 设计后期）

> 2026-07-20 · **P2 时空连续 · P3 动能连续 · P5 分层表达**  
> 用户诉求：镜间不要割裂；中英双字幕；盘点 HF/Remotion 并沉进 skill。

## 一句话

**接戏靠硬切 + 动作中切；丝滑靠剪辑语法与设计胶水——禁止用 dissolve 盖 continue 字节缝。**  
**国际字幕靠 `caption_mode: zh_en` + 每镜 `nar_en`，由 HyperFrames/Remotion 画双行，不改中文 TTS。**

---

## 1. 为什么会有「影片跟影片之间」的割裂

| 原因 | 层 | 修法 |
|------|-----|------|
| 每镜重新起跳（cast 重画） | A 戏 | continue：`extract-frame --promote-keyframe` 字节复用 |
| 切在动作结束 hold | A 戏 | `cut_on: mid_motion`；promote 用动作中帧 |
| plate 跟 VO 不同轴 | B 拼 | `visual_fit: "vo"`；hard match-cut |
| soft dissolve 在 continue 缝 | B 拼 | **禁止**；双影更糊 |
| 每镜调色/字幕样式跳 | C 设计 | 全片同一 caption preset + 统一 grade |
| 声轨每镜「断一下」 | B/C | 连续 `audio/mixed.wav` underlay（天然 L/J-cut） |

用户要的「电影后制剪接」在本管线里拆成：

### 1a. 画面剪辑（FFmpeg plate）

| 手法 | film-spec / 行为 | 说明 |
|------|------------------|------|
| **Match cut（硬切）** | `chain_mode: continue` → intent **hard** | 末帧=下镜首帧 |
| **Cut on action** | `cut_on: mid_motion` | 切在动作中 |
| **Soft / dissolve** | 仅 **非 continue** 场景缝 | `transition_intents: soft` |
| **Hold dissolve** | afterglow 着陆 | `hold` + 略长 xfade |
| **转场 fluency** | `transition_fluency: silk\|punchy\|auto` | silk：非 continue 更偏 soft；**不**改 continue=hard |

### 1b. 声音剪辑（已有能力 · 要写进话术）

| 手法 | 实现 |
|------|------|
| **L-cut / J-cut** | 连续 mixed.wav underlay；画面 hard cut 时旁白/BGM 不断 |
| **BGM 侧链** | rnb sidechain；VO 让路 |
| **SFX 跨缝** | auto_sfx 点缀不绑死硬切 |

### 1c. 设计后期「观感胶水」（HF/Remotion · 允许）

| 手法 | 实现 | 禁止 |
|------|------|------|
| 全片统一字幕样式 | preset ecchi-rnb / minimal | 每镜换字体 |
| 字幕入场动效 | GSAP y+opacity | 盖住接戏双影 |
| 连续 vignette/grade | CSS 全片 overlay | 每缝换滤镜 |
| 片头/片尾 | designed card on **blank pad** | plate 烧字 + 设计字 |
| 场景缝 soft xfade | 仅 multiclip 非接戏 | underlay 上 dissolve continue 缝 |

---

## 2. film-spec 字段（新）

```json
{
  "transition_fluency": "silk",
  "caption_mode": "zh_en",
  "scenes": [{
    "shots": [{
      "id": "shot01",
      "nar": "她掀帘出来，锁骨还挂着热气。",
      "nar_en": "She parts the curtain, collarbones still warm.",
      "dsl": { "chain_mode": "continue", "cut_on": "mid_motion" }
    }]
  }]
}
```

| 字段 | 值 | 默认 |
|------|-----|------|
| `transition_fluency` | `auto` → silk（惊悚 tone → punchy）\| `silk` \| `punchy` | auto |
| `caption_mode` | `zh` \| `zh_en` \| `en` | zh |
| `shot.nar_en` | 英文行（**不**默认进 TTS） | 可选；zh_en 时 write-spec soft 报告缺省 |

---

## 3. 中英双字幕

| 规则 | 说明 |
|------|------|
| 中文 VO | 仍 `tts_backend: edge` + `nar` |
| 英文字幕 | `nar_en` 只上画面，不朗读（除非用户改 VO 语言） |
| 绘制层 | HyperFrames 双行 / Remotion `pre-line` |
| 样式 | 中文主行 1.0em；英文 0.72em 略淡 |
| 缺 `nar_en` | soft report，不 hard fail；agent 应补译 |

```bash
# 写好 caption_mode + nar_en 后 re-export + re-final
"$AIFILM" write-spec --root "<root>"
"$AIFILM" final --root "<root>" --post-engine hyperframes \
  --lipsync off --music-mood rnb --tts-backend edge --compose-preset auto
```

---

## 4. Agent 剪辑检查清单（防割裂）

- [ ] continue 缝：`frame-chain` / promote SHA 字节相等  
- [ ] continue 缝：`transition_intents` = **hard**（silk 不覆盖）  
- [ ] 非 continue：silk 下可用 soft/hold + 轮转 `transition_styles`  
- [ ] plate：`visual_fit: vo` 动能接戏时  
- [ ] 设计后期：`plate-cards blank` + `subs off`  
- [ ] 观感：全片同一 caption preset；可选双字幕  
- [ ] 用户抱怨「像两段片」：先查字节接戏与 mid_motion，再查 soft 是否误用在 continue  

---

## 5. 与旧教训关系

| 旧 | 本课 |
|----|------|
| [motion-transition](lessons-2026-07-20-motion-transition.md) soft soup / hard 断点 | 增加 fluency silk + continue 强制 hard |
| [action-fluency](lessons-2026-07-20-action-fluency.md) mid_motion | 仍是像素层主药 |
| [designed-post-fluency](lessons-2026-07-20-designed-post-fluency.md) HF 胶水 | 明确 glue 白名单 / 黑名单 |
| [title-double-burn](lessons-2026-07-20-title-double-burn.md) | 标题只画一次；本课补字幕双行 |
| [hf-remotion-capability-matrix](hf-remotion-capability-matrix.md) | 能力盘点 |

## 不可宣称

- soft dissolve = 动作连续  
- HF 场景转场 catalog 已全部启用在 I2V 接戏缝  
- 只有中英字幕 = 已英语配音  
