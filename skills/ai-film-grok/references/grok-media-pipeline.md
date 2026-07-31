# 动作媒体管线（FRW LTX → Grok → FRW Wan → local）

**Grok Imagine** 负责身份/静帧；动作 I2V 默认依序使用 **FRW LTX 2.3、Grok、已证明模型身份的 FRW Wan、已验证本地路线**。本地持久化队列负责去重、预算、退避、回执与断点续作。Python 不内嵌 key；FRW 经 frwclaw `.env`。

## 工具分工

| 工具 | 用途 |
|---|---|
| Grok `image_gen` | 无源图的风格/角色/场景 master |
| Grok `image_edit` | 身份保持的镜头变体与修复（bulk still） |
| **FRW `img2video`** | 显式 legacy 救生艇；不得作为默认 bulk 2V |
| **FRW `first-last-frame`** | 有明确首尾帧时锁构图 |
| FRW `img2video-audio` | 当前 `ltx23_primary` 第一动作路线；须影片级批准 canary |
| Grok `image_to_video` | 第二动作路线；不宣称 FLF |
| FRW Wan I2V | 第三路线；canary 与响应都须明确证明 Wan 模型身份 |
| Grok `reference_to_video` | 多参考运动；不宣称精确 first/last 锁定 |
| `"$AIFILM" frw …` | 官方 dispatch 代理 |

## 生成原则

- **Keyframe-first**：I2V 输入 = 本镜 `keyframes/shotXX`；keyframe 主 ref = **状态照** `cast_state_masters[id][wardrobe_state]` 或 undress-anchor（非 full cast）。视频不对 → 改 keyframe/状态照再 I2V。见 [keyframe-first-state-index.md](keyframe-first-state-index.md)。
- 沿用 film `aspect_ratio`；默认 480p，用户要求或重点镜头才用 720p。
- prompt 顺序：主体 → 动作 → 场景 → 风格签名 → 镜头 → 光线。
- 一镜一动作；写清相机与身体/环境运动。禁止空 motion 或 mouth-speaking-primary。
- 默认 6 秒；只在动作真需要时用 10 秒。
- 当 endpoint/model 或会话能力变化时，先生成一条低成本 canary，检查完整解码、时长与运动。

## 持久化队列

```bash
SKILL_DIR="$HOME/.grok/skills/ai-film-grok"
Q="$SKILL_DIR/scripts/media-queue"

"$Q" --budget-units 20 add \
  --root "<root>" --shot-id shot01 --operation image_to_video \
  --prompt-file "<prompt.txt>" --input "<keyframe.png>"
"$Q" status --root "<root>"
"$Q" claim --root "<root>"
```

`add` 用 operation + shot ID + prompt hash + input hash 去重，队列不保存 prompt 明文。`--budget-units` 设置新队列的初始生成单元上限，不是费用估价。已存在的队列要明确调整：

```bash
"$Q" budget --root "<root>" --units 30
```

每次只 claim 一项，复制回传的 `job_id` 和 `claim_token`，调用当前锁定的 provider 后立即回写。每个 FRW 路线都须对应 canary；已启动路线只可在技术失败后签名切换：

```bash
# 显式 FRW legacy 救生艇（先 upload keyframe，再 img2video --wait）
"$Q" complete --root "<root>" \
  --job-id "<job-id>" --claim-token "<token>" \
  --output "<generated.mp4>" --endpoint frw_img2video \
  --provider-request-id "<optional-task-id>"

"$Q" fail --root "<root>" \
  --job-id "<job-id>" --claim-token "<token>" --error "<sanitized-error>"
```

`complete` 会拒绝无可观察且不连续的运动：单次硬切即使让平均像素差很高，也不能把静态轮播伪装成动态镜头。通过后会写入 endpoint、时间、输出 hash 和 QA 回执。`fail` 默认指数退避，确定不可重试才加 `--terminal`。

进程意外结束后：

```bash
"$Q" reconcile --root "<root>" --stale-after 1800
```

能力回执：

```bash
"$Q" capability --root "<root>" \
  --endpoint frw_img2video --media "<verified-moving-clip.mp4>"
```

## 生成后注册

```bash
AIFILM="$SKILL_DIR/scripts/aifilm"
"$AIFILM" reencode-clips --root "<root>"   # FRW 编码建议先 clean
"$AIFILM" register-clip --root "<root>" --shot-id shot01 \
  --source "<clip.mp4>" --source-endpoint frw_img2video \
  --identity-approved --motion-approved \
  --review-note "provider=frw identity_lock_ok；相机与身体动作可见"
```

队列 `complete` 是技术验收；`register-clip` 另要人工验收身份与运动。两者不可互相替代。

## 能力边界

- Grok I2V 不保证 endpoint match 或 A/B 连镜精确衔接；**`motion_first_last: false`**（只有 frame-1）。
- **bulk 默认链**：FRW LTX 2.3 → Grok → verified FRW Wan → verified local；legacy `img2video` 不在自动链。见 [frw-degrade-dispatch.md](frw-degrade-dispatch.md)。
- **流畅度（强制）**：continue 缝 **逐字节复用**上镜已核准末帧为下镜 2V frame-1——`extract-frame --promote-keyframe <next>`；长片维护 `continuity_chain.md` 九项核对；**禁止** cast 重起、禁止 dissolve/定格/倒放/插镜掩盖。见 [continuity_chain.md](continuity_chain.md)。
- 需要引擎级 first/last lock 时用 FRW `first-last-frame`，仍共用 pose 字段 + chain 文件。
- Grok HTTP 429 / FRW 排队时串行请求，让队列退避，只恢复缺失镜头。
