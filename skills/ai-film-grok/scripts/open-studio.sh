#!/bin/sh
# open-studio.sh — 自动打开导演总控台（studio mode / 总控台）
#
# 用法:
#   ./open-studio.sh [studio-dir] [--no-open] [--port=N]
#
# - studio-dir : 包含若干“影片根”子目录（每个含 manifest.json）的目录。
#                省略时使用 $AIFILM_STUDIO_DIR（来自仓库根 config.env），
#                再退回到 <repo>/studio。
# - 启动 `aifilm review-ui serve --studio <dir> --port <port>`，解析其打印的
#   URL（含会话 token），并用 macOS `open` 自动在浏览器打开控制台。
#   控制台以 studio 模式启动 → “总控台”标签页可见。
# - --no-open : 仅启动并打印 URL，不调用 open（便于测试 / 无 GUI 环境）。
# - --port=N  : 指定端口；默认 0 = 系统分配空闲端口，保证每次都能起。
#
# “只要触发就自动打开”：把本脚本绑到快捷键 / 别名，或双击运行即可。
#   例如：alias studio='~/.grok/plugins/ai-film-grok/skills/ai-film-grok/scripts/open-studio.sh'

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH= cd -- "$SCRIPT_DIR/../../.." && pwd)

# 载入 config.env（AIFILM_STUDIO_DIR 等；该文件不提交）
if [ -f "$REPO/config.env" ]; then
  set -a; . "$REPO/config.env"; set +a
fi

NO_OPEN=0
PORT=0
STUDIO=""
for a in "$@"; do
  case "$a" in
    --no-open) NO_OPEN=1 ;;
    --port=*) PORT="${a#--port=}" ;;
    -*) : ;;                      # 忽略其它 -x 选项
    *) STUDIO="$a" ;;             # 第一个位置参数 = studio 目录
  esac
done

STUDIO="${STUDIO:-${AIFILM_STUDIO_DIR:-$REPO/studio}}"

echo "总控台 studio 目录: $STUDIO"

if [ ! -d "$STUDIO" ]; then
  mkdir -p "$STUDIO"
  cat > "$STUDIO/README.md" <<'EOF'
# 导演总控台 studio 目录

把每个“影片根”子目录（含 `manifest.json`）放进本目录即可。
总控台会扫描本目录下所有影片根，统览全部已制作 / 制作中的 AI FILM。

或者：在仓库根 `config.env` 里设置
    AIFILM_STUDIO_DIR=/path/to/your/films
然后直接运行 `scripts/open-studio.sh`（无需参数）。
EOF
  echo "已创建 studio 目录并写入 README。请放入影片根，或设置 AIFILM_STUDIO_DIR，然后重新运行。"
  exit 0
fi

if [ -z "$(find "$STUDIO" -maxdepth 2 -name manifest.json -print -quit 2>/dev/null)" ]; then
  echo "未在 $STUDIO 下找到任何影片根（含 manifest.json 的子目录）。"
  echo "请将影片根子目录放入，或设置 AIFILM_STUDIO_DIR 指向你的影片目录。"
  exit 1
fi

LOG=/tmp/open-studio.log
: > "$LOG"

echo "启动控制台 (studio 模式)…"
cd "$REPO"
nohup "$SCRIPT_DIR/aifilm" review-ui serve --studio "$STUDIO" --port "$PORT" > "$LOG" 2>&1 &
SRV_PID=$!

URL=""
for _ in $(seq 1 40); do
  if grep -q '"url"' "$LOG" 2>/dev/null; then
    URL=$(grep -m1 '"url"' "$LOG" | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['url'])" 2>/dev/null || true)
    [ -n "$URL" ] && break
  fi
  if ! kill -0 "$SRV_PID" 2>/dev/null; then
    echo "服务启动失败，日志：" ; cat "$LOG" ; exit 1
  fi
  sleep 0.3
done

if [ -z "$URL" ]; then
  echo "未能从日志解析到控制台 URL。日志：" ; cat "$LOG" ; exit 1
fi

echo "总控台已启动: $URL"

if [ "$NO_OPEN" -eq 0 ]; then
  echo "正在打开浏览器…"
  open "$URL" || echo "(open 失败：请手动复制上面的 URL 打开)"
else
  echo "(--no-open: 未调用 open)"
fi
