#!/bin/sh
set -eu

# Always run from the directory containing this script.
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "错误：没有找到 Python 3，请先安装 Python 3.10 或以上版本。" >&2
    exit 1
fi

if ! "$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
    echo "错误：夜寻需要 Python 3.10 或以上版本。" >&2
    exit 1
fi

if ! "$PYTHON" -c 'import sqlite3, urllib.request' >/dev/null 2>&1; then
    echo "错误：当前 Python 缺少 SQLite 或标准网络模块。" >&2
    exit 1
fi

# Load optional local configuration. Keep .env out of Git.
if [ -f .env ]; then
    set -a
    . ./.env
    set +a
fi

PORT=$(printenv PORT 2>/dev/null || printf '8000')
if ! "$PYTHON" -c 'import sys; p = int(sys.argv[1]); raise SystemExit(not 1 <= p <= 65535)' "$PORT" 2>/dev/null; then
    echo "错误：PORT 必须是 1–65535 之间的整数。" >&2
    exit 1
fi
export PORT

echo "正在启动夜寻…"
echo "浏览器访问：http://localhost:$PORT"
echo "保持此终端窗口开启，按 Ctrl+C 停止。"

exec "$PYTHON" -u app.py
