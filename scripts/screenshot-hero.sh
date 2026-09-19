#!/usr/bin/env bash
# Regenera docs/assets/hero.png (hero da landing, 1440x900 @2x) a partir do build de produção.
# Requer Google Chrome no macOS e `npm install` em web/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
cd "$ROOT/web" && npx next build >/dev/null
npx next start -p 3100 >/dev/null 2>&1 &
PID=$!
trap 'kill $PID 2>/dev/null' EXIT
sleep 5
mkdir -p "$ROOT/docs/assets"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
  --window-size=1440,900 --virtual-time-budget=6000 \
  --screenshot="$ROOT/docs/assets/hero.png" http://localhost:3100/ 2>/dev/null
echo "ok: docs/assets/hero.png"
