# 四工具闭环：脚本 → 动效 → 剪辑 → 渲染

> 2026-07-23 · ai-film-grok × {HyperFrames, Remotion, video-use, Seedance}
> 全程 AI 闭环，每个工具落位到八环主脊的精确环节。

## 一句话

| 工具 | 在闭环里的角色 | 落地模块 |
|------|---------------|---------|
| **Seedance** | 电影级运镜提示词（camera language + visual styles） | `cinema_prompt.py` → `dsl.camera_prompt`；`seedance_bridge.py` → `@Image1` 结构化 prompt |
| **Grok I2V / Seedance** | 生成式动效（image-to-video） | `i2v_provider.py` 注册表（Grok + Seedance provider） |
| **video-use** | 真人素材剪辑（词级 ASR + 音频优先卡点） | `real_footage.py`（ingest-footage）+ `auto_cut.py`（auto-cut） |
| **HyperFrames / Remotion** | 设计后期（片头/字幕/underlay/渲染） | `compose_render.py`（已接 + 时长分卷 + 转场受控） |

## 闭环路径

```
Idea → Story → Beats → Shots
  ↓ cinema_prompt.inject_camera_prompts  (Seedance 运镜词库)
  ↓ prompt_injector 写 prompts/*.txt    (camera_prompt 进 I2V 指令)
  ↓ seedance_bridge.bridge_film_spec      (camera_prompt → @Image1 结构化 prompt)
Media → Selects
  ↓ i2v_provider.provider_priority()       (FRW LTX → FRW API I2V → Grok Video 1.5)
  ↓ (生成式 clip) 或 ingest-footage → auto-cut (真人素材)
  ↓ edit_policy.merge_edls                (生成式 + 真人 EDL 合并, 字幕最后)
(Cut) → Rough
  ↓ color_grade.plan_shot_grades          (palette → ASC CDL)
  ↓ compose_render.duration_advisory      (>90s HF 分卷建议)
Verified → final (HF/Remotion designed-post) → review → export
```

## 新增模块清单

| 模块 | 命令 | 职责 |
|------|------|------|
| `cinema_prompt.py` | `aifilm …`（write-spec 内调） | Seedance 运镜词库 → `dsl.camera_prompt` |
| `seedance_bridge.py` | `aifilm …`（I2V 前调） | camera_prompt → `@Image1` 中文结构化 prompt + negative + 分段 |
| `i2v_provider.py` | `aifilm capability`（注册表探针） | Grok/Seedance provider 抽象 + profile 路由 |
| `real_footage.py` | `aifilm ingest-footage` | 真人素材 → local Whisper → takes_packed.md |
| `auto_cut.py` | `aifilm auto-cut` | 词边界 + 静默卡点 → EDL（video-use Hard Rules 6/7） |
| `color_grade.py` | `aifilm …`（final 前调） | palette → ASC CDL per-segment 调色 |
| `compose_render.duration_advisory` | `aifilm compose-render` 内 | >90s HF 分卷 / >180s 路由 /general-video |
| `edit_policy.merge_edls` | `aifilm …`（assemble 前调） | 生成式 + 真人 EDL 合并（字幕最后） |

## 决策树

```
有真人素材？
  ├─ 是 → ingest-footage → auto-cut → merge_edls(生成式, 真人)
  └─ 否 → 纯生成式 clip
↓
I2V provider = provider_priority()  (ltx23_primary 默认；逐级 live gate)
  ├─ Grok: image_to_video (in-session)
  └─ Seedance: frw newvideo seedance-2-fast-i2v (恢复路径)
↓
final --post-engine hyperframes (默认) / remotion (实验)
  ├─ >90s → duration_advisory 分卷
  └─ 接戏缝 → hard match-cut (转场受控)
```

## 验证

- 闭环集成测试：`tests/test_closed_loop.py`（story_plan → cinema → seedance → i2v → grade → merge → advisory）
- doctor 探针：`video_use`（Whisper/helpers）+ `i2v_providers`（注册表）+ `designed_post`（HF/Remotion）
- 各模块独立测试：`test_cinema_prompt` · `test_seedance_bridge` · `test_i2v_provider` · `test_auto_cut` · `test_color_grade` · `test_merge_edls` · `test_duration_advisory`

## 相关

- [seedance-camera-vocab.md](seedance-camera-vocab.md) — 运镜/视觉词库
- [hf-transition-policy.md](hf-transition-policy.md) — HF 转场受控
- [remotion-captions-anim-slots.md](remotion-captions-anim-slots.md) — TikTok 字幕 + 动画槽
- [hf-remotion-capability-matrix.md](hf-remotion-capability-matrix.md) — HF/Remotion 能力矩阵
- [frw-degrade-dispatch.md](frw-degrade-dispatch.md) — Seedance 降级路线
