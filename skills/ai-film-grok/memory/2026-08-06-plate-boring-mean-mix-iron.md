# 2026-08-06 · plate 有片仍无聊：mean + 邻镜 + sidechain 假死

## 原话
是有没错 但是很单一很无聊 还有办法优化吗？  
A 你帮我打通后 把这个状况拿来优化项目 下次不要再犯

## 三句
1. **`OFFICIAL_FINAL_PLATE` 绿/有片 ≠ 好看**——门禁过一半（或 skip cinematic）仍可整集「会动的静帧」：mean 肉戏≪20、邻镜同 camera/景别、声轨一条直线。  
2. **dynamic_eq（sidechain+acrossover 六轨）可假死 30–60min+** 写不出 `mixed.wav`；逃生：`AIFILM_FORCE_BROADBAND_DUCK=1`（轻 duck）或 `AIFILM_FORCE_SIMPLE_AMIX=1`（无 duck PARTIAL），禁硬等。  
3. **无聊优先修像素不是改报告**：weak mean 重渲 → `select-shortlist --promote`（anti-hijack）→ 轻 duck 再 final；spec 改 variety **不**等于 takes 已变。

## 清单
- [ ] ship plate 前：`i2v-high-motion-audit` 肉戏 mean 抽检（肉戏 avg 趋近 18–20；禁全片 8–12 装片当好看）
- [ ] variety-precheck 绿后 **须 re-I2V / promote**，禁只改 film-spec camera 字段交差
- [ ] final mix：默认宽带 duck；acrossover 挂 >10min 且文件大小不变 → 杀进程切 `FORCE_BROADBAND_DUCK` / `FORCE_SIMPLE_AMIX`
- [ ] multi-take 分辨率变体（`*_704x1280`）**不算**创意 PK；禁只靠它宣称 multi_take 完成
- [ ] free-first：外片队列 busy 时 **等 idle**，禁 cancel 外片；busy 提交 → `COMFY_QUEUE_BUSY` / `VRAM_BELOW_FLOOR` 立刻 wait 不 burn shot list

## 链
hard-defaults 高动态 · shot-variety-anti-boring · bulk→final plate≠master · multi-agent-gpu-no-hog · suse-ep01-official-final-iron · h3-native-ship-review
