# Sound Design Sheet — 声音设计表模板

> P3-2 声音分层混音 · dialogue/SFX/ambience/foley/music 独立轨
> 每场戏的声音设计：环境声/动效/拟音/对白/音乐分层。

## 场景：雨夜街头

### 轨道分层

| 轨道 | 内容 | gain | duck_to_bgm | 备注 |
|---|---|---|---|---|
| **dialogue** | hero/partner 对白 | 1.0 | true | VO 增益 1.32，侧链 duck BGM |
| **sfx** | 雨声、脚步声、伞撑开声 | 0.6 | false | sfx_level=rich |
| **ambience** | 城市远处的车流/霓虹电流声 | 0.4 | false | 持续铺底 |
| **foley** | 衣物摩擦/手表声/湿地面脚步 | 0.3 | false | 细节拟音 |
| **music** | rnb 情绪底乐 | 0.55 | n/a | bed_gain_hint=0.55，侧链 duck |

### 混音时间线

| 时间 | 事件 | 轨道 | 动作 |
|---|---|---|---|
| 0.0s | music_in | music | 淡入 rnb 底乐 2s |
| 3.5s | sfx_accent | sfx | 伞撑开声 +0.2s |
| 5.0s | duck | music | 对白开始，BGM duck -6dB |
| 12.0s | sfx_accent | foley | 脚步入水坑 |
| 15.0s | music_out | music | 淡出 3s |

### 响度标准

- 对白轨目标：-23 LUFS（EBU R128）
- 整片目标：-16 LUFS（流媒体）
- True Peak：≤ -1.5 dBTP
- `lufs_strict: true` 时超出范围为 hard fail
