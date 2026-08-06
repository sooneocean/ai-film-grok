# Lessons · 分层路由：人物一致性 × LTX T2V 合成层

> 2026-07-20 · **P1 身份连续 · P5 分层表达**  
> 用户问题：LTX T2V 没有人物导入，能否在**稳固人物一致性**下用 T2V 产出再拼接？

## 一句话

**可以——但 T2V 只能做「合成层 / 环境层」，不能做人脸身份层。**  
**有脸的戏 = hero I2V（Grok still → Seedance/Grok 动）**；  
**无脸的床 / 空镜 / 氛围 = LTX T2V 主力**，拼进时间线。

---

## 为什么不能「全片 LTX T2V」

| 事实 | 含义 |
|------|------|
| LTX T2V **无**角色参考图入口 | 每镜人物会漂移，锁不住 cast |
| 一致性靠 **frame-1 定妆图 + I2V** | 人物镜必须 I2V，不是 T2V |
| T2V 探针可用（completed） | 适合**无脸**素材量产 |

类比：定妆照 + 图生视频 = 主演；T2V = 空镜空城、光影、雨、霓虹床——剪进片里当胶水与呼吸，不替主演演戏。

---

## 四层生产（谁主力 / 谁 fallback）

### 总表

| 层 | 职责 | **主力 Primary** | **Fallback** | **禁止当主力** |
|----|------|------------------|--------------|----------------|
| **L0 身份静帧** | cast / style / lookbook | **Grok** `image_edit(cast)` | FRW img2image（慎：易混 provider） | 纯 T2I 每镜重抽脸 |
| **L1 人物动态 A-roll** | 有脸/有角色的戏 | **Seedance i2v** `seedance-2-fast-i2v` | ① `ltx-i2v`（若 502 跳过）② **Grok I2V 720p** | legacy `img2video`；**LTX T2V** |
| **L2 合成 / 环境 B-roll** | 空镜、氛围、转场垫、无脸 insert | **LTX T2V** `ltx-t2v` | Seedance t2v → classic text2video | 用 T2V 生成「像角色」的脸并声称一致 |
| **L3 设计后期** | 字幕/片头/grade/双字幕 | **HyperFrames** | Remotion | Ken Burns 冒充 I2V |

### 拼接点（FFmpeg plate）

```text
[ L2 env bed ]──soft/hold──[ L1 hero A ]──hard continue──[ L1 hero B ]──soft──[ L2 env ]
         ↑ LTX T2V                          ↑ I2V + promote                     ↑ LTX T2V
```

- **continue 人物缝**：hard match-cut（字节 promote）  
- **env ↔ hero 缝**：可用 silk soft/hold（场景跳切胶水）  
- 声轨连续 mixed.wav = L/J-cut  

---

## film-spec 字段

```json
{
  "frw_video_model": "seedance-2-fast-i2v",
  "frw_env_model": "ltx-t2v",
  "frw_width": "720",
  "frw_height": "1280",
  "scenes": [{
    "shots": [
      {
        "id": "shot01",
        "shot_role": "hero",
        "dramatic_function": "hook",
        "dsl": { "cast": ["heroine"], "chain_mode": "continue", "motion": "…" }
      },
      {
        "id": "shot01b",
        "shot_role": "env",
        "dramatic_function": "bridge",
        "nar": "粉紫灯牌在雨里呼吸。",
        "dsl": {
          "subject": "neon BOYS CAFE sign, rain, no people",
          "motion": "neon flicker, rain on glass, locked static"
        }
      }
    ]
  }]
}
```

| `shot_role` | 含义 | 引擎 |
|-------------|------|------|
| **`hero`**（默认） | 人物/身份戏 | still=Grok cast → motion=`frw_video_model` I2V 链 |
| **`env`** | 环境/空镜床 | `frw_env_model` = **ltx-t2v** |
| **`bridge`** | 转场垫 | 优先 ltx-t2v；可短 hold |
| **`insert`** | 物件/细节无脸 | ltx-t2v 或 hero 的 ECU 物件 I2V |

write-spec 写入：

- `spec._layer_routing` — 全片主力/fallback  
- `shot._recommended_engine` — 每镜该调谁  
- `spec._layer_report` — soft 警告（hero 无锚 / env 写了脸）

---

## Agent 操作清单

1. **先** lock-style + cast master（L0）  
2. 分镜标 `shot_role`：人物戏 `hero`，空镜/氛围 `env`  
3. **hero**：upload keyframe → Seedance/Grok I2V → register `frw_seedance_i2v` / `image_to_video`  
4. **env**：`ltx-t2v` 竖屏 720×1280 string → register `frw_ltx_t2v`  
5. plate：hero continue hard；env 接 hero 可用 soft  
6. HF：字幕/片头 only（L3）  

**禁止**：

- 用 LTX T2V 生成「长得像 Rin 的人」当主角  
- 半片 Grok still + 半片 FRW T2V 脸混同一角  
- 无 promote 却标 continue  

---

## 主力排序口诀

```text
脸   → Grok still  >  …  
动脸 → Seedance i2v > LTX i2v(若好) > Grok I2V  >  禁 legacy
无脸 → LTX t2v     > Seedance t2v   > classic t2v
壳   → HyperFrames  > Remotion       > 纯 ffmpeg 烧字
```

## 验证

```bash
"$AIFILM" write-spec --root <root>
# 查 film-spec.json: frw_env_model, _layer_routing, 每镜 shot_role
"$AIFILM" frw newvideo --model ltx-t2v --prompt "neon rain no people" \
  --width 720 --height 1280 --duration 5 --fps 24 --wait
```
