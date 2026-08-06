# Lessons · FRW 2V 优先（无限配额）

> 2026-07-20 · 映射 **P1 身份连续** + **P2 时空连续** + **P5 分层表达**  
> 触发：用户明确「FRW API 无限，确定性部分优先用 2V」

## 问题

- 旧 skill 把 FRW 写成 **「仅 Imagine 不可用时的降级」** → 有限 Grok 配额被 bulk I2V 烧光。  
- 文档写 `source-endpoint external`，代码只认 `image_to_video` → FRW clip 无法正规 register。  
- 「确定性」与「创作性」未分层：定妆与 bulk 动画抢同一付费通道。

## 决策

| 层 | Provider | 说明 |
|----|----------|------|
| 创作 / 身份 | **Grok Imagine** | style · cast · lookbook · bulk still |
| 确定性 2V | **FRW 优先** | 已批 keyframe → bulk 动画烧无限配额 |
| 兜底 | Grok I2V | FRW fail 或用户显式 `i2v_provider: grok` |

## 2026-07-20 晚 · 质量升级（胃镜室）

**无限 FRW ≠ 随便刷旧 `img2video`。**  
2V 命令默认升级为 **Seedance `newvideo`**：

| 项 | 新默认 |
|----|--------|
| CLI | `frw newvideo --model seedance-2-fast-i2v` · 9:16 · **720p 原生** · duration 5 |
| 有尾帧 | `seedance-2-pro-flf` |
| film-spec | `frw_video_model`（默认 `seedance-2-fast-i2v`） |
| register | `frw_seedance_i2v` / `frw_seedance_flf` |
| 禁止 | 默认 legacy `img2video`（模板 `348771…` 质量地板）；576→720 假清晰 |

完整事故账本与硬纪律：[lessons-2026-07-20-seedance-quality.md](lessons-2026-07-20-seedance-quality.md)。  
dispatch 契约：[frw-degrade-dispatch.md](frw-degrade-dispatch.md)。

## 落点

| 资产 | 变更 |
|------|------|
| film-spec | `i2v_provider` 默认 `frw`；**`frw_video_model` 默认 `seedance-2-fast-i2v`** |
| media_qa | `frw_seedance_i2v` / `frw_seedance_flf` / `frw_newvideo` + legacy endpoints |
| scripts/frw_dispatch.py | 解析 hermes/agents frwclaw + `.env`；文档强调 Seedance-first |
| aifilm | `"$AIFILM" frw …` 代理；reencode 默认 label `frw_seedance_i2v`；**不升分辨率** |
| 文档 | FRW-first for 2V **升级为 Seedance-first 质量** |

## 不可宣称

- Grok `image_to_video` ≠ first-last-frame  
- FRW 2V 通过 ≠ 身份已锁（仍须 cast + pilot still）  
- 用了 FRW ≠ 用了 Seedance  
- 未 reencode 的 FRW mp4 ≠ 可交付 clip  
- reencode 放大 576→720 ≠ 高清

## 验证

```bash
"$AIFILM" frw help
"$AIFILM" write-spec --root <root>   # i2v_provider=frw + frw_video_model=seedance-2-fast-i2v
# register-clip --source-endpoint frw_seedance_i2v 须被接受
```
