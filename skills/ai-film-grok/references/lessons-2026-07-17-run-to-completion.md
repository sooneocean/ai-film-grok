# 实战：pilot「可以」→ 一路生成完成（2026-07-17 · 仪玄午夜私课）

## 决策

用户说「可以 / 直接进行到生成完成」时：
1. `pilot approve --user-phrase "<原话>"`（须 scorecard 三维 pass）
2. `run_to_completion: true` 写入 approval
3. Agent **不得再停问**，批量 still/I2V → final（rnb+edge）→ 打开成片

## 批准词

- 通过：`可以` / `ok` / `好的` / `pilot 过` / 含 `生成完成` `做完` `直接进行`
- 拒绝：`可以改` / `不行` / `重做`

## 60s 时长

`film-spec` 每镜 `duration_sec` 作为 stretch **下限**（短 VO 静音 pad + 画面 hold），10×6s ≈ 60s。
