# Lessons · FRW Key 能力位探针（漫剧兜底可用矩阵）

> 2026-07-21 · **P0 可观测变化 · P5 分层 · P1 身份不假装**  
> 样本：新 `X-Api-Key` 对 `https://frw-dreamaiai-api2.aiaiartist.com` 全模板烟雾测试  
> 权威路由：[frw-degrade-dispatch.md](frw-degrade-dispatch.md) · 质量纪律：[lessons-2026-07-20-seedance-quality.md](lessons-2026-07-20-seedance-quality.md)

## 一句话

**Key 有效 ≠ 能跑 Seedance。**  
提交前先分清 **403 无权 / 502 平台挂 / 201→completed 真可用**。  
未开通 Seedance 的 key：**环境用 `ltx-t2v`，人物优先 Grok 720p**；经典 `img2video` 仅作 **FRW-only 最后救生艇**（质量地板，须记账）。

---

## 探针账本（2026-07-21）

| 检查 | 结果 |
|------|------|
| `GET /api/frwapi/v1/balance` | ✅ 通（例：总额 5000 级、`callLimit=-1`） |
| Seedance 全族 `seedance-2-*` | ❌ **403 无权使用该模板** |
| BytePlus `byteplus-seedance-2-*` | ❌ **403** |
| `ltx-t2v` | ✅ **201 → completed**（cost ≈20） |
| `ltx-i2v` / `ltx-flf` / `ltx-lipsync` | ⚠️ **502**（与 07-20 探针一致） |
| classic `text2image` | ✅ completed（cost ≈10） |
| classic `text2video` | ✅ completed（cost ≈20） |
| classic `img2video` | ✅ completed（cost ≈20）——**能跑但质量地板** |
| classic `first-last-frame` | ✅ completed |
| classic `img2image` | ⚠️ 502（平台） |
| `gimm-vfi` / `wan-lipsync` | ⚠️ 502 |
| frwcore `thirdparty/auth/<key>` 上传换票 | ❌ 403「无效的 token」→ 只能喂 **FRW 可抓取的公网 URL** |

线上模板列表权威：`GET /api/frwapi/v1/templates`（约 17 个，含 seedance/ltx/byteplus/gimm/p0…）。  
frwclaw 映射：`NEW_VIDEO_TEMPLATES`（15 个新视频 key，排除 p0 换脸）。

---

## 判读口诀（agent 必记）

| HTTP / 文案 | 含义 | 动作 |
|-------------|------|------|
| **403**「无权使用该模板」 | **账号能力位**未开 | 找运营开通；**不要**当参数错重试刷分 |
| **400** 参数 / 资源无法访问 | payload 或图 URL 被拒 | 改 string 宽高 / 换可抓取 URL |
| **502** | **平台/上游**挂 | 换族（如 LTX→classic/Grok）；稍后可再探 |
| **201 + completed** | 真可用 | 才可进 bulk 账本 |
| **201 + failed** | 提交成功业务失败 | 看 `errorMessage`，勿当权限问题 |

**禁止**：403 后仍写 `model=seedance-…` 的 register 评语。  
**禁止**：把 classic `img2video` 说成 Seedance。

---

## 对本类 key 的生产路由（捡起来能用的）

```text
【理想 · 权限已开】
L1 hero: seedance-2-fast-i2v → ltx-i2v → Grok 720p
L2 env:  ltx-t2v → seedance t2v → classic text2video

【现实 · Seedance/BytePlus 全 403 · LTX i2v 502】  ← 2026-07-21 样本
L0 still:  Grok image_edit(cast)  （FRW 文生图仅非身份）
L1 hero:   Grok I2V 720p
           ↳ 仅当 Grok 不可用且必须走 FRW：classic img2video（显式 + WARN + 账本）
L2 env:    ltx-t2v ✅ → classic text2video ✅
FLF:       classic first-last-frame ✅（非 pro-flf）
```

### 现在就能用（不改权限）

1. **`ltx-t2v`**：空镜 / 氛围 / bridge（竖屏 `720`×`1280` 全 **string**）  
2. **classic `text2video`**：L2 最底兜底  
3. **classic `text2image`**：非身份静帧 / 探针  
4. **classic `img2video`**：FRW-only 人物救生艇（**质量地板**，register `frw_img2video`）  
5. **classic `first-last-frame`**：经典 FLF  
6. **Grok I2V 720p**：L1 真兜底（不烧 FRW Seedance 权限）

### 必须找运营开的

| 优先级 | template / model | 理由 |
|--------|------------------|------|
| P0 | `seedance-2-fast-i2v` | 默认 bulk 人物 |
| P0 | `seedance-2-pro-flf` | 有尾帧锁构图 |
| P1 | `seedance-2-fast-t2v` / byteplus i2v | 渠道备胎 |
| P1 | frwcore 上传换票 | 本地 keyframe → `files/view` URL |

开通验收（期望 **201** 不是 403）：

```bash
curl -sS -X POST "$FRW_HOST/api/frwapi/v1/tasks" \
  -H "X-Api-Key: $FRW_API_KEY" -H "Content-Type: application/json" \
  -d '{"templateId":"3500510042619121664","clientUserId":"u-probe","parameters":{
    "prompt":"@Image1 blink","imageUrls":["https://www.w3schools.com/w3css/img_lights.jpg"],
    "aspectRatio":"9:16","resolution":"720p","duration":"5"}}'
```

---

## 生产前 canary（推荐命令）

每次换 key / 怀疑权限漂移时，**先 canary 再 bulk**：

```bash
AIFILM="$HOME/.grok/skills/ai-film-grok/scripts/aifilm"

# 默认：balance + Seedance 权限枪 + ltx-t2v 提交 + upload 换票
# 写入 <root>/receipts/frw-key-capability.json
"$AIFILM" frw canary --root "<film-root>"

# 等 ltx-t2v completed（耗积分）
"$AIFILM" frw canary --root "<film-root>" --wait

# 加 classic T2I/I2V + ltx-i2v
"$AIFILM" frw canary --root "<film-root>" --full --wait
```

实现：`scripts/frw_canary.py`（也可 `python3 …/frw_canary.py --root …`）。

回执字段（节选）：

```json
{
  "probed_at": "ISO-8601",
  "host": "https://frw-dreamaiai-api2.aiaiartist.com",
  "credits_remaining": 4900,
  "seedance_i2v": "403:…|201_submitted:…",
  "ltx_t2v": "201_submitted:…|completed",
  "ltx_i2v": "502|…",
  "classic_img2video": "201_submitted:…",
  "upload_token": "ok|403:…",
  "recommended_l1": "grok|seedance-2-fast-i2v|ltx-i2v",
  "recommended_l2": "ltx-t2v|legacy-text2video",
  "seedance_permission": "open|blocked",
  "ok": true
}
```

---

## 外链图纪律

FRW **服务端抓图**。本机可达 ≠ FRW 可达。

| 现象 | 处理 |
|------|------|
| 400「参数 imageUrl 指向的资源无法访问」 | 换 CDN / w3schools 类开放图，或 frwcore **upload** 后用 `files/view` |
| wikimedia 等 403 | 不要当探针图 |
| upload 换票 403 | 本 key 可能只开 frwapi：优先公网 URL 或找运营开上传 |

---

## 与旧规则的关系（别打架）

| 规则源 | 仍成立 | 本次补丁 |
|--------|--------|----------|
| 胃镜室：禁默认 legacy | ✅ 默认仍 Seedance | 403+无 Grok 时 **显式** legacy 可作 FRW-only 救生艇 |
| 男娘片：403 → 勿假装 Seedance | ✅ | 补全矩阵：本类 key **全 Seedance 403**；`ltx-i2v` 常 502 |
| layer-routing：L2=`ltx-t2v` | ✅ 本 key 已 completed | L2 最可靠 FRW 通道 |
| 无限配额优先质量 | ✅ | **前提是权限开了**；否则质量链断在 key |

---

## 不可宣称

- 有 FRW key = 能 Seedance  
- `callLimit=-1` = 所有模板都能调  
- classic img2video completed = 质量过关  
- LTX i2v 在 schema 里 = 今天能出片（仍可能 502）  
- 本机 curl 通的图 URL = FRW 能抓  

---

## 安全

- Key **禁止**进 git / SKILL 正文 / 队列 receipt 明文  
- 对话泄露 → 联系运营轮换  
- 只用环境变量 / frwclaw `.env`（`FRW_API_KEY`）

---

## 验证清单

- [ ] `balance` 通  
- [ ] Seedance i2v 一枪：201 或明确 403（写入 capability 回执）  
- [ ] `ltx-t2v` 能 completed（L2）  
- [ ] bulk 前 `frw_video_model` 与 capability 一致  
- [ ] register-note 写真实 `model=` / `fallback=`  

## Canonical

- 路由：[frw-degrade-dispatch.md](frw-degrade-dispatch.md)  
- 质量：[lessons-2026-07-20-seedance-quality.md](lessons-2026-07-20-seedance-quality.md)  
- LTX 参数：[lessons-2026-07-20-frw-ltx-probe.md](lessons-2026-07-20-frw-ltx-probe.md)  
- film-spec 链：`scripts/film_spec.py` → `_frw_fallback_chain`  
