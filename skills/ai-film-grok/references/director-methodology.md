# Director Methodology · 40 年导演方法论注入总纲

> 本文档是 ai-film-grok 的导演方法论总纲——把一位 40 年资历电影导演的毕生方法论
> 注入这个 plugin 的每一个环节。每个维度都是**独立参数**，可被**考验**
> （schema 字段 → lint/度量 → 门禁 → 测试）。

## 一、方法论三原则

1. **去类型偏移**：`dramatic_function` 七值枚举不绑定任何单一类型默认。
   节拍骨架按 `genre` 切换（adult/drama/mystery/arthouse/documentary）。
2. **独立参数化**：每个电影维度（锁脸/锁服装/发型/妆造/场景/美术/分镜/
   声音/BGM/台词/调色/节奏）是 schema 独立字段，不塞进自由文本 blob。
3. **考验三件套**：每个参数同时具备 ① schema 字段 ② lint/度量 ③ 门禁
   （preflight hard 或 review 维度）④ 测试——缺任一则"不可被考验"。

---

## 二、前期 PRE-PRODUCTION

### 1. 节拍骨架（beat spine）
- **参数**：`genre`（drama-graph + film-spec schema）
- **切换**：`select_beat_spine(genre=...)` → `GENRE_SPINES[genre]`
- **方法论**：不同类型片有不同节拍结构。剧情=三幕弧，悬疑=信息驱动，
  文艺=氛围驱动，纪录=事实驱动。成人=六拍脊柱（向后兼容）。
- **文档**：[beat-spines.md](beat-spines.md)

### 2. 三幕结构 + 节奏曲线
- **参数**：`act_structure`（setup/confrontation/resolution + 比例），
  `pace_chart`（每段 start_ratio/end_ratio/cut_freq/intensity）
- **门禁**：`act_structure_strict` / `pace_chart_strict`
- **方法论**：三幕比例 ≈1:2:1 可调；节奏曲线与叙事位置对齐。

### 3. 角色设定表（character bible）
- **参数**：Character schema 16 字段（name/age/personality/want/need/flaw/
  ghost_wound/arc_turning_points/relationships/psych_markers/dramatic_role）
- **门禁**：`character_bible_strict` → protagonist 必须有 want/need/arc
- **模板**：[templates/character-bible.example.md](../templates/character-bible.example.md)
- **方法论**：角色不是一张图。40 年导演会问"这个角色为什么是这样的人？
  他的 wound 是什么？"

### 4. 锁脸 face-lock
- **参数**：`cast_locks`（per-character: face_ref_path/identity_lock_tokens/
  never_tokens/hair_lock/makeup_lock）
- **注入**：prompt_injector 优先使用 cast_locks 结构化字段
- **方法论**：锁脱离自由文本 blob，结构化。

### 5. 发型 hairstyle
- **参数**：`hair_swatches`（per-character: color_name/hex/description）
- **注入**：prompt_injector 构建 `Hair lock` 行（落实 consistency.md H4）
- **方法论**：发型是 continuity 杀手，独立参数化。

### 6. 妆造 makeup
- **参数**：`makeup`（per-character: name/ref_path/lock_tokens/cross_scene_consistency）
- **注入**：prompt_injector 注入 `Makeup` 行
- **方法论**：从 0/10 建起——妆造跨场不能无故变化。

### 7. 服装设计表（wardrobe sheet）
- **参数**：`wardrobe_variants`（per-character × state: garment/accessories/
  material/color/state）——从卸装阶梯升级为完整服装设计表
- **模板**：[templates/wardrobe-sheet.example.md](../templates/wardrobe-sheet.example.md)

### 8. 场景设计 sheet
- **参数**：Location schema 升级（color_temperature/set_dressing/lighting_plot/
  atmosphere）+ `derive_graph` 填充 `locationId`（不再 hardcoded None）
- **lint**：`SCENE_LOCATION_MISSING`

### 9. 美术设计 art direction
- **参数**：`art_direction`（color_script/visual_motifs/texture_continuity）
- **方法论**：脱离单字符串 palette/lighting，结构化色温脚本/视觉母题/质感锁定。

### 10. 分镜表 + 构图法则
- **参数**：Panel 升级（shot_number/composition_rule/camera_height/lens_mm/
  eyeline_target/axis_side/transition_to_next）
- **lint**：`lint_composition_rules`（180°轴线/30°原则/eyeline match/景别递进）

### 11. 对白台词库（dialogue ledger）
- **参数**：`dialogue_ledger`（DialogueLine: line_id/speaker/emotion/subtext/
  beat_ref/delivery_note/lipsync_anchor/is_key_line）
- **lint**：`DIALOGUE_LEDGER_MISSING`——有对白但无 line_id 锚点

---

## 三、制作期 PRODUCTION

### 1. 像素级 face identity 闸
- **门禁**：`FACE_IDENTITY_DRIFT`（post_audit warning → `aifilm face-identity enroll-bible && audit`；像素比对见 [face-identity-pixel](lessons-2026-07-23-face-identity-pixel.md)）
- **方法论**：字节 SHA 链保证"下镜从上镜末帧出发"，但像素锁需要 face identity
  比对。诚实声明能力边界——不做自动 face embedding，但要求人工/工具验证。

### 2. 跨镜头一致性 lint
- **lint**：`lint_production_consistency`（WARDROBE_DRIFT / HAIR_DRIFT /
  MAKEUP_DRIFT / SCENE_LIGHT_DRIFT / CAMERA_RHYTHM_FLAT / LIPSYNC_DRIFT /
  VOICE_CHARACTER_MISMATCH）

---

## 四、后期 POST-PRODUCTION

### 1. 调色 color grading
- **参数**：`grade`（lut_path/color_temperature/saturation/contrast/brightness/
  skin_tone_protection/gamma）
- **门禁**：`color_grade_strict: true` → `COLOR_GRADE_MISSING` hard gate
- **方法论**：从 0/10 建起——成片"电影感"的核心。

### 2. 声音分层混音
- **参数**：`sound_plan.audio_tracks`（dialogue/SFX/ambience/foley/music
  各自 gain/ducking）
- **方法论**：脱离单 bed——声音是分层设计的。

### 3. BGM spotting + 情绪曲线
- **参数**：`sound_plan.music_spotting`（label/start_sec/end_sec/fade_in_sec/
  fade_out_sec/emotion/beat_ref/intensity）
- **事件**：sound_plan.events type 新增 music_in/music_out/fade_in/fade_out
- **方法论**：BGM 不再是整段 bed loop——有入点出点、有情绪段。

### 4. 导演复审升级
- **维度**：十一维（自 v1.22.0 由七维扩为十一维）——新增 rhythm/emotion/theme/performance
- **方法论**：导演复审不只校验元数据——真正考验节奏曲线、情绪弧线、
  主题贯穿、表演质量。

---

## 五、考验矩阵

> 2026-07-24 更新：P1 接活 5 处死代码 + P2 升级 6 处门禁硬度 + P3 补齐 3 处 stub。
> "骨架"→"肌肉"已填充，矩阵评分反映实际接线状态。

| 维度 | schema | lint | 门禁 | 测试 | 评分(前→后) | 备注 |
|---|:---:|:---:|:---:|:---:|---|---|
| 节拍骨架 | ✓ | ✓ | ✓ | ✓ | 3→8 | |
| 三幕+节奏 | ✓ | — | ✓ | ✓ | 2→7 | rhythm_strict 路径已测 |
| 角色设定表 | ✓ | — | ✓ | ✓ | 2→7 | |
| 锁脸 | ✓ | — | ✓ | ✓ | 4→6 | premium 默认 hard（P2-6） |
| 发型 | ✓ | ✓ | ✓ | ✓ | 2→7 | lint_production_consistency 接活（P1-1） |
| 妆造 | ✓ | ✓ | ✓ | ✓ | 0→6 | lint_production_consistency 接活（P1-1） |
| 服装设计表 | ✓ | — | ✓ | ✓ | 9→9 | lint_production_consistency 接活 |
| 场景设计 | ✓ | ✓ | ✓ | ✓ | 6→8 | lint_locations 接活（P3-13） |
| 美术设计 | ✓ | — | — | ✓ | 5→7 | |
| 分镜+构图 | ✓ | ✓ | ✓ | ✓ | 3→8 | lint_composition_rules 接活（P1-2） |
| 对白台词库 | ✓ | ✓ | ✓ | ✓ | 3→7 | validate_dialogue_contract 接活（P1-3） |
| face identity | — | — | ✓ | ✓ | 4→7 | premium 默认 hard + drift 测试（P2-6） |
| 服装/发型/妆造一致 | — | ✓ | ✓ | ✓ | —→7 | lint_production_consistency 接活 + 测试（P1-1） |
| 场景光影 | — | ✓ | ✓ | ✓ | 2→7 | lint_production_consistency SCENE_LIGHT_DRIFT |
| 运镜曲线 | — | ✓ | ✓ | ✓ | 4→7 | meaningful_motion_strict 接入 preflight hard（P2-7） |
| lipsync质量 | — | ✓ | ✓ | ✓ | 2→6 | lint_production_consistency LIPSYNC_DRIFT |
| voice绑定 | — | ✓ | ✓ | ✓ | 4→6 | lint_production_consistency VOICE_CHARACTER_MISMATCH |
| 调色 | ✓ | — | ✓ | ✓ | 0→7 | premium 默认 strict（P2-8）+ lighting timeline 驱动（P1-5） |
| 声音分层 | ✓ | — | ✓ | ✓ | 3→7 | audio_bible premium hard（P2-11） |
| BGM spotting | ✓ | ✓ | ✓ | ✓ | 2→7 | audio_visual_alignment AV 对齐度量（P3-12）+ premium hard |
| 导演复审 | — | — | ✓ | ✓ | 3→6 | |
| AV 时序对齐 | ✓ | ✓ | ✓ | ✓ | 0→7 | audio_visual_alignment 重写（P3-12）：BGM cue vs shot boundary, VO onset vs cut |
| LUFS 响度 | ✓ | ✓ | ✓ | ✓ | 2→7 | 三套统一为 -16±2（P3-15）|
| VO 去 AI 味 | ✓ | ✓ | ✓ | ✓ | 0→6 | vo_lint_strict（P2-10）|
| post_bible | ✓ | ✓ | ✓ | ✓ | 2→7 | premium advisory→hard（P2-11）|

---

## 六、方法论演进方向

剩余可深化的方向（后续迭代）：
- **像素级 CV 校验**：face embedding / 服装颜色直方图 / 光照估计（需 CV 后端）
- **三幕比例自动校验**：成片实际幕比例 vs act_structure 声明比例（P4-16）
- **节奏曲线兑现校验**：成片切镜频率 vs pace_chart 声明曲线（P4-17）
- **BGM 与 beat 对齐校验**：music_spotting.beat_ref vs 实际 beat 时间轴（P4-18）

这些方向的 schema 字段和 lint 代码已就位——只差 CV/音频分析后端的接入。
**2026-07-24 进展**：LUFS 已统一为 -16±2 hard（不再是 warning）；AV 时序对齐已实现（BGM cue vs boundary, VO onset vs cut）；死代码全部接活；premium 项目门禁硬度已到位。剩余 CV/成片兑现校验为后续迭代。
