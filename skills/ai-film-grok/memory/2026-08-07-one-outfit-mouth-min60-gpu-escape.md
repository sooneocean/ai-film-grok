# Memory · 2026-08-07 · 定装一装 + 嘴动片长 + 外片锁 GPU 逃逸

**片例**：`/Users/dex/AI FILM SPACE/0806/abroad-slut-manhua-h3-gen2`  
**交付**：`out/gen2-ship-mixed.mp4`（≈66.5s · Grok I2V）· `receipts/min60-one-outfit-mouth.json` · `receipts/SESSION_WRAP.md`

## 用户原话
> 衣服还是脱了很多次 这问题没解决  
> 剧情太复杂了 只要讲好几个事情就好  
> 片长太短了 然后嘴巴都没动啊 这根本不能 我需要至少一分钟 你可以继续i2v r2v延续  
> 把教训写回记忆

## 三句话
1. **一装 = still 家族一致，不是「少切肉戏」**：红腰马甲 / 白束腰+红袖 / 全裸床单 混剪 = 观感「脱了很多次」。交付前抽帧验同装；I2V 须 `--still` 定装 still + prompt 写死 NEVER undress；禁 continue_handoff 乱代装。
2. **对白交付禁静帧 Ken Burns**：用户要嘴动 → 必须真 I2V/R2V（H3 或 **Grok Imagine Video**）；口白 Edge 可叠，但画面须 articulatory 张合。片长跟故事，用户点 ≥1min 则镜数×单镜秒数够，禁 12s 三拍糊弄。
3. **外片 ACTIVE `gpu-owner-lock` + guardian 时禁抢 5090**：被 kill 就 PARTIAL/换轨，**勿对杀 guardian**。保交付可走 **Grok 云端 I2V**（不占 5090）；H3 等 lock RELEASED 再重跑。剧情先砍到 **3–5 件事** 再 bulk。

## 检查清单
- [ ] 成片抽帧：全片 corset/袖色一致，无「红腰↔白腰↔裸」跳装
- [ ] 对白镜：同镜多时间点嘴形有变（非 zoompan 死脸）
- [ ] 片长 ≥ 用户下限（默认故事优先；点名 1min 则 ≥60s）
- [ ] 提交 H3 前读他片 `receipts/gpu-owner-lock.json`；ACTIVE 外 owner → 零 submit 或 Grok 逃逸
- [ ] 剧情：单集 3–5 beat，禁 24 镜杂弧硬塞一集

## 链
- 多 agent GPU：[multi-agent-gpu-no-hog](2026-08-06-multi-agent-gpu-no-hog.md) · hard-defaults 禁 hog  
- 要影片不要图 / 禁 hero Ken Burns：hard-defaults `true_video_policy`  
- 卸装不回穿：[wardrobe-no-redress](2026-08-06-wardrobe-no-redress-fullnude-fallback.md)  
- 对白原声 XOR TTS：[native-xor-tts](2026-08-06-native-xor-tts-no-double-dialogue.md)  
- 双片排水：[dual-film-drain](2026-08-06-dual-film-drain-takes-progress.md)
