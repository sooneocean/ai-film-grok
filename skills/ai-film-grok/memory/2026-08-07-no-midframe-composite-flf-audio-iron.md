# Memory · 2026-08-07 · 禁半帧换脸 / 禁打断首尾帧 / 禁狠 gate 毁原声（P0 · abroad 崩片事故）

> **类比**：给照片贴半张新脸会鬼影；剪辑链中间硬插新片会跳戏；把麦克风增益拧到只剩门限会变「进水」。  
> **片例**：`AI FILM SPACE/0806/abroad-slut-manhua-h3`  
> **回执**：`receipts/restore-pre-composite-20260807.json` · 交付 `out/film_native_stable.mp4`

## 用户原话
> 画面崩掉了 然后有奇怪的镜头 请修复 音轨也严重崩坏  
> 全面反思如何优化 修正此错误 不准在犯 首尾帧的使用也有问题

## 事故（agent 自责 · 三连炸）

### 1) 画面鬼影 / 怪镜
- 为锁里昂脸，对 **上半帧 image_edit 再 feather 贴回整 still** → 中线双头、半透明第二身体（sh11/sh16 铁证）。  
- 毒 still 当 H3 首帧 → 整镜运动模糊/解剖糊。  
- **禁**：任何「裁半帧 → 换脸 → 拼回」作为 **I2V/FLF 源 still**。  
- **可**：整帧 restyle 通过质检；或 **整镜重出**；禁机械半帧 paste。

### 2) 首尾帧 / continue 链被打断
- 片链 `wants_continue` + `continue_endframe_lock`，`mode_with_last=flf`，`combo` 可 r2v。  
- 补救时 **一律强行 `--mode i2v` + 新 still**，无视 `h3 list/plan` 的 resolve、无视 prev `_end.png`。  
- 结果：邻镜 pose/衣着/空间 **重置**，观感「奇怪镜头」。  
- **铁**：重跑 H3 必须 `aifilm h3 list/plan` 决议 mode；continue 镜用 **本镜 keyframe 首帧 + 上镜 end 尾帧** 同代资产；restyle 后先 `enrich-last` / 从 clip 抽 end，再 FLF/R2V。

### 3) 音轨「进水/碎掉」
- 用户要原声口型后，用 **双 arnndn + 狠 agate** 当默认「语音隔离」→ RMS **-inf 空洞**、相位糊、人声门限抽噎。  
- **铁**：原声默认 **轻处理**：`highpass + afftdn(nr≤12) + adeclick + loudnorm`；**禁默认 agate**；双 arnndn 仅用户点名且抽听通过。  
- 交付名：`film_native_stable`；`film_native_speech` 狠 gate 版标 **BROKEN**。

## 三句话

1. **I2V 源 still = 完整单场景静帧**，禁止半帧贴脸复合。  
2. **H3 mode 跟 resolve / continue 链**，禁全片盲 i2v；改 still 后必对齐 endframe。  
3. **原声以可懂为先**，轻降噪；狠 gate 毁轨 = 事故。

## 检查清单（H3 / 成片前）

- [ ] still 全幅目视：无重影、无接缝带、无双头  
- [ ] `keyframes/<id>.png` sha = 批准 still；与 clip **首帧**一致（或明确 FLF 另册）  
- [ ] `stills/<prev>_end.png` 来自 **当前** clip 末帧（改 clip 后重抽）  
- [ ] `aifilm h3 list` 的 mode 未被「图方便」覆盖；override 写收据  
- [ ] 原声音轨抽听：无抽噎门限、无 -inf 长静音块  
- [ ] 毒 still 目录隔离，**禁** promote 进 timeline  

## 本片处置（已做）

- 隔离毒 still/clip → `_archive_poison_composite_20260807`  
- 恢复 restyle 前 archive still + `_archive_pre_leon_restyle` clips  
- still/keyframe 与 clip 首帧对齐；全链 endframe 重抽  
- 轻音轨拼 `out/film_native_stable.mp4`（并覆盖 `film_final` 为 plate 指针）  
- 旧：`film_native_speech_BROKEN_gate.mp4` · `film_final_BROKEN_composite_20260807.mp4`

## 链

- hard-defaults 表行「禁半帧复合 / FLF 同代 / 原声轻处理」  
- [partner-cast-master](2026-08-07-partner-cast-master-iron.md) · [identity-generation-lock](2026-08-07-identity-generation-lock-no-mix.md) · [native-speech-iso](2026-08-07-h3-native-speech-isolate.md)（后者 **修正**：狠 gate 非默认）  
- `aifilm h3 enrich-last` · continue-handoff


## 追加 · 25s 性别互换（2026-08-07）

- **现象**：sh05 仍是女主 Q 脸，sh06 电梯变成「红眼长发男性 + 陌生黑发女」。  
- **铁**：`珍珠发箍+红眼+长青绿发` **只能是女主**；`短黑发+棕眼` **只能是里昂**。H3 前目视双人镜，**性别互换 = 毒 still 禁 I2V**。  
- 修复：整帧重出 sh05–07 + 重 H3；交付 `film_native_stable`。
