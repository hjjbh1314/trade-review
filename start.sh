#!/usr/bin/env bash
#
# Trade Review 启动脚本
#
# 安全说明（重要）：
#   不安全公共 Wi-Fi（学校/咖啡馆/机场）不要用任何"多设备"模式，只用默认本机模式。
#
# 用法：
#   ./start.sh                默认本机模式，只有 Mac 本机能访问（最安全）
#   ./start.sh --tailscale    Tailscale 专用：仅 Tailscale 私网内设备可访问
#                             （手机在全世界任何网络都能用，子网其他人扫不到端口）
#   ./start.sh --no-build     跳过前端构建（代码没改过时加速）
#   ./start.sh --port=8091    换端口
#
# ⚠️ 旧的 --lan 模式已移除。在不受信任的网络（例如学校 Wi-Fi）绑定 0.0.0.0
#    会让同子网任何人都能访问你的数据。如确需局域网使用，请装 Tailscale。
#

set -e

cd "$(dirname "$0")"

MODE="local"        # local | tailscale
DO_BUILD=1
PORT=8090

for arg in "$@"; do
  case "$arg" in
    --tailscale|--ts)    MODE="tailscale" ;;
    --lan)
      echo "❌ --lan 模式已移除（学校 / 公共 Wi-Fi 下会暴露你的数据）"
      echo "   请改用 --tailscale（先装 Tailscale：https://tailscale.com/download）"
      exit 1 ;;
    --no-build)          DO_BUILD=0 ;;
    --port=*)            PORT="${arg#*=}" ;;
    -h|--help)
      sed -n '3,19p' "$0"
      exit 0 ;;
    *)
      echo "⚠️  未知参数: $arg"
      exit 1 ;;
  esac
done

# ── 加载 .env（如果存在）────────────────────────────────
# .env 仅你本地有；开源仓库提供 .env.example 给 fork 用户。
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# ── 解析 Token ──────────────────────────────────────────
# 优先读 .tr_token 文件；没有就生成一个
TOKEN_FILE=".tr_token"
if [ ! -f "$TOKEN_FILE" ]; then
  # 生成 24 字符随机 token（足够防扫描+猜测）
  TOKEN=$(LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 24)
  echo "$TOKEN" > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
  echo "🔑 已生成访问 Token 并写入 $TOKEN_FILE"
fi
TR_ACCESS_TOKEN=$(cat "$TOKEN_FILE")
export TR_ACCESS_TOKEN

# ── 解析绑定地址 ─────────────────────────────────────────
HOST="127.0.0.1"
ACCESS_HOST="127.0.0.1"

if [ "$MODE" = "tailscale" ]; then
  if ! command -v tailscale >/dev/null 2>&1; then
    echo "❌ 未检测到 tailscale 命令"
    echo "   装：brew install --cask tailscale"
    echo "   装好后在 Tailscale App 登录，再跑一次此脚本"
    exit 1
  fi
  TS_IP=$(tailscale ip -4 2>/dev/null | head -1)
  if [ -z "$TS_IP" ]; then
    echo "❌ Tailscale 未登录或未连接"
    echo "   打开 Tailscale App 登录，确认状态为 Connected 后再试"
    exit 1
  fi
  HOST="$TS_IP"
  ACCESS_HOST="$TS_IP"
  echo "✅ Tailscale 已连接，本机 Tailscale IP：$TS_IP"
  echo "   服务将只在 Tailscale 虚拟网卡监听，子网其他人无法访问"
fi

# ── 检查 Python venv ──────────────────────────────────────
if [ ! -x ".venv/bin/python" ]; then
  echo "❌ 未找到 .venv/bin/python"
  echo "   请先建虚拟环境：python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

# ── 检查 AI 引擎配置 ────────────────────────────────────────
TR_AI_ENGINE="${TR_AI_ENGINE:-claude}"
case "$TR_AI_ENGINE" in
  claude)
    if ! command -v claude >/dev/null 2>&1; then
      echo "⚠️  未检测到 claude 命令。请先装 Claude Code："
      echo "   npm install -g @anthropic-ai/claude-code"
      echo "   装好后运行 \`claude\` 登录你的 Max 订阅，然后再启动此脚本。"
      exit 1
    fi ;;
  deepseek)
    if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
      echo "⚠️  TR_AI_ENGINE=deepseek，但未配置 DEEPSEEK_API_KEY"
      echo "   请在 .env 中填写你的 DeepSeek API Key 后重启。"
      exit 1
    fi ;;
  *)
    echo "⚠️  未知 TR_AI_ENGINE=$TR_AI_ENGINE（可选: claude, deepseek）"
    exit 1 ;;
esac

# ── 构建前端 ─────────────────────────────────────────────
if [ "$DO_BUILD" = "1" ]; then
  if [ -d frontend ]; then
    echo "🔨 构建前端..."
    # 把 VITE_USER_NAME 传进构建（前端 import.meta.env.VITE_USER_NAME）
    (cd frontend && npm install --silent && \
     VITE_USER_NAME="${VITE_USER_NAME:-${TR_USER_NAME:-}}" npm run build --silent) || {
      echo "❌ 前端构建失败"; exit 1;
    }
    echo "✅ 前端构建完成"
  fi
fi

# ── 清理旧 uvicorn ──────────────────────────────────────────
OLD_PID=$(lsof -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)
if [ -n "$OLD_PID" ]; then
  echo "🔄 杀掉占用 $PORT 的旧进程 PID $OLD_PID"
  kill "$OLD_PID" 2>/dev/null || true
  sleep 1
fi

# ── 打印访问 URL ─────────────────────────────────────────
echo
echo "════════════════════════════════════════════════════════"
echo "  Trade Review · 启动中"
echo "════════════════════════════════════════════════════════"
echo "  模式：      $MODE"
echo "  监听地址：  $HOST:$PORT"
if [ "$MODE" = "local" ]; then
  echo "  访问 URL：  http://127.0.0.1:$PORT/#token=$TR_ACCESS_TOKEN"
  echo "              （只有 Mac 本机可用；手机/iPad 请用 --tailscale 模式）"
else
  echo "  主 URL：    http://$ACCESS_HOST:$PORT/#token=$TR_ACCESS_TOKEN"
  echo "              （已登录 Tailscale 的设备：手机/iPad/另一台电脑 都可用）"
  echo "              提示：首次打开后 token 会存入浏览器 localStorage，以后只开 URL 就行"
fi
echo "  API 文档：  http://$ACCESS_HOST:$PORT/docs"
echo "  Token：    已保存到 .tr_token 文件（请勿公开此文件）"
echo "  按 Ctrl+C 停止"
echo "════════════════════════════════════════════════════════"
echo

# ── 启动 ───────────────────────────────────────────────────
exec .venv/bin/python -m uvicorn backend.main:app --host "$HOST" --port "$PORT"
