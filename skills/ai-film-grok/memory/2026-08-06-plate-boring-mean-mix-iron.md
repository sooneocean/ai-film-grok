# 2026-08-06 · plate 有片仍无聊：mean + 邻镜 + sidechain 假死

## 原话
是有没错 但是很单一很无聊 还有办法优化吗？  
A 你帮我打通后 把这个状况拿来优化项目 下次不要再犯  
你弄一弄收工吧 你不要再搞那个了 不要抢h3 把教训写回记忆

## 三句
1. **`OFFICIAL_FINAL_PLATE` 有片 ≠ 好看**——mean 肉戏≪20、邻镜同质、声轨一条直线 = 静帧联播；门禁 skip / plate 诚实标签不能当「好看」。  
2. **mix：`sidechain+acrossover` 可假死 30–60m+** 写不出 `mixed.wav`；**直出宽带 duck 或 simple amix 秒级**。`AIFILM_FORCE_BROADBAND_DUCK=1` / `FORCE_SIMPLE_AMIX=1`；挂 >10min 且文件大小不变 → 杀切。  
3. **外片占 5090 时禁止再开 weak-mean 重渲链抢 H3**——free-first 空等+反复 `COMFY_QUEUE_BUSY` 烧会话；收工保留 plate + 写记忆，重渲改独占窗或用户点名。

## 清单
- [x] 有 plate 仍无聊 → 制度卡 + hard-defaults 行 + AGENTS 7c
- [x] acrossover 假死 → 直出 `mixed_broadband` + mux（禁硬等 render_final 卡死图）
- [x] 收工：**杀 savani weak12 / finish watcher**，**不 cancel 外片 H3**
- [ ] 独占 GPU 窗再 weak mean re-I2V（s38/s28 已有新 take；其余 10 未齐）→ shortlist promote 后再 final
- [ ] variety 改 spec 后须像素 re-I2V，禁字段交差
- [ ] 分辨率变体 `*_704x1280` 不算创意 multi-take

## 本轮交付（收工快照）
- 片：`/Users/dex/AI FILM SPACE/0805/savani-ep01-5m/out/film_final.mp4`（宽带 duck · ~209.6s · OFFICIAL_FINAL_PLATE）
- 桌面：`~/Desktop/savani-ep01-plate/`
- H3 本轮仅成功 **2/12** 弱镜（s38 r2v、s28 i2v）；**已停抢卡**
- 非 master：mean 门禁未绿 + 无人审 review-final

## 链
hard-defaults「plate 有片仍无聊」· multi-agent-gpu-no-hog · shot-variety-anti-boring · bulk→final plate≠master · dual-film-drain · h3-native-ship-review
