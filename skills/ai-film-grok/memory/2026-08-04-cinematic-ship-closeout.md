# Memory · 2026-08-04 · 电影规格 α–ε 全波收口

**代码**：`true_video_policy` · `edit_policy` γ · `five_track` · `cinematic_gate` · closeout 阶梯  
**版本**：plugin **2.39.9**（α–ε + gate-auto 机读过闸）

## 用户原话
> 工作流核心 grok i2v and h3 r2v i2v；不接受图片运镜；只接受生成视频剪辑；最终像电影规格  
> go / 推进到最后

## 三句话
1. **Still 只作 I2V 输入**；hero 轨只许 Grok/H3 生成 mp4。
2. **电影感四闸**：介质 · 动能 · 意涵/VO-fit · 5 轨声；一键 `cinematic-gate`。
3. **交付诚实**：export-desktop / closeout 均要 gate 绿，不许静默 PARTIAL 当 DONE。

## 检查清单
- [x] α true-video register/preflight/final
- [x] β camera serves event · variety framing
- [x] γ visual_fit=vo · mid_motion · freeze≤0.15s
- [x] δ five-track · -16 LUFS · sex_sfx
- [x] ε cinematic-gate CLI + export + dispatch
- [x] closeout status/run 合入 cinematic_gate

## 作战序（成片）
```text
bulk Grok+H3 → ship-prep → gate-auto → cinematic-gate
→ final (HF+rnb) → review-final(人) → closeout run → export-desktop
```
