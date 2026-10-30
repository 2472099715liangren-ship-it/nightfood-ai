#!/bin/sh
set -eu

# Resolve the project directory even when launched from another directory.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$script_dir"

if command -v python3 >/dev/null 2>&1; then
    python_cmd=python3
elif command -v python >/dev/null 2>&1; then
    python_cmd=python
else
    printf '%s\n' '错误：未找到 Python。请先安装 Python 3.10 或以上版本。' >&2
    exit 1
fi

if ! "$python_cmd" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    printf '%s\n' '错误：需要 Python 3.10 或以上版本，请升级 Python。' >&2
    exit 1
fi

if ! "$python_cmd" -c 'import sqlite3' >/dev/null 2>&1; then
    printf '%s\n' '错误：当前 Python 缺少 sqlite3 模块，请安装包含 SQLite 支持的 Python。' >&2
    exit 1
fi

PORT=${PORT:-8000}
if ! "$python_cmd" -c 'import sys; p = int(sys.argv[1]); sys.exit(not 1 <= p <= 65535)' "$PORT" 2>/dev/null; then
    printf '%s\n' '错误：PORT 必须是 1–65535 之间的整数。' >&2
    exit 1
fi
export PORT

printf '正在启动夜寻网页，端口：%s\n' "$PORT"
printf '本机浏览器地址：http://localhost:%s\n' "$PORT"
printf '%s\n' '首次启动会自动创建数据库；保持此窗口开启，按 Ctrl+C 停止。'
exec "$python_cmd" -u app.py
