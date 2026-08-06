# Memory · 分层路由（人物 × LTX T2V 合成）

**User**: 稳固人物一致性下用 LTX T2V 拼接；T2V 无人物导入 → 合成层；排序主力/fallback。

## 答案

**可以。** T2V 只做 **L2 合成/环境床**；脸只走 **L0 still + L1 I2V**。

## 排序

```
脸静帧  Grok cast          >  FRW i2i(慎)
脸动态  Seedance i2v       >  LTX i2v  >  Grok 720p  >  禁 legacy / 禁 T2V
无脸床  LTX t2v            >  Seedance t2v  >  classic t2v
后期    HyperFrames        >  Remotion
```

## film-spec

- `frw_video_model` = 人物 I2V  
- `frw_env_model: ltx-t2v` = 合成层  
- `shot_role: hero|env|bridge|insert`

## Canonical

`references/lessons-2026-07-20-layer-routing.md`
