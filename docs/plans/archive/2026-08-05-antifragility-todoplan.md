# Antifragility Todo Plan — ai-film-grok（2026-08-05）

**Status:** ACTIVE · AF1–AF6+AF8 SHIPPED in 2.39.34 · AF7 PARTIAL (execute proven · drain open) (execute capacity_not_ready) · was analysis-only（本档不写生产代码）  
**Repo:** `/Users/dex/.grok/plugins/ai-film-grok` · plugin **2.39.34**  
**Theme:** 反脆弱 = **压力下更诚实、更可恢复**（fail-closed 门 + PARTIAL 回执 + 超时/resume），不是「多重试几次假装成功」。

## 一句话

管线已有大量抗压面（checkpoint / comfy_recovery / bulk-preflight / closeout / mix_partial / until-empty stop_reason / caption-pixel）；**残余缺口**集中在：热路径子进程无超时挂死、静默 `except: pass`、closeout 未串 post-doctor、TTS 降级无诚实回执、身份抽帧挂机、以及真片 overnight canary 仍 open。

---

## Operational definition（本仓）

| 类 | 含义 | 例子 |
|----|------|------|
| **Fail-closed** | 不确定就停；禁止假 execute / 假绿 | 毒 still 禁 I2V；pilot 自批挡；capacity not ready 不烧；motion core 空核挡 bulk |
| **PARTIAL-honest** | 降级可继续，但回执写明诚实边界 | sidechain→amix `final-mix-partial.json`；Imagine 拦 bare 记 PARTIAL；queue 进度只认 takes 文件 |
| **Recoverable** | 坏状态可续跑、不重烧无证据 | `checkpoint.py` final-render；media-queue stale reclaim；comfy_recovery 有界 SSH |

**不是反脆弱：** 静默降 heat / 静默换 provider / 无回执多 retry / 把 doctor soft 当成 ship 绿。

---

## Already SHIPPED（勿重开为绿野）

对照既有计划，下列 **DONE / partial 已登记** — 本档只列 **residual**：

| Wave / 面 | 计划指针 | 现状 | 残余？ |
|-----------|----------|------|--------|
| ROI A–E | `docs/plans/2026-08-03-roi-optimization-plan.md` | CLOSED | 否 |
| Workflow A–H + W8 | `docs/plans/2026-08-03-workflow-optimize-todo.md` | SHIPPED | 否（bulk-preflight / closeout / lease / shortlist 已在） |
| Opt W0–2,4,5 · M | `docs/plans/2026-08-05-optimization-todoplan.md` | SHIPPED | **Wave 3 util partial**；真片 until-empty canary open |
| h3_primary + until-empty dry | `docs/plans/2026-08-05-h3-primary-capacity.md` · `test_h3_until_empty` | 代码+dry 测 | 真烧 + hang 面 |
| post P1 mix/post-doctor/caption | `mix_partial.py` · `post_doctor.py` · `caption_pixel_check.py` | 模块在；测在 | **closeout 未串 post_doctor** |
| checkpoint / resume / comfy_recovery | `checkpoint.py` · `test_checkpoint` · `test_resume_idempotency` · `test_comfy_recovery` | 有界超时已在 recovery | final-only checkpoint 可延后 |
| util.subprocess | `util/subprocess.py` (`run` / `run_ffmpeg` / `run_compose_env`) | 封装有默认 timeout | **调用迁移未完**（`run_ffmpeg` 仅 `render_final*`） |

### Probe snapshot（2026-08-05 · 本机 checkout）

| 探针 | 观察 |
|------|------|
| bare `subprocess.(run\|…)` in scripts（excl util） | **~153** 处 |
| `util.run_ffmpeg(` 调用点 | **2**（`render_final.py` · `render_final_music.py`） |
| `h3_fill_idle._soft_identity_penalty` midframe ffmpeg | **无 `timeout=`**（过夜可挂死） |
| `comfy_recovery` SSH/curl | **有** timeout 20/90/20 |
| `media_qa._run` | default `timeout=60` |
| `media_queue.complete` handoff/sidecar | `except Exception: pass`（静默丢） |
| `closeout.py` × `post_doctor` | **0 引用**（agent_review_final / preflight 有） |
| until-empty tests | dry + queue_empty；**无** capacity_not_ready / hang 测 |
| hard-defaults L169 | 仍写「hero bulk Grok→FRW…」— **doc drift** vs `h3_primary` |

---

## Policy matrix（写代码时不许混）

| 场景 | 策略 | 禁止 |
|------|------|------|
| 毒 still / 解剖红 | **fail-closed** 禁 I2V / register | 静默仍进 queue |
| pilot 未用户批 | **fail-closed** bulk | 自批 / always-approve 当 GO |
| Comfy VRAM/queue not ready | **fail-closed** 停 execute；`stop_reason=capacity_not_ready` | 假跑成功 |
| sidechain 混音失败 | **PARTIAL-honest** amix + receipt | 装五轨齐 |
| TTS 降级 edge | **PARTIAL-honest** 回执 + used 链 | 当 primary 成功无痕 |
| continue handoff 写失败 | **PARTIAL-honest** 或 fail-loud 记 warning | `except: pass` |
| ffmpeg 抽帧/混音 | **fail-closed timeout** → 软跳过身份或 hard 停循环 | 无限挂 |
| caption 像素无中文（有 final+srt） | **fail-closed** closeout | soft 绿 ship |
| 质量/人审拒 | **不**签 provider 降级 | 429 逻辑套质量拒 |

---

## Prioritized residual todos（8）

每项独立可验：owner · failure mode · verify · policy。

### AF1 · Wave 3 residual：热路径子进程超时收口（P0）

- **Problem signal:** `util.run_ffmpeg` 几乎无人用；`h3_fill_idle` 身份 midframe `subprocess.run` **无 timeout**；同类 bare 调用在 `tts_backend` / `scene_sound_stems` / `delivery_artifact` 等仍散落。历史 Wave 3 标 partial 即此。
- **Failure mode:** 过夜 `h3 cycle --until-empty` 卡在单次 ffmpeg 永不返回；agent 会话假死。
- **Intended outcome:** 热路径（final / fill-idle identity / lipsync 外调已有 timeout 的保持；**无 timeout 的 ffmpeg/ffprobe**）统一走 `util.run` / `util.run_ffmpeg`（或显式 `timeout=`）。身份抽帧失败 → 跳过 penalty 并 caution，**不挂进程**。
- **Owner:** `util/subprocess.py` · `h3_fill_idle.py` ·（可选）`tts_backend` probe 仍 bare 但已有 timeout 的可顺手迁
- **Verify:**  
  - 单测：mock/慢命令 → `TimeoutExpired` 或 util 包装抛错；`h3_fill_idle` midframe 路径带 `timeout=`（静态断言或行为测）  
  - `pytest skills/ai-film-grok/tests/test_util.py skills/ai-film-grok/tests/test_h3_until_empty.py -q`  
  - 探针：`rg -n 'subprocess\.run\(' scripts/h3_fill_idle.py` 同行或邻行含 `timeout`
- **Policy:** **fail-closed timeout**；身份检查失败 = **soft skip + caution**（PARTIAL-ish），不升格假绿

### AF2 · media-queue continue-handoff / sidecar 静默 pass → 诚实（P0）

- **Problem signal:** `media_queue.py` complete 路径 `except Exception: pass`（sidecar + `maybe_write_for_clip`）— 压力下丢末帧 handoff，下一镜 continue 无锚，且 **无 receipt**。
- **Failure mode:** bulk 显示完成，续镜 I2V 用错仍/无 handoff；返工在 bulk 后才发现。
- **Intended outcome:** 写失败记入 job warning 或 `receipts/media-queue-partial.json`（`honest_limits` + shot_id + error）；**不**回滚已落盘 take；禁止裸 `pass`。
- **Owner:** `media_queue.py` · 可选 `continue_handoff.py`
- **Verify:**  
  - 单测：强制 `maybe_write_for_clip` 抛 → complete 仍 ok 但 receipt/warning 含 handoff 失败  
  - `pytest … -k 'handoff or media_queue' -q`（新测 `test_media_queue_handoff_honesty.py` 或扩展既有 queue 测）
- **Policy:** **PARTIAL-honest**（媒体已成）+ 可见 warning；非 fail-closed 整 job（避免重烧），除非 handoff 被标 required

### AF3 · closeout 串 post-doctor hard codes（P0）

- **Problem signal:** `post_doctor.py` 查 caption/双烧/SRT/五轨/单钟/mix PARTIAL；`agent_review_final` 与 `preflight` soft 已用；**`closeout.py` 零引用** → 一键收尾可漏 doctor hard。
- **Failure mode:** closeout 绿 + 双 timeline clock / CAPTION_PIXEL_RED 仍在 `receipts/post-doctor.json`。
- **Intended outcome:** `closeout status|run` 增加 step `post_doctor`：hard issues → 停 + `next_cmd`；`MIX_PARTIAL` 保持 **advisory + honest_limits**（与现 evidence 一致）。
- **Owner:** `closeout.py` · `post_doctor.py`
- **Verify:**  
  - fixture：造 DUAL_TIMELINE_CLOCK hard → closeout `ok=false` stopped_at=post_doctor  
  - mix partial only → closeout 不 hard stop  
  - 扩 `tests/test_workflow_wave_a.py` 或 `test_post_p1_timeline_doctor.py`
- **Policy:** doctor **hard = fail-closed**；**MIX_PARTIAL = PARTIAL-honest**

### AF4 · TTS 降级诚实回执（P1）

- **Problem signal:** `tts_backend` 有 opt-in fallback 链（`choice->edge_opt_in_fallback` 等），但无稳定 **film-root receipt** 标「非主声线 / 合成感」；交付易口头当 primary。
- **Failure mode:** 主 TTS 挂 → 静默 edge 成片，审片不知声线已降。
- **Intended outcome:** 任意 fallback 成功时写 `receipts/tts-partial.json`（`used` 链 · `honest_limits` · voice）；closeout/post-doctor soft 露出；不阻断 final 除非用户 strict。
- **Owner:** `tts_backend.py` · 可选 `closeout.py` soft step
- **Verify:**  
  - 单测：mock primary fail + edge ok → receipt `partial=true` · `used` 含 fallback  
  - 无 fallback 成功路径 → **不**写 partial 文件
- **Policy:** **PARTIAL-honest**（默认）；strict 可选 fail-closed 另议，本 todo 不做

### AF5 · until-empty 停机诚实 + hang 面（P1 · 代码侧）

- **Problem signal:** `fill_idle_until_empty` 已有 `stop_reason`（dry / queue_empty / capacity_not_ready / run_failed）；测覆盖 dry+queue_empty。**缺** capacity_not_ready execute 断言；叠加 AF1 挂死则 stop_reason 永远写不出。
- **Failure mode:** 算力不足仍空转；或进程挂死无 `receipts/fill-idle-until-empty.json`。
- **Intended outcome:**  
  1. 单测 mock `skipped_reason=capacity_not_ready` + execute → `stop_reason=capacity_not_ready` · ok 语义明确（capacity 停 ≠ run_failed）  
  2. 依赖 AF1 后：单 job timeout 记 `run_failed` 或 `job_timeout` 并 break（与现 run_failed 分支一致）
- **Owner:** `h3_fill_idle.py` · `tests/test_h3_until_empty.py`
- **Verify:** `pytest skills/ai-film-grok/tests/test_h3_until_empty.py -q` 新增用例绿
- **Policy:** capacity → **fail-closed stop**（不假 execute）；job fail → stop + `ok=false`

### AF6 · closeout evidence/caption 探针崩溃勿假绿（P1）

- **Problem signal:** `closeout` 中 `evidence_stale_after_final` 异常时 step 变 `ok=True, advisory`（「advisory skip」）— 探针炸 = 当通过。
- **Failure mode:** 导入/解析异常时 closeout 全绿，证据链实已坏。
- **Intended outcome:** 有 final 时探针异常 → `ok=False` 或显式 soft 且 **不得** `ok=True` 默认；detail 含异常码。
- **Owner:** `closeout.py`
- **Verify:** monkeypatch `evidence_stale_after_final` raise → closeout status 不绿该步  
  - 扩 wave_a / closeout 测
- **Policy:** **fail-closed**（有 final 时）；无 final 可 skip

### AF7 · 真片 until-empty canary（P2 · 运维） · **PARTIAL 2026-08-05**

- **Problem signal:** dry canary 已过（`artifacts/2026-08-05-h3-until-empty-canary.json`）；**真烧 GPU 过夜**仍 open（optimization next）。
- **Failure mode:** 代码路径未在 5090 idle 真压下验证 stop_reason / lease / 误杀。
- **Intended outcome:** 用户确认 5090 idle + pilot GO 后：`h3 capacity-plan` + `h3 cycle --until-empty --execute`；回执 `fill-idle-until-empty.json` stop_reason ∈ {queue_empty, capacity_not_ready, max_cycles}；**不**自动 promote。
- **Owner:** 运维 session · film root 用户指定
- **Verify:** 回执 path + `stop_reason` + takes 增量文件数；写 memory 短卡
- **Policy:** capacity / 失败 **fail-closed stop**；成功 takes **不**自动 PK 胜出

### AF8 · hard-defaults FRW-first 文案漂移（P2 · 文档）

- **Problem signal:** `references/hard-defaults.md` 推荐 `h3_primary`，但流程步骤仍写「hero bulk 按 Grok → FRW API I2V → FRW LTX…」— 与 2026-08-05 主产线矛盾；实现者易按旧链「加固」错 provider。
- **Failure mode:** 新 session 按旧 FRW-first 路由，浪费配额 / 与 media-queue 硬拦冲突。
- **Intended outcome:** 改该步为 **h3_primary 默认**（Grok=pilot/soft 对照；无 5090 才 grok_primary）；标注旧 ltx23 仅 legacy。
- **Owner:** `references/hard-defaults.md`（+ 若 SKILL 镜像句）
- **Verify:** `rg -n 'hero bulk 按 Grok|FRW API I2V' references/hard-defaults.md` 无陈旧主路径；doctor 不要求
- **Policy:** 文档 only；**不**改默认 provider 代码（已 h3_primary）

---

## Suggested order

```text
AF1 timeout 热路径  →  AF5 until-empty 停机测（挂 AF1）
        ‖
AF2 handoff 诚实     →  AF3 closeout↔post_doctor  →  AF6 探针不假绿
        ↓
AF4 TTS partial 回执
        ↓
AF8 文档漂移（随时可夹）
        ↓
AF7 真片 canary（等人 + 5090 idle）
```

映射：AF1 ⊂ optimization **Wave 3 residual**（勿另起平行波名）；AF7 ⊂ optimization **next canary**。

---

## Non-goals（读者易误以为在 scope）

- 实现本清单代码 / version bump / push（本 goal = **分析 + 落档 plan**）
- 全自动 chaos / 多区域 failover 产品
- 自动批 pilot、静默降 heat、静默换 `i2v_provider`
- 全自动毒镜 CV 完美识别（bulk-preflight 标记+硬拦已在；W7 仍延后）
- 整仓 `except Exception` 大扫除或 monolith 压到 1500 行冲刺
- 重开 ROI A–E / Workflow A–H / caption-pixel 主实现为绿地
- 用 FRW/ltx23 替换当前 **h3_primary** 默认
- 把 checkpoint 扩到全 I2V job 图（core-adjacent **deferred**，见下）

### Deferred core-adjacent（scope-capped）

1. **Job-graph checkpoint beyond final-render** — `CheckpointManager` 仅 `receipts/checkpoints/final-render.json`；H3/media-queue 靠 takes 文件 + stale reclaim。完整 shot-graph resume 有价值，但成本高，且 takes 存在已部分抗重烧 → **延后**，不进本 8 条执行序。
2. **Provider 质量拒 vs 429 签名再审计** — `i2v_provider` 已有 degrade 关键字表；全面审计每个 adapter 属另一会话。

---

## 与「优化 todoplan」关系

| 文档 | 角色 |
|------|------|
| `2026-08-05-optimization-todoplan.md` | 产能/门禁/canary **主执行板** |
| **本档** | 反脆弱 **残余缺口** 板；不重复 DONE 行，只挂 residual |
| workflow / ROI plans | 历史 SHIPPED 对照；禁止当未做清单重开 |

---

## Acceptance of *this* analysis artifact

- [x] 主题反脆弱 / antifragility · 日期 2026-08-05 · status ACTIVE  
- [x] 接地真实模块路径（上表 + todos）  
- [x] 8 todos（∈ [3,12]），各含 problem / outcome / verify / policy  
- [x] 显式 fail-closed vs PARTIAL-honest  
- [x] Non-goals + ≥1 deferred core-adjacent  
- [x] 不重开已 SHIPPED waves 为绿地  

**Implementer next:** 从 AF1 起按 Suggested order 改代码；每项独立 PR/commit 级可验。
)
