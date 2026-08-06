# Plan：移除 lipsync 死区 + 出片质量 P0 硬门 + 额外优化

**结论先行：** 生产已冻结后期对嘴（SKILL P0#17 · `references/lipsync.md`），但代码里仍挂着 ~3.3k LOC lipsync 栈 + final `--lipsync auto/require` 真路径；专家团诊断里「lipsync 自动 canary 晋级」与现行政策**冲突，应改为删除/墓碑，不当增强**。本轮主轴 = **删 lipsync 死区 + 把已半实现的 5 个质量 P0 补成硬门** + 额外高 ROI 清理；做完 `check-all` → commit → push → 收工。

| 项 | 值 |
|----|-----|
| 仓库真相 | `/Users/dex/.grok/plugins/ai-film-grok`（plugins checkout） |
| 当前版本 | `plugin.json` **2.39.97** |
| 互补已关板 | 工程质量 `2026-08-06-codebase-quality-todoplan` CLOSED；产品 GPU C1 仍 OPEN_OPS |
| 互补 ACTIVE | 短版 `2026-08-06-shortform-optimization-todoplan`（S0.3+：H3 5.2s 计划根因） |
| 本板目标版本 | **2.40.0**（breaking：lipsync 生产路径移除）或 **2.39.98**（若仅 fail-closed 不删实现则 patch）→ **推荐 2.40.0** |

---

## 0. 代码账实（读库结论 · 勿当绿野重开）

### 0.1 Lipsync：政策冻结 ≠ 代码消失

| 层 | 现状 |
|----|------|
| 政策 | hard-defaults / SKILL / `references/lipsync.md`：**对白=原音**；LatentSync/MuseTalk/FRW lipsync/**全部冻结** |
| 实现仍在 | `scripts/audio/lipsync_{backend,canary,challenge,node_*,pilot}.py`（合计 ~3.3k）+ top-level shim + `media/frw_lipsync.py` + `node/{latentsync,musetalk}_adapter.py` + start/configure ps1 |
| 仍接线 | `post/render_final.py`：`--lipsync off\|auto\|require`，可真跑 `lipsync_one`；`cli_audio`：`lipsync-canary/pilot/challenge/node`；`cli_status` doctor 仍 probe ready backends；`shortform enable/render-lipsync` 与冻结政策打架 |
| 测试 | `tests/test_lipsync_*.py` + `test_frw_lipsync.py` |
| 专家团原文 P1「lipsync 自动晋级」 | **作废** → 本板改为 **移除/墓碑** |

### 0.2 专家团 5×P0 vs 已有代码

| 专家 P0 | 已有 | 缺口（本板要补） |
|---------|------|------------------|
| 抗无聊硬门 | `workflow_pack.variety_precheck` + gate-auto/cinematic **已跑**；肉戏 pose/CU/L4/相邻 motion | ① 非肉戏「主戏≥4.5s / 景别真变」弱 ② 多靠 **film-spec 字段**，**测得片上时长**未硬卡 ③ production_gates 未统一断言 |
| 每镜脸身份 post_audit | enroll/verify 有；register-clip 仅 **`--require_face_identity`** 才 hard；post_audit 多为 **warning** `FACE_IDENTITY_DRIFT` | 有 enroll 时 register **默认 hard reject**（逃生 env） |
| 九项接戏程序化 | `continuity_chain.md` 文档门 + preflight 要求文件；export 文案禁 dissolve | **缺** receipts 级 join 解析 + 末帧 hash/禁 dissolve 机读 hard |
| render_final 超时/假死 | hard-defaults 写 timeout≥600s；`util.subprocess` 局部 | **缺** 分阶段 heartbeat、长片 sidechain 假死检测/分片重试 |
| TTS 语言乒乓 | `validate_voice_language_locks` + cast_voices 剥 ja；film_spec 部分校验 | **缺** audio_plan 写语言标记 + preflight/final **统一**禁中日乒乓（含 ElevenLabs 误挂 zh-CN-*） |

### 0.3 额外高 ROI（专家团未写满 · 本板建议加）

1. **短版计划 vs H3 实源 ~5.2s**（ACTIVE shortform 板 P0）— 门绿但成片短；与「抗无聊主戏时长」同根。  
2. **CLI 旁路孤岛**：shortform lipsync 子命令与主脊矛盾（对齐删除）。  
3. **Seedance 桥**：政策禁 Seedance，保留 `seedance_bridge.py` 仅 tombstone/拒绝，勿再增强。  
4. **doctor 探针**：新硬门各 1 条「能力/门缺失即红」。  
5. **lesson 归档指针**：晋升硬门后 INDEX/memory 标 ARCHIVED，避免再当绿野。  
6. **GPU 多 agent 禁 hog**（2026-08-06 memory）— 文档/默认 flag 已有；本板不重做调度器，只在 doctor 提示。

---

## 1. 范围与非目标

### 做

- **Wave L（用户点名）**：移除/墓碑后期 lipsync 生产路径与 CLI 暴露面  
- **Wave Q（专家 P0 补洞）**：5 门 harden + 测 + doctor  
- **Wave X（额外）**：短版 H3 时长 plan 硬约束（最小切片）、Seedance/CLI 清理指针、CHANGELOG + bump  
- 验证 `make check-all`；commit（英文）；**push origin**（用户已要求收工 commit+push）

### 不做（本轮）

- HeartMuLa sung / visual_bible 自动生成 / H3 Fill-Idle 全自动派单（P2）  
- 5090 统一调度器重写（P1 大块；仅引用既有 free-first 纪律）  
- 物理删除全部 lipsync **研究 docs/lessons**（保留 tombstone 引用）  
- 静默改 heat / pilot / i2v_provider；假 master  

---

## 2. Wave L — 移除 lipsync（breaking · 优先）

### L0 策略（两阶段，同一 PR 内可连做）

| 阶段 | 动作 | 验收 |
|------|------|------|
| **L0a Fail-closed** | `final --lipsync` 仅允许 `off`；`auto/require/wav2lip/...` → 明确 `FilmError`/`RenderError`，文案指向 prefer_native + lipsync.md | 单测：非 off raise |
| **L0b CLI 退场** | `cli_audio`：`lipsync-canary/pilot/challenge/node` → 打印 frozen + exit 2（或删 subparser）；`shortform enable/render-lipsync` 同；`cli_status` 不再把 lipsync ready 算 capability 绿 | doctor 不因「无 LatentSync」红 core |
| **L0c 删实现（推荐本轮）** | 删除 `audio/lipsync_*.py`、top shims、`frw_lipsync` 生产入口、`node/*lipsync*adapter*`、start/configure lipsync ps1、对应 tests；`render_final` 剥 lipsync 分支与 import | `rg lipsync scripts --glob '*.py'` 仅剩 tombstone/注释/硬禁字符串 |
| **L0d 文档** | `references/lipsync.md` 保留为**墓碑政策**；README/AGENTS/hard-defaults 去掉「5 后端挑战」生产表述；SKILL 已冻结句保留 | 人读无「默认开 lipsync」 |

**兼容逃生（可选 · 默认不留）：** `AIFILM_EXPERIMENTAL_LIPSYNC=1` 仅开发机 — **建议本轮不留**，与「移除」一致；历史片用旧 tag/commit。

### L0 风险

- 外部脚本仍调 `aifilm lipsync-*` → 明确 exit + next_cmd  
- `test_external_backends` / capability_report / production_team 引用 → 改 stub 期望  
- runtime lock 指纹若含删文件 → `make lock-runtime`  

---

## 3. Wave Q — 专家 P0 硬门补洞

实现原则：**复用已有函数，升级 soft→hard / 接线点前移**，少造新子系统。

### Q1 抗无聊 → production hard（Top-1 叙事 ROI）

- 入口：`gates/production_gates.py` 或 `assert_variety_preflight` 在 **bulk-preflight + gate-auto** 统一 hard（肉戏矩阵已有）  
- 增强：  
  - 全片（或主戏非 insert）**测得时长** floor（ffprobe / measured map），不只 `duration_sec` 字段  
  - 相邻非 meat 的 **shot_size 去重** 可选 soft→hard（防「七镜同头肩」）  
- 测：`tests/test_variety_*` 或扩展现有 workflow_pack 测  
- hard-defaults 表行：标记「已机读 hard」  

### Q2 脸身份 register 默认 hard

- `cli_media.cmd_register_clip` / still register：若 `receipts/face-identity.json` 已 enroll 对应角色 → **默认** verify 失败 reject（去掉仅 `--require_face_identity`）  
- 逃生：`AIFILM_SKIP_FACE_IDENTITY=1` 或无 enroll 时 skip+caution  
- post_audit：`FACE_IDENTITY_DRIFT` 在 ship 路径 hard（与 enroll 绑定）  
- 测：fixture enroll + 坏图 register 失败  

### Q3 九项接戏程序化（最小可机读子集）

- 新模块建议：`scripts/gates/continuity_programmatic.py` 或 `assets/continuity_chain.py` 扩展  
- **MVP 校验（先 4 项，不全做 NLP 九项）：**  
  1. 长片 `continuity_chain.md` 存在且含 join 表行  
  2. 解析 `chain_mode=continue` 的 shot 对：下镜 keyframe/首帧 hash == 上镜 promoted 末帧（已有 byte 工具则复用）  
  3. film-spec / edit EDL **禁止** join 类型 `dissolve|freeze|reverse` 盖 continue 缝  
  4. 禁「无关 insert 夹在 continue 对之间」启发式（shot_id 序 + chain_mode）  
- 接线：preflight hard（longform）+ gate-auto soft→可 soft 首版  
- 测：合成 2 镜 continue 字节一致/不一致  

### Q4 render_final 超时/假死防护

- 阶段心跳：`receipts/final-heartbeat.json`（stage, unix, pid）每段混音/字幕/export 更新  
- 单段 `util_run(..., timeout=...)` 覆盖无 timeout 的 ffmpeg 长调用  
- 失败分类：Timeout → 可 `--resume-from-stage` 或明确 next_cmd（不静默假绿）  
- 测：mock timeout 路径（不真跑长片）  

### Q5 TTS 语言乒乓 hard

- `audio_plan` / film-spec：每 cue `lang=zh`；cast_voices 禁 `ja-*`（已有 normalize 则 preflight 再 assert）  
- 禁：Edge `zh-CN-*` 进 ElevenLabs voice_id；日文 spoken + 中文 voice 混镜  
- final 已有 `validate_voice_language_locks` → **preflight 前置**，失败更早  
- 测：ja cast_voices / 乒乓 fixture  

### Q6 doctor 探针

- 五个门各一探针：`variety_hard` · `face_register_hard` · `continuity_prog` · `final_heartbeat_capable` · `voice_lang_lock`  
- core doctor 不因「可选后端缺失」红  

---

## 4. Wave X — 额外优化（本轮可装进同一 release）

| ID | 项 | 动作 | 优先级 |
|----|-----|------|--------|
| X1 | **H3 名义时长进 plan** | `shot_planning` / `duration_target`：shortform 下 `duration_sec` 默认贴近 `H3_NOMINAL_CLIP_SEC≈5.2`；target 升高时 **加镜建议 hard advice 或 rebalance 增 shot**（对接 shortform 板 S0.3，最小：write-spec 警告+preflight hard 已有则 plan 侧降 DEFAULT 6.0→5.2） | P0 附 |
| X2 | Seedance | `seedance_bridge` 仅 raise 禁用 + 测；CLI 不暴露启用 | P1 |
| X3 | 文档分层 | 新 plan 落 `docs/plans/2026-08-06-quality-gates-lipsync-removal-todoplan.md`；lesson 晋升行更新 INDEX | P1 |
| X4 | 死 import / 空 shim | lipsync 删后 `test_w3_package_shims` 更新；勿留半截 shim | P0 随 L |
| X5 | 专家团原文纠偏 | 文档声明：**不做** lipsync canary 晋级；质量杠杆=原音+硬门 | P0 文案 |

**未纳入本轮但登记 backlog：**

- 成人弧 beat 齐备机读（foreplay→insert→ejac）  
- narrative closeout 重绑 receipt  
- 发色/首帧毒化进 style_lock 默认 NEG  
- 运动光流量化门  
- 字幕像素中文+无空格自动修  
- BGM 抗疲劳长片  

---

## 5. 执行顺序（单会话可交付切片）

```text
1. Wave L0a–L0b（fail-closed + CLI 退场）→ 相关 pytest
2. Wave L0c–L0d（删模块 + 文档墓碑）→ check-all 子集
3. Wave Q1 + Q5（已半实现，改 hard/接线）→ 快
4. Wave Q2 face register hard → 中
5. Wave Q3 continuity MVP → 中
6. Wave Q4 final heartbeat/timeout → 中
7. Wave Q6 doctor + X1 最小 + X3 文档
8. bump 2.40.0 · CHANGELOG · make lock-runtime（若指纹变）· make check-all
9. commit · fetch · push origin main
10. 收工摘要（中文）
```

并行安全：L 与 Q1/Q5 可交错；L0c 删文件前必须 L0a 测绿，避免半删 import 炸。

---

## 6. 文件触点（预期）

| 区域 | 路径 |
|------|------|
| 删 | `scripts/audio/lipsync_*.py`, top `lipsync_*.py` shims, `media/frw_lipsync.py`（或留 stub raise）, `node/*adapter*` lipsync, `tests/test_lipsync_*`, start-lipsync ps1 |
| 改 | `post/render_final.py`, `cli/cli_audio.py`, `cli/cli_status.py`, `shortform_director.py`, `config_loader.py`, `capability_report.py`, `workflow_pack.py`, `gates/*`, `cli/cli_media.py`, `final/voice.py`, `audio/audio_plan.py` |
| 文档 | `references/lipsync.md`, `hard-defaults.md`, `README` 矩阵行, `AGENTS.md` Audio 行, `CHANGELOG`, `plugin.json`, 本 plan 的 docs 副本 |
| 测 | 新 `test_lipsync_frozen.py`（禁启用）；`test_variety_*` 增强；`test_face_register_hard.py`；`test_continuity_programmatic.py`；`test_voice_lang_*`；`test_final_heartbeat.py`（轻） |

---

## 7. 验收清单（完成定义）

- [ ] `final --lipsync auto` **失败**且 next 指向原音路径  
- [ ] `rg` 生产路径无 lipsync 后端调用（仅墓碑/错误文案）  
- [ ] variety / face / voice_lang 在对应阶段 **hard** 可单测证明  
- [ ] continuity MVP 对 bad join **可红**  
- [ ] render_final 关键调用带 timeout；heartbeat 收据 schema 存在  
- [ ] `make check-all` 绿（validate + ruff + doctor + pytest -m 'not slow'）  
- [ ] `plugin.json` bump + CHANGELOG  
- [ ] git commit（英文）+ `git push origin main`  
- [ ] 用户可见收工：做了什么 / 怎么验 / backlog 剩什么  

---

## 8. 一句话

**先把已冻结的 lipsync 从代码里抬走，再把「门绿但翻车」的五个半成品门补成硬门；专家团的 lipsync 晋级项作废，杠杆在原音 + 程序化校验，不在死后端复活。**
