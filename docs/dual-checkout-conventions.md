# 双 Checkout 操作铁律（Dual-Checkout Operating Rules）

> 本仓库存在两个工作树：
> - **开发树** `/Users/dex/.grok/ai-film-grok`（用户日常编辑）
> - **运行时树** `/Users/dex/.grok/plugins/ai-film-grok`（运行时通过 symlink `~/.grok/skills/ai-film-grok` 加载；CI / 发布以它为准）
>
> 两树各自有独立 `.git`，但指向同一 remote（`github.com/sooneocean/ai-film-grok`）。本文件是硬化总板 H0「双 checkout 对账」的流程沉淀，旨在消除"未提交 dailies 工作堆积 → 瞬态半写 → 启动即崩 / 手拷冲突"的痛点。
>
> 来源：`docs/plans/2026-08-08-project-hardening-refactor-todoplan.md` (H0.3)。

## 铁律（binding）

1. **改前确认当前树**：任何 git 操作前先 `git rev-parse --show-toplevel`，确认你在哪个树。禁止凭记忆手拷文件。
2. **只改当前树，禁手拷**：跨树同步走 `git fetch` + `git merge` / `git pull`（同 remote），不要 `cp` 文件互相覆盖。
3. **长写入期间勿起服**：大文件（如 `workflow_pack.py`）重构中途若被另一 agent 写入，启动 `aifilm` CLI 可能瞬态 `IndentationError`。提交前 `ast.parse` 自检，或等写入稳定再起服。
4. **提交即同步意图**：在运行时树提交后，若开发树需同步，明确走 pull / merge，不要各自漂移导致双树 HEAD 长期不一致。
5. **落盘优先（小步提交）**：进行中工作尽快提交，避免未提交 dailies 工作堆积成"瞬态半写"状态。
6. **不捕获他人 in-flight 工作**：提交时 `git add <具体路径>`，**禁止** `git add -A` / `git commit -a`，以免把别的 agent 的未提交改动一并落盘。

## 自检清单（启动服务器 / 提交前）

- [ ] `git status` 确认无别人的 in-flight 大文件改动卡在半写态
- [ ] 若刚改过 Python：`python3 -c "import ast,pathlib; ast.parse(pathlib.Path('scripts/X.py').read_text())"` 通过
- [ ] `git rev-parse --show-toplevel` 确认当前树是符合预期的那一个
- [ ] 提交用显式路径 `git add <path>...`，未 `git add -A`

## 典型事故复盘（2026-08-08）

- 运行时树 HEAD `dafb18dc`(2.41.38) 提交 `cli_post.py`+`workflow_pack.py` 的 dailies 重构前，这俩文件处于未提交"半写"态；期间启动 `aifilm review-ui serve` 曾瞬态报 `workflow_pack.py:1747 IndentationError`。属他 agent 进行中产物，非本功能改动；复跑 `ast.parse` 已通过、服务正常。
- 教训：长文件重构期间，起服前先 `ast.parse` 自检；或等提交稳定后再起服。

## 相关

- 硬化总板（单一执行板）：`docs/plans/2026-08-08-project-hardening-refactor-todoplan.md`
- 单 live 投影源铁律、fail-closed、无静默 except 等同板 §2
