# Memory · 2026-08-04 · H3 效果最大化

**完整课**：[lessons-2026-08-04-h3-max-effect.md](../references/lessons-2026-08-04-h3-max-effect.md)

## 用户原话
> 继续跑通 思考哪些角度可以使用这个模型  
> 好啊 把这个经验写回项目 让我们可以把h3效果发挥到最大

## 三句话
1. **I2V 锁脸主责**（主角/肉戏/续镜）；**R2V 补能量与狠嘴 CU**；**T2V 只做无脸环境**。
2. **高动靠狠 prompt + 状态 still**（I2V 可从 ~4 提到 ~23），不是改走 T2V；续镜 = **末帧→I2V**（接缝 L1≈7.7）。
3. 换模式前 **free-memory**；对白注入现已与自定义 prompt **合并**（禁再被 `s_*.i2v.txt` 吃掉）。

## 检查清单
- [ ] restricted 镜 `aifilm h3 list` 可见
- [ ] 有 still → `--mode i2v`；参考链/大嘴 → `r2v`；env → `t2v`
- [ ] 对白镜有 `audio_cues.spoken_text` + on_camera；跑后 prompt 含「line:「…」」
- [ ] 续镜：抽末帧写入下一镜 still 再 I2V
- [ ] 每镜前 `comfy free-memory --confirm`；capacity ready
- [ ] `h3 run --register` → manifest candidate + `use_clip_audio`
- [ ] bulk 仍等人批 pilot（candidate ≠ 可 bulk）

## 片例
`artifacts/5090-evaluation/h3-angles-runthrough/` · `h3-e2e-runthrough/` · `h3-stress-ab-20260804/` · `h3-quality-ab-20260804/`
