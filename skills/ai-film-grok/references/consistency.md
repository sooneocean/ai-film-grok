# Consistency（画风 / 身份 / 画质一致性）硬门禁

> 2026-07-16 教训：Kei 片用 FRW 批量 img2image 且定妆仅为角色设定转面图裁切 →
> 镜间画风漂、服装漂、质感不齐。**批量前必须有 cast master + pilot 审批。**

与 `write-spec` / `register-*` / `review-final` 纪律对齐。Agent **不得**用「赶工期」跳过本节。

## 0. 目标一句话

整片看起来像**同一套动画工房**画的，不是 22 张各自抽卡。

## 1. 资产层级（必须按序）

| 顺序 | 资产 | 路径约定 | 用途 |
|------|------|----------|------|
| 1 | **Style master** | `canonical/style-v1.*` | 介质/色板/光感/线条语言（可无主角脸） |
| 2 | **Cast master（每角一张）** | `canonical/cast/<id>-v1.*` | 脸、发型、瞳色、**默认全装**、身材比例 |
| 3 | **Lookbook（3 张）** | `canonical/lookbook/` | 近景脸 / 半身 / 情绪极端各 1，先批再量产 |
| 3b | **状态照 State photos** | `canonical/cast-states/<id>/{full,partial,undressed,bare}.*` | **衣着状态索引**；keyframe 主 ref（见 [keyframe-first-state-index](keyframe-first-state-index.md)） |
| 3c | **undress-anchor** | `canonical/wardrobe/undress-anchor.*` | 本片卸装峰值；≥partial 后可用 |
| 4 | **Shot keyframes** | `keyframes/shotXX.*` | 本镜 t=0；**只** `image_edit(状态照/已脱 still)`，禁止纯文生角色；**9:16 默认 ≥704×1280 全分辨率**（接受 provider 原生 704×1280；禁压缩缩略图，见 §1e） |
| 5 | **I2V clips** | `clips/shotXX.mp4` | **只**以 keyframe 为 frame-1 |

角色转面设定图（turnaround）**只能当参考**，不能直接当 `style-v1` 锁定成片画风。

### 1a. 输入图 → 画风锁（2026-07-23 · P0 稳定性）

> 写实多镜 I2V 脸漂；漫剧更稳。完整：[lessons-2026-07-23-style-lock-from-ref.md](lessons-2026-07-23-style-lock-from-ref.md)。

| 规则 | 要求 |
|------|------|
| **S0 Medium 先锁** | 开片选定 `anime` / `manhua` / `semi_real` / `photoreal`；写入 `style_fingerprint` |
| **S1 输入图 plan** | 有用户角色图 → `aifilm style-lock plan --ref`（裁 face-lock + plan JSON） |
| **S1a 上传图为全片锚** | plan 将上传图拷入 `source/` 并记录 SHA-256；`lock-style --from-plan` 默认用它建 `canonical/style-v1.*`，所有静帧与 I2V 队列必须把它作为实际 style input；有状态照时，状态照仍是唯一主像素参考 |
| **S2 禁止 sheet 当 9:16 脸** | 整页设定表只裁 FRONT/脸；cast master 9:16 用 `image_edit` |
| **S3 稳优先默认 manhua** | 用户要「漫剧/稳/一致」→ **不要**默认 photoreal |
| **S4 photoreal 明示低稳** | bulk 前 soft warn；pilot 人脸严拒 |
| **S5 参考输入硬闸** | 每镜 still 必须带上传 style image；I2V 必须走 `reference_to_video` 并同时带 keyframe + style image。`image_to_video`（只吃首帧）在参考图锁定项目中禁止入队 |
| **S5a 来源回执硬闸** | `register-still approved` 只接受已完成 `image_gen/image_edit` 队列任务；`register-clip approved` 只接受已完成 `reference_to_video` 队列任务。两者都要同镜、同输出 SHA-256、同上传 style SHA-256 的 `--queue-job-id` |

批量 Grok adapter 也必须真实上传两张图片：`--image` 是已验收 keyframe，`--ref` 是上传的 style anchor；不能只把参考图写在 prompt 里。
| **S6 像素路径** | 有角色 → 只 `image_edit(cast\|face-lock\|已过审 still)`，禁纯 gen 绕脸 |
| **S7 face-identity** | `aifilm face-identity enroll-bible && audit`；`receipts/face-identity.json#verified`；post_audit `FACE_IDENTITY_DRIFT` |

```bash
aifilm style-lock plan --root "$ROOT" --ref sheet.png --char-id hero --medium manhua
aifilm style-lock apply --root "$ROOT"
aifilm lock-style --root "$ROOT" --from-plan --cast-master … --char-id hero
aifilm style-lock check --root "$ROOT"
```

登记时保留队列回执，不能把未绑定参考图的本地图片直接混入成片：

```bash
aifilm register-still --root "$ROOT" --shot-id shot01 --source keyframes/shot01.png \
  --queue-job-id "<image-edit-job>" --identity-approved --review-note "style/id approved"
aifilm register-clip --root "$ROOT" --shot-id shot01 --source clips/shot01.mp4 \
  --source-endpoint reference_to_video --queue-job-id "<reference-to-video-job>" \
  --identity-approved --motion-approved --review-note "style/motion approved"
```

**Keyframe-first**：视频坏了 → **回头改 keyframe / 状态照**，不是从 full cast 平行重抽。详 [keyframe-first-state-index.md](keyframe-first-state-index.md)。

### Cast master 验收清单（全勾才算过）

- [ ] 脸型/瞳色/发型与用户参考一致
- [ ] **发色稳定**：与 ref/cast 同色名；禁霓虹光下漂成黑/棕/另一女主色（见 §1b）
- [ ] 服装主色与配件（如光环、领带色）稳定
- [ ] 介质正确（anime ≠ photoreal）
- [ ] 竖屏 9:16 或可安全裁切
- [ ] 明确 **18+ 成人**比例与脸
- [ ] 光线干净、可做后续 edit 锚点

### 1e. 静帧禁压缩 / 错幅（2026-07-22 · P0）

> 片例：薇薇安 EP01——`shot30.jpg` 为 **1152×864 横图**却被 I2V，成片呈「压缩糊」。用户：「图片被压缩导致影片也是压缩状态」。完整见 [lessons-2026-07-22-keyframe-no-compress.md](lessons-2026-07-22-keyframe-no-compress.md)。

| 规则 | 要求 |
|------|------|
| **C0 交付分辨率** | 9:16 默认 keyframe **宽≥704 且 高≥1280**；provider 原生 704×1280 不强制升到 720 |
| **C1 画幅** | `w/h` ∈ 0.50–0.62；横图/方图 **禁 I2V** |
| **C3 择优** | 同 stem `.png`/`.jpg` 并存 → **优先更高分辨率且过 C0/C1**（`pick_best_keyframe`） |
| **C4/C5 硬闸** | `register-still approved` + `preflight` 跑 `analyze_still_geometry`；fail 禁 bulk I2V |
| **C6 promote** | 末帧 promote **png 全像素**，勿再压低质 jpg |

**铁律**：I2V 不能「放大」糊 still；坏几何 = 整 clip 废。

### 1f. 先验后生 · 算力刀口（2026-07-22 · P0）

> 用户：「验证完再生成视频；图片也是一样逻辑；算力放在刀口上；重复生成成本过高」。
> 完整：[lessons-2026-07-22-verify-before-generate.md](lessons-2026-07-22-verify-before-generate.md)

| 规则 | 要求 |
|------|------|
| **V0 先验后生** | 上游过闸 → 才烧下游（still→I2V；ref→edit bulk） |
| **V1 出图即验** | image 落盘后先验几何+身份+结构，再 register / 当 ref |
| **V2 I2V 前再验** | 只吃 `pick_best_keyframe` 且 geometry ok 的路径 |
| **V3 坏了修上游** | 禁止对坏 still 盲重试 I2V；禁止未验 30 镜就 bulk 视频 |
| **V5 成本** | 修 1 张 still ≫ 盲烧 10 段 I2V |

### 1b. 发色硬锁（2026-07-21 · P1）

> 片例：双女主丝绒舞台——Astra 深青发漂成纯黑 → 无法辨认同人。完整见 [lessons-2026-07-21-hair-color-lock.md](lessons-2026-07-21-hair-color-lock.md)。

| 规则 | 要求 |
|------|------|
| **H1 可复述发色句** | 每角 `cast_locks.<id>` 写色名 + **NEVER** 禁色（例：`dark teal cyan-green; NEVER pure black`） |
| **H2 hair_swatches** | style-bible 建议写 `{ "id": "色名 #hex" }`；prompt 可复述 |
| **H3 多角多锚** | 镜内每位出场角色：**各自 cast master 都进 `image[]` 前列**（双人=两张 cast 在前） |
| **H4 Hair lock 行** | 每镜 still/I2V prompt 在 identity 后加 `Hair lock: …` 逐角重复 |
| **H5 pilot 发色** | 对照 cast 发色 fail = **identity fail**，禁 approve / bulk |
| **H6 漂了只修** | 用 cast master `image_edit` 修 still；**禁止**从已漂 still 平行重抽再 I2V |

**禁止**：只写 `dark hair` / `colored hair`；双人镜只喂一张 cast；靠 I2V「希望视频修回发色」。

### 1c. 画面零工程字（2026-07-21 · P0 致命）

> 片例：成片角落残留 `shot11` / `keyframe shot05`。用户定性**致命**。见 [lessons-2026-07-21-no-shot-watermark.md](lessons-2026-07-21-no-shot-watermark.md)。

| 规则 | 要求 |
|------|------|
| **T1 零工程字** | 画面禁 `shot##` · `keyframe` · `cast master` · `v1/v2` · 文件名 · 调试 caption |
| **T2 Prompt 不印 ID** | 镜号只在文件名/JSON；prompt **禁止**写 `shot11 keyframe` 等可被画成字的串 |
| **T3 干净句** | 每镜 still 必含：`No text, no watermark, no caption, no labels, no shot numbers.` |
| **T4 入组前检** | register-still 前目视/OCR 四角+底边；命中 → **禁 register / 禁 I2V** |
| **T5 脏了先 scrub** | `image_edit` 去字 → 复检 → 再 I2V；禁止脏 keyframe bulk |

I2V 成片若仍出现内生字幕、乱码、伪字或水印，不可用最终字幕覆盖或裁切掩盖：先运行 `visual-text-audit` 全解码帧审计；命中后运行 `visual-text-repair`，它会对命中帧及相邻帧逐帧 Qwen i2i，保留被拒绝源片、重编输出，再对修复片执行全帧复审与人工审。最终中文字幕只由 HyperFrames 在最后一层烧入。

**禁止**：带着角落 `shot11` 字样的 still 进成片；把工程 ID 写进 Imagine prompt 当画面描述。

### 1d. 首帧结构门禁（2026-07-21 · P0 致命）

> 片例：成片 ~33s `shot13`——**静帧手/身结构坏 → I2V 整段毒化**。用户：「首帧坏了导致整个片段都坏了」。
> 完整见 [lessons-2026-07-21-keyframe-first-frame-poison.md](lessons-2026-07-21-keyframe-first-frame-poison.md)。

| 规则 | 要求 |
|------|------|
| **F1 首帧=交付帧** | keyframe 按成片冻帧审，不是草图 |
| **F2 解剖学** | 手 **5 指**清晰；无多余肢；无躯干/腿融合；无破面「第三物体」 |
| **F3 高风险构图** | 双人无头+多手交叠 insert → 简化为单手/单腿清晰 insert |
| **F4 坏 still 禁 I2V** | F2 fail → 禁止 image_to_video，先修 still |
| **F5 I2V 后抽首帧** | `t=0` 与 `t=0.5s` 结构仍坏 → 禁 register-clip approved |
| **F6 final 抽镜起点** | 每镜起点 ±0.3s 抽帧；坏则换镜，禁只 re-final |

**铁律**：`I2V 首帧 ≈ keyframe`；**结构坏会演满 6 秒**。`motion_ok` 不能替代 `structure_ok`。

### 1e. 卸装后禁止回穿 · Still 源链（2026-07-21 · P0 致命）

> 片例：`xide-hardcore-thrust`——film-spec 已 `bare`，shot05–10 仍从**全装 cast master** 重画 → 丝袜/甲「穿回去」。用户定性**严重 bug**。
> 完整见 [lessons-2026-07-21-wardrobe-no-redress-still.md](lessons-2026-07-21-wardrobe-no-redress-still.md) · [sex-undress-ladder](lessons-2026-07-21-sex-undress-ladder.md)。

| 规则 | 要求 |
|------|------|
| **W1 脱下=永久** | 本片内 `wardrobe_state` rank **只前进**；afterglow 也禁回 full/armored |
| **W2 undress-anchor** | 卸装峰值 still 批准后立刻：`canonical/wardrobe/undress-anchor.png` |
| **W2b 状态照索引** | heat max 建议 `cast_state_masters` 齐 full/partial/undressed（±bare）；路径见 style-bible |
| **W3 peak 后源** | `partial\|undressed\|bare` 镜：**只** `image_edit(state photo \| undress-anchor \| 上一已脱 still)` |
| **W4 禁 cast 全装源** | peak 后 **禁止** 以全装 cast master 当 still 主 ref（脸可辅 ref，衣着必须以状态照为准） |
| **W5 I2V 锁衣** | motion 必写 `Keep first-frame clothing — never re-dress`；禁「重新穿好」 |
| **W6 抽检** | 从 peak 起每镜 t≈1s：半脱标记仍在；整齐全装 = **identity/escalation fail**，禁 final 装傻 |
| **W7 keyframe-first** | I2V 只吃本镜 keyframe；坏了先改 keyframe/状态照再 I2V（[keyframe-first-state-index](keyframe-first-state-index.md)） |

**铁律**：`wardrobe_state` 文字过闸 ≠ 像素过闸；**ref 全装 = 成片回穿**。
**禁止**：审核失败后用全装 cast 重起 act 十镜；并行 bulk `image_edit(cast)` 覆盖已脱镜。

### 1f. I2V 末帧禁止回穿 + promote 门（2026-07-22 · P0 致命）

> 片例：`astra-encore-120`——shot04 首帧 partial 正确，I2V 末帧红外套穿回肩/胸；promote 把毒末帧写成 shot05 → 全线回穿。
> 完整见 [lessons-2026-07-22-i2v-endframe-no-redress.md](lessons-2026-07-22-i2v-endframe-no-redress.md)。

| 规则 | 要求 |
|------|------|
| **W8 末帧门** | `register-clip` 前/后抽 last frame：肩/胸不得整穿**本片已脱**主外套/盔甲 |
| **W9 promote 条件** | 仅 W8 通过的末帧才可 promote → 下镜 keyframe；失败则 fail clip、重 I2V |
| **W10 I2V 硬词** | `Keep first-frame clothing — do NOT put [discarded] back on / never re-dress` |
| **W11 文字不污染** | `identity_lock` 只锁脸发；`ceremonial jacket ON` 等 full 词禁止进入 undressed/bare 的 Character/subject |
| **W12 motion 不换衣** | motion 分不够 → 加大转体/甩发/走步；**禁止**用回穿换 `motion_score` |

**铁律**：静帧对 + 末帧回穿 = 仍算回穿事故。**末帧才是衣着真相。**

## 2. 生成纪律（动作优先链）

1. **主角出现的每一镜**：`image_edit`，按 **wardrobe_state 选状态照为主 ref**；full 时用 cast master。
   - **W3**：已过卸装峰值 / non-full state → **主图 ref = state photo / undress-anchor / 已脱 still**；cast 仅可作脸辅，不得当衣着真相源。
2. Prompt **必须**以 `style-bible.signature_block` + `identity_lock` + **`Hair lock`** 开头（见 style-bible.md）。
3. 只改：pose / expression / environment / action / wetness / camera——**不改发色/瞳色/签名服色**。
4. **禁止**对主角反复 `image_gen` 从零抽卡。
5. 漂了：用 cast master 当 ref 修坏帧，不要整镜重抽换脸/**换发色**。

### 量产前 Pilot（硬）

在写满 10+ 镜之前：

1. 只做 **3 镜 pilot**（建议 hook + reaction + action）。
2. **用户**对比 cast master：脸 / 发 / 服 / 介质（agent 不得自批）。
3. 写 `receipts/pilot-approval.json`：

```json
{
  "approved": true,
  "approved_by": "user",
  "user_phrase": "pilot 过",
  "shots": ["shot01", "shot04", "shot11"],
  "compared_to_cast": "canonical/cast/kei-v1.png",
  "notes": "face/hair/outfit/medium match"
}
```

4. 缺 `approved_by: user`（或会话中用户原话批准）→ **禁止**批量。
5. 全片 still **同一 img2img 锚**（cast master）。禁止「机构戏用 cast、色气戏用 naked 用户图」两套锚。用户高色气图只作 **style 参考/lookbook**，定妆锚用着衣 cast。

## 3. Provider 路由（FRW LTX → Grok → FRW Wan → local）

当前默认是 `ltx23_primary`。FRW LTX 必须有当前影片 canary；缺证据时运行时跳到 Grok，不永久改写项目锁。FRW Wan 只有模型身份明确时才能启用；本地路线还要通过队列、RAM、VRAM 与 pilot。完整契约见 [hard-defaults.md](hard-defaults.md) 与 [frw-degrade-dispatch.md](frw-degrade-dispatch.md)。

| 规则 | 要求 |
|------|------|
| **分层** | 创作/身份静帧 → Grok；人物动作按 FRW LTX → Grok → verified FRW Wan → verified local |
| **Key canary** | 每条动作路线须有当前影片证据；API key 与 upload JWT 分离 |
| film-spec | 默认 `i2v_provider: auto`→`frw-ltx23`；回退顺序写入 `_layer_routing` |
| 技术失败 | 已尝试路线 timeout/429/5xx/连接失败才可签名切到下一条；质量、人工、未知拒绝不自动切换 |
| 锚点（若 FRW still） | 必须先 `upload` cast；每镜 **img2image**（禁止 text2image 出主角） |
| 模型 | FRW 侧 **整片固定同一 `frw_video_model`**；禁止半 Seedance 半 legacy 冒充 |
| 尺寸 | 保留 provider 原生画幅；9:16 的 FRW pair 可为 **704×1280**；禁止强制 720 或拉伸 |
| Prompt | 每镜前缀同一 `identity_lock` + `signature_block`；场景句放后半；Seedance 用 `@Image1 …` |
| **分镜动态** | 默认 FRW LTX 2.3；未就绪或技术失败依序到 Grok、verified FRW Wan、verified local |
| **禁止默认** | legacy `img2video` / 旧 FLF 模板（须显式 `legacy-img2video`） |
| **入口** | `"$AIFILM" frw …` 或 `scripts/frw_dispatch.py`；stdout JSON `protocol_version=1.0` |
| **入组** | 下载 → **`reencode-clips`（不升分辨率）** → `register-clip`（真实 endpoint） |
| 禁止 | 半片 Grok still + 半片 FRW still 混剪同一角色 |
| 禁止 | 长期半片 Grok I2V + 半片 FRW I2V（单镜兜底后尽快统一） |
| 禁止 | 错 poll 的 `frw_batch_flf`；把 Grok I2V 说成 FLF；403 后仍写 model=seedance |
| 质检 | 每 5 镜抽 1 镜对照 cast；失败整批 pause；每条已启用路线的 pilot 均须人审 |
| 注册 | `--review-note` 写真实 `provider=` `model=` `fallback=` `res=` `identity_lock_ok` |

```bash
AIFILM="$HOME/.grok/skills/ai-film-grok/scripts/aifilm"

# 仅在当前路线的 canary／门禁通过后，按动作优先链提交已批 keyframe
"$AIFILM" frw upload --file-path "<root>/keyframes/shot01.png" --category image
"$AIFILM" frw newvideo \
  --model seedance-2-fast-i2v \
  --img-url "<url>" --prompt "@Image1 <sig+lock+motion>" \
  --aspect-ratio 9:16 --resolution 720p --duration 5 --wait

# 有首尾帧时锁构图
"$AIFILM" frw newvideo \
  --model seedance-2-pro-flf \
  --img1 "<head-url>" --img2 "<tail-url>" \
  --prompt "@Image1 @Image2 continuous mid-action, subject stays centered" \
  --aspect-ratio 9:16 --resolution 1080p --duration 5 --wait

# 回 Grok 控制台（reencode 只 clean codec，不放大）
"$AIFILM" reencode-clips --root "<root>"
"$AIFILM" register-clip --root "<root>" --shot-id shot01 \
  --source "<clip.mp4>" --source-endpoint frw_seedance_i2v \
  --identity-approved --motion-approved \
  --review-note "provider=frw model=seedance-2-fast-i2v res=720p identity_lock_ok"
```

## 4. 注册门禁（人工）

### Still

注册前目视：

- 与 cast master 同一人（脸/发/服）
- 与 style master 同一介质与色级
- 无乱入元素、无儿童化脸

`review-note` 建议模板：`id-ok face/hair/outfit; medium=anime; cast=kei-v1`。

### Clip

- 身份不漂于该镜 still
- 可见运动（非冻帧）
- 不因 I2V 糊成另一画风

身份/画风 fail → `director-notes` + reshoot，**禁止**靠 assemble 硬拼。

## 5. 终审 scorecard

`review-final` 除原维度外必须评 **style**（画风统一）：

| 维度 | pass 条件 |
|------|-----------|
| identity | 主角可识别为 cast master |
| **style** | 介质/线稿或渲染/色板全片一致，无明显「换模型」感 |
| motion | 真实运动 |
| escalation | 叙事情绪弧成立 |
| audio / subs / dead_air | 同前 |

`style=fail` → 不得 `final_complete`；优先重做 still 再 I2V，不要只靠调色掩盖。

## 5b. 签名配件（光环 / 道具）硬锁

若角色设定含 **唯一视觉签名**（如 Kei 的粉色霓虹双文件光环）：

1. `identity_lock` 与 `signature_block` **必须**写清配件名称与位置（`MANDATORY … always visible`）。
2. cast master 验收：配件可见才算过；无配件 = 定妆失败。
3. 每镜 prompt 前缀重复配件；`negative_hints` 写 `no missing halo / do not remove …`。
4. pilot 抽检明确勾「配件在」。

教训 [2026-07-16 v2]：简化定妆漏掉光环 → 整片身份错误，须 v3 重做。

## 6. 反模式（本次踩过）

| 反模式 | 正确做法 |
|--------|----------|
| 转面图裁切当 style-v1 | 单独生成**成片介质**的 cinematic style + cast 立绘 |
| 批量 22 镜无 pilot | 先 3 镜批准 |
| Imagine 挂了就无锚点 text2image | FRW 也必须 img2image + 固定 model |
| 01–04 Grok、05–22 FRW 混用 | 选一条 provider 做完或全量重生成 |
| 只评 identity 不评 style | scorecard 含 style |
| 赶工跳过 lookbook | 近景/半身/情绪三张未批禁止量产 |
