# Lesson · 成片收尾门禁 IRON（P0 · 2026-07-29 · 后面不要再犯）

> 片例：`AI FILM SPACE/0729/chaebol-cast-rule-max`（财阀潜规则·顶层招待）  
> 用户句：「推进到最后」「把这些经验写回去 以后不要再犯」  
> 挂：`hard-defaults` · `SKILL.md` §18 · `memory/2026-07-29-closeout-gates-iron.md` · `stages/deliver.md`  
> 关联：[evirus bulk→final](lessons-2026-07-29-evirus-ch04-bulk-final-iron.md) · [high-motion](lessons-2026-07-27-high-motion-style-lock-final.md) · [sex-arc](lessons-2026-07-27-adult-scale-max-sex-arc.md)

## 一句话

**plate 有了 ≠ 收尾完了。**  
`film_final.mp4` 在 `out/` 只是起点；必须过 **heat final → adult-max sensory → motion gate → truth_contract → 字幕切镜 → 叙事证据 → quality（无冻帧缓存）→ review-final → post-audit → export-desktop**。任一门假绿 = 禁止宣称 DONE。

---

## 0. 收尾最短命令链（有 plate 之后）

```bash
AIFILM="$HOME/.grok/plugins/ai-film-grok/skills/ai-film-grok/scripts/aifilm"
R="<film-root>"

# 0) film-spec 改完立刻刷新 truth_contract（见 §3）
# 1) heat：双方脱尽字段 + assert_heat_allows_final
"$AIFILM" heat check --root "$R"
# 2) post-plan 先于 register（owner 与 post-engine 对齐）
"$AIFILM" post-plan --root "$R" init --owner hyperframes --force
# 3) motion：--rows 必须是 JSON 文件路径（禁超长内联）
"$AIFILM" i2v-motion-gate --root "$R" --rows "$R/receipts/_motion_rows.json" --write
# 4) 注册成片（post-engine 标签与 post_owner 一致）
"$AIFILM" register-final --root "$R" --source "$R/out/film_final.mp4" --post-engine hyperframes
# 5) 叙事三点 verified（媒体哈希=当前 final）
"$AIFILM" narrative-evidence init --root "$R"
"$AIFILM" narrative-evidence record --root "$R" --evidence-id "…" --status verified …
"$AIFILM" narrative-evidence validate --root "$R"
# 6) 改片后删旧质检缓存再 review
rm -f "$R/out/quality-report.json"
"$AIFILM" review-final --root "$R" --approve --watched-full --reviewer … --notes … \
  --score-* pass --grade-* 4… --screening-evidence "dim@sec:note" ×11
# 7) 审计 + 桌面
"$AIFILM" post-audit --root "$R"   # 须 delivery_ready=true
"$AIFILM" export-desktop --root "$R" --name "<中文名>" --force
```

CLI 坑：**多数子命令**是 `aifilm <cmd> --root R <sub>` 或 `aifilm <cmd> <sub> --root R`（以 `--help` 为准）。`post-plan` / `narrative-evidence` 常见写法：`post-plan --root R init`；`narrative-evidence init --root R`。

---

## 1. heat final：S:100 仍可能 hard_fail

| 现象 | 根因 | 铁律 |
|---|---|---|
| impact=S:100 但 `assert_heat_allows_final` 失败 | `hard_fail = bool(codes)`；**任一 code 即 hard** | 不只看分数，看 `heat check` 的 `codes` / `hard_relevant_codes` |
| `SEX_BOTH_UNDRESS_UNSTATED` | 插入镜只写了女主 `wardrobe_state`，**未写** `partner_wardrobe_state` | 对 act/climax/**penetration** 镜显式写 `partner_wardrobe_state=undressed\|bare`（dsl 同步） |
| `heat boost --apply` 显示 needed=false | boost 只修 impact，**不消 UNSTATED** | 修 film-spec 字段，不是再 boost |

**最小补丁（penetration 镜）：**
```json
"wardrobe_state": "bare",
"partner_wardrobe_state": "bare"
```

---

## 2. adult-max sensory（review-final 硬拦）

`build_evidence` 失败 codes 常见：

| code | 修法 |
|---|---|
| `ADULT_MAX_FOLEY_MISSING:<shot>` | `sound_plan.events` 增加 `type=sfx_accent` + `sex_sfx=true` + `shot_id`（act/climax 每镜） |
| `ADULT_MAX_AV_ALIGNMENT_MISSING` / `_LOW` | 写 `receipts/audio-visual-alignment.json`，`av_alignment_score`≥90（默认门槛） |
| `ADULT_MAX_MIX_EVIDENCE_MISSING` | `audio/mix_report.json` 必须有 **hash 绑定** `artifacts.{bgm,sfx,mixed}`，路径在 root 内且 sha 与文件一致 |

```json
"artifacts": {
  "bgm":   {"path": "<root>/audio/mix/bgm.wav",   "sha256": "…"},
  "sfx":   {"path": "<root>/audio/mix/sfx.wav",   "sha256": "…"},
  "mixed": {"path": "<root>/audio/mix/mixed.wav", "sha256": "…"}
}
```

有 `mixed.wav` / `bgm.wav` 不够；**没有 artifacts 块 = MIX 失败**。

---

## 3. truth_contract / stills / clips_complete

| 坑 | 铁律 |
|---|---|
| 改 `film-spec.json` 后 `clips_complete=false` 尽管 10 镜全 approved | `manifest.truth_contract.contract_sha256` **必须 = 当前 film-spec 的 sha256**；否则 `manifest_truth.ok=false` → `clips_complete` 假 |
| 手写 `pilot-approval.json` 用 `approver` | 合法字段是 **`approved_by: "user"`**（不是 `approver`） |
| still `status=frame_chain_seed` | **不算** approved；`stills_complete` 要 `status=approved` + 文件匹配 |
| pilot 短语 | 白名单含 `做完`/`可以继续`/`可以`/`ok`…；**`推进到最后`  alone 不进 approve 白名单**；`直接推到成片` 仅 rtc 不全等 approve。用户原话能进白名单才 `pilot approve`；禁止 agent 自拟短语冒充 |

刷新 contract（改 spec 后立刻）：
```python
manifest["truth_contract"]["source_of_truth"] = "local-contract-and-receipts"
manifest["truth_contract"]["contract_sha256"] = sha256_file(root / "film-spec.json")
```

---

## 4. 字幕 × 切镜时钟（SUBTITLE_CROSSES_HARD_CUT）

| 坑 | 铁律 |
|---|---|
| `timeline.json` 规划时长 ≠ 真实 concat | 收尾前用 **实际 plate/clip durs** 重写 `timeline.json` + 写 `receipts/film_timeline.json`（`shot_starts`） |
| SRT 按 VO 估时跨镜 | 每 cue **整段落在单镜** `[start+pad, end-pad]` 内；`chain_mode=continue` 的切点算 hard boundary |
| 只改 SRT 不重烧 | 像素烧字仍是旧时钟 → 收据记 PARTIAL「硬字幕略偏」；理想：改 SRT 后 **重烧** 再 register |

`i2v-motion-gate --rows`：**文件路径**，禁把整段 JSON 当 path（Errno 63 File name too long）。

---

## 5. quality 冻帧 + 缓存毒（review-final）

| 坑 | 铁律 |
|---|---|
| `hard-fail on freezes` | `freezedetect` ≥1s 静段即 fail；先 `ffmpeg … freezedetect` 定位 |
| 破冻后仍 fail 且 score 不变 | `load_quality_report` **按 video path 复用**旧 `out/quality-report.json` |
| 修法 | **重编码/改 final 后必须 `rm out/quality-report.json`**（及相关 detect txt）再 `review-final` |

破冻可对冻结窗加极轻时域噪：  
`noise=alls=4:allf=t+u:enable='between(t,T0,T1)'` → 再 register-final。

改 final 后还要：**重绑** `narrative-evidence` 三点（`NARRATIVE_MEDIA_HASH_STALE`）。

---

## 6. review-final / export-desktop 前置清单

**review-final 硬前置：**
- [ ] `clips_complete`（含 truth_contract + uniqueness + anatomy）
- [ ] `outputs.final_film` 已 register + technical_qa ok
- [ ] heat final_ok（无 SEX_* hard codes）
- [ ] adult_max sensory ok
- [ ] subtitle-cut-boundaries ok
- [ ] narrative-evidence verified 且 media hash 当前
- [ ] quality-report 当前且 `hard_fail=false`
- [ ] contract v2：`--watched-full` + 十一维 score/grade + 十一维 `screening-evidence dim@sec:note`

**export-desktop 硬前置：**
- [ ] `gates.final_complete=true`
- [ ] `post-audit` 存在且 **未 stale** 且 **`delivery_ready=true`**
- [ ] heat 再检（export 也会 assert）
- [ ] `i2v-final-gate.ok` 才许覆盖桌面主片（与 high-motion IRON 一致）

`register-final --post-engine` 必须与 `post-plan.post_owner` 一致（hyperframes 计划不可标 ffmpeg 除非改 plan）。

---

## 7. 简化 final 路径的诚实 PARTIAL

当 `aifilm final` 侧链超时/假死时允许：

1. concat 真 I2V  
2. edge VO + 批准 rnb `--music`（有 license）  
3. 简单 amix  
4. PIL/无空格路径烧中文字幕  
5. 走完 §0 收尾链  

**必须**在 `receipts/delivery.json` 写：

- `status: PARTIAL`（若 Imagine 无真 bare / 非官方 full sidechain）  
- `honest_limits[]`：双轨暗示、简化混音、SRT 与烧字时钟差、foley 仅台账等  
- **禁止**用内衣/军裤 still 或软提示冒充「插入完成」

---

## 8. 片例回读（chaebol 2026-07-29）

| 项 | 结果 |
|---|---|
| 成片 | ~62s · 720×1280 · quality 88 |
| motion | 全镜过 floor；i2v-final-gate ok |
| review-final | 十一维 pass · final_complete true |
| export | `~/Desktop/财阀潜规则·顶层招待/` |
| PARTIAL | Imagine 双轨非真 bare；plate+VO+rnb+烧字+破冻，非 full sidechain |

---

## 禁止（checklist）

1. 有 `film_final.mp4` 就报 DONE  
2. `approver` 手写 pilot、或 agent 自拟「做完」  
3. impact S 却无视 `SEX_BOTH_UNDRESS_UNSTATED`  
4. 无 mix `artifacts` / 无 AV alignment / 无 sex_sfx 事件就 review  
5. 改 film-spec 不刷 `contract_sha256`  
6. `timeline` 规划钟 vs 真 concat 混用导致字幕跨切  
7. 改片不删 `quality-report.json`  
8. 改 final 不重绑 narrative-evidence  
9. post_owner 与 register post-engine 打架  
10. `--rows` 塞超长内联 JSON  
11. bare 被拦却用着装镜装插入  
12. export 前跳过 post-audit freshness / delivery_ready  
