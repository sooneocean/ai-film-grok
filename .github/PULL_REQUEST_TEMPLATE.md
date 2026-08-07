# Pull Request

## 改动摘要
<!-- 一句话说明这次 PR 做了什么 -->

## 涉及区域
- [ ] 验片选素材控制台（`web_core.py` / `asset_picker.py` / `gate_panel.py` / `review_ui.py` / `web_api.py` / `onboarding.py` / `web/console.html`）
- [ ] 流水线其它模块
- [ ] 文档 / 流程

## 控制台改动自查（涉及控制台文件时必填）
- [ ] 本地跑过 `pytest -m console`（双网关安全契约：token / 跨域 / 冲突 409 / 门禁 403 / 越界 404）
- [ ] CI `console` 门禁绿（`.github/workflows/ci.yml` 的 `console` job 通过；或本地 `make smoke-console` 全绿，等价于端到端冒烟）
- [ ] `make doctor` 绿（`failed_checks: []`）
- [ ] `ruff` 干净（改动文件）
- [ ] 若改了 `asset_picker.select_asset`：确认 shot 仍只写 `manifest.json` 的 `clips`，角色/声线/BGM 不发明进 manifest
- [ ] 若改了门禁逻辑：确认 `blocking` 仅由 *required* gate `fail` 触发；`unknown/skipped/warn` 不误锁
- [ ] 若改了安全内核：确认仍仅绑 127.0.0.1、跨域 403、绝不回传密钥、错误体无 secret

## 测试计划
<!-- 手动 / 自动验证了什么 -->

## 风险 / 回滚
<!-- 已知风险与回滚方式 -->
