# Memory · 2026-08-06 · Comfy 隧道强制自动打通

## 用户原话
> 这个隧道可以帮我记起来吗 以后强制打通 不要再让我手动做

## 三句话
1. **默认路径**：Tailscale `user@100.66.2.28` + key `~/.ssh/aifilm_5090_ed25519` → 本机 **`18188→远程 8188`**（禁 8189）。
2. **命令**：`aifilm tunnel-ensure`（或 `tunnel-probe --ensure`）；doctor 在 `AIFILM_COMFY_TUNNEL_AUTO=1`（默认）时自动 ensure。
3. **后台**：LaunchAgent `com.aifilm.comfy-tunnel` 每 **300s** + 登录跑 `scripts/comfy_tunnel_ensure.sh`。

## 检查清单
- [ ] `curl -sS -m 5 http://127.0.0.1:18188/system_stats` 200 + Comfy JSON
- [ ] `aifilm tunnel-ensure` → ok
- [ ] `launchctl print gui/$(id -u)/com.aifilm.comfy-tunnel` 已 load
- [ ] config.env 有 `AIFILM_COMFY_SSH_TARGET=user@100.66.2.28`

## 码
- `media/comfy_recovery.ensure_comfy_tunnel`
- CLI `tunnel-ensure` / `tunnel-probe --ensure`
