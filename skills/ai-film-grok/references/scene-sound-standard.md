# 场景声音标准（Scene Sound Standard）v1

> **等级：P0（声音完整性）**。本标准规定每次带影片根目录的 `aifilm` 命令都必须
> 检查场景声音待办；`final` 必须执行已确认的声音计划并给出可核验回执。
> 它补足 I2V 静音素材，不能把 I2V 误称为原生收音。

## 1. 目标与边界

成片声音由四类独立内容组成：

| 类别 | 用途 | 例子 |
|---|---|---|
| `dialogue` | 叙事与角色说话 | 中文旁白、日文角色对白 |
| `ambience` | 连续空间感 | 房间底噪、走廊回响、雨声、街道 |
| `foley` | 画面中可见动作/道具 | 脚步、门把、开门、坐下、衣物摩擦 |
| `sfx` | 非写实的叙事强调 | 心跳、冲击、whoosh |

`sfx` 不得代替 `ambience` 或 `foley`。例如，角色开门时播放一个 generic chime
不等于完成开门声音。

本标准不改变既有语言锁：旁白为中文、角色口语为日文、字幕为中文。环境音和拟音
不是对白，绝不可写入 `nar` 或 `nar_ja`。

## 2. 每次运行的必经逻辑

### 2.1 适用命令

任何带 `--root <film>` 的影片命令开始时，必须运行**只读**
`scene-sound reconcile`；包括 `dispatch`、`advance`、`craft`、`write-spec`、
`audio-plan`、`final`、`status` 以及后续新增的影片根目录命令。

它必须：

1. 读取当前 `drama-graph.json`/`film-spec.json`、镜头动作、地点、道具与作者已有
   `sound_cues`；不得改动故事真相。
2. 推导每镜的环境、拟音和强调音需求；作者显式事件优先，自动推导只能补缺。
3. 写入或刷新 `receipts/scene-sound-status.json`（`--no-write` 时仅回传同内容）。
4. 在 `dispatch` 的待办中展示 blocking/`needs_review` 项目；不得静默省略。

该检查不可产生付费调用、下载、外发或覆盖音频。它只是发现与计划；执行仅在明确的
本地素材混音或经用户确认的外部动作中发生。

### 2.2 触发词与最低覆盖

规范词典至少识别以下语义；可从 `action`、`visible_change`、`location`、`props`、
`sound_cues` 或受控的动作描述导出：

| 画面语义 | 必须的 foley 事件 | 建议环境 |
|---|---|---|
| 走/跑/进入/离开 | `footsteps`（按步数或节奏重复） | 当前位置的室内/室外底噪 |
| 摸门把/推门/拉门 | `door_handle` + `door_open` 或 `door_close` | 门两侧空间的过渡 |
| 坐下/起身 | `seat_contact`、必要时 `cloth_rustle` | 当前空间底噪 |
| 拿起/放下杯、手机、钥匙、抽屉 | 对应 `prop_contact` | 当前空间底噪 |
| 无对白的建立或停留镜 | 无拟音也可 | 必须 `ambience`，除非作者标注为叙事静默 |

材质必须优先从已知视觉状态读取，例如 `floor=wood|tile|gravel`、
`shoe=heels|sneakers`、`door=wood|metal|glass`。未知材质不得伪造为精确声源，
事件必须标记 `needs_review: true` 并采用中性候选或等待人工指定。

## 3. 事件契约

所有运行时事件以镜头的 `audio_cues` 编译为可执行的 audio timeline；`sound_plan` 只
保留 BGM mute/duck 和叙事 `sfx_accent`，不得把未编译的 metadata 当作声音交付。

```json
{
  "event_id": "sc03-shot07-foley-01",
  "shot_id": "shot07",
  "track": "foley",
  "kind": "door_open",
  "at_offset_sec": 0.62,
  "duration_sec": 0.8,
  "material": "wood",
  "repeat": {"count": 1, "interval_sec": 0},
  "priority": "required",
  "source": "authored|inferred|library|procedural",
  "license": "local-library:<asset-id>",
  "needs_review": false
}
```

`track` 只能是 `ambience`、`foley`、`sfx`；`priority` 为 `required`、`recommended`、
`optional`。`required` 事件不可被自动覆盖或删除。每个已执行事件必须在回执内包含
实际素材路径、SHA-256、混入时间和 `executed=true|false`。

## 4. 缺口分级与动作

| 状态 | 条件 | 命令行为 |
|---|---|---|
| `ok` | 所有 required 事件有可执行素材/明确程序实现 | 继续 |
| `needs_review` | 动作/材质/时点不够确定，或作者要求静默 | 继续，但 dispatch 显示待确认 |
| `blocked` | 明确可见的 required 动作无素材、无安全降级或事件未落时 | `final` 失败关闭；其它命令显示阻挡项 |
| `degraded` | 仅使用受允许的通用/程序降级 | 可继续，但必须写明 `degraded_from` 和原因 |

默认可安全降级仅限抽象环境床或非关键的程序拟音。`door_open`、材质脚步、明显道具
接触等具象动作，若没有可信素材，必须 `blocked` 或由人审降级为 `recommended`；不得
把无关提示音标为已完成。

## 5. 最终混音与验收门

`final` 前必须将 `scene_events` 展开为绝对时间并输出独立：

```text
audio/ambience_stereo.wav
audio/foley_stereo.wav
audio/sfx_stereo.wav
audio/mix_report.json
receipts/scene-sound-status.json
```

`mix_report.json` 必须记录各 stem 的路径、SHA-256、来源/授权、全部事件的绝对时间、
执行结果、降级信息和对话 ducking。最终审片至少抽查：

1. 每个 required 动作音与可见接触点误差不超过 **2 帧**。
2. 每个非静默场景有连续 ambience，场景切换有合理淡变。
3. 对白时 ambience/foley/BGM 不遮盖中文旁白或日文角色语音。
4. `ffprobe` 可读取所有 stem 与混合文件；检查回执 hash 与实际文件一致。

未通过任一 required 项，交付状态只能是 `PARTIAL`，不能标记 `final_complete`。

## 6. 回执格式与展示

`receipts/scene-sound-status.json` 至少含：

```json
{
  "schema_version": 1,
  "source_projection_sha256": "...",
  "checked_at": "ISO-8601",
  "summary": {"required": 8, "ok": 6, "needs_review": 1, "blocked": 1},
  "events": [],
  "blocking_shot_ids": ["shot07"],
  "degradations": []
}
```

所有显示型命令仅总结数量和最紧急的三个镜头；完整事件只写入回执，避免控制台噪声。
任何故事/镜头/地点/道具改动使 `source_projection_sha256` 失效时，下次运行必须重新
扫描，旧回执不能作为完成证明。

## 7. 实施顺序与测试样本

第一批功能必须完整覆盖：室内/室外 ambience、木/金属/玻璃门的把手与开关、
木地板/磁砖/碎石的脚步。端到端基准样片为：**走路 → 扭门把 → 开门 → 进入室内**。

完成标准：单元测试覆盖词典、作者覆盖、未知材质、重复脚步、失败关闭与降级；端到端
测试证明三 stem、事件回执、混音回执、`ffprobe` 和人工声画审查均通过。后续扩充道具
不得削弱上述 P0 门禁。
