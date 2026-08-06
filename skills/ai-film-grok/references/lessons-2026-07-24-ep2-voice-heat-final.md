# Lessons · ep2 出片复盘（声线分轨 + 肉戏强度 + final 工程）

> 2026-07-24 · **P0**  
> 片根：`AI FILM SPACE/0724/ep2` · 用户硬要求：**口白中文、角色日文；禁止突然中日乱切；肉戏动态要够猛；别再犯今天同类错。**

## 一句话

**听感分层固定：说书口白=中文 · 角色开口=日文 · 字幕=中文。**  
禁止为赶片整盘清 `nar_ja`，也禁止同一听感层里无 `speaker` 地中日来回跳。  
肉戏「两倍强度」优先 **I2V 动态 + 口播加长 + 荤字幕**，别赌审核会放行露点/插入像素。

---

## 今天犯过的错 → 以后怎么做

| # | 错误 | 正确纪律 |
|---|------|----------|
| 1 | **声线乱切**：一镜中文、下一镜日文，无 `speaker` 规划，听感像频道乱跳 | 先画 **声线轨**：setup/env/montage/storyteller → 只中文；heroine 自语/对白 → 只日文。相邻镜若换层，中间用静音半拍或纯音乐桥，**不要**无理由中日互跳 |
| 2 | **赶片清掉全部 `nar_ja`** 改全中文「方案 B」 | 用户要 hybrid 时 **禁止** 为省事删日文轨；最多「先出无字幕 plate，再补轨」也不能删字段契约 |
| 3 | **把 `nar_ja` 塞进每一镜**（含纯说书） | 只有 `speaker∈角色` 才写 `nar_ja`；说书镜 **禁止** 填 `nar_ja`/`dialogue_ja`（填了会触发角色日文轨，听感乱） |
| 4 | **字幕用日文 / 口播用中文读日文** | TTS 读 `spoken_text_for_shot`；字幕永远 `nar` 中文。禁止日文 voice 念中文长句、中文 voice 念日文 |
| 5 | **`sub_lead=0.08` → SRT 条重叠** `segment N starts before previous ends` | final 默认 **`sub_lead=0`** 或 cue 写盘前 **钳制非重叠**（`start = max(start, prev_end)`） |
| 6 | **`aifilm final --plate-timeout 900` 杀长片** | 长片 **直调** `scripts/render_final.py`（≥15–30min）；`aifilm final` 的 plate timeout 对 20+ 镜不够 |
| 7 | **`review-shot --approve` 以为已 approved** | review 只写回执；**必须再** `register-clip --status approved --review-receipt …`；换片后旧 review sha 对不上要重 review |
| 8 | **肉戏只加文案不加 I2V** 或 **过激 prompt 全 400 moderated** | 重跑肉镜 I2V 用 **edge-safe 高动态**（rock/thrash/push-in/breath，禁 genital/penetration/squirt 字眼）；`heat.jpg` 作 I2V 源更易炸 → 优先主 keyframe png |
| 9 | **`duration_sec` 写 28s 期望长板，实际跟 6s VO** | 板长跟 **实际口播**；要长肉戏 = **加长 `nar_ja` 喘息句** + 允许 loop 策略，不是只改 JSON 秒数 |
| 10 | **write-spec 连环 fail**（wardrobe/vo spice/size ladder/sex floor） | heat=max 改文案后 **先 write-spec 绿** 再 bulk/final；act 须 bare+sex verbs；六拍 coitus；景别勿 act 内猛开 wide |

---

## P0 · 声线契约（勿再乱）

```text
层 A  口白/说书  storyteller | narrator | env | montage
      TTS = 中文 edge（zh-CN-XiaoxiaoNeural 等）
      字段 = nar 中文 only；speaker=storyteller
      禁止 nar_ja / dialogue_ja

层 B  角色开口  heroine | partner | 具名角色
      TTS = 日文 edge（女 Nanami / 男 Keita）
      字段 = speaker + nar(中文·字幕) + nar_ja(日文·口播)
      禁止 vo_voice=zh-CN-* 读角色镜

层 C  字幕像素  永远中文（caption_lang=zh，烧 nar）
```

### 禁止「突然中日切换」的操作定义

- **坏**：镜序列 `ZH → JA → ZH → JA` 且都是「旁白感」长句（听起来像旁白在换语言）。  
- **好**：  
  - 开场 2–3 镜纯中文说书定调；  
  - 进入身体/情绪后 **角色日文自语** 成块（连续多镜 JA）；  
  - 蒙太奇/新闻/章卡回 **中文说书** 成块；  
  - 块与块之间语言切换 **≤2 次/分幕**，且 `speaker` 变了才切。  
- **自检**：`final` 前打印每镜 `speaker | voice | spoken_lang | first20(spoken)`，相邻镜 `spoken_lang` 跳变须有 speaker 变化理由。

### film-spec 最小钉死

```json
{
  "vo_mode": "hybrid",
  "tts_backend": "edge",
  "dialogue_spoken_lang": "ja",
  "narration_spoken_lang": "zh",
  "caption_lang": "zh",
  "cast_voices": {
    "storyteller": "zh-CN-XiaoxiaoNeural",
    "heroine": "ja-JP-NanamiNeural",
    "partner": "ja-JP-KeitaNeural"
  }
}
```

每镜：

| speaker | nar | nar_ja | vo_voice |
|---------|-----|--------|----------|
| storyteller | 中文说书 | **空** | zh-CN-* |
| heroine | 中文（字幕/叙事） | **必填日文** | ja-JP-NanamiNeural |

---

## P0 · final / 字幕工程

1. plate：`subs=off` + `plate-cards blank`（HF 路径）；交付前 **PIL burn** 中文 SRT（`burn_srt_pil.py`）。  
2. SRT：`sub_lead=0`；写盘前非重叠钳制。  
3. 长片：直调 `render_final.py --force`，勿被 900s wrapper 假失败。  
4. 换 clip 后：review-shot → register-clip（sha 对齐）再 final。  
5. 验收：抽帧 **可见中文**；抽声 **角色段日文 / 说书段中文**。

---

## P0 · 肉戏「两倍强度」现实路径

| 杠杆 | 做 | 不做 |
|------|----|------|
| 动态 | 肉镜 **重跑 I2V** 高 motion edge prompt | 只改 film-spec 形容词 |
| 时长 | 加长 `nar_ja` 喘息；sex_min_ratio 抬到 ≥0.4–0.55 | 空改 duration_sec 不改口播 |
| 听感 | rnb BGM 0.55–0.58；act SFX impact | dark BGM 当色气 |
| 像素 | 暗示 thrash/arch/wet sheen | genital/penetration/squirt 硬词赌审核 |

审核挡了仍 **不降 heat_scale**；用 VO/SFX/动态补偿（见 hardcore-meat-plan 双轨）。

---

## Agent 检查清单（final 前 30 秒）

- [ ] 无「整盘 storyteller 无日文」或「整盘 heroine 无中文说书」的极端误配（按故事需要混合，但 **分层清晰**）  
- [ ] 说书镜无 `nar_ja`；角色镜有 `nar`+`nar_ja`+`speaker`  
- [ ] 相邻镜语言跳变有 speaker 理由（禁止无理由 ZH/JA 乒乓）  
- [ ] `write-spec` ok；24 镜 clip status=approved 且 review sha 匹配  
- [ ] `sub_lead=0` 或 SRT clamp；plate 后 burn 中文  
- [ ] 肉戏至少对 peak 镜做过高动态 I2V 或明确 soften-log  

---

## 关联

- [character-dialogue-ja](lessons-2026-07-23-character-dialogue-ja.md)（本课强化「禁乱切」）  
- [subs-always-burn-hard](lessons-2026-07-23-subs-always-burn-hard.md)  
- [sex-hard-floors](../memory/2026-07-21-sex-hard-floors.md) · [sex-vo-spice](lessons-2026-07-21-sex-vo-spice.md)  
- [hard-defaults](hard-defaults.md) · [voices](voices.md)  

## 验收句（用户向）

「角色说话是日文，旁白是中文，字幕是中文；听起来不会一镜中文一镜日文乱跳；肉戏镜头动得够猛。」
