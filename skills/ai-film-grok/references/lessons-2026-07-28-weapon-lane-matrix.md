# 武器排列组合 · 最大火力（2026-07-28）

## 用户意图
场景类可用 FRW T2V；尺度小可用 Grok Video 1.5；肉戏/露乳靠 5090。要思考如何组合发挥最大力量。

## 三层车道（不要混职责）

| 层 | 镜头类型 | 主武器 | 备胎 | 禁止 |
|---|---|---|---|---|
| **L0 静帧** | 人脸/衣着/bare 锚 | **Comfy Qwen i2i 5090**（+ 日后 FRW img2image 双打） | Grok image_edit（易审） | 全装 cast 当 bare 源 |
| **L1 人物戏** | hero / 对白 / 肉戏 I2V | **对白 FRW LTX**；**肉戏 5090 MiniMax H3**（pilot · ≤8s · mp0.2） | Grok 1.5 仅 **非露** setup | 肉戏硬塞 Grok；Wan 本地退役 |
| **L2 场景/空气** | env / bridge / insert / 墙外/白板空镜 | **FRW `ltx-t2v` / text2video** | classic t2v · Seedance t2v | 用 T2V 冒充脸一致 |

## 并行时间轴（真省墙钟）

```
时间 →
5090 GPU:  [静帧 i2i bare] → [Wan 肉戏串行 turbo] → [可选升画质]
云 Grok:   ........ [setup 非露 I2V 并行] ........ [轻 afterglow 试]
云 FRW:    [env T2V 并行提交] ........ [query 回收] ........
本机 CPU:  [TTS/BGM/SRT 全程可并行] → final
```

**原则**：GPU 只做 GPU 才做得好的；场景/口白不要占 5090。

## 决策树（每镜 5 秒）

1. 要**同一张脸/同一件衣着状态**？ → L0 still 锁死 → L1 I2V（Wan 或 Grok）
2. 只要**气氛/空间/空镜**、人物可虚/可远？ → **L2 FRW T2V**（不锁脸）
3. 露乳/插入/bare？ → **只 Wan**（+ Qwen 补图）
4. setup 未露、动作轻？ → **Grok 1.5 480p** 抢时间
5. 通片未齐？ → **一律先低压**；selects 后再升

## 本集 ch04 映射

| 内容 | 武器 |
|---|---|
| 墙外/检疫区建立空镜 | FRW T2V（修好 endpoint 后） |
| 沈筱露乳/前戏/办事 | 5090 Qwen still + Wan turbo |
| 白板公式环境 B-roll | FRW T2V 或 远景 Wan |
| 口白中文 | Edge TTS（已并行完成） |
| BGM | rnb 曲库 |

## 状态注意
- FRW **key 有、平台 endpoint 曾 404** → L2 车道修好前先用 5090 扛；好了立刻把 env 卸出 GPU 队列
- Grok bare → moderated；**不要再烧额度试肉戏**
- 单卡 Wan 禁止双开当真并行

## 最大力量一句话
**脸与衣着与尺度：5090（Qwen+H3）；空气：FRW T2V；轻人物非露：Grok；对白：LTX；声音：Edge+rnb——GPU 只打最贵的仗。**
