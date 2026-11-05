"""Start NightFind locally and open the browser once the server is ready.

    python3 run.py
    python3 run.py --port 8001
    python3 run.py --no-browser

Only standard-library modules are needed. The existing app owns database setup.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parent


def load_environment():
    """Read optional KEY=value settings; never execute .env as shell code."""
    environment = os.environ.copy()
    path = ROOT / ".env"
    if not path.is_file():
        return environment
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        name = name.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f".env 第 {line_number} 行需要使用 KEY=value 格式")
        try:
            parts = shlex.split(value, comments=True, posix=True)
        except ValueError as error:
            raise ValueError(f".env 第 {line_number} 行引号未闭合") from error
        if len(parts) > 1:
            raise ValueError(f".env 第 {line_number} 行含空格的值需要加引号")
        # Explicit process settings take precedence over local defaults.
        environment.setdefault(name, parts[0] if parts else "")
    return environment


def wait_until_ready(process, address):
    """Check the actual application, using a direct loopback request only."""
    http = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("服务未能启动，请查看上方错误信息")
        try:
            with http.open(address + "/api/health", timeout=1) as response:
                health = json.load(response)
            if health.get("status") == "ok" and health.get("app") == "NightFind":
                return
        except (URLError, OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError("服务在 20 秒内没有就绪，请查看上方错误信息")


def main():
    parser = argparse.ArgumentParser(description="启动夜寻并自动打开网页")
    parser.add_argument("--port", type=int, help="指定端口，默认读取 PORT 或使用 8000")
    parser.add_argument("--no-browser", action="store_true", help="只启动服务，不打开浏览器")
    args = parser.parse_args()

    if sys.version_info < (3, 10):
        raise ValueError("需要 Python 3.10 或以上版本")
    try:
        import sqlite3  # noqa: F401 -- confirm the runtime includes SQLite.
    except ImportError as error:
        raise ValueError("当前 Python 缺少 SQLite 支持") from error

    environment = load_environment()
    try:
        port = args.port if args.port is not None else int(environment.get("PORT", "8000"))
    except ValueError as error:
        raise ValueError("PORT 必须是 1–65535 之间的整数") from error
    if not 1 <= port <= 65535:
        raise ValueError("端口必须是 1–65535 之间的整数")
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("0.0.0.0", port))
        except OSError as error:
            raise ValueError(
                f"无法使用端口 {port}：{error}。可运行 python3 run.py --port 8001 更换端口。"
            ) from error

    environment["PORT"] = str(port)
    address = f"http://127.0.0.1:{port}"
    print("正在启动夜寻，首次运行会自动准备门店资料…", flush=True)
    process = subprocess.Popen(
        [sys.executable, "-u", str(ROOT / "app.py")], cwd=ROOT, env=environment
    )
    try:
        wait_until_ready(process, address)
        print(f"夜寻已就绪：{address}", flush=True)
        print("保留此窗口，按 Ctrl+C 停止。", flush=True)
        if not args.no_browser:
            try:
                opened = webbrowser.open(address)
            except webbrowser.Error:
                opened = False
            if not opened:
                print("未找到可用浏览器，请在运行服务的电脑上手动打开上述地址。", flush=True)
        return process.wait()
    except KeyboardInterrupt:
        print("\n正在停止夜寻…", flush=True)
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, OSError) as error:
        print(f"启动失败：{error}", file=sys.stderr)
        raise SystemExit(1)
