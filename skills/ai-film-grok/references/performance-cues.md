# 声音表演谱

`performance_cue` 是每句对白的表演控制，不是角色身份锁，也不是把所有意图塞进 prompt。

```json
{
  "emotion": "teasing",
  "intensity": 0.72,
  "rate": "+6%",
  "pitch": "+2st",
  "volume": "-3%",
  "delivery": ["breathy", "whisper_start", "emphasis:last_phrase"],
  "pauses_ms": [180, 320],
  "pronunciation": {},
  "language": "ja",
  "take_seed": 42
}
```

默认值保持旧行为：中性情绪、无额外停顿、`+0%` 语速／音量／音高。`tone_tags` 只在没有显式 `performance_cue.delivery` 时作为初始 delivery 标签。

## 后端行为

| 后端 | 表演控制 | 默认 | 失败行为 |
|---|---|---:|---|
| `edge` | rate/pitch/volume、可审计 SSML、便携标点停顿 | ✅ | 硬失败 |
| `qwen3` | voice design／clone + instruction | ❌ | 未安装或无参考音时硬失败 |
| `higgs` | 多说话人／情绪／联合音频的 adapter 边界 | ❌ | 未配置 `HIGGS_AUDIO_ARGV` 时硬失败 |
| `minimax`／`fish`／`external` | 现有 provider 参数 + 表演 instruction receipt | ❌ | 不跨 provider 静默替换 |

每次合成返回 `performance_hash`、规范化 cue 和 provider 编译结果。真实质量仍需 `tts-ab` 试听与人工锁定；测试通过不等于艺术质量通过。

## BGM 响应

`write-spec` 会写入 `_performance_bgm`，`final` 会把平均表演强度转换为可解释的 BGM gain、VO duck 和尾部余韵参数，并写入 `audio/mix_report.json` 的 `performance_bgm`。
