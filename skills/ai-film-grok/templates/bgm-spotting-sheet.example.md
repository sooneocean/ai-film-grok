# BGM Spotting Sheet — 音乐标注表模板

> P3-3 BGM spotting + 情绪曲线 · music_spotting 结构化
> BGM 不再是整段 bed loop——有入点出点、有情绪段、与 beat 对齐。

## 音乐标注

| label | start_sec | end_sec | fade_in_sec | fade_out_sec | emotion | beat_ref | intensity |
|---|---|---|---|---|---|---|---|
| main_theme | 0.0 | 8.0 | 2.0 | 0.0 | 孤独·雨夜 | bt_001_hook | 3 |
| tension_rise | 8.0 | 15.0 | 0.5 | 0.0 | 犹豫·靠近 | bt_002_approach | 5 |
| silence_break | 15.0 | 18.0 | 0.0 | 0.0 | 留白·信任 | bt_003_rising | 1 |
| climax_hit | 18.0 | 25.0 | 0.0 | 0.0 | 释放·接受 | bt_005_climax | 9 |
| outro_echo | 25.0 | 30.0 | 0.0 | 3.0 | 余韵·新关系 | bt_006_resolution | 4 |

## 情绪曲线

```
intensity
  10|          ___
   9|         /   \        ← climax_hit
   7|        /
   5|   ___/              ← tension_rise
   3|  /                  ← main_theme
   1|        __           ← silence_break
   0|________________________
    0  5  10  15  20  25  30  sec
```

## 设计原则

1. **music_in/out**：精确入点出点，不再是整段铺满
2. **fade_in/out**：平滑过渡，避免突兀
3. **emotion**：每段音乐服务一个情绪功能
4. **beat_ref**：与戏剧节拍对齐——音乐跟着故事走
5. **intensity**：0-10 情绪强度曲线，与 pace_chart.intensity 对齐
6. **留白也是设计**：silence_break 段不铺音乐，让环境声说话
