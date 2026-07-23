# P0 · 字幕必须进画面（2026-07-23 · E病毒案复盘）

## 现象
用户反复反馈「怎么没有字幕」。根因不是「没生成 SRT」，而是 **成片像素里没烧字**。

## 根因（两层）

1. **`final --post-engine hyperframes` 默认 plate `subs=off`**  
   HF 路径假定设计层会画字幕；HF 未真烧字时，画面仍是空的。  
   同案已写：`lessons-2026-07-22-shaofu-cast-subs-bgm-final.md` —— **必须** `render_final --subs burn` 补；禁止为过 review 清空 `final.srt`。

2. **本机 Homebrew ffmpeg 常无 libass**  
   `ffmpeg -vf subtitles=...` 会直接 `No such filter: 'subtitles'`。  
   **正确烧字**：走 `render_final.py` 的 **PIL `sub_png` + overlay**（`--subs burn`），不要依赖 libass。

3. **手搓 final / 超时降级 mux**  
   风格重渲、timeout 后用 `video_silent + mixed.wav` 直 mux 时，若漏跑 burn 阶段 → 再次无字幕。

## 硬规则（agent 每次 final）——**分阶段，不假定**

`aifilm final --post-engine hyperframes` 固定四阶段（见 `scripts/final_stages.py`）：

| 阶段 | 动作 | 字幕归属 | 验收 |
|------|------|----------|------|
| `stage_plate` | `render_final --subs off --plate-cards blank` | **无**（plate 只出 VO/BGM/片） | plate ok + `out/final.srt` 已写 |
| `stage_hf` | HyperFrames export+render | **HF 设计字幕** | `captions_placed` / index `.caption` |
| `stage_caption` | 像素探针；失败则 **显式** `burn_srt_pil` recovery | hyperframes 或 pil_recovery | 底栏探针或 recovery ok |
| `stage_deliver` | 写 `receipts/final-stages.json` + `caption_owner` | 记账 | `burned_in` 与 owner 一致 |

| 步骤 | 命令/动作 | 验收 |
|------|-----------|------|
| A | 生成 `out/final.srt`（非空） | `wc -l final.srt` > 0 |
| B | HF 负责设计字幕；**禁止**假定已进像素 | stage_caption ok |
| C | 导出桌面的 **主 mp4 必须是 burned 版** | 用户打开即见字 |
| D | SRT 仍保留作外挂备份 | 不删 `final.srt` |

**禁止**：
- 只交付 `subs=off` 的 HF plate 当「成片」
- 用「有 srt 外挂」代替画面内字幕（用户竖屏完播默认不挂外挂）
- 因 review-final / cut-boundary 失败而清空 SRT

## 本机烧字配方（无 libass）

```bash
# 首选：render_final 内置 PIL burn
python3 "$AIFILM_SCRIPTS/render_final.py" --root "<root>" --subs burn ...

# 若已有 film_final 无字 + final.srt：
# 用 render_final.sub_png + ffmpeg overlay 分批烧（见 session 2026-07-23 脚本）
# 或：aifilm final --post-engine ffmpeg --subs burn
```

## 抽帧验收（强制）

```bash
ffmpeg -y -ss 5 -i out/film_final.mp4 -frames:v 1 /tmp/subcheck.jpg
# read_file /tmp/subcheck.jpg → 必须看到中文字幕条
```

无字 = **未完成**，不得报 DONE。

## 关联
- P0 字幕空窗：`lessons-2026-07-22-shaofu-cast-subs-bgm-final.md`
- Agents.md 日常影音 Combo · 字幕空窗
