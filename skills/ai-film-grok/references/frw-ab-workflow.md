# FRW 全模型 A/B 工作流

FRW A/B 是独立评测层，不改变默认动作优先链。Pilot 可并行提交当前目录中同
operation 的全部可调用模型；production 必须先由机器 QA 排名，再由用户明确
批准 champion 与 challenger。人物主链进入 FRW 时仍需既有
`provider-switch-<shot>.json` 技术失败回执；此要求专用于 production I2V。

## 稳定阶段

```text
catalog → plan → run → poll → rank → approve → production plan
```

- `catalog`：只读调用 frwclaw `capabilities`，不提交任务。
- `plan --stage pilot`：同 operation 的全部 callable 平台／classic 模型。
- `plan --stage pilot --model A --model B`：只用于复测明确不合格候选；至少两个
  当前 eligible 模型，仍并行提交并保存选择范围。
- `--seed`：图像路由需要独立样本时显式传入；seed 与其余输入一样只保存
  SHA-256 绑定，并在 run 时要求完全相同。
- `run`：一次性并行提交；已有 run receipt 时拒绝重复生成。
- `poll`：并行查询一次，不自动重送。
- `rank`：本机文件 read-back。视频须完整解码、9:16 最小几何、24 fps 与真实
  motion gate；图片须可读且通过 9:16 几何门。
- `approve`：机器结果只是 provisional；必须保存用户原话。
- `plan --stage production`：只保留已批准的 champion＋challenger。

计划与运行收据保存 input SHA-256，不保存 prompt 或 URL 原文。task ID、媒体
SHA-256、catalog／plan／run／rank／promotion hash 形成可审计链。
`poll` 也有独立 `poll_sha256`；进入 rank 前必须与当前 run、全部 task ID
及 completed 终态一致，rank receipt 会再绑定该 poll hash。

## Pilot 示例

```bash
AIFILM="$HOME/.grok/skills/ai-film-grok/scripts/aifilm"

"$AIFILM" frw ab catalog --root "<film>"

"$AIFILM" frw ab plan \
  --root "<film>" --experiment-id shot01-i2v-pilot \
  --operation image_to_video --stage pilot \
  --content-class restricted \
  --prompt-file "work/shot01-i2v.txt" \
  --img-url "<public-https-keyframe>"

# run 必须重给完全相同的输入；hash 不同会阻挡
"$AIFILM" frw ab run \
  --root "<film>" --experiment-id shot01-i2v-pilot \
  --prompt-file "work/shot01-i2v.txt" \
  --img-url "<public-https-keyframe>"

"$AIFILM" frw ab poll \
  --root "<film>" --experiment-id shot01-i2v-pilot
```

使用 run receipt 的 task ID 和 query command 取得每个结果，将实际文件下载到
film root 内，再进入 QA：

```bash
"$AIFILM" frw ab rank \
  --root "<film>" --experiment-id shot01-i2v-pilot \
  --candidate seedance-2-fast-i2v=work/frw-ab/seedance.mp4 \
  --candidate ltx-i2v=work/frw-ab/ltx.mp4

"$AIFILM" frw ab approve \
  --root "<film>" --experiment-id shot01-i2v-pilot \
  --champion seedance-2-fast-i2v --challenger ltx-i2v \
  --user-phrase "pilot 过，可以量产"
```

## Production

相同 operation 的 promotion receipt 存在且 catalog hash 未变化后：

```bash
"$AIFILM" frw ab plan \
  --root "<film>" --experiment-id shot20-i2v-production \
  --operation image_to_video --stage production \
  --shot-id shot20 \
  --content-class restricted \
  --prompt-file "work/shot20-i2v.txt" \
  --img-url "<public-https-keyframe>"
```

production plan 只产生 champion＋challenger 两个候选，且
`changes_primary_provider=false`、`requires_provider_switch_receipt=true`。
执行前会核对 `receipts/provider-switch-shot20.json` 确实记录 Grok 技术失败；
它不会自动改 `film-spec.i2v_provider`，也不会把机器第一名冒充成人审批准。
非 I2V operation 仍须人审 promotion，但不套用 I2V 专属的 switch receipt。

production I2V 前须在本机环境设置至少 32 字元的
`AIFILM_PROVIDER_SWITCH_RECEIPT_KEY`。路由器用它签署 switch receipt；A/B
执行端会同时核对内容 hash 与 HMAC，缺 key、旧式无签章 receipt 或手工伪造值
一律 fail closed。密钥不得写入 film root、收据或版本库。

## Operation

目录 adapter 支持 `text_to_image`、`image_to_image`、`text_to_video`、
`image_to_video`、`first_last_frame_to_video`、`lip_sync`、
`motion_transfer`、`video_enhancement` 与 `text_to_speech` 的 plan/run/poll。
图片与视频具备本机 ranking adapter；音频目前保留 plan/run/poll，未有至少两个
通过专用音频 QA 的候选时不得 promotion。
