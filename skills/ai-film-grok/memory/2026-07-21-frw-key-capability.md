# Memory · FRW Key 能力位 + 漫剧可用兜底（2026-07-21）

**User**: 测新 FRW API key 哪些模型能用，把教训与可用项沉进 ai-film-grok skill。

## 产品结论

1. **Key 有效 ≠ Seedance 可用**。样本 key：Seedance / BytePlus **全 403**；`ltx-t2v` + classic T2I/T2V/I2V/FLF **completed**。
2. bulk 前 **canary**：`balance` + Seedance 一枪 + `ltx-t2v` → `receipts/frw-key-capability.json`。
3. **403**=能力位（找运营）；**502**=平台挂（换族）；勿混。
4. 无 Seedance：**L1 Grok 720p**；**L2 ltx-t2v → classic t2v**；legacy `img2video` 仅 FRW-only **显式**救生艇 + WARN。
5. 禁默认 legacy；禁 403 后假装 Seedance；register 写真实 model/fallback。
6. 部分 key frwcore 上传换票 403 → 公网可达图 URL。

## 落地（2026-07-21 续）

1. 本机 key 已写入 `~/.hermes/skills/frwclaw-pro/.env` 与 `~/.agents/skills/frwclaw-pro/.env`（旧 key 有 `.env.bak-*`；`FRW_TOKEN` 已清）。
2. 命令：`"$AIFILM" frw canary --root <film>` → `receipts/frw-key-capability.json`（`scripts/frw_canary.py`）。
3. canary 须自定义 UA（Cloudflare 1010 禁默认 Python-urllib）。

## Canonical

- `references/lessons-2026-07-21-frw-key-capability.md`
- `references/frw-degrade-dispatch.md`
- `references/lessons-2026-07-20-seedance-quality.md`（403 节已补丁）
- `references/hard-defaults.md` · `references/consistency.md` §3
- `SKILL.md` 工具条 + 视觉步 + 按需加载表
- `scripts/film_spec.py`：`FRW_I2V_FRW_ONLY_LIFEBOAT` + `_layer_routing.key_canary`
- `scripts/frw_canary.py` · `frw_dispatch.py canary`

## P 码

P0 可观测 · P1 身份诚实 · P5 分层
