# 创作工作室合同

`workshop` 把剧本创作的判断转成离线、可审计的生产输入；它不是生成器，也不替代
人工导演审批。

## 权属与边界

- `creative-brief.json`：平台、节奏、受众、时长、类型和创作约束；唯一可由 workshop
  写入的源文件，必须提供当前 `revision`。
- `drama-graph.json`：故事、表演和镜头的唯一真相；`apply` 只能把已验证的镜头层创作投影
  写回这里，必须给 `--expected-graph-revision`，并且目标镜头与 `shots` 范围都未锁定。
- Visual / Audio / Post Bible：视觉资产、声音和后期的唯一真相；workshop 不修改。
- `receipts/workshop/`：诊断、导演包、验证与供应商文本导出的 hash 绑定派生产物。

## 工作顺序

1. `intake` 保存确认的创作 brief。
2. `diagnose` 输出七维台词诊断（角色声音、潜台词、冲突、类型、信息、可朗读性、记忆点），不重写台词。
3. `compile` 从 canonical drama graph 编译每镜导演字段、资产职责和音乐 Cue Sheet。
4. `validate` 检查时长、镜头字段、内部 ID 泄漏、九图上限、素材职责和单实例道具。
5. `apply --expected-graph-revision N`（可选）把通过严格验证的镜头功能、段末状态、台词节拍与
   素材职责写回 `drama-graph.json`，生成叙事 revision receipt；随后用既有 `graph project`
   重建 `film-spec.json` 和 Shot Package。
6. `export` 输出 Grok、FRW/Seedance 或通用的文本包；绝不提交请求。

默认验证仅报告兼容性警告；`--strict` 把它们升级为阻断。空镜头包、来源或收据遭篡改永远阻断。
发现问题时回到故事图或对应 Bible 修改、按既有锁定与审批规则重新投影，不得直接修改收据。

## 导演提示词规则

每镜必须包含功能、摄影机、动作、光影、声音及段末状态。参考素材只以自然语言的
“只参考／不继承”职责出现；不得泄漏 `CH001`、`SC001`、`asset-*` 等内部标识，亦不得把
BGM 写成视频模型必须生成的原声。
