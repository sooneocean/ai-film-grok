# 短剧量产 SOP 桥接（运营层）

> 本文把「AI 短剧视频制作 SOP」的可执行纪律接到本 skill 已有的 Director Contract、Production Book 与证据门禁。
> **它不替代任何现有硬门禁，也不把计划、任务状态或模型成功误报为交付完成。**

## 为什么需要这一层

现有系统强在导演合约、资产/媒体哈希、真实解码、审片和交付证据；但操作者仍需要一张能回答四件事的运行卡：

1. 现在在哪一关、下一步是谁负责；
2. 这关必须交出什么，而不是「大概做过」；
3. 发现问题时该回到哪个最早的源头；
4. 哪些项目事实已经锁定，哪些仍可改。

本 SOP 以 **阶段产物 → 质量门 → 局部返工** 为单位工作。`aifilm director status`、`aifilm status` 与 receipts 是机器真相；运行卡是人类可读索引，不能反过来放行生成或交付。

## 开工运行卡（每集一张）

在 `brief.json` / `production-book.json` 的项目事实之外，为每一集维护一张 Markdown 运行卡（建议 `receipts/sop-run-card.md`，不含密钥或 provider URL）：

| 项目事实 | 必填内容 |
|---|---|
| 标识 | 项目、章节/集数、当前 revision、负责人 |
| 交付 | 画幅、母版分辨率、FPS、目标时长、字幕模式、交付平台 |
| 叙事 | 一句 hook、受众、旁白模式、角色对白语言 |
| 锁定物 | 当前 `brief` / `drama-graph` / `film-spec` / 三本 bible 的 revision + SHA-256 |
| 生产 | pilot 覆盖的镜头类型、已批准的 provider/profile、成本上限与批次大小 |
| 风险 | 未解决 P0–P3、受影响的 asset/shot/line ID、下一位责任人 |

开始任何付费或批量任务前，先跑 `aifilm doctor`、`aifilm director status --root <film-root>` 和 `aifilm preflight --root <film-root>`，并对**所选 provider/profile**执行它自己的 live-probe / no-spend probe（私有 5090 还要实查身份、queue、VRAM、RAM、磁盘）。`doctor` 会检查本地就绪状态和有限的 provider/OAuth 信号，但不构成所选路由的上传、付费、生成能力或远端容量证明；服务可用更不等于可交付。

## G0–G11 与现有工序的映射

| SOP 门 | 运营产物（给人看） | 本系统的权威产物/门 | 放行条件 |
|---|---|---|---|
| G0 初始化 | 运行卡、交付参数、能力/连接记录 | `production-book.json`、capability snapshot、`doctor` 加所选路由的独立 live-probe receipt | 参数完整；所选执行路由已有当前的独立 probe；未把 `doctor` 当成 upload/付费授权 |
| G1 原文整理 | 已分章原文、来源与不确定项 | Story T2T storyboard 草案/已批准脚本 | 原文事实、影视化增强和待确认项可区分 |
| G2 剧情拆解 | 分幕、镜头事件表、一镜一个主动作 | `drama-graph.json`、`film-spec.json`、`script_lock` | 每镜有可见主动作、因果与时长；前三镜有角色/冲突/悬念 |
| G3 全局美术 | 风格卡、区域规则、负面项 | `style-bible.json` | 视觉语言可执行且没有冲突；不是只写一个泛风格词 |
| G4 资产锁定 | 角色/妆造/场景/道具 ID 表 | assets registry、state index、continuity chain | 基础身份和剧情状态分离；每项能追溯到原文或明确增强 |
| G5 正式参考 | 每项唯一 approved reference 与版本 | reference SHA-256、face-identity / style audits | 核心资产只有一个正式源；候选图不能混入生产引用 |
| G6 分镜与声音计划 | 分镜卡：构图、动作节拍、终态、单一运镜、声音 | `film-spec`、timeline、dialogue ledger/audio timeline、`shot_animatic_lock` | 首/尾状态明确；动作不塞入 TTS；对白镜仍有视觉任务 |
| G7 Pilot | 在**最多 3 个 shot_id**内优先覆盖最高风险组合的测试片与结论 | pilot receipt + 人类 approval、媒体 QA | 能连续观看；人物、画风、动作、声音均实测；用户明确批准，才许扩批 |
| G8 分批生产 | 按场景/妆造的 batch 清单、失败/替代记录 | media queue、per-shot receipt、full decode/QA、dailies | 先验 still 再 I2V；未过审素材不得进入 time line；失败只重做受影响镜头 |
| G9 声音与字幕 | 台词表、音色锁、stems、SRT | dialogue package、audio delivery gate、subtitle audit | 台词与动作分离；最终人声驱动字幕；对白可懂度优先 |
| G10 合成与终检 | 审核版、三轮审片记录、问题 ledger | final/review-final/post-audit/master delivery | 静音看画面、闭眼听声音、音画合看均完成；修改后复查前后相邻镜头 |
| G11 交付归档 | 成片、字幕/台词、设定、素材、日志、known issues、恢复抽查 | export-desktop、hash-bound delivery receipt | 全片可解码/拖动/播放；版本一致；可定位并局部返工 |

### 三层事实状态

每项运行卡条目必须标记为：

- `draft`：已提出，尚未审；
- `locked`：人审和哈希绑定仍当前；
- `stale`：上游改动后必须重审/重做。

不使用「最终版」「最终版2」命名。文件名使用 `项目_章节_镜号_资产类型_vNN_状态.ext`；只有通过审核的素材可标为 `approved` / `locked`。版本递增，旧证据保留。

## 小样优先与安全批量

Pilot 不是随便抽三镜，而是**最多 3 个 shot_id**的最小风险覆盖集：优先合并环境建立、核心人物近景、动作、光线变化、至少一句角色对白或旁白等最高风险。如果三镜不足以覆盖，先取得用户的 Pilot 批准；不得为了「测试完整」直接加第 4 镜。它必须复用将要批量使用的资产绑定、模型/profile、关键参数和声音策略。

批量时优先按同一场景、妆造或连续动作链分组；并发从低到高。首帧/状态照不合格，回到 G4–G6 修源，不把坏图交给视频模型「碰碰运气」。任何 provider terminal status 都不是媒体验收：本地下载、完整 decode、`ffprobe`、抽帧/听检和人工审片缺一不可。

## 返工分流（最早错误源原则）

| 现象 | 回到的最早阶段 | 局部影响范围 |
|---|---|---|
| 换脸、年龄/发型/服装漂移 | G4–G5 资产或状态照 | 此 asset/state 的下游 shots；运行 stale propagation |
| 构图、主体位置、动作不清 | G6 分镜卡/首帧 | 单镜及连续镜的衔接点 |
| 视频融化、动作/运镜失控 | G6 节拍/动作设计 | 单镜重做；必要时换 end state，禁止盲重试 |
| 角色音色/表演不对、动作被朗读 | G9 台词表/音色锁 | 对应 `line_id` 与 lipsync/字幕证据 |
| 字幕、响度、音画不准 | G9–G10 时间线/混音 | 修改点与前后一镜的复检 |
| 错序、缺镜、不能播放或交付包不可恢复 | G10–G11 时间线/交付清单 | 阻断交付，修复后按影响范围复检 |

原则：先分类，再回到最早的错误源；只重做受影响资产、镜头或音频块。基础资产、风格或剧本改动要通过 `aifilm director impact` 预演影响面，再用 `director rebuild` 使下游显式 stale，绝不静默沿用。

## 终检：三遍观看 + 问题等级

最终母版必须 100% 完整观看三遍：

1. **静音**：因果、人物/状态、构图、动作、连续性、黑/闪/冻帧；
2. **闭眼**：对白可懂度、角色可分辨性、环境连续、音乐抢戏、爆音/断音；
3. **音画合看**：口型、动作声、字幕、转场和情绪节奏。

| 等级 | 决策 |
|---|---|
| P0 阻断 | 不可播放、严重内容/交付风险；禁止交付，修复并全片复检 |
| P1 严重 | 破坏理解、角色一致性或关键台词；必须修复并复检相关段落 |
| P2 一般 | 明显降质；原则上修复，保留须有人类明确记录原因与影响 |
| P3 轻微 | 可保留，但必须进入 known-issues 清单 |

**放行线：P0/P1=0；P2 要么清零、要么带人类签字的例外；P3 可带出但必须可追溯。** 这不取代现有 post-audit、字幕、真实运动、交付 read-back 或完整人审门禁。

交付完成后，建议执行一项**人工附加归档纪律**：至少保留一份独立备份，并抽查一次恢复。当前 `export-desktop` 与 delivery receipt 不会自动证明这件事；在它有可核验收据前，不得把它误报为现有机器门禁已经通过。

## 一页执行顺序

`开工参数 → 原文/故事板 → 剧情事件 → 风格/资产 → 正式参考 → 分镜+声音计划 → 覆盖式 Pilot → 分组生产与逐镜验收 → 声音/字幕 → 合成三遍审片 → 交付与恢复抽查`

日常入口仍是 `aifilm next --root <film-root>`；它给出机器计算的下一步。运行卡只把它翻译成制作人员可执行、可交接的任务，不创建隐藏的工作流或绕过权限、成本和人审。
