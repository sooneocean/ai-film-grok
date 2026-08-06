# Memory · 2026-08-05 · LTX2.3 有声成人第三轨 + FRW i2i 修复

**完整规划**：[docs/plans/2026-08-05-ltx23-adult-audio-lane.md](../../../docs/plans/2026-08-05-ltx23-adult-audio-lane.md) · [weapon-lane](../references/weapon-lane-matrix.md)

## 用户原话
> 帮我规划把 frw ltx2.3 当成大尺度成人内容生成手段 而且他还有 audio … 还有 frw 的 i2i 做修复手段 帮我完整规划在流程内

## 三句话
1. **`ltx23_adult`**：safe 对白/soft → LTX 2.3 `img2video-audio` 原音；**bare/肉戏永远 H3**。
2. **FRW i2i** = still-challenge 修底片（毒/弱/hijack）→ 人 promote → 再 LTX/H3。
3. 成人 **不** 静默全片 LTX primary；403 不降 heat，签名切 H3。

## 检查清单
- [ ] `AIFILM_I2V_PROFILE=ltx23_adult` 或 lanes `allow_ltx_dialogue`
- [ ] canary 绿再 bulk LTX
- [ ] restricted 镜 `provider_lock=comfy-h3`
- [ ] safe 对白 `cloud_ltx23_audio` + `prefer_native`
- [ ] 坏 still → `still-challenge` ≥30s unit
- [ ] register endpoint `frw_ltx23_img2video_audio`

## 触发口诀
裸/插/高难→H3 · 过审有声对白→LTX · 底片烂→i2i · 云拒审→H3 不降尺度
