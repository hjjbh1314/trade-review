#!/usr/bin/env bash
#
# scripts/screenshot.sh
#
# 一键截图：起一个独立的 demo backend（独立 db、独立端口），
# 用 Chrome 自动打开各页面，screencapture 批量截图到 docs/screenshots/。
#
# 不会动你真实的 data/trade_review.db，也不会占用 8090 端口。
#
# 用法：
#   ./scripts/screenshot.sh
#
# 依赖：
#   - .venv 已建好
#   - 前端已 build (./start.sh 跑过一次就有了 frontend/dist/)
#   - Google Chrome 已装
#

set -e
cd "$(dirname "$0")/.."

DEMO_DB="/tmp/tr_demo.db"
DEMO_PORT=8099
SHOTS_DIR="docs/screenshots"
URL="http://127.0.0.1:${DEMO_PORT}"

mkdir -p "$SHOTS_DIR"

# ── 1. 重置 demo db ──────────────────────────────────────
echo "🌱 seeding demo data..."
rm -f "$DEMO_DB"
TR_DB_PATH="$DEMO_DB" .venv/bin/python scripts/seed_demo.py

# ── 2. 检查前端构建产物 ─────────────────────────────────
if [ ! -d frontend/dist ]; then
  echo "⚠️  frontend/dist 不存在，先构建前端..."
  (cd frontend && npm install --silent && npm run build --silent)
fi

# ── 3. 启动 demo backend（不设 token，避免 URL 复杂化）──
echo "🚀 starting demo backend on :${DEMO_PORT} (no token)"
TR_DB_PATH="$DEMO_DB" \
  .venv/bin/python -m uvicorn backend.main:app \
    --host 127.0.0.1 --port "$DEMO_PORT" \
    > /tmp/tr_demo_uvicorn.log 2>&1 &
DEMO_PID=$!

cleanup() {
  echo "🧹 stopping demo backend (PID $DEMO_PID)"
  kill "$DEMO_PID" 2>/dev/null || true
  rm -f "$DEMO_DB"
}
trap cleanup EXIT

# 等就绪
echo "⏳ waiting for backend..."
for i in $(seq 1 60); do
  if curl -sf "$URL/api/health" > /dev/null 2>&1; then
    echo "✅ backend ready"
    break
  fi
  sleep 1
done

if ! curl -sf "$URL/api/health" > /dev/null 2>&1; then
  echo "❌ backend 没起来，看 /tmp/tr_demo_uvicorn.log"
  tail -20 /tmp/tr_demo_uvicorn.log
  exit 1
fi

# 给前端拉一次行情，避免第一张图全是 spinner
sleep 2
curl -sf "$URL/api/positions/with-quotes" > /dev/null 2>&1 || true
sleep 3

# ── 4. 用 osascript 控制 Chrome 打开页面 ─────────────────
shoot() {
  local route=$1
  local name=$2
  local wait_seconds=${3:-4}

  echo "📸 ${name} ← ${route}"
  osascript <<APPLESCRIPT
tell application "Google Chrome"
    activate
    if (count of windows) = 0 then
        make new window
    end if
    set URL of active tab of front window to "${URL}${route}"
end tell
APPLESCRIPT

  sleep "$wait_seconds"
  # 截 Chrome 窗口；-x = 静音；-l = 指定 windowID 但需先拿，简单点用 -W 等用户选窗后回车
  # 用 -o 不带阴影，-T 0 立即截
  screencapture -x -o -T 0 -l \
    "$(osascript -e 'tell application "Google Chrome" to id of front window' 2>/dev/null)" \
    "${SHOTS_DIR}/${name}.png" 2>/dev/null \
  || screencapture -x -o "${SHOTS_DIR}/${name}.png"   # fallback: 全屏

  echo "   → ${SHOTS_DIR}/${name}.png"
}

# 先把 Chrome 拉到 1280x800 这种适合 README 的尺寸
osascript <<'APPLESCRIPT'
tell application "Google Chrome"
    activate
    if (count of windows) = 0 then
        make new window
    end if
    set bounds of front window to {80, 80, 1440, 960}
end tell
APPLESCRIPT
sleep 1

shoot "/"         "dashboard"  6
shoot "/flash"    "flash"      3
shoot "/mindset"  "mindset"    4
shoot "/journal"  "journal"    3

echo
echo "✅ done. Screenshots in ${SHOTS_DIR}/"
ls -la "${SHOTS_DIR}/"
