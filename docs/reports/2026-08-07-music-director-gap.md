# Music Director gap 对账（2026-08-07）

## 结论

零件半套已有；缺「总监岗」闭环。本轮已补 **plan → apply → review → final 读 directed**。

| 零件 | 路径 | 本轮 |
|------|------|------|
| music_cue / duck | `audio/music_cue.py` | 复用 draft BGM |
| native XOR lane | `final/native_audio.py` | 不破；silence=整镜 |
| 全局 alimiter | `render_final` mix | 保留 |
| **mute 时间窗** | — | **NEW** `music_director` |
| **peak 按规划** | — | **NEW** peak_fix auto |
| **CLI 岗** | — | **NEW** `music-director` |
| ASR 自动判错句 | — | residual（人写窗） |
| 画面剪台词 | editor_cut | residual（非 v1） |

## 接线

- plan：`audio/music-director-plan.json`
- stems：`audio/native_directed/{shot_id}.wav`
- receipt：`receipts/music-director-apply.json`
- final：`resolve_directed_native_path` + BGM overlay on `shot_dicts`
