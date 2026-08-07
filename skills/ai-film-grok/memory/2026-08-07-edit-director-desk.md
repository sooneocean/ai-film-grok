# Memory · 2026-08-07 · 剪辑总监（edit-director）

> **用户**：剪辑层需要剪辑总监统筹最后输出；可用 ffmpeg / hyperframes / remotion。

## 三句

1. **机床齐了，缺车间主任** → `post/edit-director-plan.json` 唯一真相。
2. **只编排**：plate=FFmpeg；design 默认 HF；Remotion 仅 explicit；禁双正式 final。
3. **动词**：draft → apply（editor_cut+post-route）→ run（dry-run 或 `--execute` 调既有 final）。

## 清单

- [ ] `edit-director draft`（**ship-prep 也会自动 draft**）
- [ ] `apply` 锁 caption 路径
- [ ] `run` 看 stages；确认后 `--execute`
- [ ] `final` 无 CLI 时读 plan 路由（R2）
- [ ] `post-doctor` 对账 plan vs post-route
- [ ] `gate-auto` + `review-final`（final≠complete）
- [ ] 可选 `snapshot` / `activate` 多版本 cut

## 链

- 机读：`post/edit_director.py` · hard-defaults「剪辑总监」
- stages/post 快卡 · [todoplan](../../../docs/plans/2026-08-07-edit-director-todoplan.md)
- 姊妹桌：`music-director`（mute 不剪画面）
- R2：`workflow_pack.ship_prep` · `post_doctor` · `cmd_final` · `closeout._final_next_cmd`
- R3：`apply` 同步 post-plan · editorial EDL/trims · `checklist`
