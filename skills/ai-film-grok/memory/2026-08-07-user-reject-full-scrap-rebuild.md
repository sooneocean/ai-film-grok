# Memory · 2026-08-07 · 用户全盘否决 · 打掉重练（P0 · abroad gen1 崩片）

**完整课**：见同日 identity-generation-lock · no-midframe-composite · partner-cast-master

## 用户原话
> 完全不OK 脸都漂移了 人物都不一样 男女混在一起 语音也有问题 剪辑转场不平滑 我实在看不出哪里是好的 都是坏的 打掉重练

## 三句话
1. **贴脸 / 混代 / softskip plate 不是成片**：`verified` 只验 keyframe、final 有声干净，**都不等于**角色对、性别对、剪辑可看。  
2. **打掉重练 = 新 film root + 新 cast generation**；旧 root 标 `FAILED_SCRAP`，**禁止** clips/stills/archive 混进 gen2。  
3. **先定妆人批 → enroll → 整帧 still（禁 paste）→ pilot 3 镜人批 → 才 bulk**；男主声线必须男 Edge（禁 Xiaoxiao 挂 hero）。

## 检查清单
- [ ] 旧 root：`receipts/FAILED_USER_REJECT_SCRAP.json` + `out/FAILED_*_do_not_ship.mp4`
- [ ] 新 root：`abroad-slut-manhua-h3-gen2` · `cast_generation_id=gen2-20260807-rebuild`
- [ ] 男主 `cast_voices` = `zh-CN-YunxiNeural`（或用户指定男声）；女主 Xiaoxiao
- [ ] 无人批 masters 前 **不** enroll 宣称稳定、不 bulk、不 final
- [ ] still 来源禁 `composite/midframe_paste`；I2V 前 still 目视无双头/性别混
- [ ] pilot 用户批脸+性别构图+动感后才 bulk

## 片例
- 失败：`AI FILM SPACE/0806/abroad-slut-manhua-h3`
- 重建：`AI FILM SPACE/0806/abroad-slut-manhua-h3-gen2`

## 链
- [identity-generation-lock](2026-08-07-identity-generation-lock-no-mix.md)
- [no-midframe-composite](2026-08-07-no-midframe-composite-flf-audio-iron.md)
- [partner-cast-master](2026-08-07-partner-cast-master-iron.md)
- hard-defaults 对应表行
