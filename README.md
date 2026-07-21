# ai-film-grok（Grok Plugin · 独立仓）

把「灵感到可验收动态成片」收成一条可恢复流水线：**dispatch 八环** + Grok Imagine 静帧/I2V + edge TTS + HyperFrames/FFmpeg。

## 本机绝对路径（给 coding agent）

```text
/Users/dex/.grok/plugins/ai-film-grok
```

Agent 请先读 **[AGENTS.md](./AGENTS.md)**。  
改完后：`make validate doctor test` → bump `plugin.json` version → `make update` → commit/push。

## 目录

```text
ai-film-grok/                 # plugin root = git root
├── plugin.json
├── AGENTS.md                 # agent 迭代协议
├── CHANGELOG.md
├── Makefile
├── commands/                 # /ai-film-grok · /aifilm
└── skills/ai-film-grok/      # skill 本体
    ├── SKILL.md
    ├── scripts/aifilm
    ├── references/
    ├── tests/
    └── config.env.example
```

## 安装 / 启用

### A · 本机开发（推荐，源码即运行）

源码已在用户插件目录时，Grok 会发现；仍需 enable：

```bash
grok plugin validate /Users/dex/.grok/plugins/ai-film-grok
grok plugin install /Users/dex/.grok/plugins/ai-film-grok --trust
grok plugin enable ai-film-grok
grok plugin update ai-film-grok   # 改完源码刷新 installed 副本
```

TUI：`/plugins` → `ai-film-grok` → `Space` 启用 · `r` 重载。

### B · 从 GitHub 装到另一台机器

```bash
grok plugin install <owner>/ai-film-grok --trust
grok plugin enable ai-film-grok
# 之后拉更新：
grok plugin update ai-film-grok
```

`plugin.json` 的 `repository` / `homepage` 即 GitHub 地址。

## 日常迭代

```bash
cd /Users/dex/.grok/plugins/ai-film-grok
# … edit …
make validate doctor test
# bump version in plugin.json if behavior changed
make update
git add -A && git commit -m "feat: …" && git push
```

GitHub Actions（`.github/workflows/ci.yml`）在 push/PR 上跑校验 + pytest。

## 配置

1. 复制 `skills/ai-film-grok/config.env.example` → 同目录 `config.env`（**勿提交**）
2. 中文 final TTS 默认 **edge**；色气 BGM 默认 **rnb**；I2V 默认 `grok_primary`

## 与 `~/.grok/skills/ai-film-grok`

本机为 **symlink → 本 plugin 的 skill 目录**。不要再开第二份可写副本。

## 验证

```bash
make validate
make doctor
test -x skills/ai-film-grok/scripts/aifilm
grok plugin details ai-film-grok
```

## License

MIT
