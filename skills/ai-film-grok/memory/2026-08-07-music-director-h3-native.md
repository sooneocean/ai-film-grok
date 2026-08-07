# Memory · 2026-08-07 · 音乐总监（H3 原声）

> **用户**：声音是 H3 原音；要音乐总监控 BGM 和语音、调爆音、把不对的台词 mute/剪掉，取决于总监规划。

## 三句

1. **prefer_native** 主链：错台词 v1 = **音频 mute**（时间窗或整镜 silence），画面不动。
2. 单一真相：`audio/music-director-plan.json` → set/audit → apply → `audio/native_directed/` + final 自动读。
3. 爆音：`peak_fix=auto` + true-peak；apply 默认 light 处理；非 wav（mp4/m4a）经 ffmpeg 解码。

## 清单

- [ ] draft plan
- [ ] `set --mute-window` / duck / mute-entire
- [ ] `audit` 看 hot 镜
- [ ] apply
- [ ] review 抽听
- [ ] final

## 链

- stage：`references/stages/voice.md` · `post.md`
- 代码：`audio/music_director.py` · CLI `aifilm music-director`
- IRON：原声 XOR TTS · hard-defaults
