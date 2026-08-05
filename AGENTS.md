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
│   ├── scripts/                 ← aifilm CLI + domain packages
│   │   ├── core/                ← emit / film_io / gates / media_ops
│   │   ├── spine/               ← dispatch / advance / workflow
│   │   ├── assets/              ← continuity / style_lock / face
│   │   ├── plan/                ← drama_graph / narrative_control
│   │   ├── gates/               ← preflight / production_gates
│   │   ├── post/                ← render_final（W4）
│   │   ├── narrative/           ← edit_policy_heat（W4）
│   │   ├── cli_*.py             ← CLI clusters（shim-compat names）
│   │   └── <name>.py            ← hard-compat shims → packages
│   ├── references/              ← 稳定规则
│   ├── memory/                  ← 会话索引
│   ├── tests/                   ← pytest
│   ├── templates/ schemas/ assets/
│   └── config.env.example
└── .github/workflows/
```

Package layout tracker: `docs/plans/2026-08-05-project-module-refactor.md`

## 维护区块（改哪测哪）

| AREA | 范围 | 优先测 |
|------|------|--------|
| Spine | dispatch / craft / next / SKILL 主脊 | `test_dispatch` `test_craft_spine` |
| Graph+Registry | drama-graph derive / skill list | `test_drama_graph` `test_skill_registry` |
| Plan | story.normalize → shot plan | `test_story_plan` |
| Assets | character/location/prop/state | `test_asset_registry` |
| Media | I2V / queue / register / OAuth 出图 | media / continuity 相关 |
| Audio | TTS / BGM / recipe / lipsync | `test_audio_recipe` `test_capability` |
| Post | final / compose / review / export · `scripts/post/` | `test_delivery_gates` compose 相关 |
| Narrative | 色气 / 性爱时长≥20% / 剪辑 / 景别 · `scripts/narrative/` | `test_heat_arc_multi` + soft gate |
| Gates | hard-defaults / security / runtime-lock | doctor + delivery gates |

细则见 skill 内 `references/pipeline-methodology.md` · `references/hard-defaults.md`。

## 迭代循环（agent 默认 · 已打通）

```bash
ROOT="$(git rev-parse --show-toplevel)"
# 或一键：make check-all && make release-light

# 1) 改源码（仅 $ROOT）
# 2–5) 日常绿线（与 make check-all 等价）
make -C "$ROOT" check-all          # validate + ruff + doctor + pytest -m 'not slow'

# 6) 功能变更 → bump plugin.json version（semver）+ CHANGELOG
# 7) 若改了 scripts 指纹：make lock-runtime
# 8) make sync-docs（版本指针）
# 9) 刷新本机 installed 副本
grok plugin update ai-film-grok

# 10) commit（message 英文）
# 11) push：pre-push 默认 light（docs+doctor core）；重测用 AIFILM_RELEASE_GATE=full
git push origin main
```

JSON 约定：`util.read_json` 软（None）；`util.require_json` 硬（FilmError）；新代码勿再复制 `_read_json`。

## 硬规则（指针 · 正文在 hard-defaults / stages）

1. **单一真相**：禁止在 `~/.grok/skills/` 另开可写副本；改源码只改本 checkout。
2. **密钥**：`config.env` 永不提交；只用 `config.env.example`。
3. **pilot / bulk**：不自批 pilot；不静默改 `i2v_provider`。
4. **机读门禁**：`skills/ai-film-grok/references/hard-defaults.md`（成人 MAX、毒镜、卸装、抗无聊、声线等 **只改这里** + 对应测）。
5. **阶段卡**：`references/stages/*`（dispatch 默认 context）；长课 `lessons-*` 按需，**不**默认整页进 context。
6. **短记忆卡**：`memory/*` 仅原话+三句+清单+链 lesson；见 `memory/README.md`。
7. **声线 / 成人 / 毒镜 / final**：见 SKILL P0 短列表 + hard-defaults；勿在本档复写长段 IRON。
8. **字幕 ship 硬烧 + 肉戏 speaker/体位（2026-08-03 荒岛 v3）**：用户可见=像素有中文；`on_camera` speaker=画面主体；肉戏邻镜差异 + afterglow 禁单人站桩 → [huangdao lesson](skills/ai-film-grok/references/lessons-2026-08-03-huangdao-rhythm-still-voice-silk.md) · [memory](skills/ai-film-grok/memory/2026-08-03-huangdao-caption-hardburn-meat-variety.md)。
8b. **H3 效果最大化（2026-08-04）**：I2V 锁脸默认 · R2V 高动/大嘴 · T2V 无脸 env；续镜末帧→I2V；对白注入合并自定义 prompt → [h3-max lesson](skills/ai-film-grok/references/lessons-2026-08-04-h3-max-effect.md) · [memory](skills/ai-film-grok/memory/2026-08-04-h3-max-effect.md) · [weapon-lane-matrix](skills/ai-film-grok/references/weapon-lane-matrix.md)。
8c. **Fill-Idle 挑战（2026-08-04）**：Grok 铺 soft；restricted 主轨 H3；5090 P0→P1→P2 空闲挑战（能烧就烧、禁抢 P0）；R2V=能量位；PK=shortlist 建议+人 promote；P2=mean 最低优先；final 不等 P2 / 高光不强制挑战；跨集胜率不自动 → [weapon-lane Fill-Idle](skills/ai-film-grok/references/weapon-lane-matrix.md) · [memory](skills/ai-film-grok/memory/2026-08-04-h3-fill-idle-challenge.md)。
8. **文档分层**：SKILL 短 → hard-defaults 硬表 → stages 回合卡 → memory 速查 → lessons 复盘。
8d. **剧本呈现价值（2026-08-04）**：story.receive 后、lock 前写 `receipts/script-value-debrief.json`（用户/编剧/导演/观众/生产 L0–L4）；确认 promise+不可砍 beat 才 lock → [script-value-debrief](skills/ai-film-grok/references/script-value-debrief.md) · [memory](skills/ai-film-grok/memory/2026-08-04-script-value-debrief.md)。
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
- **圣旨协议（P0 · 2026-08-04）**：用户命令是圣旨 — 短令 `go`/`go next` 立刻执行既定 next，不重开讨论。详见 `~/.grok/Agents.md` · [memory](skills/ai-film-grok/memory/2026-08-04-user-command-is-edict.md)

