# Memory · 2026-08-07 · 音乐总监（H3 原声）

> **用户**：声音是 H3 原音；要音乐总监控 BGM 和语音、调爆音、把不对的台词 mute/剪掉，取决于总监规划。

## 三句

1. **prefer_native** 主链：错台词 v1 = **音频 mute**（时间窗或整镜 silence），画面不动。
2. 单一真相：plan → **set/batch/audit/checklist** → apply → `native_directed/` → final。
3. 爆音：`audit --apply-peak-auto`；非 wav 经 ffmpeg；apply 默认 light。

## 清单

- [ ] draft
- [ ] set / batch（mute 窗 · duck）
- [ ] audit（hot）
- [ ] checklist 抽听
- [ ] apply → final

## 链

- `audio/music_director.py` · CLI `music-director`
- stages/voice · hard-defaults
