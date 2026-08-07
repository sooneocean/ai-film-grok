# Onboarding 重构：从"填空作业"到"AI 自动拆解"

> 目标：用户只输入 **一个故事 + 一张主角图**，系统像 agent 一样自动拆解成
> 角色 / 场景 / 分镜 / 声线 / BGM 情绪，并给出一份**可审阅、可编辑**的方案；
> 而不是让用户逐项填空。
>
> 日期：2026-08-07 · 状态：提案（待评审，未实现）

---

## 1. 问题诊断（当前痛点）

当前 `onboarding.py` + `console.html` 是**固定三步向导**：

```
① 参考物（逐条填 url） → ② 故事（粘贴文本） → ③ 角色（逐条填 id/名称/描述/图）
```

用户反馈的核心问题：

1. **像写作业**：每一步都是空白表单，必须手动枚举角色/参考物；早期用户根本没有资源可填。
2. **没有 agent 规划感**：系统只是被动收数据，不做任何"理解故事→拆解"的动作。
3. **`film-spec.json` 不被 onboarding 写**：genre / heat_scale 只能之后再设，导致 `collect_gates` 长期 `blocking`，起步即卡门禁。
4. **无图片上传**：角色图只能贴 URL/路径，无法"丢一张主角图进去"。
5. **缺自动拆解**：故事文本进了 `intake/story/story.md` 后，后续靠 `drama_graph.derive_graph` 从 `style-bible.json` 反推——但 `style-bible` 也是空的，等于没拆。

已具备、可复用的能力（不需要从零造）：

- `plan/local_llm.py`：私有 OpenAI 兼容 LLM 客户端（`draft()` / `shot_draft()`），配置 `AIFILM_LOCAL_LLM_BASE_URL`（私有/loopback `/v1`）+ `AIFILM_LOCAL_LLM_TOKEN`，`probe()` 探活；`glm-4.6v-flash` 视觉模型已在 `ALLOWED_MODELS`。输出语义为 `candidate_only / human_apply_required`（不写真值、不批门禁）。
- `drama_graph.derive_graph(root, write=True)`：`film-spec.json` + `style-bible.json` → 角色/场景/道具。自动拆解只要把方案写进这两个文件，`derive_graph` 自然接上。
- 既有安全不变式（`web_core` token / loopback / 哈希版本 409 / `write_json_locked` / 越界 404）可直接复用。

---

## 2. 设计原则

1. **最小输入、最大推导**：必填只有「故事文本」；主角图可选（有图则自动登记为 lead）。其余全部自动推导。
2. **agent 规划感**：用户点"让 AI 拆解"后，看到**流式思考步骤**（分析结构→识别主角→规划分镜→建议声线），最后给一份**预填好的方案**，而非空白表单。
3. **方案 = 提案，不是真值**：LLM 输出标注 `source: llm` 且 `human_apply_required`；用户可改、可增删，再"确认并启动"。符合 `local_llm` 既有 fail-closed 语义。
4. **优雅降级**：无本地 LLM → 走 `deterministic_decompose()` 启发式（绝不阻塞起步）。有 LLM → 走 `decompose()`。两种产物同构（同一份 plan schema）。
5. **不变式不破**：所有写盘仍走 `write_json_locked`；浏览器不发明生产状态；token/loopback/版本冲突 409/越界 404 全保留。

---

## 3. 目标交互流（用户视角）

```
┌─ Brief（唯一必填）─────────────────────────────┐
│  大文本框：粘贴你的故事 …                       │
│  📎 拖入/选择 主角图（1+，可选）                 │
│  [💡 氛围提示 chips：虐恋/悬疑/甜宠 …] 可选      │
│            [ ✨ 让 AI 拆解 ]                    │
└────────────────────────────────────────────────┘
        │ 点击后显示"思考中"步骤流（agent feel）
        ▼
┌─ Plan（AI 提案，全部预填、可编辑）──────────────┐
│  🤖 已为你拆解《故事名》  (来源：本地 LLM / 启发式)│
│  ├ 角色卡片：主角图缩略 + 名称/身份/描述  [编辑][+]│
│  ├ 场景/分镜：标题 + 摘要 + 情绪 + 地点         │
│  ├ 声线建议：角色 → 推荐 zh 声线               │
│  └ BGM 情绪：____                               │
│            [ ✅ 确认并启动流水线 ]               │
└────────────────────────────────────────────────┘
        │ 写 style-bible / film-spec / intake / derive_graph
        ▼
   跳转到 总览/选素材，门禁已就绪（不再一进来就 403）
```

保留一个「手动录入（高级）」折叠区，给需要精确控制的人用（兼容现有三步逻辑）。

---

## 4. 数据契约 & 落盘目标

**新增 `onboarding.json` 状态字段**（向后兼容旧 `steps`）：

```json
{
  "schema_version": 2,
  "kind": "onboarding",
  "revision": 0,
  "stage": "brief",            // brief | decomposing | plan | committed
  "brief": { "story_text": "", "image_paths": [], "hints": [] },
  "plan": null,                // 拆解方案（见下）
  "plan_source": null,         // "llm" | "heuristic"
  "go_status": null,
  "completed_at": null
}
```

**`plan` schema（LLM 与启发式同构）**：

```json
{
  "title": "故事名（推断）",
  "genre": "adult",
  "heat_scale": "max",
  "theme": "…", "tone": "…",
  "characters": [
    {"id":"lead","name":"…","role":"主角","description":"…",
     "is_lead":true,"reference_image":"intake/characters/lead.png"}
  ],
  "scenes": [
    {"title":"…","summary":"…","mood":"…","location":"…"}
  ],
  "shot_hints": [ {"action":"…","camera":"…"}, … ],
  "voice_suggestions": [ {"character_id":"lead","voice":"zh-CN-XiaoyiNeural"} ],
  "bgm_mood": "…"
}
```

**`go` 落盘（扩展 `_persist_canonical`）**：

| 目标文件 | 内容 |
|---|---|
| `film-spec.json` | **新增** `genre` / `heat_scale`（之前不写，导致门禁卡死）；保留已有字段 |
| `style-bible.json` | `characters` / `cast_masters`（含主角图）、`references`、`theme`/`tone` |
| `intake/story/story.md` | 故事原文 |
| `intake-manifest.json` | `characters[]`（带 `reference_image`）+ `story` 元信息 |
| `drama-graph.json` | **新增**：`derive_graph(root, write=True)` 自动从上面两文件生成角色/场景 |

> 关键收益：`go` 后门禁即刻就绪，`derive_graph` 直接产出可用图谱，不再需要用户事后手动补 `film-spec`。

---

## 5. 后端改造 TODO（模块 / 函数级）

### P0 · 脚手架 & 上传
- [ ] `scripts/onboarding.py`
  - 状态模型升级到 `schema_version=2`：`get_state` 兼容旧 `steps`；新增 `stage` / `brief` / `plan` / `plan_source` 字段。
  - `submit_brief(root, story_text, image_paths, hints, *, expected_revision)`：写 `brief`，`stage="brief"`。
  - `save_plan(root, plan, *, expected_revision)`：写用户编辑后的方案，`stage="plan"`。
  - `go()`：消费 `plan`（而非旧 `steps`）→ 调新 `_persist_canonical_v2`。
- [ ] **新增 `POST /api/upload`**（双网关：`web_api.py` + `post/review_ui.py`）
  - 仅 `multipart/form-data`，loopback + token；校验 `Content-Type` 白名单（png/jpg/webp）、大小上限（如 10 MB）、写入 `intake/characters/<sha16>.<ext>`；**禁止路径穿越**（basename only）。
  - 返回 `{path: "intake/characters/xxx.png"}`；复用 `web_core` 的 loopback/跨域拒绝。

### P1 · 拆解引擎
- [ ] `scripts/plan/local_llm.py`
  - **新增 `decompose(base_url, *, prompt, image_path=None, model=…, token=, timeout=)**：
    - `response_format.json_schema`（新增 `_DECOMPOSE_SCHEMA`：genre/heat_scale/theme/tone/characters[]/scenes[]/shot_hints[]/voice_suggestions[]/bgm_mood），`temperature=0`，`Draft202012Validator` 校验。
    - 若 `image_path` 且模型是视觉模型（`glm-4.6v-flash`）→ messages 加 `image_url` 多模态部分（描述主角）。
    - 沿用 `normalize_base_url` 私有网约束 + `human_apply_required` 语义。
  - `ALLOWED_MODELS` 已含视觉模型；无需改白名单。
- [ ] **新增 `scripts/onboarding_planner.py`**
  - `decompose(root, brief) -> (plan, source)`：
    1. 读 `AIFILM_LOCAL_LLM_BASE_URL`；`probe()` 可用 → 调 `local_llm.decompose`（带主角图若可见）；`source="llm"`。
    2. 否则 `deterministic_decompose(brief)`（见下）；`source="heuristic"`。
  - `deterministic_decompose(brief)`：启发式兜底（**不依赖 LLM**）
    - 场景：按空行/分段切分故事 → `scenes[]`。
    - 角色：中文「X说/道」、引号内称谓、首段高频专有名词 → 候选 `characters[]`；第一张上传图 → `lead.reference_image`，`is_lead=true`。
    - genre/heat_scale：若 `hints` 有给则用；否则给保守默认（如 `genre="adult"`, `heat_scale="max"` 仅当故事明显成人向；否则留可编辑空值并标 `needs_confirm`）。
    - voice：每个角色默认轮询 `ZH_VOICES` 列表。
    - bgm_mood：从 tone 关键词映射。
  - `render_plan_for_ui(plan, source)`：补前端展示字段（缩略图 URL、思考步骤文案）。
- [ ] `POST /api/onboarding/decompose`（双网关）：触发 `onboarding_planner.decompose`，返回 `{plan, source, stage:"plan"}`，`revision+1`。**同步返回**（LLM 私有网，几十秒；前端显示思考步骤流）。

### P2 · 提交（消费方案）
- [ ] `onboarding.py::_persist_canonical_v2(root, plan)`：按 §4 表写 `film-spec.json`（merge，不覆盖已有）+ `style-bible.json` + `intake/story/story.md` + `intake-manifest.json`。
- [ ] `go()` 末尾调用 `drama_graph.derive_graph(root, write=True)`（lazy import，fail-soft，写 `drama-graph.json`）；`advanced_detail` 含图谱角色数。
- [ ] `get_state` 把 `plan` / `plan_source` / `stage` 透传给前端（console-state 也加 `onboarding.stage`）。

### P3 · 前端重写（`scripts/web/console.html`）
- [ ] 替换 §167–205 的 onboarding `<section>` 为：Brief 面板（故事 textarea + 拖拽/选择主角图 + 氛围 chips + 「✨ 让 AI 拆解」）+ Plan 面板（角色/场景/声线/BGM **预填卡片，内联编辑**，来源徽章 `llm`/`heuristic`）+ 确认启动。
- [ ] 思考步骤流：点拆解后显示 `分析故事结构… → 识别主角… → 规划分镜… → 建议声线…`（agent feel；reduced-motion 下退化为静态"处理中"）。
- [ ] 保留「手动录入（高级）」折叠（复用旧 `saveStep` 三步逻辑），默认收起。
- [ ] 沿用既有：token 头、`api()` 封装、主题切换、magnetic hover、ARIA、`syncState` 多标签版本同步。

### P4 · 测试 & 门禁
- [ ] `tests/test_onboarding_planner.py`（新）：
  - `decompose` 走 mock `local_llm.decompose` → 结构化 plan；
  - 无 `AIFILM_LOCAL_LLM_BASE_URL` → `deterministic_decompose` 仍产出合法 plan（含 lead 图）；
  - `decompose` schema 校验失败 → 抛 `LocalLLMError`，不落盘。
- [ ] `tests/test_web_api.py` / `tests/test_review_ui.py` 扩：
  - `/api/upload`：拒绝越界/超大/坏类型；成功返回 `intake/characters/...`；
  - `/api/onboarding/decompose` → 200 + plan + source；
  - `/api/onboarding/plan` 版本冲突 → 409；
  - `/api/onboarding/go` 消费 plan → `film-spec.json` 含 genre/heat_scale、`drama-graph.json` 生成、角色数一致；
  - 安全：upload 跨域 → 403、坏 token → 401 不变。
- [ ] `scripts/smoke_console.py` 扩展：覆盖 upload + decompose + go-with-plan（保留现有 11 项门禁检查）。
- [ ] `make doctor` / `pytest -m console` / `ruff` 全绿；PR 模板勾选照旧。

### P5 · 文档
- [ ] `docs/RUNBOOK.md`、`references/web-review-console.md`：新增「AI 自动拆解起步」一节（brief→拆解→方案→启动）+ 本地 LLM 配置说明（`AIFILM_LOCAL_LLM_BASE_URL`）。
- [ ] `plugin.json` + `CHANGELOG.md` bump（特性变更）。
- [ ] 若改 `scripts/` 指纹：`make lock-runtime`。

---

## 6. 安全 & 门禁不变式（必须保留）

- 所有新端点：`require_auth` + `require_loopback` + 跨域 403 + 坏 token 401（复用 `web_core`）。
- `/api/upload`：内容类型白名单 + 大小上限 + basename 落盘（禁止 `../`、禁止绝对路径、禁止写 `intake/` 之外）。
- 拆解产物 `human_apply_required`：前端明确标注「AI 建议，请确认」；`go` 之前不写任何生产真值。
- 写盘全部 `write_json_locked`（0o600 + 排他锁）。
- 版本冲突：brief/plan/go 均哈希版本校验，stale → 409（双标签不互踩）。
- 不引入新第三方依赖（local_llm 已用 stdlib `urllib` + `jsonschema`）。

---

## 7. 风险 / 回滚 / 验收

**风险**
- 本地 LLM 不可用是常态 → 必须有 `deterministic_decompose` 兜底（P1 已含），否则起步体验反而更差。
- LLM 输出不稳定 → `decompose` 失败必须 fail-soft 到启发式，不报错卡死。
- 自动写 `film-spec.json` 的 genre/heat_scale 需尊重 `hard-defaults`（成人 MAX 等）；用户可在方案里改。

**回滚**：`onboarding.py` 保留旧 `steps` 读取兼容；若新流出问题，可切回「手动录入（高级）」折叠区，不影响既有 `go` 语义。提交按 P0–P5 小步推进，单 commit 可回退。

**验收标准**
1. 用户只贴故事 + 拖一张图 → 点「让 AI 拆解」→ 看到思考步骤 → 得到预填方案。
2. 无本地 LLM 时，同样流程走启发式仍能给出可用方案（不阻塞）。
3. 「确认并启动」后：`film-spec.json` 有 genre/heat_scale、`drama-graph.json` 生成、门禁不再一进来就 403。
4. `make doctor` + `pytest -m console` + `ruff` 全绿；`make smoke-console` 覆盖新流程。

---

## 8. 明确不做（范围外）

- 不做"全自动无人确认就开工"（违反 `human_apply_required` 与成人内容硬规则）。
- 不做跨网络 LLM（只用私有/loopback 本地池，符合 `local_llm` 既有约束）。
- 不改 `asset_picker` / 门禁 403 逻辑（本提案只动 onboarding 起步段）。
- 不做多语言故事解析泛化（首版聚焦中文故事 + zh 声线）。
