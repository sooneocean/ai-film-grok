# 历史记录：FRW i2i 优先尝试与 5090 重地址恢复（已由 Qwen 主路由取代）

> 已取代：当前 `dialogue_drama` 合同规定 **5090 Comfy Qwen i2i 为状态照与关键帧主路由**；FRW 仅在明确授权 `allow_frw_fallback`、Qwen 本地 preflight 未通过且 FRW 精确 i2i 能力已证明时使用。保留本文只为说明 2026-07-29 的网络/能力事故，不可把历史 FRW-first 当作当前调度政策。

## 结论

故事先投影为**对白驱动的电影分镜**：角色讲话是主镜头；旁白只在剧情空窗补中文信息。每个讲话镜头在 lipsync/I2V 前必须拥有一张锁定角色状态的 i2i 静帧，锁住脸、服装、情绪、视线、手部道具和机位朝向。

声线合同不变：角色 `speaker` 走日文 TTS；旁白走中文 TTS；成片烧录中文字幕。旁白不能替代角色对白，也不应常驻覆盖讲话镜头。

## 可执行路由

1. `state-index check` 为每个缺少 performance-state 的 on-camera 对白镜头写出 `generate_dialogue_state_photo`，并附带 `i2i_route`。
2. 当前先跑本地 `aifilm comfy capacity`；通过后走 `comfy_qwen_i2i`。`COMFY_QUEUE_BUSY`、`VRAM_BELOW_FLOOR` 或 `RAM_BELOW_FLOOR` 只能回 `wait_for_local`。
3. 只有使用者明确启用 FRW fallback，且 `receipts/frw-key-capability.json` 同时证明 `upload_token=ok` 与 **classic img2image** 探针 `i2i_capability=available`，FRW 才可提交。T2V、I2V、文字出图成功均不能推论 i2i 可用。
4. FRW 403、旧 receipt、缺精确探针均为“未证明”，不是成功；不得静默换供应商。
5. 忙碌时禁止全局 interrupt、删除别人的 prompt、杀进程，或调用 free-memory 驱逐其模型。用户明确授予的优先调度权是一次性运行授权，仍须留下 capacity/queue receipt，不能写成默认自动行为。

这使“Qwen first、FRW explicit fallback”是能力可验证的决策，而不是名字排序或静默换供应商。

## 5090 网络恢复

旧私网地址不可达不等于 GPU 停机。先以只读方式核对候选主机的 Comfy `/system_stats`、队列和模型/显存状态；私网 Comfy 只经 loopback SSH tunnel 使用。SSH host key 改变时不得覆盖 `known_hosts` 或盲信新 key：必须独立验证目标身份后才建立临时、固定指纹的 tunnel。

在一次 30 秒日中双语对白样片中，FRW 上传与精确 i2i 模板均返回 403，故其不是可用 i2i 路由；本地 RTX 5090 随后在重地址后以 loopback tunnel 通过容量检查。该结论只证明当次能力，不替代下次 run 的 receipt。

## 验收

- 每个 on-camera 对白镜头有 `canonical/performance-states/<speaker>/<state>.png`。
- route receipt 明确 selected provider 或 wait/blocked 原因；没有“猜测可用”。
- TTS receipt 中角色均 `ja`，旁白均 `zh`；最终字幕为中文。
- 每条状态静帧及成片均需几何、身份、音频与人工画面复核；技术 receipt 不等于播出批准。
