# AGENTS · ai-film-grok

> Coding agent 入口。人读 README；agent 先读本档再改代码。

## Source checkout（本机开发真相）

```text
/Users/dex/.grok/plugins/ai-film-grok
```

- **只改这里**（plugin 源码）。
- User skill 是 symlink：`~/.grok/skills/ai-film-grok` → `…/plugins/ai-film-grok/skills/ai-film-grok`
- 运行时副本：`~/.grok/installed-plugins/ai-film-grok-*`（用 `grok plugin update` 刷新，勿当源码改）

## 布局

```text
ai-film-grok/                    ← plugin root / git root
├── plugin.json                  ← name + semver（发版必 bump）
├── commands/                    ← /ai-film-grok · /aifilm
├── skills/ai-film-grok/         ← skill 本体
│   ├── SKILL.md                 ← 主脊（短）
│   ├── scripts/                 ← aifilm CLI + 模块
│   ├── references/              ← 稳定规则
│   ├── references/lessons-*     ← 踩坑（可晋升到稳定）
│   ├── memory/                  ← 会话索引
│   ├── tests/                   ← pytest
│   ├── templates/ schemas/ assets/
│   └── config.env.example       ← 复制为 config.env（gitignored）
└── .github/workflows/           ← GitHub CI
```

## 维护区块（改哪测哪）

| AREA | 范围 | 优先测 |
|------|------|--------|
| Spine | dispatch / craft / next / SKILL 主脊 | `test_dispatch` `test_craft_spine` |
| Graph+Registry | drama-graph derive / skill list | `test_drama_graph` `test_skill_registry` |
| Plan | story.normalize → shot plan | `test_story_plan` |
| Assets | character/location/prop/state | `test_asset_registry` |
| Media | I2V / queue / register / OAuth 出图 | media / continuity 相关 |
| Audio | TTS / BGM / recipe / lipsync | `test_audio_recipe` `test_capability` |
| Post | final / compose / review / export | `test_delivery_gates` compose 相关 |
| Narrative | 色气 / 性爱时长≥20% / 剪辑 / 景别 / lessons | `test_heat_arc_multi` + soft gate |
| Gates | hard-defaults / security / runtime-lock | doctor + delivery gates |

细则见 skill 内 `references/pipeline-methodology.md` · `references/hard-defaults.md`。

## 迭代循环（agent 默认）

```bash
ROOT="$(git rev-parse --show-toplevel)"
SKILL="$ROOT/skills/ai-film-grok"
AIFILM="$SKILL/scripts/aifilm"

# 1) 改源码（仅 $ROOT）
# 2) 校验包装
grok plugin validate "$ROOT"

# 3) Ruff lint + format check
ruff check "$SKILL/scripts/" && ruff format --check "$SKILL/scripts/"

# 4) 机位 / 门禁
"$AIFILM" doctor

# 5) 相关测试（fast path: 排除 slow）
cd "$SKILL" && python3 -m pytest tests/ -q --tb=line -m "not slow"

# 6) 功能变更 → bump plugin.json version（semver）
# 7) 刷新本机 installed 副本
grok plugin update ai-film-grok

# 8) commit（message 英文）+ push origin main
```

## 硬规则（指针 · 正文在 hard-defaults / stages）

1. **单一真相**：禁止在 `~/.grok/skills/` 另开可写副本；改源码只改本 checkout。
2. **密钥**：`config.env` 永不提交；只用 `config.env.example`。
3. **pilot / bulk**：不自批 pilot；不静默改 `i2v_provider`。
4. **机读门禁**：`skills/ai-film-grok/references/hard-defaults.md`（成人 MAX、毒镜、卸装、抗无聊、声线等 **只改这里** + 对应测）。
5. **阶段卡**：`references/stages/*`（dispatch 默认 context）；长课 `lessons-*` 按需，**不**默认整页进 context。
6. **短记忆卡**：`memory/*` 仅原话+三句+清单+链 lesson；见 `memory/README.md`。
7. **声线 / 成人 / 毒镜 / final**：见 SKILL P0 短列表 + hard-defaults；勿在本档复写长段 IRON。
8. **文档分层**：SKILL 短 → hard-defaults 硬表 → stages 回合卡 → memory 速查 → lessons 复盘。
9. **完成定义**：doctor 绿 + 相关 pytest 绿 +（若改 CLI）`plugin validate` 过；不是「改完文件」。
10. **对外**：PR / release 文案给人过目后再发；本仓默认 private。

## GitHub

- Remote：见 `plugin.json` → `repository`
- 多机安装：`grok plugin install <owner>/ai-film-grok --trust && grok plugin enable ai-film-grok`
- 更新：`grok plugin update ai-film-grok`
- CI：`.github/workflows/ci.yml`（validate + pytest）

## 语言

- 与使用者沟通：中文
- commit message：英文
- 结论先行；不确定就标明信心
