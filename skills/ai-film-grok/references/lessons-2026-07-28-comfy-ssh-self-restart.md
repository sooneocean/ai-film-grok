# 教训 · Comfy 卡关自己 SSH 重启（2026-07-28）

## 用户铁律
**以后卡关自己重启 Comfy，不要干等用户。**

## 怎么判卡
- 经 SSH 隧道访问的 `curl http://127.0.0.1:18188/system_stats` 非 200 / 超时
- **`{"detail":"unauthorized"}` 401** → 多半隧道指到 **8189（鉴权服务）不是 Comfy 8188**；`ps aux | grep 'L 18188'` 核对远程端口后重建（见 [tunnel-8188-not-8189](lessons-2026-07-29-comfy-tunnel-8188-not-8189.md)）
- `aifilm comfy probe` fail 或 queue 不通
- Wan/i2i history 轮询 `Operation timed out` 且端口已死
- **勿**把「本地 18188 在 LISTEN」当成健康：LISTEN + 401 = **指错业务端口**

## 重启（本机已配密钥）
```bash
KEY="$HOME/.ssh/aifilm_5090_ed25519"
HOST="user@192.168.88.52"
ssh -i "$KEY" -o BatchMode=yes -o IdentitiesOnly=yes "$HOST" \
  "powershell -NoProfile -ExecutionPolicy RemoteSigned -File C:\\ComfyUI_windows_portable\\stop_comfyui.ps1 -Port 8188"
ssh -i "$KEY" -o BatchMode=yes -o IdentitiesOnly=yes "$HOST" \
  "powershell -NoProfile -ExecutionPolicy RemoteSigned -File C:\\ComfyUI_windows_portable\\start_comfyui.ps1 -Port 8188 -Host 127.0.0.1"
# 验
ssh -fN -L 18188:127.0.0.1:8188 -i "$KEY" -o BatchMode=yes -o IdentitiesOnly=yes "$HOST"
curl -s -o /dev/null -w "%{http_code}\n" --max-time 10 http://127.0.0.1:18188/
```
- 脚本路径：`C:\ComfyUI_windows_portable\start_comfyui.ps1`（无头仅绑定 127.0.0.1:8188，SSH 隧道断线后服务仍活但局域网不可直连）
- 日志：`C:\ComfyUI_windows_portable\comfyui_headless_8188.log`
- 勿误杀 8788 audio_node / lipsync
- **隧道远程端口硬锁 8188**：`-L 18188:127.0.0.1:8188`（**禁止** 8189；lipsync 用 **18790→8790**）

## 顺序
探测失败 → stop → start → probe ok → 再继续 i2i/Wan；禁止空等报告「请用户重启」。
