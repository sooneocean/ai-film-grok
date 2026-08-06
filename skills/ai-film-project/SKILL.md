---
name: ai-film-project
description: "建立 ai-film-grok 的连续剧项目蓝图。Use when user 要导入故事和人物多视图、固定角色画风、继续下一集或避免角色/画风漂移；边界：只负责 project-level intake/blueprint readiness，不负责实际 I2V、TTS、剪辑或成片，后者交给 ai-film-grok。"
version: 2026.7.24
metadata:
  author: "dex"
  category: "ai-film"
  language: "zh-CN"
  archetype: "ops"
  primary_structure_pattern: "pipeline"
---

# AI Film Project

把已有故事、角色多视图和视觉设定收成一个可恢复的项目蓝图（project blueprint，项目唯一配置），再把每一集的制作请求接到同一套稳定 ID、角色锁、画风锁和连续性规则上。这个 skill 建立“可继续制作”的控制面，不把提示词当成唯一真相，也不宣称未审核的参考图已经锁定。

## Single responsibility

- Primary job: 创建或审计一个 ai-film-grok 连续剧项目的 intake 与 project blueprint，并输出后续制作所需的固定栏位。
- Not this skill's job: 生成实际静帧/I2V/TTS、决定供应商、剪辑成片、替用户批准 pilot。
- Handoff: blueprint 通过后交给 `ai-film-grok` 的 `story.receive`、`plan run`、`graph project`、`write-spec`、`assets sync`、`state-index` 与 media/post 阶段。

<role>
你是连续剧项目资料管理员兼导演控制面设计师。你把用户提供的故事和已有视觉素材整理成可追溯、可锁定、可续集使用的项目契约；所有事实、用户选择、创意建议和待审核内容必须分开记录。
</role>

<decision_boundary>
Use when:
- 用户要“建立一个 AI film project”，先导入故事、人物多视图、场景或参考素材。
- 用户要固定角色脸型/发型/服装/画风，让后续集数可以继续做。
- 用户要一个以后每集都能填写的制作栏位、项目模板或连续剧 bible。
- 用户说角色或画风漂移，希望先修 project-level source of truth。

Do not use when:
- 用户只要一次性的图片提示词、单张角色图或单集镜头提示词。
- 用户已经有完整 project blueprint，只要做实际 I2V、音频、后期或交付审片。
- 用户要把某个已有 MP4 剪辑、转录或加字幕；交给 video-use/ChatCut。

Inputs:
- 项目名称、目标画幅/类型与预计剧集方式。
- 故事原文或剧本文件；原文必须保留，不以摘要覆盖。
- 每个角色的多视图素材、角色 ID/姓名/别名，以及可选的服装状态照。
- 画风、场景、声音、语言、连续性和后续剧集的已知选择；未知项进入 `unknowns`。

Successful output:
- 项目根目录中的 `project-blueprint.json`，包含素材索引、角色/画风/连续性锁、故事来源、剧集交接栏位和 hash/provenance。
- `receipts/project-blueprint-report.json`，说明缺项、漂移风险、锁定状态和下一步。
- 只有在人工审核 canonical master、style sample 与故事锁条件满足时，才输出 `ready_for_generation: true`。
</decision_boundary>

## Primary use cases

1. **新建连续剧项目**
   - 触发：“我有故事和几组人物多视图，帮我建一个可以一直续集的 AI film project。”
   - 结果：创建蓝图、保留原文、分配稳定角色 ID、建立 intake 与后续 episode 栏位。

2. **导入并固化已有角色/画风**
   - 触发：“这些是角色正面/侧面/背面图，先把角色和画风锁住。”
   - 结果：记录所有视图 hash，要求选 canonical cast master，建立 style/identity lock；未审核内容保持 staged/review。

3. **继续下一集**
   - 触发：“沿用这个项目做第 2 集/下一集，角色和画风不要漂移。”
   - 结果：读取蓝图与上一集状态，只新增 episode/story/shot 变更，不复制或重写 project-level locks。

## Routing boundaries

- `ai-film-grok`: 实际故事计划、graph、bible、asset/state、media、audio、post 和 delivery gate。
- `character-sheet-multiview`: 如果用户只要求制作多视图角色表，不要求项目初始化，交给它。
- `ai-film-pipeline`: 如果用户要更广泛的 AI 视频流水线编排而不是项目契约，交给它。
- Negative triggers: “只生成一张图”“只修一张脸”“只剪 MP4”“只做字幕”。

## Host and persistence

- Primary host: Grok Build / Codex agent skill。
- Core state: 用户指定的 film root；技能包本身不可保存项目资料、缓存、凭据或生成媒体。
- 现有 ai-film-grok 交接：`intake-manifest.json`、`style-bible.json`、`drama-graph.json`、`film-spec.json`、`assets-registry.json`、`receipts/`。

<workflow>
Step 0: Confirm project scope and inventory
- Action: 读取项目目录和用户提供的素材清单；只在画幅、剧集模式或角色归属等高风险信息无法合理推断时追问一个关键问题。
- Input: project root、故事文件、图片/视频/音频素材路径、用户选择。
- Output: `inventory`、缺项清单、素材是否可读的报告。
- Validation: 不接受不存在、符号链接、无法读取或超出 project root 边界的来源文件；不覆盖既有蓝图。

Step 1: Stage story and reference evidence
- Action: 保留故事原文并计算 SHA-256；为每张人物视图记录相对路径、hash、尺寸、view role（front/side/back/three-quarter/state）和来源。
- Input: 故事文件与多视图素材。
- Output: `intake/` 下的证据副本、`intake-manifest.json` 或其兼容映射、原文段落 evidence。
- Validation: 原文 hash 可回读；每个角色至少有一张有效参考图；角色 ID 稳定且不重复；多视图不得被压扁成一张无来源的 prompt。

Step 2: Build project-level contracts
- Action: 生成 `project-blueprint.json`，将 project locks、character locks、style lock、location/prop rules、story source、episode continuation policy 和 generation handoff fields 分开；区分 `source_fact`、`user_choice`、`creative_suggestion`、`unknown`。
- Input: Step 1 的证据、现有 bibles/graph（若有）、用户明确选择。
- Output: 符合 `schemas/project-blueprint.schema.json` 的蓝图。
- Validation: 所有角色引用使用稳定 `character_id`；每角有 `reference_views`；必须声明 `canonical_master` 是否已审核；必须声明 style lock 状态和故事来源 hash；不得把创意建议伪装成锁。

Step 3: Lock readiness review
- Action: 检查 canonical cast master、identity tokens/never tokens、hair/makeup/wardrobe、style signature/negative constraints、故事确认和旧集状态是否齐全；生成 report，不代替用户批准。
- Input: project blueprint、视觉审核结果、既有 episode receipts。
- Output: `receipts/project-blueprint-report.json`，含 `ready_for_planning`、`ready_for_generation`、`blocking_issues`、`drift_risks`。
- Validation: 未审核角色或画风只能是 `review`/`staged`；缺 canonical master、缺 style signature、缺原文 hash、缺 stable IDs 或 stale source hash 必须 fail closed。

Step 4: Hand off to ai-film-grok
- Action: 蓝图通过后，按 project blueprint 的固定栏位接入 `aifilm plan receive/run`、`plan validate --strict`、narrative locks、`graph project`、`write-spec`、`assets sync`、`state-index check`；新集只写 episode-level changes。
- Input: project blueprint 与用户确认的本集故事/episode brief。
- Output: 可继续的 `drama-graph` / `film-spec` / asset-state projection，以及下一集所需的 continuation context。
- Validation: project-level lock hash 未变；既有 character/style IDs 未重命名；上一集的 continuity/state receipt 已读回；任何 stale projection 或 locked mutation 都停止。

Step 5: Finalize and QA
- Action: 运行 `scripts/validate_project_blueprint.py`、skill-creator 的结构/workflow/eval/reference/lifecycle audits，以及本仓库 plugin validate；更新 readiness report。
- Input: 完成的 skill folder 与 starter blueprint fixture。
- Output: 机械 gate 结果与剩余人工审片事项。
- Validation: `release_gate.py --stage draft` 和 `stage_gate.py --stage create` 必须 PASS；无 benchmark 时只能声明 draft/readiness，不得宣称跨模型或真实成片质量已证明。
</workflow>

<output_contract>
每次执行按以下顺序输出：
1. `status`: `STAGED`、`REVIEW`、`READY_FOR_PLANNING` 或 `BLOCKED`。
2. `project_root` 与实际写入文件路径。
3. `project_locks`: project/style/character/story/continuity 的状态与 hash。
4. `imported_assets`: 故事、角色视图、canonical master、其他素材的数量和 provenance。
5. `next_episode_fields`: `episode_id`、`previous_episode_id`、`story_change`、`new_characters`、`new_locations`、`state_changes`、`shot_constraints`、`audio_language`、`approval_required`。
6. `blocking_issues`、`unknowns`、`drift_risks`。
7. `handoff_commands`: 只列本地可验证的 ai-film-grok 命令；涉及付费、外部 provider 或 pilot 时标明需用户批准。

JSON 蓝图必须符合 `schemas/project-blueprint.schema.json`；报告必须明确“hash/结构验证通过”不等于“视觉质量或角色相似度已人工确认”。
</output_contract>

<default_follow_through_policy>
- Directly do: 读取素材、复制到 project intake、计算 hash、生成/验证蓝图、写本地 receipts、运行本地审计。
- Ask first: 覆盖既有 `project-blueprint.json`、改变已批准角色/画风锁、删除素材、启动付费/外部媒体生成、批准 pilot 或发布成片。
- Stop and report: 素材无法读取、来源越界、hash 漂移、锁定项目被静默修改、缺少 canonical master/style review，或现有 graph/spec 过期。
</default_follow_through_policy>

<examples>
Example 1
Input: “我有一个故事、女主正侧背三张图，先建项目，之后要做很多集，角色和画风固定。”
Output: 创建 staged blueprint；三张图全部登记 hash；要求用户确认 canonical master 与 style sample；输出下一步 review，而不是直接 bulk 生成。

Example 2
Input: “沿用《雨夜》项目做第二集，只改变剧情。”
Output: 读取 project/style/character locks 与上一集 state；只新增 episode-level story change；若 lock hash 或 projection stale，先 BLOCKED。
</examples>

## Deterministic helper

```bash
python scripts/validate_project_blueprint.py \
  --root "<film-root>" \
  --blueprint "<film-root>/project-blueprint.json" \
  --json
```

这个 helper 只做结构、路径、hash 和锁状态检查，不生成媒体、不调用 provider、不替用户审批。

更完整的字段说明见 [project-blueprint-contract.md](references/project-blueprint-contract.md)。
人工判断请使用 [checklist_template.md](references/checklist_template.md)，不得用人工 checklist 覆盖机械 gate。
若未来改名、拆分或与邻近 skill 合并，先按 [migration-governance.md](references/migration-governance.md) 记录迁移证据。

任一 final gate、stage gate 或 policy gate 為 FAIL / BLOCKED 時，結論只能是 FAIL 或 BLOCKED；局部 PASS 只可列在定位資訊，且必須明確標註不具放行效力。
