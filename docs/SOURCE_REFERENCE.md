# 夜寻：全量源码汇编

整理日期：2026-11-20。分支：`feature/vivid-motion-code-guide`。本文件是本次交付的源文件原文阅读快照；实际修改请编辑各原始文件，汇编不会自动同步。

先读 [代码阅读与修改指南](CODE_GUIDE.md)，再通过下方目录查看源码。完整源码 ZIP 还包含 CSV、JSON、GeoJSON、图片、第三方 Leaflet 及全部文档。为方便学习，本汇编不重复这些大体积数据和第三方压缩代码，也不包含本机 `.env`、数据库、缓存或 Git 内部文件。

共收录 **53 个自有代码、测试与配置文件**；每节附原文件链接、行数和 SHA-256，便于核对。下方代码块保留源码内容，不是改写示例；仅统一为 LF 换行以便 Markdown 阅读。原始文件未改写，SHA-256 按原文件字节计算。

## 文件目录

1. [run.py](#source-01)
2. [app.py](#source-02)
3. [decision_preferences.py](#source-03)
4. [dining_decision.py](#source-04)
5. [decision_catalog.py](#source-05)
6. [real_catalog.py](#source-06)
7. [database.py](#source-07)
8. [.env.example](#source-08)
9. [.gitattributes](#source-09)
10. [.github/workflows/osm-collect.yml](#source-10)
11. [.github/workflows/tests.yml](#source-11)
12. [.gitignore](#source-12)
13. [README.md](#source-13)
14. [catalog_language.py](#source-14)
15. [catalog_policy.py](#source-15)
16. [comparison.py](#source-16)
17. [conversation.py](#source-17)
18. [geo_coordinates.py](#source-18)
19. [geofabrik_sync.py](#source-19)
20. [import_merchants.py](#source-20)
21. [import_wuhan_catalog.py](#source-21)
22. [manage_osm_photos.py](#source-22)
23. [map_services.py](#source-23)
24. [merchant_photos.py](#source-24)
25. [osm_sync.py](#source-25)
26. [refresh_wuhan_catalog.py](#source-26)
27. [services.py](#source-27)
28. [start.sh](#source-28)
29. [static/api-client.js](#source-29)
30. [static/app.js](#source-30)
31. [static/botanical.svg](#source-31)
32. [static/decision-view.js](#source-32)
33. [static/decision.css](#source-33)
34. [static/decorations.js](#source-34)
35. [static/experience.css](#source-35)
36. [static/index.html](#source-36)
37. [static/session-store.js](#source-37)
38. [static/style.css](#source-38)
39. [static/wuhan_map.js](#source-39)
40. [tests/decorative_motion.cjs](#source-40)
41. [tests/recommendation_navigation.cjs](#source-41)
42. [tests/session_store.test.mjs](#source-42)
43. [tests/test_app.py](#source-43)
44. [tests/test_catalog_refresh.py](#source-44)
45. [tests/test_decision.py](#source-45)
46. [tests/test_experience.py](#source-46)
47. [tests/test_http.py](#source-47)
48. [tests/test_map_services.py](#source-48)
49. [tests/test_osm_photos.py](#source-49)
50. [tests/test_osm_sync.py](#source-50)
51. [tests/test_real_catalog.py](#source-51)
52. [tests/test_real_catalog_workflow.py](#source-52)
53. [启动网页.bat](#source-53)

<a id="source-01"></a>

## 1. run.py

[打开原文件](../run.py) · 137 行

SHA-256：`802eb3d93136567a70ac1121c16a5b18bc5b2fc9c5adb257981951c76cddd50a`

````python
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
````

<a id="source-02"></a>

## 2. app.py

[打开原文件](../app.py) · 436 行

SHA-256：`5e9e5a415d405cc40995d2e0ecb0089f36b8ede037f992ea871f4fb4e2e884f8`

````python
"""NightFind HTTP application.

Routes are intentionally small and explicit. Database queries live in database.py;
the real dining workflow lives in dining_decision.py.
services.py retains the older demonstration API.
"""

import json
import mimetypes
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from database import (
    connect,
    create_feedback,
    create_suggestion,
    ensure_session,
    get_merchant,
    initialize_database,
    list_districts,
    list_favorites,
    list_saved_merchants,
    list_merchants,
    list_reviews,
    review_summary,
    set_favorite,
    suggestion_summary,
)
from services import SCENES
from comparison import compare_merchants
from real_catalog import (
    public_real_merchants,
    catalog_coverage,
    get_public_real_merchant,
)
from merchant_photos import public_photo_file, safe_image_path
from decision_catalog import set_real_favorite, saved_real_merchants, real_map_catalog
from dining_decision import (
    prepare_decision,
    make_decision,
    describe_merchant,
    compare_real_merchants,
)
from map_services import public_map_config, walking_route


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
MAX_REQUEST_BYTES = 20_000
SESSION_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,80}$")
STATIC_FILES = {
    "/": "index.html",
    "/style.css": "style.css",
    "/experience.css": "experience.css",
    "/app.js": "app.js",
    "/wuhan_map.js": "wuhan_map.js",
    "/map/wuhan-basemap.geojson": "map/wuhan-basemap.geojson",
    "/botanical.svg": "botanical.svg",
    "/decorations.js": "decorations.js",
    "/api-client.js": "api-client.js",
    "/session-store.js": "session-store.js",
    "/decision-view.js": "decision-view.js",
    "/decision.css": "decision.css",
    "/vendor/leaflet/leaflet.js": "vendor/leaflet/leaflet.js",
    "/vendor/leaflet/leaflet.css": "vendor/leaflet/leaflet.css",
    "/vendor/leaflet/images/layers.png": "vendor/leaflet/images/layers.png",
    "/vendor/leaflet/images/layers-2x.png": "vendor/leaflet/images/layers-2x.png",
    "/vendor/leaflet/images/marker-icon.png": "vendor/leaflet/images/marker-icon.png",
    "/vendor/leaflet/images/marker-icon-2x.png": "vendor/leaflet/images/marker-icon-2x.png",
    "/vendor/leaflet/images/marker-shadow.png": "vendor/leaflet/images/marker-shadow.png",
}


class NightFindHandler(BaseHTTPRequestHandler):
    """Small JSON API and static-file handler."""

    server_version = "NightFind/2.0"

    def _send_bytes(self, content, content_type, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _read_json(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("请求长度无效") from error
        if size <= 0 or size > MAX_REQUEST_BYTES:
            raise ValueError("请求内容为空或超过大小限制")
        try:
            payload = json.loads(self.rfile.read(size).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("请求必须是有效的 JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("请求内容必须是 JSON 对象")
        return payload

    def _session_id(self, required=True):
        session_id = self.headers.get("X-Session", "").strip()
        if not SESSION_PATTERN.fullmatch(session_id):
            if required:
                raise ValueError("请刷新页面后重试")
            return ""
        return session_id

    def _serve_static(self, path):
        filename = STATIC_FILES.get(path)
        if filename is None:
            self._send_json({"error": "页面不存在"}, 404)
            return

        file_path = STATIC_DIR / filename
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        if filename.endswith(".html"):
            content_type += "; charset=utf-8"
        elif filename.endswith(".js") or filename.endswith(".css"):
            content_type += "; charset=utf-8"
        self._send_bytes(file_path.read_bytes(), content_type)

    def _serve_real_photo(self, path):
        identifier = path.removeprefix("/real-photo/")
        if not identifier.isdigit():
            self._send_json({"error": "照片不存在"}, 404)
            return
        try:
            with connect() as connection:
                entry = public_photo_file(connection, int(identifier))
            if entry is None:
                self._send_json({"error": "照片未经审核或资料已失效"}, 404)
                return
            path = safe_image_path(entry["image_filename"])
            mime = {
                ".jpg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
            }.get(path.suffix)
            self._send_bytes(path.read_bytes(), mime or "application/octet-stream")
        except (OSError, ValueError):
            self._send_json({"error": "照片暂不可用"}, 404)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/real-photo/"):
            self._serve_real_photo(path)
            return
        if not path.startswith("/api/"):
            self._serve_static(path)
            return

        try:
            session_id = self._session_id(required=False)
            query = parse_qs(parsed.query)
            if path == "/api/map-config":
                self._send_json(public_map_config())
                return
            with connect() as connection:
                if path == "/api/health":
                    self._send_json({"status": "ok", "app": "NightFind"})
                    return

                if path == "/api/bootstrap":
                    self._send_json(
                        {
                            "districts": list_districts(connection),
                            "favorites": (
                                list_favorites(connection, session_id)
                                if session_id
                                else []
                            ),
                            "ai_enabled": bool(
                                os.environ.get("OPENAI_API_KEY", "").strip()
                            ),
                        }
                    )
                    return

                if path == "/api/real-map":
                    self._send_json(
                        real_map_catalog(
                            connection,
                            keyword=query.get("keyword", [""])[0],
                            district=query.get("district", [""])[0],
                        )
                    )
                    return

                if path == "/api/real-favorites":
                    session_id = self._session_id()
                    items = saved_real_merchants(connection, session_id)
                    self._send_json(
                        {"items": [describe_merchant(item) for item in items]}
                    )
                    return

                if path == "/api/real-compare":
                    self._send_json(
                        compare_real_merchants(connection, query.get("ids", [""])[0])
                    )
                    return

                if path == "/api/real-merchants":
                    result = public_real_merchants(
                        connection,
                        district=query.get("district", [""])[0],
                        keyword=query.get("keyword", [""])[0],
                        limit=query.get("limit", ["30"])[0],
                        offset=query.get("offset", ["0"])[0],
                    )
                    result["items"] = [
                        describe_merchant(item) for item in result["items"]
                    ]
                    self._send_json(result)
                    return

                if path == "/api/real-merchants/coverage":
                    self._send_json(catalog_coverage(connection))
                    return

                if path.startswith("/api/real-merchants/"):
                    merchant_id = self._resource_id(path, "/api/real-merchants/")
                    item = get_public_real_merchant(connection, merchant_id)
                    if item is None:
                        self._send_json({"error": "门店核验资料不足或已过期"}, 404)
                    else:
                        self._send_json(describe_merchant(item))
                    return

                if path == "/api/merchants":
                    max_price = query.get("max_price", [""])[0]
                    if max_price:
                        try:
                            max_price = int(max_price)
                        except ValueError as error:
                            raise ValueError("人均预算必须是数字") from error
                        if not 10 <= max_price <= 500:
                            raise ValueError("人均预算范围为 10–500 元")

                    merchants = list_merchants(
                        connection,
                        keyword=query.get("keyword", [""])[0],
                        district=query.get("district", [""])[0],
                        cuisine=query.get("cuisine", [""])[0],
                        max_price=max_price,
                    )
                    self._send_json({"items": merchants, "total": len(merchants)})
                    return

                if path.startswith("/api/merchants/"):
                    merchant_id = self._resource_id(path, "/api/merchants/")
                    merchant = get_merchant(connection, merchant_id)
                    if merchant is None:
                        self._send_json({"error": "没有找到这家商户"}, 404)
                    else:
                        self._send_json(merchant)
                    return

                if path == "/api/reviews":
                    self._send_json(
                        {
                            "items": list_reviews(connection),
                            "summary": review_summary(connection),
                        }
                    )
                    return

                if path == "/api/suggestions/summary":
                    self._send_json(suggestion_summary(connection))
                    return

                if path == "/api/favorites":
                    self._send_json(list_favorites(connection, session_id))
                    return

                if path == "/api/saved":
                    session_id = self._session_id()
                    self._send_json(
                        {"items": list_saved_merchants(connection, session_id)}
                    )
                    return

                if path == "/api/compare":
                    selected_scene = query.get("scene", [""])[0]
                    if selected_scene not in SCENES:
                        selected_scene = ""
                    result = compare_merchants(
                        connection, query.get("ids", [""])[0], scene=selected_scene
                    )
                    self._send_json(result)
                    return

                self._send_json({"error": "接口不存在"}, 404)

        except ValueError as error:
            self._send_json({"error": str(error)}, 400)
        except OSError:
            self._send_json({"error": "暂时无法读取网页资源"}, 500)

    @staticmethod
    def _resource_id(path, prefix):
        value = path[len(prefix) :]
        if not value.isdigit():
            raise ValueError("商户编号无效")
        return int(value)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            session_id = self._session_id()

            if path == "/api/walking-route":
                raw_id = payload.get("merchant_id")
                if isinstance(raw_id, bool) or not isinstance(raw_id, (int, str)):
                    raise ValueError("门店编号无效")
                merchant_id = int(raw_id)
                with connect() as connection:
                    merchant = get_public_real_merchant(connection, merchant_id)
                if merchant is None:
                    raise ValueError("门店资料不存在，请重新选择")
                self._send_json(
                    walking_route(payload.get("origin"), describe_merchant(merchant))
                )
                return

            # AI extraction happens before opening a SQLite write transaction.
            if path in ("/api/decision", "/api/chat"):
                preferences, mode = prepare_decision(payload)
                with connect() as connection:
                    self._send_json(
                        make_decision(connection, preferences, payload, mode)
                    )
                return

            with connect() as connection:
                ensure_session(connection, session_id)

                if path == "/api/real-favorites":
                    set_real_favorite(
                        connection,
                        session_id,
                        payload.get("merchant_id"),
                        payload.get("active"),
                    )
                    connection.commit()
                    self._send_json({"ok": True})
                    return

                if path == "/api/suggestions":
                    create_suggestion(
                        connection,
                        session_id,
                        payload.get("category", ""),
                        payload.get("message", ""),
                    )
                    connection.execute(
                        "INSERT INTO events(session_id, kind) VALUES (?, ?)",
                        (session_id, "suggestion"),
                    )
                    connection.commit()
                    self._send_json({"ok": True})
                    return

                if path == "/api/feedback":
                    create_feedback(
                        connection,
                        session_id,
                        payload.get("merchant_id"),
                        payload.get("rating"),
                        payload.get("comment", ""),
                    )
                    connection.commit()
                    self._send_json({"ok": True})
                    return

                if path == "/api/favorites":
                    merchant_id = int(payload.get("merchant_id", 0))
                    exists = connection.execute(
                        "SELECT 1 FROM restaurants WHERE id = ?", (merchant_id,)
                    ).fetchone()
                    if not exists:
                        raise ValueError("没有找到这家商户")
                    active = payload.get("active")
                    if not isinstance(active, bool):
                        raise ValueError("收藏操作需要明确的状态")
                    set_favorite(connection, session_id, merchant_id, active)
                    connection.commit()
                    self._send_json({"ok": True})
                    return

                self._send_json({"error": "接口不存在"}, 404)

        except (ValueError, TypeError) as error:
            self._send_json({"error": str(error)}, 400)
        except Exception:
            self._send_json({"error": "服务器暂时遇到问题，请稍后重试"}, 500)

    def log_message(self, format_string, *args):
        """Keep local development logs concise and avoid printing request payloads."""
        print("[NightFind] " + format_string % args)


def main():
    initialize_database()
    port = int(os.environ.get("PORT", "8000"))
    if not 1 <= port <= 65535:
        raise ValueError("PORT 必须在 1–65535 之间")

    server = ThreadingHTTPServer(("0.0.0.0", port), NightFindHandler)
    server.daemon_threads = True
    print("夜寻已启动：http://localhost:{}".format(port), flush=True)
    print("按 Ctrl+C 停止服务。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在关闭夜寻…", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
````

<a id="source-03"></a>

## 3. decision_preferences.py

[打开原文件](../decision_preferences.py) · 449 行

SHA-256：`ba70f6a7b71f40ff12be1c92f9eb13884203dc95e118d946e15e444b272584e4`

````python
"""Turn a dining request into small, editable constraints.

No restaurant facts come from the model. Local parsing works without a key;
optional Responses API extraction only adds request fields. Every turn is validated.
"""

import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from real_catalog import WUHAN_DISTRICTS

try:
    LOCAL_ZONE = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:
    # Windows may lack IANA data. Modern Shanghai uses UTC+8 without DST.
    LOCAL_ZONE = timezone(timedelta(hours=8), "Asia/Shanghai")
# Approximate district centers, not device locations or route destinations.
LANDMARKS = {
    "江汉路": (30.586, 114.291, "江汉区"),
    "楚河汉街": (30.557, 114.342, "武昌区"),
    "光谷": (30.506, 114.402, "洪山区"),
    "粮道街": (30.545, 114.307, "武昌区"),
}
CUISINES = (
    "湖北菜",
    "烧烤",
    "小龙虾",
    "火锅",
    "面食",
    "家常菜",
    "清淡",
    "素食",
    "咖啡",
    "奶茶",
    "汉堡",
    "披萨",
    "日料",
    "中餐",
    "快餐",
)
DEFAULTS = dict(
    party_size=None,
    budget=None,
    budget_kind=None,
    location=None,
    arrival=None,
    arrival_date_inferred=False,
    cuisine="",
    avoid=[],
    radius_km=None,
    wait_minutes=None,
    priority="balanced",
    provenance={},
)


def local_now():
    return datetime.now(LOCAL_ZONE)


def chinese_number(text):
    """The common integer forms used for people, hours and meal budgets."""
    digits = dict(zip("零一二三四五六七八九", range(10)))
    digits["两"] = 2
    if text.isdigit():
        return int(text)
    total = current = 0
    for char in text:
        if char in digits:
            current = digits[char]
        elif char in "十百千":
            total += (current or 1) * {"十": 10, "百": 100, "千": 1000}[char]
            current = 0
        else:
            raise ValueError("无法识别这个数字")
    return total + current


@lru_cache(maxsize=1)
def metro_locations():
    """Names and WGS84 points come from the bundled OSM basemap, not the model."""
    path = Path(__file__).resolve().parent / "static" / "map" / "wuhan-basemap.geojson"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        feature["properties"]["name"]: feature["geometry"]["coordinates"]
        for feature in data["features"]
        if feature["properties"]["layer"] == "station"
    }


def resolve_location(value):
    """Only known local landmarks and explicit device coordinates are resolved."""
    if not isinstance(value, dict):
        return None
    name = str(value.get("name", "")).strip()[:100]
    if not name:
        return None
    for landmark, (lat, lng, district) in LANDMARKS.items():
        if landmark in name:
            return dict(
                name=landmark,
                latitude=lat,
                longitude=lng,
                district=district,
                note="商圈中心近似位置，距离为直线估算",
            )
    for district in WUHAN_DISTRICTS:
        if district in name:
            return dict(
                name=district,
                latitude=None,
                longitude=None,
                district=district,
                note="仅按行政区筛选，尚不能计算距离",
            )
    for station, (lng, lat) in metro_locations().items():
        if name in (station, station + "站", station + "地铁站", station + "附近"):
            return dict(
                name=station + "地铁站",
                latitude=lat,
                longitude=lng,
                district="",
                note="OSM 地铁站中心近似位置，非具体出入口；距离为直线估算",
            )
    if value.get("latitude") is not None or value.get("longitude") is not None:
        lat, lng = float(value.get("latitude")), float(value.get("longitude"))
        if not (29.8 <= lat <= 31.5 and 113.5 <= lng <= 115.2):
            raise ValueError("当前版本只支持武汉范围的位置")
        return dict(
            name=name,
            latitude=lat,
            longitude=lng,
            district="",
            note="用户提供的 WGS84 坐标",
        )
    return None


def validate_preferences(raw):
    raw = raw if isinstance(raw, dict) else {}
    result = {key: raw.get(key, default) for key, default in DEFAULTS.items()}
    for key, low, high in (
        ("party_size", 1, 50),
        ("budget", 1, 100000),
        ("radius_km", 0.1, 100),
        ("wait_minutes", 0, 180),
    ):
        if result[key] is not None:
            try:
                number = float(result[key])
            except (TypeError, ValueError, OverflowError) as error:
                raise ValueError("人数、预算、距离和等待时间需要是有效数字") from error
            if not math.isfinite(number) or not low <= number <= high:
                raise ValueError("人数、预算、距离或等待时间超出支持范围")
            if key in ("party_size", "wait_minutes") and not number.is_integer():
                raise ValueError("人数和等待分钟数需要是整数")
            result[key] = (
                int(number) if key in ("party_size", "wait_minutes") else number
            )
    if result["budget_kind"] not in (None, "total", "per_person"):
        raise ValueError("预算单位需要是总预算或人均预算")
    result["location"] = resolve_location(result["location"])
    if result["arrival"]:
        arrival = datetime.fromisoformat(str(result["arrival"]))
        if arrival.tzinfo is None:
            arrival = arrival.replace(tzinfo=LOCAL_ZONE)
        result["arrival"] = arrival.astimezone(LOCAL_ZONE).isoformat(timespec="minutes")
    result["arrival_date_inferred"] = bool(result["arrival_date_inferred"])
    result["cuisine"] = str(result["cuisine"] or "")[:40]
    if not isinstance(result["avoid"], list) or len(result["avoid"]) > 10:
        raise ValueError("忌口需要是最多 10 项的列表")
    result["avoid"] = list(
        dict.fromkeys(str(item)[:40] for item in result["avoid"] if item)
    )
    result["priority"] = (
        result["priority"]
        if result["priority"] in ("balanced", "distance", "budget")
        else "balanced"
    )
    provenance = result["provenance"] if isinstance(result["provenance"], dict) else {}
    result["provenance"] = {
        k: v
        for k, v in provenance.items()
        if k in DEFAULTS and v in ("user", "inferred", "device")
    }
    return result


def _extract_with_ai(message, now):
    """Optional semantic extraction; return data only, never merchant suggestions."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return {}
    endpoint = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1/responses")
    if not endpoint.startswith("https://"):
        raise ValueError("AI 地址必须使用 HTTPS")
    body = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-5.5"),
        "store": False,
        "instructions": (
            "只提取用户本轮明确说出的餐饮条件，返回一个JSON对象，不要Markdown。"
            "可用字段：party_size整数；budget数字；budget_kind为total或per_person；"
            "location为{name:原文位置}；arrival为带+08:00的ISO到店时间；"
            "cuisine字符串；avoid忌口数组；radius_km数字；wait_minutes整数。"
            "没有提及的字段省略。预算单位模糊时不要猜。禁止编造坐标或餐厅信息。"
            "人数不能从聚会二字推断。当前北京时间：" + now.isoformat()
        ),
        "input": message,
        "max_output_tokens": 500,
    }
    request = Request(
        endpoint,
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        output = json.load(response)
    text = output.get("output_text") or "".join(
        part.get("text", "")
        for item in output.get("output", [])
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    )
    fields = json.loads(text)
    if not isinstance(fields, dict):
        raise ValueError("AI 条件格式无效")
    allowed = set(DEFAULTS) - {"provenance", "priority", "arrival_date_inferred"}
    fields = {
        key: value
        for key, value in fields.items()
        if key in allowed and value is not None
    }
    if "location" in fields:
        fields["location"] = {"name": str(fields["location"].get("name", ""))}
    return fields


def parse_request(message, context=None, location=None, now=None):
    """Merge a single turn; defaults never masquerade as explicit choices."""
    now = now or local_now()
    preferences = validate_preferences(context)
    changes = {}
    mode = "local"
    if os.environ.get("OPENAI_API_KEY", "").strip():
        try:
            changes = _extract_with_ai(message, now)
            validate_preferences({**preferences, **changes})
            mode = "ai"
        except (URLError, OSError, ValueError, TypeError, AttributeError, KeyError):
            changes, mode = {}, "fallback"
    text = re.sub(
        r"[零一二两三四五六七八九十百千]+",
        lambda match: str(chinese_number(match.group())),
        message,
    )
    # A diner with a dietary restriction is not a change to the whole party.
    describes_diner = (
        preferences["party_size"]
        and any(word in text for word in ("不吃", "过敏", "忌口", "不能吃"))
        and not re.search(r"改成|改为|人数|一共|总共|现在是|我们(?:是)?\d+", text)
    )
    if describes_diner:
        changes.pop("party_size", None)
    else:
        match = re.search(r"(\d+)\s*(?:个人|人|位)", text)
        if match:
            changes["party_size"] = int(match[1])
    if re.search(r"^(?:我|就我|今晚)?自己吃", message):
        changes["party_size"] = 1
    match = re.search(
        r"(人均|每人|总共|总预算|一共|合计|预算)\s*(?:不超过|最多|约|在|为|降到|提高到|改成|改为)?\s*[¥￥]?\s*(\d+(?:\.\d+)?)",
        text,
    )
    if match:
        changes["budget"] = float(match[2])
        changes["budget_kind"] = (
            "per_person"
            if match[1] in ("人均", "每人")
            else preferences["budget_kind"] if match[1] == "预算" else "total"
        )
    else:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块)", text)
        if match:
            changes.update(budget=float(match[1]), budget_kind=None)
    # Unit-only replies resolve the previous budget without losing its amount.
    if "budget" not in changes:
        if "人均" in text or "每人" in text:
            changes["budget_kind"] = "per_person"
        elif "总预算" in text or "总共" in text or "总价" in text:
            changes["budget_kind"] = "total"
    place = next((name for name in LANDMARKS if name in message), None)
    place = place or next((name for name in WUHAN_DISTRICTS if name in message), None)
    if place:
        changes["location"] = {"name": place}
    elif re.search(r"(?:在|去|到).+?(?:附近|吃饭|用餐)", message):
        # A newly mentioned unknown place must not silently reuse the old origin.
        changes["location"] = None
    unsupported_day = re.search(r"下周|本周|周末|周[1-7]|星期[1-7]", text)
    # Preference adjustments such as "便宜一点" are not one o'clock.
    time_text = re.sub(r"(?:便宜|近)1点", "", text)
    hour = re.search(
        r"(凌晨|上午|中午|下午|傍晚|晚上|今晚)?\s*(\d{1,2})(?:[:：](\d{2})|点(半|\d{1,2}分?)?)",
        time_text,
    )
    if unsupported_day and "arrival" not in changes:
        changes["arrival"] = None
    if hour and not unsupported_day:
        period, value, minutes, suffix = hour.groups()
        h = int(value)
        minute = int(
            minutes or (30 if suffix == "半" else (suffix or "0").rstrip("分"))
        )
        if not 0 <= h < 24 or not 0 <= minute < 60:
            raise ValueError("请给出有效的到店时间")
        if (period in ("下午", "傍晚", "晚上", "今晚") or "今晚" in text) and h < 12:
            h += 12
        if period in ("凌晨", "上午") and h == 12:
            h = 0
        if period == "中午" and h < 11:
            h += 12
        day_offset = 2 if "后天" in text else 1 if "明天" in text else 0
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", text)
        day = (
            datetime.fromisoformat(date_match[0]).date()
            if date_match
            else (now + timedelta(days=day_offset)).date()
        )
        changes["arrival_date_inferred"] = not (
            date_match or any(word in text for word in ("今天", "今晚", "明天", "后天"))
        )
        changes["arrival"] = (
            datetime.combine(day, datetime.min.time(), LOCAL_ZONE)
            .replace(hour=h, minute=minute)
            .isoformat(timespec="minutes")
        )
    elif ("明天" in text or "后天" in text or "今天" in text) and preferences[
        "arrival"
    ]:
        previous = datetime.fromisoformat(preferences["arrival"])
        day = (
            now + timedelta(days=2 if "后天" in text else 1 if "明天" in text else 0)
        ).date()
        changes["arrival_date_inferred"] = False
        changes["arrival"] = datetime.combine(day, previous.timetz()).isoformat(
            timespec="minutes"
        )
    if "现在" in text:
        changes["arrival_date_inferred"] = False
        changes["arrival"] = now.isoformat(timespec="minutes")
    if "location" not in changes:
        for station in sorted(metro_locations(), key=len, reverse=True):
            if len(station) >= 3 and (
                station + "站" in message or station + "附近" in message
            ):
                changes["location"] = {"name": station + "地铁站"}
                break
    for cuisine in CUISINES:
        if cuisine in message and not re.search(r"(?:不吃|不要)" + cuisine, message):
            changes["cuisine"] = cuisine
            break
    if "不限口味" in text or "不限制口味" in text:
        changes["cuisine"] = ""
    avoid = re.findall(
        r"(?:不吃|忌口|不能吃)\s*([\u4e00-\u9fff]{1,8}?)(?=[，。；、！\s]|$)", message
    )
    avoid += re.findall(r"([\u4e00-\u9fff]{1,5})过敏", message)
    if "没有忌口" in text or "取消忌口" in text:
        changes["avoid"] = []
    elif avoid:
        changes["avoid"] = list(dict.fromkeys(preferences["avoid"] + avoid))
    distance = re.search(r"(\d+(?:\.\d+)?)\s*(?:公里|千米|km)", text, re.I)
    if distance:
        changes["radius_km"] = float(distance[1])
    if "不限距离" in text:
        changes["radius_km"] = None
    wait = re.search(r"(?:等位|等待|排队|等)\s*(?:最多|不超过)?\s*(\d+)\s*分钟", text)
    if wait:
        changes["wait_minutes"] = int(wait[1])
    if "近一点" in text or "找近" in text:
        changes["priority"] = "distance"
    if "便宜" in text or "太贵" in text:
        changes["priority"] = "budget"
    provenance = dict(preferences["provenance"])
    provenance.update({key: "user" for key in changes})
    if location is not None:
        changes["location"] = location
        provenance["location"] = "device"
    result = validate_preferences({**preferences, **changes, "provenance": provenance})
    return result, mode


def per_person_budget(preferences):
    amount = preferences["budget"]
    if amount is None or not preferences["budget_kind"]:
        return None
    if preferences["budget_kind"] == "total":
        return amount / preferences["party_size"] if preferences["party_size"] else None
    return amount


def next_question(preferences, now=None):
    """Ask one necessary question at a time; cuisine can stay unrestricted."""
    checks = (
        (
            not preferences["location"],
            "你准备从哪里出发？目前可识别江汉路、楚河汉街、光谷、粮道街及武汉行政区，也可以使用当前位置。",
            ["江汉路附近", "楚河汉街附近", "光谷附近"],
        ),
        (
            not preferences["party_size"],
            "一共有几个人用餐？",
            ["一个人", "两个人", "四个人"],
        ),
        (
            preferences["budget"] is None,
            "这顿饭预算大概多少？请说明是人均还是总预算。",
            ["人均50元", "人均80元", "总预算300元"],
        ),
        (
            not preferences["budget_kind"],
            "刚才的预算是每个人的，还是所有人加起来的总预算？",
            ["是人均预算", "是总预算"],
        ),
        (
            not preferences["arrival"],
            "预计什么时候到店？可以说“今晚七点”或“明天中午十二点”。",
            ["现在出发", "今晚七点", "明天中午十二点"],
        ),
    )
    for missing, question, actions in checks:
        if missing:
            return {"question": question, "actions": actions}
    if datetime.fromisoformat(preferences["arrival"]) < (
        now or local_now()
    ) - timedelta(minutes=30):
        return {
            "question": "这个到店时间已经过去了，请确认是明天还是另一个时间。",
            "actions": ["明天同一时间", "现在出发"],
        }
    return None
````

<a id="source-04"></a>

## 4. dining_decision.py

[打开原文件](../dining_decision.py) · 569 行

SHA-256：`8107dde038be658251b4ced2233350183bd6615cc669978dba0f02173c1c85e8`

````python
"""Explainable decisions over the real catalog.

Hard known failures are excluded. Missing facts remain conditional candidates;
we never synthesize wait times, opening hours, menu prices or travel durations.
"""

import math
import re
from collections import Counter
from datetime import datetime, timedelta
from urllib.parse import urlencode

from decision_catalog import list_public_merchants, require_public_merchant
from decision_preferences import (
    next_question,
    parse_request,
    per_person_budget,
    validate_preferences,
)

from catalog_language import CUISINE_TERMS, BRAND_ALIASES, display_cuisine
from catalog_policy import catalog_cutoff
from geo_coordinates import wgs84_to_gcj02

WEEKDAYS = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")


def opening_status(raw, arrival):
    """Understand simple daily or OSM weekday time ranges, including midnight.

    Unsupported holiday/seasonal/free-text schedules deliberately stay unknown.
    A returned 'open' means the published schedule covers arrival, not live status.
    """
    if not raw or not arrival:
        return "unknown"
    raw = raw.strip()
    if raw.lower() in ("closed", "off", "暂停营业", "已停业", "永久停业"):
        return "closed"
    if raw in ("24/7", "24小时", "全天营业"):
        return "open"
    raw = re.sub(r"[至~–—]", "-", raw).replace("：", ":")
    schedules = []
    sections = []
    for section in raw.split(";"):
        prefix = re.match(
            r"((?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?\s+)",
            section.strip(),
        )
        for index, interval in enumerate(section.strip().split(",")):
            sections.append((prefix[1] if index and prefix else "") + interval.strip())
    for section in sections:
        match = re.fullmatch(
            r"(?:(Mo|Tu|We|Th|Fr|Sa|Su)(?:-(Mo|Tu|We|Th|Fr|Sa|Su))?\s+)?(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})",
            section.strip(),
        )
        if not match:
            return "unknown"
        first, last, sh, sm, eh, em = match.groups()
        sh, sm, eh, em = map(int, (sh, sm, eh, em))
        if sh > 23 or eh > 24 or sm > 59 or em > 59 or (eh == 24 and em):
            return "unknown"
        days = set(range(7))
        if first:
            start = WEEKDAYS.index(first)
            end = WEEKDAYS.index(last or first)
            days = {(start + step) % 7 for step in range((end - start) % 7 + 1)}
        if sh * 60 + sm == eh * 60 + em:
            return "unknown"
        schedules.append((days, sh * 60 + sm, eh * 60 + em))
    current = datetime.fromisoformat(arrival)
    for day in (current.date(), current.date() - timedelta(days=1)):
        for weekdays, start, end in schedules:
            if day.weekday() not in weekdays:
                continue
            if end <= start:
                end += 24 * 60
            midnight = datetime.combine(day, datetime.min.time(), current.tzinfo)
            if (
                midnight + timedelta(minutes=start)
                <= current
                < midnight + timedelta(minutes=end)
            ):
                return "open"
    return "closed"


def distance_km(origin, merchant):
    values = (
        origin.get("latitude"),
        origin.get("longitude"),
        merchant.get("latitude"),
        merchant.get("longitude"),
    )
    if any(value is None for value in values):
        return None
    lat1, lng1, lat2, lng2 = map(math.radians, values)
    angle = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 6371 * 2 * math.asin(min(1, math.sqrt(angle)))


def price_ceiling(merchant):
    if merchant.get("price_range_basis") == "per_person":
        return merchant.get("price_range_max") or merchant.get("price_per_person")
    # A dish-price band must never masquerade as a per-person meal budget.
    return merchant.get("price_per_person")


def navigation_links(merchant):
    name = merchant["name"]
    district = merchant["district"] if "待确认" not in merchant["district"] else ""
    address = merchant["address"]
    if any(word in address for word in ("待核实", "待确认", "来源地图")):
        address = ""
    query = " ".join(part for part in ("武汉市", district, address, name) if part)
    search = "https://uri.amap.com/search?" + urlencode(
        dict(keyword=query, city="武汉", src="nightfind", callnative=0)
    )
    has_coordinates = (
        merchant.get("latitude") is not None and merchant.get("longitude") is not None
    )
    if has_coordinates:
        lat, lng = wgs84_to_gcj02(merchant["latitude"], merchant["longitude"])
        navigation = "https://uri.amap.com/navigation?" + urlencode(
            dict(
                to=f"{lng:.6f},{lat:.6f},{name}",
                mode="walk",
                coordinate="gaode",
                src="nightfind",
                callnative=0,
            )
        )
    else:
        navigation = search
    return dict(
        navigation_url=navigation,
        map_search_url=search,
        navigation_notice=(
            "按来源坐标定位，请核对分店与具体入口。"
            if has_coordinates
            else "尚无可靠坐标，按店名与地址查找，请核对具体分店。"
        ),
    )


def describe_merchant(merchant):
    """A single presentation model shared by results, details and comparisons."""
    item = dict(merchant)
    item["cuisine_display"] = display_cuisine(item["cuisine"])
    item.update(navigation_links(item))
    phone = item.get("phone") or ""
    item["phone_url"] = (
        "tel:" + re.sub(r"[ ()-]", "", phone)
        if re.fullmatch(r"\+?[\d ()-]{5,30}", phone)
        else None
    )
    item["quality_label"] = {
        "verified": "门店来源资料",
        "community": "OSM 社区资料",
        "web_listing": "公开网页资料",
    }.get(item.get("data_quality"), "资料待确认")
    item["price_notice"] = "来源参考价，实际消费以门店为准"
    if item.get("source_checked_at"):
        item["evidence_label"] = "来源日期 " + item["source_checked_at"]
    elif item.get("source_collected_at"):
        item["evidence_label"] = "在线采集 " + item["source_collected_at"]
    elif item.get("source_archived_at"):
        item["evidence_label"] = (
            "资料归档 " + item["source_archived_at"] + "，本次未重新采集"
        )
    else:
        item["evidence_label"] = "日期待确认"

    return item


def evaluate_merchant(merchant, preferences):
    """Return (candidate, exclusion). Keep each decision rule easy to change."""
    item = describe_merchant(merchant)
    reasons, questions = [], []
    budget = per_person_budget(preferences)
    ceiling = price_ceiling(item)
    if budget is not None and ceiling is not None and ceiling > budget:
        return None, "超过预算参考上限"
    if ceiling is None:
        questions.append("缺少可靠人均参考价，需确认是否符合预算")
    else:
        reasons.append(
            "来源参考人均上限约 ¥{:g}，在 ¥{:g}/人的预算内".format(ceiling, budget)
            if budget is not None
            else "来源参考人均上限约 ¥{:g}".format(ceiling)
        )
    location = preferences["location"] or {}
    distance = distance_km(location, item)
    if (
        distance is None
        and location.get("district")
        and item["district"] != location["district"]
    ):
        return None, "不在所选行政区且无法确认距离"
    radius = preferences["radius_km"]
    if distance is not None and radius is not None and distance > radius:
        return None, "超过指定直线距离"
    if distance is None:
        questions.append("距离待确认，缺少出发位置或门店坐标")
    else:
        reasons.append("距出发位置约 {:.1f} 公里（直线估算）".format(distance))
    item["distance_km"] = round(distance, 1) if distance is not None else None
    status = opening_status(item.get("opening_hours"), preferences["arrival"])
    if status == "closed":
        return None, "来源营业时间不覆盖到店时间"
    if status == "unknown":
        questions.append("无法确认到店时是否营业，请电话或通过来源渠道核实")
    else:
        reasons.append("来源营业时间覆盖预计到店时间，仍建议出发前确认")
    item["opening_status"] = status
    cuisine = preferences["cuisine"]
    text = item["cuisine"] + " " + item.get("signature_dishes", "")
    taste_match = bool(
        cuisine and any(word in text for word in CUISINE_TERMS.get(cuisine, (cuisine,)))
    )
    if cuisine:
        (reasons if taste_match else questions).append(
            "菜系或招牌菜符合「{}」偏好".format(cuisine)
            if taste_match
            else "菜系与「{}」偏好不同，作为备选".format(cuisine)
        )
    for avoid in preferences["avoid"]:
        if avoid in text:
            return None, "已知菜系或菜品与忌口冲突"
    if preferences["avoid"]:
        questions.append("忌口/过敏需向门店逐项确认，现有菜单不能证明不含相关食材")
    if (preferences["party_size"] or 1) > 1:
        questions.append(
            "{} 人座位及是否需要预约需联系门店确认".format(preferences["party_size"])
        )
    if preferences["wait_minutes"] is not None:
        questions.append(
            "没有实时排队资料，无法保证等待不超过 {} 分钟".format(
                preferences["wait_minutes"]
            )
        )
    item.update(
        reasons=reasons,
        questions=questions,
        needs_confirmation=bool(questions),
        taste_match=taste_match,
        estimated_total=(
            round(ceiling * preferences["party_size"], 2)
            if ceiling and preferences["party_size"]
            else None
        ),
    )
    # No opaque quality score: rank by facts and the visitor's current priority.
    distance_order = distance if distance is not None else math.inf
    price_order = ceiling if ceiling is not None else math.inf
    priority = preferences["priority"]
    order = (
        (distance_order, price_order)
        if priority == "distance"
        else (price_order, distance_order)
    )
    if priority == "balanced":
        order = (not taste_match if cuisine else False, distance_order, price_order)
    item["_order"] = (len(questions), *order, item["id"])
    return item, None


def prepare_decision(payload):
    message = str(payload.get("message", "")).strip()
    if not message or len(message) > 2000:
        raise ValueError("请写下 1–2000 个字符的需求")
    if "preferences" in payload:
        if not isinstance(payload["preferences"], dict):
            raise ValueError("用餐条件需要是对象")
        preferences = validate_preferences(payload["preferences"])
        if payload["preferences"].get("location") and preferences["location"] is None:
            raise ValueError(
                "暂未识别出发位置，请选择江汉路、楚河汉街、光谷、粮道街、地铁站或武汉行政区，也可使用当前位置"
            )
        return preferences, "local"
    return parse_request(message, payload.get("context"), payload.get("location"))


def _ids(values):
    if not isinstance(values, list) or len(values) > 100:
        raise ValueError("候选门店编号列表无效")
    try:
        return {int(value) for value in values}
    except (TypeError, ValueError) as error:
        raise ValueError("候选门店编号无效") from error


def make_decision(connection, preferences, payload, mode="local"):
    lookup = (
        None
        if payload.get("intent") == "plan"
        else catalog_lookup(connection, preferences, payload, mode)
    )
    if lookup is not None:
        return lookup
    question = next_question(preferences)
    result = dict(
        stage="clarify" if question else "candidates",
        constraints=preferences,
        budget_per_person=per_person_budget(preferences),
        mode=mode,
        items=[],
        eligible_total=0,
        excluded={},
        follow_up=question,
        exhausted=False,
    )
    if question:
        result["reply"] = question["question"]
        return result
    message = str(payload.get("message", ""))
    seen = (
        _ids(payload.get("seen_ids", []))
        if any(word in message for word in ("换一批", "换一家", "换掉", "看看别的"))
        else set()
    )
    keep = _ids(payload.get("keep_ids", []))
    previous = payload.get("previous_ids", [])
    if not isinstance(previous, list) or len(previous) > 3:
        raise ValueError("上一轮候选编号无效")
    reference = re.search(r"第([一二三123])家", message)
    if reference:
        position = (
            "一二三".find(reference[1])
            if reference[1] in "一二三"
            else int(reference[1]) - 1
        )
        if position < len(previous):
            merchant_id = int(previous[position])
            if "保留" in message:
                keep.add(merchant_id)
            elif "换" in message or "贵" in message:
                seen.add(merchant_id)
    candidates, excluded = [], Counter()
    for merchant in list_public_merchants(connection):
        item, reason = evaluate_merchant(merchant, preferences)
        if reason:
            excluded[reason] += 1
        else:
            candidates.append(item)
    candidates.sort(key=lambda item: item["_order"])
    pinned = [item for item in candidates if item["id"] in keep][:3]
    available = [item for item in candidates if item["id"] not in seen | keep]
    selected = (pinned + available)[:3]
    result["exhausted"] = bool(seen) and not available and len(selected) < 3
    for item in selected:
        item.pop("_order")
        item["kept"] = item["id"] in keep
        # Enrich just the selected rows with dated menu/image evidence.
        detail = require_public_merchant(connection, item["id"])
        item.update(
            menu_items=detail["menu_items"],
            images=detail["images"],
            photos=detail["photos"],
        )
    result.update(
        items=selected, eligible_total=len(candidates), excluded=dict(excluded)
    )
    if not selected:
        result["reply"] = (
            "当前条件下没有新的可用候选。不会自动放宽预算、距离或忌口；可以明确修改条件后再找。"
        )
    else:
        result["reply"] = "找到 {} 家真实门店候选。".format(len(selected))
        if any(item["needs_confirmation"] for item in selected):
            result[
                "reply"
            ] += "标出的未知信息需要出发前向门店确认，这些候选不代表已满足全部条件。"
        if result["exhausted"]:
            result["reply"] += "当前没有更多未展示的候选。"
    result["follow_up"] = {
        "question": "还想调整什么？",
        "actions": ["便宜一点", "找近一点", "换一批", "不限口味"],
    }
    return result


def compare_real_merchants(connection, raw_ids):
    from comparison import parse_merchant_ids

    ids = parse_merchant_ids(raw_ids)
    items = [
        describe_merchant(require_public_merchant(connection, value)) for value in ids
    ]
    return {
        "items": items,
        "notice": "按来源事实并列比较；不使用演示评分。未知价格、营业和距离不作保证。",
    }


def catalog_lookup(connection, preferences, payload, mode):
    """Answer a factual lookup immediately; planning questions remain optional."""
    from real_catalog import catalog_coverage

    message = str(payload.get("message", "")).strip()
    all_merchants = list(list_public_merchants(connection))
    previous = payload.get("previous_ids", [])
    ordinal = re.search(r"第([一二三123])家", message)
    topic = (
        "menu"
        if any(word in message for word in ("菜单", "菜品", "价格", "多少钱", "单价"))
        else "overview"
    )
    targeted_id = None
    if ordinal and topic == "menu" and isinstance(previous, list):
        index = (
            "一二三".find(ordinal[1]) if ordinal[1] in "一二三" else int(ordinal[1]) - 1
        )
        if index < len(previous):
            targeted_id = int(previous[index])
    # An explicitly named branch wins over a brand-wide match.
    normalize = lambda value: re.sub(r"[^\w\u4e00-\u9fff]", "", value).casefold()
    branch_matches = [
        item
        for item in all_merchants
        if re.search(r"[（(]", item["name"])
        and normalize(item["name"]) in normalize(message)
    ]
    if branch_matches and targeted_id is None:
        targeted_id = max(branch_matches, key=lambda item: len(item["name"]))["id"]
    keyword = ""
    # Match names actually present in the database, including branch-free names.
    stems = {re.split(r"[（(·]", item["name"])[0].strip() for item in all_merchants}
    stems.update(BRAND_ALIASES)
    for name in sorted(stems, key=len, reverse=True):
        if len(name) >= 2 and name.casefold() in message.casefold():
            keyword = name
            break
    explicit = any(
        word in message
        for word in (
            "查",
            "搜索",
            "有哪些",
            "有什么",
            "菜单",
            "菜品",
            "多少钱",
            "价格",
            "地址",
            "坐标",
            "数据库",
            "真实商家",
        )
    )
    has_missing = next_question(preferences) is not None
    if not (
        explicit or targeted_id or keyword or (has_missing and preferences["cuisine"])
    ):
        return None
    if not keyword:
        keyword = preferences["cuisine"]
    if (
        not keyword
        and explicit
        and not any(
            word in message for word in ("哪些", "有什么", "数据库", "真实商家", "所有")
        )
    ):
        match = re.search(
            r"(?:查一下|查下|查询|搜索|查查|找找|找|查)\s*(.+?)(?:的(?:菜单|菜品|价格|地址|坐标)|$)",
            message,
        )
        if match:
            keyword = match[1].strip(" ，。？?!！")[:80]
            keyword = keyword.removeprefix("武汉").removesuffix("附近")
        else:
            noun = re.search(
                r"^(.{2,40}?)(?:的)?(?:菜单|菜品|价格|多少钱|地址|坐标)", message
            )
            if noun:
                keyword = noun[1].removesuffix("的").strip(" ，。？?!！")

    if targeted_id is not None:
        records = [item for item in all_merchants if item["id"] == targeted_id]
    elif keyword:
        records = list(list_public_merchants(connection, keyword=keyword))
    else:
        records = all_merchants
    candidates, excluded = [], Counter()
    for record in records:
        item, reason = evaluate_merchant(record, preferences)
        if reason:
            excluded[reason] += 1
        else:
            candidates.append(item)
    candidates.sort(key=lambda item: item["_order"])
    if (preferences["location"] or {}).get("latitude") is not None:
        candidates.sort(
            key=lambda item: (
                item["distance_km"] if item["distance_km"] is not None else math.inf
            )
        )
    if topic == "menu":
        # Prefer sourced menu evidence for a menu lookup, never synthesize a price.
        priced = {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT merchant_id FROM real_merchant_menu_items WHERE price IS NOT NULL AND price_checked_at >= ?",
                (catalog_cutoff(),),
            )
        }
        candidates.sort(key=lambda item: item["id"] not in priced)
    selected = candidates[:3]
    for item in selected:
        item.pop("_order", None)
        detail = require_public_merchant(connection, item["id"])
        item.update(
            menu_items=detail["menu_items"],
            images=detail["images"],
            photos=detail["photos"],
            kept=False,
        )
    stats = catalog_coverage(connection)
    if selected:
        reply = "在真实资料库中找到 {} 家符合本轮查询的门店，先列出 {} 家。".format(
            len(candidates), len(selected)
        )
        if topic == "menu":
            reply += "以下是来源记录的参考单价，不是实时门店报价；实际价格和适用期限请向门店确认。"
            parts = []
            for item in selected:
                prices = [
                    "{} ¥{:g}/{}".format(
                        dish["dish_name"],
                        dish["price"],
                        dish["price_unit"].removeprefix("元/"),
                    )
                    for dish in item["menu_items"]
                    if dish["price"] is not None
                ]
                parts.append(
                    item["name"]
                    + "："
                    + (
                        "；".join(prices[:3])
                        if prices
                        else "尚无带来源的菜单单价，不能据此保证预算"
                    )
                )
            reply += "\n" + "\n".join(parts)
    else:
        reply = "资料库中没有找到同时满足本轮查询的门店；不会用模拟商家或虚构价格补齐。"
    return dict(
        stage="catalog",
        constraints=preferences,
        budget_per_person=per_person_budget(preferences),
        mode=mode,
        reply=reply,
        items=selected,
        eligible_total=len(candidates),
        excluded=dict(excluded),
        exhausted=False,
        catalog_stats=stats,
        query_keyword=keyword,
        follow_up=next_question(preferences)
        or dict(
            question="还想了解哪家店？",
            actions=["查蔡林记的菜单价格", "有哪些咖啡店", "江汉路附近有哪些餐厅"],
        ),
    )
````

<a id="source-05"></a>

## 5. decision_catalog.py

[打开原文件](../decision_catalog.py) · 124 行

SHA-256：`1b8debb5c82b04c88034434f0af2c3439f2bad7ba5905cc7d55518018f5c8a15`

````python
"""Persistence for real dining choices; demo restaurant IDs never enter this API."""

from real_catalog import get_public_real_merchant, public_real_merchants


def initialize_decision_tables(connection):
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS real_favorites (
            session_id TEXT NOT NULL REFERENCES sessions(id),
            merchant_id INTEGER NOT NULL REFERENCES real_merchants(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(session_id, merchant_id)
        )
    """
    )


def list_public_merchants(connection, **filters):
    """Read every public page, so ranking is not limited to the first 100 rows."""
    offset = 0
    while True:
        page = public_real_merchants(connection, limit=100, offset=offset, **filters)
        yield from page["items"]
        offset += len(page["items"])
        if not page["items"] or offset >= page["total"]:
            return


def require_public_merchant(connection, merchant_id):
    try:
        merchant_id = int(merchant_id)
    except (TypeError, ValueError) as error:
        raise ValueError("门店编号无效") from error
    item = get_public_real_merchant(connection, merchant_id)
    if item is None:
        raise ValueError("门店资料不存在或已过期，请重新选择")
    return item


def set_real_favorite(connection, session_id, merchant_id, active):
    if not isinstance(active, bool):
        raise ValueError("收藏操作需要明确的状态")
    if active:
        item = require_public_merchant(connection, merchant_id)
        connection.execute(
            "INSERT OR IGNORE INTO real_favorites(session_id,merchant_id) VALUES (?,?)",
            (session_id, item["id"]),
        )
    else:
        # An expired record may still be removed from a visitor's collection.
        connection.execute(
            "DELETE FROM real_favorites WHERE session_id=? AND merchant_id=?",
            (session_id, int(merchant_id)),
        )


def saved_real_merchants(connection, session_id):
    result = []
    for row in connection.execute(
        "SELECT merchant_id FROM real_favorites WHERE session_id=? ORDER BY created_at DESC, merchant_id DESC",
        (session_id,),
    ):
        item = get_public_real_merchant(connection, row["merchant_id"])
        if item is not None:
            result.append(item)
    return result


def real_map_catalog(connection, keyword="", district=""):
    """All matching source coordinates, independent of the directory list page."""
    from catalog_policy import catalog_cutoff

    menus = {}
    for row in connection.execute(
        "SELECT merchant_id,dish_name,price,price_unit,price_source_url,price_checked_at "
        "FROM real_merchant_menu_items WHERE price IS NOT NULL AND price_checked_at >= ?",
        (catalog_cutoff(),),
    ):
        menus.setdefault(row["merchant_id"], []).append(dict(row))
    fields = (
        "id",
        "name",
        "district",
        "address",
        "cuisine",
        "latitude",
        "longitude",
        "source_name",
        "source_url",
        "source_checked_at",
        "source_collected_at",
        "source_archived_at",
        "source_updated_at",
        "evidence_url",
        "data_quality",
        "price_per_person",
        "price_range_min",
        "price_range_max",
        "price_range_basis",
    )
    result = []
    total = 0
    for item in list_public_merchants(connection, keyword=keyword, district=district):
        total += 1
        lat, lng = item["latitude"], item["longitude"]
        if (
            lat is None
            or lng is None
            or not (29.8 <= lat <= 31.5 and 113.5 <= lng <= 115.2)
        ):
            continue
        result.append(
            {
                **{field: item[field] for field in fields},
                "priced_menu": menus.get(item["id"], []),
            }
        )
    return dict(
        items=result,
        total=total,
        mapped_total=len(result),
        notice="展示当前筛选下全部有来源坐标的门店，不受列表分页限制；点位不代表实时营业。",
    )
````

<a id="source-06"></a>

## 6. real_catalog.py

[打开原文件](../real_catalog.py) · 828 行

SHA-256：`31795acfa332024f093d06c002e82d71d45a39de00e03e3dd06f84e8026bd991`

````python
"""Real Wuhan merchant catalog, separate from demonstration merchants.

Public web listings are attributed and marked unverified until checked in person.
Only recent source records are shown; prices and images retain their own sources.
"""

import csv
import datetime as dt
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

from database import connect
from catalog_policy import catalog_cutoff, photo_cutoff, clean_date
from catalog_language import search_terms

WUHAN_DISTRICTS = (
    "江岸区",
    "江汉区",
    "硚口区",
    "汉阳区",
    "武昌区",
    "青山区",
    "洪山区",
    "东西湖区",
    "蔡甸区",
    "江夏区",
    "黄陂区",
    "新洲区",
    "汉南区",
)
UNKNOWN_DISTRICT = "待确认区县"
VALID_STATUSES = ("draft", "pending", "verified", "rejected")
REQUIRED_COLUMNS = (
    "external_id",
    "name",
    "district",
    "address",
    "cuisine",
    "source_name",
    "source_url",
    "verified_at",
    "verification_method",
)


def initialize_real_catalog(connection):
    """Additive migration; original demo restaurants remain untouched."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS real_merchants (
            id INTEGER PRIMARY KEY,
            external_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            district TEXT NOT NULL,
            address TEXT NOT NULL,
            cuisine TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            phone TEXT,
            price_per_person INTEGER,
            price_range_min INTEGER,
            price_range_max INTEGER,
            price_range_basis TEXT NOT NULL DEFAULT 'unknown',
            opening_hours TEXT,
            source_name TEXT NOT NULL,
            source_url TEXT NOT NULL,
            verified_at TEXT,
            source_checked_at TEXT NOT NULL DEFAULT '',
            source_collected_at TEXT NOT NULL DEFAULT '',
            source_archived_at TEXT NOT NULL DEFAULT '',
            source_updated_at TEXT NOT NULL DEFAULT '',
            evidence_url TEXT NOT NULL DEFAULT '',
            source_published_at TEXT NOT NULL DEFAULT '',
            signature_dishes TEXT NOT NULL DEFAULT '',
            location_note TEXT NOT NULL DEFAULT '',
            verification_method TEXT,
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK(status IN ('draft','pending','verified','rejected')),
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_real_merchants_district_status
            ON real_merchants(district,status);
        CREATE INDEX IF NOT EXISTS idx_real_merchants_name
            ON real_merchants(name);

        CREATE TABLE IF NOT EXISTS real_catalog_seed_state (
            file_name TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS real_merchant_geocode_cache (
            query TEXT PRIMARY KEY,
            latitude REAL,
            longitude REAL,
            display_name TEXT NOT NULL DEFAULT '',
            checked_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS real_merchant_menu_items (
            id INTEGER PRIMARY KEY,
            merchant_id INTEGER NOT NULL REFERENCES real_merchants(id) ON DELETE CASCADE,
            dish_name TEXT NOT NULL,
            price REAL,
            price_unit TEXT NOT NULL DEFAULT '元/份',
            price_source_url TEXT NOT NULL DEFAULT '',
            price_checked_at TEXT NOT NULL DEFAULT '',
            price_note TEXT NOT NULL DEFAULT '',
            UNIQUE(merchant_id, dish_name)
        );
        CREATE TABLE IF NOT EXISTS real_merchant_images (
            id INTEGER PRIMARY KEY,
            merchant_id INTEGER NOT NULL REFERENCES real_merchants(id) ON DELETE CASCADE,
            image_url TEXT NOT NULL,
            image_type TEXT NOT NULL DEFAULT 'dish_reference',
            caption TEXT NOT NULL DEFAULT '',
            taken_at TEXT NOT NULL DEFAULT '',
            author TEXT NOT NULL DEFAULT '',
            license TEXT NOT NULL DEFAULT '',
            license_url TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            UNIQUE(merchant_id, image_url)
        );
        CREATE INDEX IF NOT EXISTS idx_merchant_menu ON real_merchant_menu_items(merchant_id);
        CREATE INDEX IF NOT EXISTS idx_merchant_images ON real_merchant_images(merchant_id);
        CREATE TABLE IF NOT EXISTS real_merchant_photos (
            id INTEGER PRIMARY KEY,
            merchant_id INTEGER NOT NULL REFERENCES real_merchants(id) ON DELETE CASCADE,
            image_filename TEXT NOT NULL UNIQUE,
            taken_at TEXT NOT NULL,
            source_url TEXT NOT NULL,
            copyright_holder TEXT NOT NULL,
            license_note TEXT NOT NULL,
            permission_confirmed INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','verified','rejected')),
            verified_at TEXT,
            reviewed_by TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_merchant_photos
            ON real_merchant_photos(merchant_id,status);
    """
    )
    photo_columns = {
        item["name"]
        for item in connection.execute("PRAGMA table_info(real_merchant_photos)")
    }
    if "created_by" not in photo_columns:
        connection.execute(
            "ALTER TABLE real_merchant_photos ADD COLUMN created_by TEXT NOT NULL DEFAULT ''"
        )
    columns = {
        item["name"] for item in connection.execute("PRAGMA table_info(real_merchants)")
    }
    merchant_migrations = {
        "source_collected_at": "TEXT NOT NULL DEFAULT ''",
        "source_archived_at": "TEXT NOT NULL DEFAULT ''",
        "source_updated_at": "TEXT NOT NULL DEFAULT ''",
        "evidence_url": "TEXT NOT NULL DEFAULT ''",
        "source_published_at": "TEXT NOT NULL DEFAULT ''",
        "signature_dishes": "TEXT NOT NULL DEFAULT ''",
        "location_note": "TEXT NOT NULL DEFAULT ''",
        "price_range_min": "INTEGER",
        "price_range_max": "INTEGER",
        "price_range_basis": "TEXT NOT NULL DEFAULT 'unknown'",
    }
    for name, definition in merchant_migrations.items():
        if name not in columns:
            connection.execute(
                "ALTER TABLE real_merchants ADD COLUMN " + name + " " + definition
            )

    if "source_checked_at" not in columns:
        connection.execute(
            "ALTER TABLE real_merchants ADD COLUMN source_checked_at TEXT NOT NULL DEFAULT ''"
        )


def _clean(value, maximum=200):
    return str(value or "").strip()[:maximum]


def _validate(record):
    if not isinstance(record, dict):
        raise ValueError("每条记录必须为对象")
    item = {field: _clean(record.get(field)) for field in REQUIRED_COLUMNS}
    for key in (
        "external_id",
        "name",
        "district",
        "address",
        "cuisine",
        "source_name",
        "source_url",
    ):
        if not item[key]:
            raise ValueError("缺少必填字段：" + key)
    if item["district"] not in WUHAN_DISTRICTS and item["district"] != UNKNOWN_DISTRICT:
        raise ValueError("行政区不属于武汉市：" + item["district"])
    if item["district"] == UNKNOWN_DISTRICT:
        mapped_web = (
            item["source_name"] == "携程美食林"
            and item["external_id"].startswith("web:")
            and urlsplit(item["source_url"]).hostname == "gs.ctrip.com"
            and record.get("latitude") not in (None, "")
            and record.get("longitude") not in (None, "")
            and record.get("source_checked_at")
        )
        if item["source_name"] != "OpenStreetMap" and not mapped_web:
            raise ValueError("未知行政区需要带有来源坐标的武汉商家资料")
    url = item["source_url"]
    if not re.match(r"^https://[^\s/]+\.[^\s/]+", url):
        raise ValueError("来源链接必须为有效 HTTPS URL")
    checked_at = _clean(record.get("source_checked_at"), 10)
    if checked_at:
        try:
            checked = dt.date.fromisoformat(checked_at)
        except ValueError as error:
            raise ValueError("source_checked_at 必须为 YYYY-MM-DD") from error
        if checked > dt.date.today():
            raise ValueError("来源核验日期不能晚于今天")
    item["source_checked_at"] = checked_at
    for field in ("source_collected_at", "source_archived_at", "source_updated_at"):
        item[field] = clean_date(record.get(field), field)
    item["evidence_url"] = _clean(record.get("evidence_url"), 1000)
    if any(item[key] for key in ("source_collected_at", "source_archived_at")):
        if item["source_name"] != "OpenStreetMap" or not item["external_id"].startswith(
            "osm:"
        ):
            raise ValueError("快照采集和归档证据仅用于带源 ID 的 OSM 资料")
        if not item["evidence_url"].startswith("https://"):
            raise ValueError("快照必须带有可追溯的 HTTPS 证据链接")

    published_at = _clean(record.get("source_published_at"), 10)
    if published_at:
        try:
            dt.date.fromisoformat(published_at)
        except ValueError as error:
            raise ValueError("source_published_at 必须为 YYYY-MM-DD") from error
    item["source_published_at"] = published_at
    item["signature_dishes"] = _clean(record.get("signature_dishes"), 500)
    item["location_note"] = _clean(record.get("location_note"), 240)
    verified_at = item["verified_at"]
    if verified_at:
        try:
            dt.date.fromisoformat(verified_at)
        except ValueError as exc:
            raise ValueError("verified_at 必须使用 YYYY-MM-DD") from exc
        if dt.date.fromisoformat(verified_at) > dt.date.today():
            raise ValueError("核验时间不能晚于今天")
    item["phone"] = _clean(record.get("phone"), 40) or None
    item["opening_hours"] = _clean(record.get("opening_hours"), 300) or None
    item["verification_method"] = _clean(item["verification_method"], 160) or None
    item["latitude"] = item["longitude"] = None
    for field, low, high in (("latitude", -90, 90), ("longitude", -180, 180)):
        raw = record.get(field)
        if raw not in (None, ""):
            try:
                val = float(raw)
            except (ValueError, TypeError) as exc:
                raise ValueError(field + " 必须为数字") from exc
            if not low <= val <= high:
                raise ValueError(field + " 超出合法范围")
            item[field] = val
    # A coordinate is a WGS84 latitude/longitude pair. A half-filled
    # pair would otherwise combine an imported value with a stale value
    # during UPSERT, producing a location that was never verified.
    if (item["latitude"] is None) != (item["longitude"] is None):
        raise ValueError("纬度和经度必须同时填写或同时留空")
    raw_price = record.get("price_per_person")
    try:
        item["price_per_person"] = (
            int(raw_price) if raw_price not in ("", None) else None
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("人均价格必须为整数") from exc
    if (
        item["price_per_person"] is not None
        and not 0 < item["price_per_person"] <= 2000
    ):
        raise ValueError("人均价格超出允许范围")
    for field in ("price_range_min", "price_range_max"):
        raw_range = record.get(field)
        try:
            item[field] = int(raw_range) if raw_range not in ("", None) else None
        except (TypeError, ValueError) as error:
            raise ValueError(field + " 必须为整数") from error
        if item[field] is not None and not 0 < item[field] <= 2000:
            raise ValueError(field + " 超出允许范围")
    if (
        item["price_range_min"] is not None
        and item["price_range_max"] is not None
        and item["price_range_min"] > item["price_range_max"]
    ):
        raise ValueError("人均价格区间上下限不合法")
    item["price_range_basis"] = _clean(record.get("price_range_basis")) or "unknown"
    if item["price_range_basis"] not in ("per_person", "dish", "unknown"):
        raise ValueError("价格区间口径必须为 per_person、dish 或 unknown")
    status = _clean(record.get("status", "pending")) or "pending"
    if status not in VALID_STATUSES:
        raise ValueError("status 不合法")
    if status == "verified":
        if not verified_at or not item["verification_method"]:
            raise ValueError("发布真实商家前必须填写核验日期和核验方式")
        if not checked_at:
            raise ValueError("已核验门店需要单独的来源核查日期")
        boundary = catalog_cutoff()
        if checked_at < boundary or verified_at < boundary:
            raise ValueError("餐厅资料或人工核验超过两年，不能公开")
    item["status"] = status
    return item


def validate_real_merchants(records):
    """Validate a complete batch before any file or database state is changed."""
    prepared = [_validate(record) for record in records]
    if len({row["external_id"] for row in prepared}) != len(prepared):
        raise ValueError("同一批次 external_id 不能重复")
    return prepared


def import_real_merchants(connection, records, dry_run=False):
    """Validate entire batch before writing. Upsert by provider external_id."""
    prepared = validate_real_merchants(records)
    if dry_run:
        return {"validated": len(prepared), "written": 0}
    for item in prepared:
        # A refresh must never undo a manual verification.
        if item["status"] == "pending":
            existing = connection.execute(
                "SELECT status FROM real_merchants WHERE external_id=?",
                (item["external_id"],),
            ).fetchone()
            if existing and existing["status"] == "verified":
                continue
        connection.execute(
            """
            INSERT INTO real_merchants (
                external_id,name,district,address,cuisine,latitude,longitude,
                phone,price_per_person,price_range_min,price_range_max,price_range_basis,
                opening_hours,source_name,source_url,verified_at,source_checked_at,
                source_collected_at,source_archived_at,source_updated_at,evidence_url,
                source_published_at,signature_dishes,location_note,verification_method,status
            ) VALUES (
                :external_id,:name,:district,:address,:cuisine,:latitude,:longitude,
                :phone,:price_per_person,:price_range_min,:price_range_max,:price_range_basis,
                :opening_hours,:source_name,:source_url,:verified_at,:source_checked_at,
                :source_collected_at,:source_archived_at,:source_updated_at,:evidence_url,
                :source_published_at,:signature_dishes,:location_note,:verification_method,:status
            )
            ON CONFLICT(external_id) DO UPDATE SET
                name=excluded.name, district=excluded.district,
                address=excluded.address, cuisine=excluded.cuisine,
                -- A CSV refresh must not erase coordinates added by a later
                -- address geocoding or manual review. Explicit new coordinates
                -- are allowed to replace existing values.
                latitude=COALESCE(excluded.latitude, real_merchants.latitude),
                longitude=COALESCE(excluded.longitude, real_merchants.longitude),
                phone=COALESCE(excluded.phone, real_merchants.phone),
                price_per_person=COALESCE(excluded.price_per_person, real_merchants.price_per_person),
                price_range_min=excluded.price_range_min,
                price_range_max=excluded.price_range_max,
                price_range_basis=excluded.price_range_basis,
                opening_hours=COALESCE(excluded.opening_hours, real_merchants.opening_hours),
                source_name=excluded.source_name,
                source_url=excluded.source_url, verified_at=excluded.verified_at,
                source_checked_at=excluded.source_checked_at,
                source_collected_at=excluded.source_collected_at,
                source_archived_at=excluded.source_archived_at,
                source_updated_at=excluded.source_updated_at,
                evidence_url=excluded.evidence_url,
                source_published_at=excluded.source_published_at,
                signature_dishes=excluded.signature_dishes,
                location_note=CASE WHEN excluded.location_note = ''
                    THEN real_merchants.location_note ELSE excluded.location_note END,
                verification_method=excluded.verification_method,
                status=excluded.status, updated_at=CURRENT_TIMESTAMP
        """,
            item,
        )
    return {"validated": len(prepared), "written": len(prepared)}


def read_import_file(path):
    """Read UTF-8 CSV or JSON file; never fetch arbitrary URLs or scrape sites."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ValueError("导入文件不存在")
    if file_path.stat().st_size > 5_000_000:
        raise ValueError("单次导入文件不得超过 5 MB")
    if file_path.suffix.lower() == ".csv":
        with file_path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    if file_path.suffix.lower() == ".json":
        with file_path.open(encoding="utf-8-sig") as handle:
            values = json.load(handle)
        if not isinstance(values, list):
            raise ValueError("JSON 顶层必须为数组")
        return values
    raise ValueError("仅支持 CSV 或 JSON")


def _fresh_cutoff(reference=None):
    """Retained for licensed photo workflows; merchant evidence uses five years."""
    return photo_cutoff(reference)


def _public_filter():
    """Five-year online evidence; an archive is never labelled human verification."""
    return (
        "((status='verified' AND source_checked_at >= ? AND verified_at >= ?) OR "
        "(status='pending' AND source_name='OpenStreetMap' AND external_id LIKE 'osm:%' "
        "AND max(source_checked_at,source_collected_at,source_archived_at) >= ?) OR "
        "(status='pending' AND external_id LIKE 'web:%' "
        "AND source_name IN ('携程美食林','高德地图','武汉市商务局','武汉市文旅局',"
        "'武汉生活之窗','蔡林记官网','万豪官网','红厨帽') "
        "AND source_checked_at >= ? "
        "AND (source_published_at='' OR source_published_at >= ?)))"
    )


def public_parameters():
    return [catalog_cutoff()] * 5


def public_real_merchants(connection, district="", keyword="", limit=100, offset=0):
    """Expose recent, attributed merchant listings; distinguish verification status."""
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    conditions = [_public_filter()]
    parameters = public_parameters()
    if district:
        if district not in WUHAN_DISTRICTS:
            return {"items": [], "total": 0}
        conditions.append("district = ?")
        parameters.append(district)
    if keyword:
        choices = []
        for word in search_terms(keyword[:80]):
            term = (
                "%"
                + word.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
                + "%"
            )
            choices.append(
                "(name LIKE ? ESCAPE '\\' OR address LIKE ? ESCAPE '\\' OR cuisine LIKE ? ESCAPE '\\' "
                "OR signature_dishes LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM real_merchant_menu_items m "
                "WHERE m.merchant_id=real_merchants.id AND m.dish_name LIKE ? ESCAPE '\\' AND m.price_checked_at >= ?))"
            )
            parameters.extend([term] * 5 + [catalog_cutoff()])
        conditions.append("(" + " OR ".join(choices) + ")")
    where = " AND ".join(conditions)
    total = connection.execute(
        "SELECT COUNT(*) FROM real_merchants WHERE " + where, parameters
    ).fetchone()[0]
    results = connection.execute(
        "WITH recent_images AS (SELECT * FROM real_merchant_images WHERE taken_at >= ?) "
        "SELECT id,name,district,address,cuisine,latitude,longitude,"
        "phone,price_per_person,price_range_min,price_range_max,price_range_basis,opening_hours,source_name,source_url,"
        "verified_at,source_checked_at,source_collected_at,source_archived_at,source_updated_at,evidence_url,source_published_at,signature_dishes,location_note,"
        "verification_method,"
        "CASE WHEN status='verified' THEN 'verified' "
        "WHEN source_name='OpenStreetMap' THEN 'community' ELSE 'web_listing' END AS data_quality, "
        "(SELECT p.id FROM real_merchant_photos AS p "
        " WHERE p.merchant_id=real_merchants.id AND p.status='verified' "
        " AND p.permission_confirmed=1 AND p.taken_at >= ? "
        " AND substr(p.verified_at,1,10) >= ? ORDER BY p.id LIMIT 1) AS photo_id, "
        "(SELECT p.taken_at FROM real_merchant_photos AS p "
        " WHERE p.merchant_id=real_merchants.id AND p.status='verified' "
        " AND p.permission_confirmed=1 AND p.taken_at >= ? "
        " AND substr(p.verified_at,1,10) >= ? ORDER BY p.id LIMIT 1) AS photo_taken_at, "
        "(SELECT p.copyright_holder FROM real_merchant_photos AS p "
        " WHERE p.merchant_id=real_merchants.id AND p.status='verified' "
        " AND p.permission_confirmed=1 AND p.taken_at >= ? "
        " AND substr(p.verified_at,1,10) >= ? ORDER BY p.id LIMIT 1) AS photo_copyright_holder, "
        "(SELECT i.image_url FROM recent_images AS i "
        " WHERE i.merchant_id=real_merchants.id ORDER BY "
        "CASE i.image_type WHEN 'storefront' THEN 0 WHEN 'dish' THEN 1 ELSE 2 END,i.id LIMIT 1) AS cover_image_url, "
        "(SELECT i.image_type FROM recent_images AS i "
        " WHERE i.merchant_id=real_merchants.id ORDER BY "
        "CASE i.image_type WHEN 'storefront' THEN 0 WHEN 'dish' THEN 1 ELSE 2 END,i.id LIMIT 1) AS cover_image_type, "
        "(SELECT i.caption FROM recent_images AS i "
        " WHERE i.merchant_id=real_merchants.id ORDER BY "
        "CASE i.image_type WHEN 'storefront' THEN 0 WHEN 'dish' THEN 1 ELSE 2 END,i.id LIMIT 1) AS cover_image_caption, "
        "(SELECT i.author FROM recent_images AS i "
        " WHERE i.merchant_id=real_merchants.id ORDER BY "
        "CASE i.image_type WHEN 'storefront' THEN 0 WHEN 'dish' THEN 1 ELSE 2 END,i.id LIMIT 1) AS cover_image_author, "
        "(SELECT i.license FROM recent_images AS i "
        " WHERE i.merchant_id=real_merchants.id ORDER BY "
        "CASE i.image_type WHEN 'storefront' THEN 0 WHEN 'dish' THEN 1 ELSE 2 END,i.id LIMIT 1) AS cover_image_license, "
        "(SELECT i.license_url FROM recent_images AS i "
        " WHERE i.merchant_id=real_merchants.id ORDER BY "
        "CASE i.image_type WHEN 'storefront' THEN 0 WHEN 'dish' THEN 1 ELSE 2 END,i.id LIMIT 1) AS cover_image_license_url, "
        "(SELECT i.source_url FROM recent_images AS i "
        " WHERE i.merchant_id=real_merchants.id ORDER BY "
        "CASE i.image_type WHEN 'storefront' THEN 0 WHEN 'dish' THEN 1 ELSE 2 END,i.id LIMIT 1) AS cover_image_source_url, "
        "(SELECT i.taken_at FROM recent_images AS i "
        " WHERE i.merchant_id=real_merchants.id ORDER BY "
        "CASE i.image_type WHEN 'storefront' THEN 0 WHEN 'dish' THEN 1 ELSE 2 END,i.id LIMIT 1) AS cover_image_taken_at "
        "FROM real_merchants WHERE " + where + " ORDER BY "
        "CASE WHEN price_per_person IS NOT NULL OR price_range_min IS NOT NULL THEN 0 "
        "WHEN source_name != 'OpenStreetMap' THEN 1 ELSE 2 END, updated_at DESC,id DESC "
        "LIMIT ? OFFSET ?",
        (
            [_fresh_cutoff()]
            + [_fresh_cutoff(), _fresh_cutoff()] * 3
            + parameters
            + [limit, offset]
        ),
    ).fetchall()
    items = []
    for row in results:
        item = dict(row)
        photo_id = item.pop("photo_id")
        item["photo_url"] = "/real-photo/{}".format(photo_id) if photo_id else None
        items.append(item)
    if items:
        by_id = {item["id"]: item for item in items}
        for item in items:
            item["priced_menu"] = []
        placeholders = ",".join("?" for _ in by_id)
        for dish in connection.execute(
            "SELECT merchant_id,dish_name,price,price_unit,price_source_url,price_checked_at "
            "FROM real_merchant_menu_items WHERE merchant_id IN (" + placeholders + ") "
            "AND price IS NOT NULL AND price_checked_at >= ? ORDER BY id",
            list(by_id) + [catalog_cutoff()],
        ):
            target = by_id[dish["merchant_id"]]["priced_menu"]
            if len(target) < 3:
                target.append(dict(dish))
    return {
        "items": items,
        "total": total,
        "notice": "公开网页收录不代表营业状态已人工核实；人均参考价与菜单价格可能变化，出行前请向商家确认。",
        "license": "© OpenStreetMap contributors · ODbL (www.openstreetmap.org/copyright)",
    }


def get_public_real_merchant(connection, merchant_id):
    """Return recent community/verified details without exposing rejected candidates."""
    boundary = _fresh_cutoff()
    row = connection.execute(
        "SELECT id,name,district,address,cuisine,latitude,longitude,phone,"
        "price_per_person,price_range_min,price_range_max,price_range_basis,opening_hours,source_name,source_url,verified_at,"
        "source_checked_at,source_collected_at,source_archived_at,source_updated_at,evidence_url,source_published_at,signature_dishes,location_note,"
        "CASE WHEN status='verified' THEN 'verified' "
        "WHEN source_name='OpenStreetMap' THEN 'community' ELSE 'web_listing' END AS data_quality "
        "FROM real_merchants WHERE id=? AND " + _public_filter(),
        [merchant_id] + public_parameters(),
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    photos = connection.execute(
        """
        SELECT id,taken_at,copyright_holder,license_note,source_url
        FROM real_merchant_photos
        WHERE merchant_id=? AND status='verified' AND permission_confirmed=1
          AND taken_at >= ? AND substr(verified_at,1,10) >= ?
        ORDER BY id LIMIT 8
        """,
        (merchant_id, boundary, boundary),
    ).fetchall()
    data["photos"] = [
        {**dict(photo), "photo_url": "/real-photo/{}".format(photo["id"])}
        for photo in photos
    ]
    data["images"] = [
        dict(image)
        for image in connection.execute(
            "SELECT image_url,image_type,caption,taken_at,author,license,license_url,source_url "
            "FROM real_merchant_images WHERE merchant_id=? AND taken_at >= ? ORDER BY id",
            (merchant_id, boundary),
        )
    ]
    data["menu_items"] = [
        dict(item)
        for item in connection.execute(
            "SELECT dish_name,price,price_unit,price_source_url,price_checked_at,price_note "
            "FROM real_merchant_menu_items WHERE merchant_id=? AND price_checked_at >= ? ORDER BY id",
            (merchant_id, catalog_cutoff()),
        )
    ]
    return data


def catalog_coverage(connection):
    """Report provenance and actual coverage without claiming all stores are open."""
    params = public_parameters()
    where = _public_filter()
    counts = list(
        connection.execute(
            "SELECT district,count(*) total,sum(status='verified') verified_count FROM real_merchants "
            "WHERE " + where + " GROUP BY district",
            params,
        )
    )
    quality = {
        row["quality"]: row["total"]
        for row in connection.execute(
            "SELECT CASE WHEN status='verified' THEN 'verified' WHEN source_name='OpenStreetMap' "
            "THEN 'community' ELSE 'web_listing' END quality,count(*) total "
            "FROM real_merchants WHERE " + where + " GROUP BY quality",
            params,
        )
    }
    mapped = connection.execute(
        "SELECT count(*) FROM real_merchants WHERE "
        + where
        + " AND latitude IS NOT NULL AND longitude IS NOT NULL",
        params,
    ).fetchone()[0]
    verified = sum(row["verified_count"] for row in counts)
    total = sum(row["total"] for row in counts)
    priced_menus = connection.execute(
        "SELECT count(*) FROM real_merchant_menu_items m JOIN real_merchants r ON r.id=m.merchant_id "
        "WHERE m.price IS NOT NULL AND m.price_checked_at >= ? AND r.id IN "
        "(SELECT id FROM real_merchants WHERE " + where + ")",
        [catalog_cutoff()] + params,
    ).fetchone()[0]
    priced_merchants = connection.execute(
        "SELECT count(DISTINCT m.merchant_id) FROM real_merchant_menu_items m WHERE m.price IS NOT NULL "
        "AND m.price_checked_at >= ? AND m.merchant_id IN (SELECT id FROM real_merchants WHERE "
        + where
        + ")",
        [catalog_cutoff()] + params,
    ).fetchone()[0]
    priced_mapped = connection.execute(
        "SELECT count(DISTINCT m.merchant_id) FROM real_merchant_menu_items m JOIN real_merchants r ON r.id=m.merchant_id "
        "WHERE m.price IS NOT NULL AND m.price_checked_at >= ? AND r.latitude IS NOT NULL AND r.longitude IS NOT NULL "
        "AND r.id IN (SELECT id FROM real_merchants WHERE " + where + ")",
        [catalog_cutoff()] + params,
    ).fetchone()[0]
    return dict(
        city="武汉市",
        priced_merchant_total=priced_merchants,
        priced_mapped_total=priced_mapped,
        public_total=total,
        mapped_total=mapped,
        verified_total=verified,
        community_total=quality.get("community", 0),
        web_listing_total=quality.get("web_listing", 0),
        unassigned_district_total=next(
            (row["total"] for row in counts if row["district"] == UNKNOWN_DISTRICT), 0
        ),
        priced_menu_items=priced_menus,
        freshness_cutoff=catalog_cutoff(),
        candidate_total=connection.execute(
            "SELECT count(*) FROM real_merchants WHERE source_name='OpenStreetMap'"
        ).fetchone()[0],
        districts=[
            dict(
                name=district,
                public_count=next(
                    (r["total"] for r in counts if r["district"] == district), 0
                ),
                verified_count=next(
                    (r["verified_count"] for r in counts if r["district"] == district),
                    0,
                ),
            )
            for district in WUHAN_DISTRICTS
        ],
        notice="近五年的公开资料；采集、归档与人工核查日期分别展示。网上收录不证明当前营业，缺失价格不补造。",
    )


def seed_bundled_catalog(connection, data_dir=None):
    """Load the checked-in Wuhan CSV files once, then only when a file changes."""
    data_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parent / "data"
    files = {
        "wuhan_restaurants.csv": "merchants",
        "wuhan_menu_items.csv": "menu",
        "wuhan_restaurant_images.csv": "images",
    }
    totals = {"merchants": 0, "menu_items": 0, "images": 0}
    for file_name, kind in files.items():
        path = data_dir / file_name
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        saved = connection.execute(
            "SELECT sha256 FROM real_catalog_seed_state WHERE file_name=?",
            (file_name,),
        ).fetchone()
        if saved and saved["sha256"] == digest:
            continue

        records = read_import_file(path)
        if kind == "merchants":
            totals["merchants"] = import_real_merchants(connection, records)["written"]
        elif kind == "menu":
            for item in records:
                merchant = connection.execute(
                    "SELECT id FROM real_merchants WHERE external_id=?",
                    (_clean(item.get("external_id")),),
                ).fetchone()
                if merchant is None:
                    continue
                raw_price = _clean(item.get("price"), 30)
                try:
                    price = float(raw_price) if raw_price else None
                except ValueError as error:
                    raise ValueError("菜品价格必须为数字") from error
                if price is not None and not 0 < price <= 10000:
                    raise ValueError("菜品价格超出允许范围")
                checked_at = _clean(item.get("price_checked_at"), 10)
                if checked_at:
                    try:
                        checked = dt.date.fromisoformat(checked_at)
                    except ValueError as error:
                        raise ValueError("菜品价格核查日期必须为 YYYY-MM-DD") from error
                    if (
                        checked > dt.date.today()
                        or checked.isoformat() < catalog_cutoff()
                    ):
                        raise ValueError("菜品价格资料必须在最近五年内")
                source_url = _clean(item.get("price_source_url"), 1000)
                if not re.match(r"^https://[^\s/]+\.[^\s/]+", source_url):
                    raise ValueError("菜品价格必须附带 HTTPS 来源")
                connection.execute(
                    """
                    INSERT INTO real_merchant_menu_items(
                        merchant_id,dish_name,price,price_unit,price_source_url,
                        price_checked_at,price_note
                    ) VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(merchant_id,dish_name) DO UPDATE SET
                        price=excluded.price,price_unit=excluded.price_unit,
                        price_source_url=excluded.price_source_url,
                        price_checked_at=excluded.price_checked_at,
                        price_note=excluded.price_note
                    """,
                    (
                        merchant["id"],
                        _clean(item.get("dish_name"), 100),
                        price,
                        _clean(item.get("price_unit"), 30) or "元/份",
                        source_url,
                        checked_at,
                        _clean(item.get("price_note"), 300),
                    ),
                )
                totals["menu_items"] += 1
        else:
            allowed_hosts = {
                "thumb.wikimedia.org",
                "upload.wikimedia.org",
                "commons.wikimedia.org",
            }
            allowed_licenses = {"CC BY 4.0", "CC BY-SA 4.0", "CC0 1.0"}
            for item in records:
                merchant = connection.execute(
                    "SELECT id FROM real_merchants WHERE external_id=?",
                    (_clean(item.get("external_id")),),
                ).fetchone()
                if merchant is None:
                    continue
                image_url = _clean(item.get("image_url"), 1500)
                source_url = _clean(item.get("source_url"), 1500)
                license_url = _clean(item.get("license_url"), 500)
                image_host = urlsplit(image_url).hostname
                if (
                    urlsplit(image_url).scheme != "https"
                    or image_host not in allowed_hosts
                ):
                    raise ValueError("图片必须来自已审核的 Wikimedia 图片域名")
                if not source_url.startswith(
                    "https://commons.wikimedia.org/wiki/File:"
                ):
                    raise ValueError("图片必须附带 Wikimedia 原始文件页")
                license_name = _clean(item.get("license"), 40)
                if license_name not in allowed_licenses or not license_url.startswith(
                    "https://creativecommons.org/"
                ):
                    raise ValueError("图片授权信息不完整或不受支持")
                taken_at = _clean(item.get("taken_at"), 10)
                try:
                    taken = dt.date.fromisoformat(taken_at)
                except ValueError as error:
                    raise ValueError("图片拍摄日期必须为 YYYY-MM-DD") from error
                if taken > dt.date.today() or taken.isoformat() < _fresh_cutoff():
                    raise ValueError("图片拍摄日期必须在最近两年内")
                image_type = _clean(item.get("image_type"), 30)
                if image_type not in ("storefront", "dish", "dish_reference"):
                    raise ValueError("图片类型不合法")
                if not _clean(item.get("author"), 100):
                    raise ValueError("图片必须注明作者")
                connection.execute(
                    """
                    INSERT INTO real_merchant_images(
                        merchant_id,image_url,image_type,caption,taken_at,
                        author,license,license_url,source_url
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(merchant_id,image_url) DO UPDATE SET
                        image_type=excluded.image_type,caption=excluded.caption,
                        taken_at=excluded.taken_at,author=excluded.author,
                        license=excluded.license,license_url=excluded.license_url,
                        source_url=excluded.source_url
                    """,
                    (
                        merchant["id"],
                        image_url,
                        image_type,
                        _clean(item.get("caption"), 240),
                        taken_at,
                        _clean(item.get("author"), 100),
                        license_name,
                        license_url,
                        source_url,
                    ),
                )
                totals["images"] += 1

        connection.execute(
            """
            INSERT INTO real_catalog_seed_state(file_name,sha256)
            VALUES (?,?)
            ON CONFLICT(file_name) DO UPDATE SET
                sha256=excluded.sha256, imported_at=CURRENT_TIMESTAMP
            """,
            (file_name, digest),
        )
    return totals
````

<a id="source-07"></a>

## 7. database.py

[打开原文件](../database.py) · 615 行

SHA-256：`dfa66bcd5f2db12e39db3f11d8a561cf19c4a49eb9ffc38c0eb50e2e0af6abc3`

````python
"""Database access and schema setup for NightFind.

Keep SQL and persistence details in this module. Business rules live in services.py.
"""

import json
import os
import sqlite3
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("APP_DB", ROOT / "data" / "night.db"))


def connect():
    """Return a configured SQLite connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _add_missing_columns(connection):
    """Migrate older project databases without deleting existing records."""
    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(restaurants)")
    }
    migrations = {
        "description": "TEXT NOT NULL DEFAULT ''",
        "address_label": "TEXT NOT NULL DEFAULT ''",
        "source_note": "TEXT NOT NULL DEFAULT '研究原型模拟数据'",
    }
    for name, definition in migrations.items():
        if name not in columns:
            connection.execute(
                "ALTER TABLE restaurants ADD COLUMN " + name + " " + definition
            )


def initialize_database(
    *, import_snapshot=True, import_bundled_catalog=True, include_demo=False
):
    """Initialize the real catalog. Demo fixtures are opt-in for isolated tests only."""
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS districts (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT NOT NULL,
                lat REAL,
                lng REAL
            );

            CREATE TABLE IF NOT EXISTS restaurants (
                id INTEGER PRIMARY KEY,
                district_id INTEGER REFERENCES districts(id),
                name TEXT NOT NULL,
                cuisine TEXT NOT NULL,
                price INTEGER NOT NULL,
                rating REAL NOT NULL DEFAULT 0,
                wait INTEGER NOT NULL DEFAULT 0,
                lat REAL,
                lng REAL,
                tags TEXT NOT NULL DEFAULT '',
                color TEXT NOT NULL DEFAULT '#DCE9D4',
                description TEXT NOT NULL DEFAULT '',
                address_label TEXT NOT NULL DEFAULT '',
                source_note TEXT NOT NULL DEFAULT '研究原型模拟数据'
            );

            CREATE TABLE IF NOT EXISTS hours (
                restaurant_id INTEGER PRIMARY KEY REFERENCES restaurants(id),
                opens INTEGER NOT NULL,
                closes INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dishes (
                id INTEGER PRIMARY KEY,
                restaurant_id INTEGER REFERENCES restaurants(id),
                name TEXT NOT NULL,
                price INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS recommendation_runs (
                id INTEGER PRIMARY KEY,
                session_id TEXT REFERENCES sessions(id),
                constraints_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS recommendation_items (
                id INTEGER PRIMARY KEY,
                run_id INTEGER REFERENCES recommendation_runs(id),
                restaurant_id INTEGER REFERENCES restaurants(id),
                score REAL,
                explanation TEXT
            );

            CREATE TABLE IF NOT EXISTS favorites (
                session_id TEXT REFERENCES sessions(id),
                restaurant_id INTEGER REFERENCES restaurants(id),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(session_id, restaurant_id)
            );

            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY,
                session_id TEXT REFERENCES sessions(id),
                scene TEXT,
                priority TEXT,
                trust INTEGER,
                willingness INTEGER,
                comment TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY,
                session_id TEXT REFERENCES sessions(id),
                restaurant_id INTEGER REFERENCES restaurants(id),
                rating INTEGER,
                comment TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                session_id TEXT REFERENCES sessions(id),
                kind TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS suggestions (
                id INTEGER PRIMARY KEY,
                session_id TEXT REFERENCES sessions(id),
                category TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_restaurants_district
                ON restaurants(district_id);
            CREATE INDEX IF NOT EXISTS idx_feedback_restaurant
                ON feedback(restaurant_id);
            CREATE INDEX IF NOT EXISTS idx_suggestions_created
                ON suggestions(created_at);
            """
        )
        _add_missing_columns(connection)
        if include_demo:
            _seed_demo_data(connection)
            _backfill_merchant_descriptions(connection)
        else:
            _remove_known_demo_records(connection)
        # Keep verified real merchants in separate tables from prototype data.
        from real_catalog import initialize_real_catalog

        initialize_real_catalog(connection)
        from decision_catalog import initialize_decision_tables

        initialize_decision_tables(connection)
        # Seed the checked-in Wuhan merchant CSV files without network access.
        if import_bundled_catalog:
            from real_catalog import seed_bundled_catalog

            seed_bundled_catalog(connection)
        # Load approved OSM snapshot only when its checksum changes.
        # No network access occurs during normal app startup.
        if import_snapshot:
            from osm_sync import hydrate_osm_snapshot

            hydrate_osm_snapshot(connection)


def _remove_known_demo_records(connection):
    """Archive once before removing only the 24 explicitly known sample shops."""
    prefixes = (
        "江城炭火烧烤",
        "巷里小龙虾",
        "一碗热干面",
        "深夜食堂·小馆",
        "沿江鲜鱼馆",
        "街角砂锅粥",
    )
    areas = ("江汉路", "楚河汉街", "光谷步行街", "粮道街")
    names = [name + " · " + area for name in prefixes for area in areas]
    placeholders = ",".join("?" for _ in names)
    ids = [
        row[0]
        for row in connection.execute(
            "SELECT id FROM restaurants WHERE source_note='研究原型模拟数据' AND name IN ("
            + placeholders
            + ")",
            names,
        )
    ]
    if not ids:
        return
    # Never discard visitors' previous sample-linked records without a recoverable copy.
    connection.commit()
    backup_dir = DB_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(
        backup_dir / ("before-real-only-" + uuid.uuid4().hex + ".db")
    ) as backup:
        connection.backup(backup)
    selected = ",".join("?" for _ in ids)
    for table in ("recommendation_items", "hours", "dishes", "favorites", "feedback"):
        connection.execute(
            "DELETE FROM " + table + " WHERE restaurant_id IN (" + selected + ")", ids
        )
    connection.execute("DELETE FROM restaurants WHERE id IN (" + selected + ")", ids)


def _seed_demo_data(connection):
    """Insert the sample Wuhan directory only when the database is empty."""
    if connection.execute("SELECT COUNT(*) FROM districts").fetchone()[0] == 0:
        districts = [
            ("江汉路", "老街巷与城市夜生活交织", 30.586, 114.291),
            ("楚河汉街", "适合散步、聚餐和慢慢挑选晚餐", 30.557, 114.342),
            ("光谷步行街", "年轻人常去的夜间消费片区", 30.506, 114.402),
            ("粮道街", "街巷里的武汉风味与小吃", 30.545, 114.307),
        ]
        connection.executemany(
            "INSERT INTO districts(name, description, lat, lng) VALUES (?, ?, ?, ?)",
            districts,
        )

    if connection.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0] > 0:
        return

    samples = [
        (
            "江城炭火烧烤",
            "烧烤",
            65,
            "朋友聚会,烟火气",
            "#D9B48F",
            "适合慢慢聊天的炭火烧烤风味小馆。",
        ),
        (
            "巷里小龙虾",
            "小龙虾",
            98,
            "朋友聚会,武汉特色",
            "#E8B6A5",
            "以小龙虾和分享式菜品为主题的夜宵小馆。",
        ),
        (
            "一碗热干面",
            "湖北菜",
            22,
            "独自用餐,武汉特色",
            "#E8D8A7",
            "适合简单吃一餐的武汉风味面食档口。",
        ),
        (
            "深夜食堂·小馆",
            "家常菜",
            48,
            "独自用餐,安静",
            "#C9D9B9",
            "以家常菜为主，适合不想吃得太复杂的晚上。",
        ),
        (
            "沿江鲜鱼馆",
            "湖北菜",
            86,
            "朋友聚会,武汉特色",
            "#B9D3D0",
            "以鱼类和湖北家常风味为主题的聚餐小馆。",
        ),
        (
            "街角砂锅粥",
            "粥粉面",
            35,
            "清淡,独自用餐",
            "#E4D7BC",
            "口味相对清爽，适合想吃热乎简餐的时候。",
        ),
    ]
    districts = connection.execute(
        "SELECT id, name, lat, lng FROM districts ORDER BY id"
    ).fetchall()

    for district_index, district in enumerate(districts):
        for item_index, sample in enumerate(samples):
            name, cuisine, price, tags, color, description = sample
            restaurant_id = district_index * len(samples) + item_index + 1
            connection.execute(
                """
                INSERT INTO restaurants (
                    id, district_id, name, cuisine, price, rating, wait,
                    lat, lng, tags, color, description, address_label, source_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    restaurant_id,
                    district["id"],
                    name + " · " + district["name"],
                    cuisine,
                    price + district_index * 3,
                    round(4.3 + (item_index % 4) * 0.2, 1),
                    8 + item_index * 5,
                    district["lat"] + 0.003 * (item_index - 2),
                    district["lng"] + 0.004 * (item_index % 3 - 1),
                    tags,
                    color,
                    description,
                    district["name"] + "（示例商圈，非真实门牌）",
                    "研究原型模拟数据",
                ),
            )
            close_hour = 28 if item_index % 3 == 0 else 26
            connection.execute(
                "INSERT INTO hours(restaurant_id, opens, closes) VALUES (?, ?, ?)",
                (restaurant_id, 17, close_hour),
            )
            dish_names = ["招牌推荐", "时令小菜", "店内小食"]
            for dish_index, dish_name in enumerate(dish_names):
                connection.execute(
                    """
                    INSERT INTO dishes(restaurant_id, name, price)
                    VALUES (?, ?, ?)
                    """,
                    (
                        restaurant_id,
                        cuisine + dish_name,
                        max(8, price // (dish_index + 1)),
                    ),
                )


def _backfill_merchant_descriptions(connection):
    """Give older seeded rows readable descriptions after schema migration."""
    connection.execute(
        """
        UPDATE restaurants
        SET description = '以' || cuisine || '为主的夜间餐饮示例商户，适合'
            || REPLACE(tags, ',', '、') || '等就餐场景。'
        WHERE description IS NULL OR description = ''
        """
    )
    connection.execute(
        """
        UPDATE restaurants
        SET address_label = (
            SELECT name || '（示例商圈，非真实门牌）'
            FROM districts WHERE districts.id = restaurants.district_id
        )
        WHERE address_label IS NULL OR address_label = ''
        """
    )


def ensure_session(connection, session_id):
    connection.execute("INSERT OR IGNORE INTO sessions(id) VALUES (?)", (session_id,))


def _merchant_dict(row):
    merchant = dict(row)
    merchant["tags"] = [
        value for value in (merchant.get("tags") or "").split(",") if value
    ]
    merchant["is_demo"] = True
    return merchant


def list_merchants(
    connection, keyword="", district="", cuisine="", max_price=None, limit=100
):
    """Search the merchant directory with parameterized filters."""
    conditions = []
    parameters = []

    if keyword:
        pattern = "%" + keyword.strip()[:80] + "%"
        conditions.append("(r.name LIKE ? OR r.cuisine LIKE ? OR r.description LIKE ?)")
        parameters.extend([pattern, pattern, pattern])

    if district:
        conditions.append("d.name = ?")
        parameters.append(district)

    if cuisine and cuisine != "不限":
        conditions.append("r.cuisine = ?")
        parameters.append(cuisine)

    if max_price is not None:
        conditions.append("r.price <= ?")
        parameters.append(max_price)

    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    query = (
        """
        SELECT
            r.id, r.name, r.cuisine, r.price, r.rating, r.wait,
            r.tags, r.color, r.description, r.address_label, r.source_note, r.lat, r.lng,
            d.name AS district, h.opens, h.closes,
            COALESCE(review_stats.review_count, 0) AS review_count,
            review_stats.average_rating AS user_rating
        FROM restaurants AS r
        JOIN districts AS d ON d.id = r.district_id
        LEFT JOIN hours AS h ON h.restaurant_id = r.id
        LEFT JOIN (
            SELECT restaurant_id, COUNT(*) AS review_count,
                   ROUND(AVG(rating), 1) AS average_rating
            FROM feedback GROUP BY restaurant_id
        ) AS review_stats ON review_stats.restaurant_id = r.id
    """
        + where_clause
        + " ORDER BY r.name LIMIT ?"
    )
    parameters.append(max(1, min(int(limit), 200)))
    rows = connection.execute(query, parameters).fetchall()
    return [_merchant_dict(row) for row in rows]


def get_merchant(connection, merchant_id):
    row = connection.execute(
        """
        SELECT r.*, d.name AS district, h.opens, h.closes
        FROM restaurants AS r
        JOIN districts AS d ON d.id = r.district_id
        LEFT JOIN hours AS h ON h.restaurant_id = r.id
        WHERE r.id = ?
        """,
        (merchant_id,),
    ).fetchone()
    if row is None:
        return None

    merchant = _merchant_dict(row)
    merchant["dishes"] = [
        dict(dish)
        for dish in connection.execute(
            "SELECT name, price FROM dishes WHERE restaurant_id = ? ORDER BY id",
            (merchant_id,),
        )
    ]
    merchant["reviews"] = [
        dict(review)
        for review in connection.execute(
            """
            SELECT rating, comment, created_at FROM feedback
            WHERE restaurant_id = ? ORDER BY id DESC LIMIT 10
            """,
            (merchant_id,),
        )
    ]
    return merchant


def list_districts(connection):
    return [
        dict(row)
        for row in connection.execute(
            "SELECT id, name, description FROM districts ORDER BY id"
        )
    ]


def save_recommendation_run(connection, session_id, preferences, items):
    cursor = connection.execute(
        """
        INSERT INTO recommendation_runs(session_id, constraints_json)
        VALUES (?, ?)
        """,
        (session_id, json.dumps(preferences, ensure_ascii=False)),
    )
    run_id = cursor.lastrowid
    connection.executemany(
        """
        INSERT INTO recommendation_items(run_id, restaurant_id, score, explanation)
        VALUES (?, ?, ?, ?)
        """,
        [
            (
                run_id,
                item["id"],
                item["score"],
                item["explanation"],
            )
            for item in items
        ],
    )


def list_favorites(connection, session_id):
    return [
        row["restaurant_id"]
        for row in connection.execute(
            "SELECT restaurant_id FROM favorites WHERE session_id = ? "
            "ORDER BY created_at DESC, restaurant_id DESC",
            (session_id,),
        )
    ]


def list_saved_merchants(connection, session_id):
    """Return the current visitor's saved shops, newest first.

    This uses the existing favorites table. Saving is scoped to the browser's
    anonymous session; there is no cross-device account synchronization.
    """
    saved = list_favorites(connection, session_id)
    if not saved:
        return []
    catalog = {
        merchant["id"]: merchant for merchant in list_merchants(connection, limit=200)
    }
    return [catalog[merchant_id] for merchant_id in saved if merchant_id in catalog]


def set_favorite(connection, session_id, merchant_id, active):
    if active:
        connection.execute(
            """
            INSERT OR IGNORE INTO favorites(session_id, restaurant_id)
            VALUES (?, ?)
            """,
            (session_id, merchant_id),
        )
    else:
        connection.execute(
            "DELETE FROM favorites WHERE session_id = ? AND restaurant_id = ?",
            (session_id, merchant_id),
        )


def create_suggestion(connection, session_id, category, message):
    allowed = {"功能建议", "商家信息", "使用体验", "其他"}
    if category not in allowed:
        raise ValueError("请选择有效的建议分类")
    message = str(message).strip()
    if not message or len(message) > 2000:
        raise ValueError("建议内容需为 1–2000 个字符")
    connection.execute(
        """
        INSERT INTO suggestions(session_id, category, message)
        VALUES (?, ?, ?)
        """,
        (session_id, category, message),
    )


def suggestion_summary(connection):
    total = connection.execute("SELECT COUNT(*) FROM suggestions").fetchone()[0]
    categories = [
        dict(row)
        for row in connection.execute(
            """
            SELECT category, COUNT(*) AS count
            FROM suggestions GROUP BY category ORDER BY count DESC
            """
        )
    ]
    return {"total": total, "categories": categories}


def create_feedback(connection, session_id, merchant_id, rating, comment):
    try:
        merchant_id = int(merchant_id)
    except (TypeError, ValueError) as error:
        raise ValueError("请选择有效商户") from error
    exists = connection.execute(
        "SELECT 1 FROM restaurants WHERE id = ?", (merchant_id,)
    ).fetchone()
    if exists is None:
        raise ValueError("没有找到这家商户")
    rating = int(rating)
    if not 1 <= rating <= 5:
        raise ValueError("评分范围为 1–5")
    connection.execute(
        """
        INSERT INTO feedback(session_id, restaurant_id, rating, comment)
        VALUES (?, ?, ?, ?)
        """,
        (session_id, merchant_id, rating, str(comment).strip()[:2000]),
    )


def review_summary(connection):
    summary = connection.execute(
        """
        SELECT COUNT(*) AS total, ROUND(AVG(rating), 1) AS average
        FROM feedback
        """
    ).fetchone()
    return dict(summary)


def list_reviews(connection, limit=100):
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT f.id, f.restaurant_id, r.name AS merchant_name,
                   f.rating, f.comment, f.created_at
            FROM feedback AS f
            JOIN restaurants AS r ON r.id = f.restaurant_id
            ORDER BY f.id DESC LIMIT ?
            """,
            (max(1, min(int(limit), 200)),),
        )
    ]
````

<a id="source-08"></a>

## 8. .env.example

[打开原文件](../.env.example) · 13 行

SHA-256：`b7256026dd965196a04a2523b27176da3beb1695fd3b4d489434860287f94373`

````text
# Optional AI connection. Leave blank to use local recommendation mode.
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.5

# Optional settings
PORT=8000
# APP_DB=/absolute/path/to/nightfind.db
# OPENAI_BASE_URL=https://api.openai.com/v1/responses

# Optional China street map: TianDiTu browser key (restrict allowed domains).
TIANDITU_KEY=
# Optional Amap Web Service key: only used on the Python server for walking routes.
AMAP_WEB_KEY=
````

<a id="source-09"></a>

## 9. .gitattributes

[打开原文件](../.gitattributes) · 2 行

SHA-256：`2b5d157d4287b76be0a62f24eeb19e670abf3e17c21e6b73de8131271123e4d0`

````text
*.bat text eol=crlf
*.sh text eol=lf
````

<a id="source-10"></a>

## 10. .github/workflows/osm-collect.yml

[打开原文件](../.github/workflows/osm-collect.yml) · 35 行

SHA-256：`504dfe3f47cbb73f737a5fe1ea7242eef512d490a36773669af30a9549a3dbea`

````yaml
name: Collect Wuhan public restaurant snapshot

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  collect:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Collect at least 100 source locations
        run: python3 osm_sync.py fetch --minimum 100
      - name: Validate source coordinates and metadata
        run: |
          python3 - <<'PY'
          from osm_sync import LIVE_SNAPSHOT, read_snapshot
          rows, digest = read_snapshot(LIVE_SNAPSHOT)
          assert len(rows) >= 100
          assert len({row['external_id'] for row in rows}) == len(rows)
          assert all(row['latitude'] is not None and row['longitude'] is not None for row in rows)
          assert all(row['source_collected_at'] for row in rows)
          print('Validated', len(rows), 'online source records; operating status remains unverified.')
          PY
      - uses: actions/upload-artifact@v4
        with:
          name: wuhan-public-restaurant-snapshot
          path: data_sources/wuhan_live_catalog.json
          if-no-files-found: error
````

<a id="source-11"></a>

## 11. .github/workflows/tests.yml

[打开原文件](../.github/workflows/tests.yml) · 34 行

SHA-256：`bde91e0d3ad752e34a9a22f5a631b5dcb6fa8aa290ddff831fbd17e8ed93ae33`

````yaml
name: NightFind checks

on:
  push:
    branches:
      - "redesign/**"
      - "feature/**"
      - "fix/**"
  pull_request:
    branches:
      - main
      - "redesign/**"
      - "feature/**"
      - "fix/**"

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Check out source
        uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Compile Python modules
        run: python -m compileall -q *.py tests
      - name: Check browser JavaScript syntax
        run: |
          for file in static/*.js; do
            node --check "$file" || exit 1
          done
      - name: Run unit and HTTP tests
        run: python -m unittest discover -s tests -v
````

<a id="source-12"></a>

## 12. .gitignore

[打开原文件](../.gitignore) · 5 行

SHA-256：`567317f25dcd6c72bbf003582bb3e10b332f94600d9db1594080252186e2a047`

````text
.env
data/
__pycache__/
*.py[cod]
.DS_Store
````

<a id="source-13"></a>

## 13. README.md

[打开原文件](../README.md) · 204 行

SHA-256：`131ce0c7a504f001a2aca00d5432f6f7fa7295f8c368fe998f60e52b1b0e123a`

````markdown
# 夜寻 NightFind

以武汉为场景的餐饮决策原型：**描述需求 → 确认条件 → 筛选真实门店 → 比较最多三家 → 选定分店 → 打开导航**。

第一版专注这条功能链路，不引入前端框架、在线支付或自建预订系统。后端只使用 Python 标准库和 SQLite。

## 本版界面

最新配色、醒目动效和实际页面录屏见 [本版视觉说明](docs/VIVID_MOTION_REVIEW.md)。

检查、修改与学习代码请从 [完整代码阅读与修改指南](docs/CODE_GUIDE.md) 开始，配套 [全量源码汇编](docs/SOURCE_REFERENCE.md) 包含项目自有代码、测试和配置。

AI 首页布局的历史说明见 [AI 对话界面说明](docs/AI_CHAT_REVIEW.md)，前版柔和动效见 [装饰动效说明](docs/BOTANICAL_MOTION_REVIEW.md)，数据范围见 [资料审核说明](docs/UI_REVIEW.md)。

推荐成功提示与自动跳转见 [推荐页审核说明](docs/RECOMMENDATION_REVIEW.md)。

- AI 对话为首页主入口，聊天区占桌面主要宽度；输入框、推荐按钮和一键试问突出展示。右侧整理用餐笔记，手机优先显示聊天。
- 商家卡展示详细地址、营业资料、电话、招牌菜和来源单价；详情可查完整菜单、经纬度、图片及来源日期。
- 资料更完整的门店优先出现在目录，保留全部真实来源记录及分页、搜索、收藏、对比功能。
- 卡片的“在地图查看”会聚焦对应商家；无可靠坐标时按店名与地址交给外部地图查询。
- 使用翡翠绿与青柠强调色，深绿导航、暖白聊天卡片保持清楚的阅读层次，不引入前端构建依赖。
- 放大两侧枝叶摇摆与飘落叶片，加入金色光点、移动光环和背景流动光晕。页脚统一暂停并记住选择，跟随系统减少动态效果设置；窄屏收起边饰，保留可暂停的背景光晕。

## 启动

需要 Python 3.10+，无需安装应用依赖。查看成果时运行：

```sh
python3 run.py
```

服务就绪后会自动打开浏览器。Windows 可以双击 `启动网页.bat`，或执行 `py -3 run.py`。保留运行窗口，按 Ctrl+C 停止。

```sh
python3 run.py --port 8001    # 默认 8000 被占用时更换端口
python3 run.py --no-browser  # 云环境或只需要启动服务时使用
```

`run.py` 可从任意目录按完整路径运行；支持 `.env` 中的 `KEY=value` 配置、引号和注释，不执行 Shell 命令或变量展开。已设置的环境变量优先于 `.env`，`--port` 优先于 `PORT`。

原有命令行启动方式也可继续使用：

```sh
sh start.sh
```

在运行服务的电脑上打开 `http://localhost:8000`。按 Ctrl+C 停止。

```sh
PORT=8080 APP_DB=/absolute/path/night.db sh start.sh
```

默认数据库是 `data/night.db`。首次启动自动建表、导入仓库内资料；后续启动保留收藏等数据。修改资料或迁移旧库前请备份数据库。

## 使用流程

可以先说：

> 明天晚上七点，四个人在江汉路附近，总共三百元，想吃湖北菜。

完整用餐需求筛选出候选后，会弹出“推荐成功”提示，并自动打开“本轮推荐商家”页。该页仅展示这次推荐，支持菜单资料、收藏、对比、地图及选店导航；可以返回对话调整条件。保存编辑后的用餐条件并成功筛选时，也会自动打开推荐页。

需要追问、没有候选或请求失败时保留对话页；直接查店名、菜单等资料仍在对话中回答。刷新时会重新查询资料，有效推荐可恢复到推荐页。

系统将人数、预算金额及单位、位置、到店时间、口味和忌口分别保存。总预算按人数推算人均上限，并明确显示推算结果。规划用餐时，缺少关键条件会一次追问一项；未指定口味时保持不限。直接问店名、菜单、价格或附近商家时，首页先查真实资料库，不要求先填写人数与预算。

支持继续说：

- “改成两个人”“是人均预算”“明天同一时间”。
- “我们有一个人不吃辣”“没有忌口”。
- “便宜一点”“找近一点”“三公里以内”“不限口味”。
- “换一批”“第二家太贵，换一家”“保留第一家，换一批”。

“便宜一点”和“找近一点”调整排序，不擅自修改用户的预算或距离上限。也可在卡片上点击“下轮保留”。

候选、详情、收藏、对比及导航使用同一份真实门店资料和编号。正常启动不生成模拟商家；升级旧库时只删除明确识别出的 24 家旧模拟商户及其关联记录，删除前在数据库同目录的 `backups/` 保存完整备份，真实商家和真实收藏保留。旧演示表只保留空结构用于兼容，隔离测试可显式启用测试样本。`/api/chat` 与首页 `/api/decision` 都查询真实库，真实收藏位于 `real_favorites` 表。

右侧“用餐笔记”可直接修改人数、预算及单位、位置、时间、口味、忌口、距离和排序。位置支持原有商圈、武汉行政区、随底图提供的 OSM 地铁站，以及浏览器当前位置。修改后直接校验结构化条件并重新筛选，保留对话。收藏、对比和下轮保留使用局部更新，保持地图视野和滚动位置。

## 判断规则

- **已知不满足的硬条件会排除：**参考价格超过人均上限、已知坐标超过指定直线距离、来源营业时间不覆盖到店时间、已知菜系或招牌菜与忌口冲突。
- **未知事实不会被填补：**缺少价格、营业时间、距离、等位或食材信息时，候选列出“出发前需确认”，不宣称已满足全部条件。没有坐标且不在所选行政区的资料不作为附近候选。
- 菜系作为偏好；偏好不同的备选会明确标注。多人座位、过敏食材和实时等位必须向门店确认。
- 默认先考虑待确认项较少的门店，再按口味匹配、直线距离和参考价格排序。不生成虚构评分。修改顺序见 `dining_decision.py` 的 `evaluate_merchant`。
- 最多返回三家，不用模拟店或不满足硬条件的门店凑数。没有新的可选项时明确说明，不把已展示门店冒充“换一批”。
- 价格为来源参考值；只有明确标注为人均口径（`price_range_basis=per_person`）的区间才按上限筛选。单品价格区间或口径不明的区间不能用于人均预算计算。人数乘参考价得到的总额也不是消费保证。
- 营业时间只解析明确的每日时间段、简单 OSM 星期时间段和 `24/7`，支持跨午夜；其他写法保持未知。来源营业时间不能当作实时营业状态。
- 日期统一按北京时间处理。只说几点时默认今天，并在条件中注明；已过去的时间要求重新确认。本地解析支持今天、明天、后天和 `YYYY-MM-DD`；无法解析的日期需要补充。
- 本地位置解析支持江汉路、楚河汉街、光谷、粮道街及武汉 13 个行政区。商圈坐标只是近似中心。其他位置需使用用户主动提供的浏览器定位或进一步说明，系统不会猜坐标。

## 当前数据边界

随仓库附带 68 条网页来源门店资料，以及 2026-11-02 已归档的 834 条 OpenStreetMap 真实来源记录，均未冒充人工核验。按当前五年证据规则初始化后，公开目录为 902 条来源记录、887 个带来源坐标的点位；地图展示完整筛选结果，不受列表每页 30 条限制。首次载入不会联网重新采集。

OSM 归档的原始 JSON 不改写；`data_sources/osm_wuhan_snapshot.meta.json` 保存其 SHA-256、记录数、原始提交链接和归档日期。每次导入校验一致性。没有调查日期的记录仍保留空值，并在页面标为原资料归档。多数 OSM 记录缺少行政区或门牌，保持“待确认”，不按商圈猜填；已有 WGS84 坐标仍可在地图和距离查询中使用。

2026-11-06 实际读取公开分店页，更新 46 家分店资料。菜单现有 362 条记录，其中 **74 条有来源单品价格，覆盖 21 家门店（18 家有坐标）**；45 家网页门店有电话、40 家有营业时段。原有 55 家网页记录全部保留，增加 13 家真实来源记录。55 条图片关联记录共使用 6 个图片 URL，53 条为菜品参考图。页面显示作者、许可、拍摄日期和来源。

正常运行无需外部加载 Leaflet：地图组件随项目放在 `static/vendor/leaflet`，保留 BSD-2-Clause 许可。项目同时附带武汉 WGS84 地理底图：600 段主干道路、长江/汉江、19 个湖泊多边形，以及公园、水域和地铁站名称。在线街道瓦片可以访问时叠加详细街道图；不可访问时自动保留本地地理简图，不会退化为白底圆点。来源、许可、精度和更新方法见 [底图说明](static/map/README.md)。

没有可靠电话就不提供拨号按钮；有坐标时导航使用该坐标，无坐标时按店名和地址查找，用户需要核对具体分店。来源链接不代表已经订座。

### 主动重新采集

```sh
python3 osm_sync.py fetch --minimum 100
```

此命令访问公开 Overpass 服务，获取带真实源 ID、坐标、元素更新日期的武汉餐饮点。少于 100 条、网络失败或响应无效时不会覆盖已有数据。成功后写入 `data_sources/wuhan_live_catalog.json`，包含原始记录、采集日期和 SHA-256；下次启动自动导入。元素编辑日期、在线采集日期和调查日期分开保留，未明确来源的价格不会从模拟店、其他分店或品牌通用菜单复制。

实时采集需要网络允许 `overpass-api.de` / `overpass.kumi.systems`；菜单补充来源包括武汉市商务局、商家官方网页及已有资料引用的门店页面。网络策略、目标网站拒绝或缺少可核验菜单时，应报告实际数据覆盖，不能把历史归档称为本次新采集。

也可手动运行 GitHub Actions 的 **Collect Wuhan public restaurant snapshot**，结果作为下载产物保存，不会自动提交或推送到旧分支。

商户、菜单和图片 CSV 位于 `data/`，仍可按来源证据补充，应用通过文件 SHA 检测变更。OSM 数据须保留 **© OpenStreetMap contributors · ODbL** 署名，参见 [数据来源说明](data_sources/README.md)。

```sh
python3 import_wuhan_catalog.py
# 仅在需要补充坐标且网络可用时执行，按约每秒一条请求公开服务：
python3 import_wuhan_catalog.py --geocode
```

CSV 更新不会自动清除数据库中的补录坐标、电话或营业资料，也不会自动删除被移出 CSV 的记录。正常运行不需要人工审核操作。图片按实际来源区分门店实拍与菜品参考图；图片不可访问时保留绿色插画封面。

## 继续补充公开分店资料

```sh
python3 refresh_wuhan_catalog.py --apply --discover --limit 50
```

先检查已有携程分店，`--discover` 允许从公开同城推荐中追加分店，整次最多请求 50 个页面；不带 `--apply` 时只检查。校验武汉、来源商家 ID 与分店名，只读取页面已公开的地址、电话、周营业时段、人均与明确单品价。GCJ-02 来源坐标转换成 WGS84。无价格不猜填、未知行政区不按商圈补造；失败保留已有资料。采集是手动运行的更新命令，页面访问和启动不会自动爬取。

本次事实摘要与原页面 SHA-256 保存在 `data_sources/wuhan_web_refresh.json`。这次 50 个页面中 46 个通过解析，其余页面未更新。自动读取日期不代表实地核验或实时营业。

## 可选街道地图与步行路线

在项目根目录的 `.env` 中填写：

```dotenv
TIANDITU_KEY=你的天地图浏览器地图密钥
AMAP_WEB_KEY=你的高德Web服务密钥
```

- `TIANDITU_KEY`：来自天地图控制台的浏览器地图 Key，按服务商要求限制使用域名。浏览器先加载天地图道路与注记，失败时尝试 OSM，最后保留本地武汉简图。使用天地图 CGCS2000 Web Mercator，商家继续保存 WGS84 坐标。
- `AMAP_WEB_KEY`：来自高德控制台的 **Web 服务** Key，只在 Python 后端使用；不是 JS SDK Key，不会通过页面配置接口返回。选定有坐标的店、设置出发位置后点击“查询步行路线”，返回服务提供的距离、用时和指引，在地图画路线。源坐标转换为 GCJ-02 请求高德，响应再转换回 WGS84。
- 未配置路线服务时提供带出发点和目的地的高德导航链接；不会按直线距离编造步行时间。路线请求仅在点击查询后发起，相同路线缓存约 10 分钟。

保存配置后重新运行 `python3 run.py`。需要本机网络能访问相应地图服务；密钥和配额由你自己的地图账户管理。默认配置可以直接启动，仍支持地图、真实商家查询及高德外部导航。

## 可选 AI 条件提取

不配置密钥时，本地解析和完整决策流程均可运行。可复制 `.env.example` 为 `.env`，在本机填写 `OPENAI_API_KEY`、有权调用的 `OPENAI_MODEL`，然后重启。不要把密钥提交到仓库。

可通过 `OPENAI_BASE_URL` 指定兼容 Responses API 的完整 HTTPS 端点。配置后，服务端将本轮需求和当前北京时间发送给模型，仅提取条件；门店事实、筛选和候选解释仍由本地资料与规则生成。请求失败或返回无效数据时回退本地解析。界面显示本轮实际使用的模式。

## 代码结构与修改入口

| 文件                       | 职责                                     | 常见修改                           |
| -------------------------- | ---------------------------------------- | ---------------------------------- |
| `app.py`                   | HTTP 路由、请求校验、静态文件            | 新增 API                           |
| `decision_preferences.py`  | 本地/AI 条件提取、上下文校验、追问       | 表达识别、位置别名、日期与预算单位 |
| `dining_decision.py`       | 真实门店筛选、排序、解释、营业判断、导航 | 筛选规则、候选数量、导航供应商     |
| `decision_catalog.py`      | 真实门店读取与收藏持久化                 | 数据查询、会话隔离                 |
| `real_catalog.py`          | 来源、导入、时效及菜单/图片证据          | 数据字段、资料更新规则             |
| `database.py`              | SQLite 连接和增量建表                    | 新增数据表                         |
| `static/app.js`            | 页面状态、交互与 API 调用                | 新增操作、会话行为                 |
| `static/decision-view.js`  | 纯 HTML 渲染，不发请求                   | 卡片、条件、详情、对比的显示内容   |
| `static/session-store.js`  | 浏览器对话与草稿的 24 小时保存           | 保存范围、恢复行为                 |
| `map_services.py`          | 地图配置、后端步行路线和缓存             | 地图服务参数与错误回退             |
| `geo_coordinates.py`       | WGS84 / GCJ-02 明确转换                  | 坐标转换                           |
| `refresh_wuhan_catalog.py` | 公开分店页采集与证据导出                 | 补充、更新来源资料                 |
| `static/api-client.js`     | 匿名访客 ID 与请求封装                   | 通信逻辑                           |
| `static/style.css`         | 浅绿色主题、字体、页头和两侧植物纹样     | 全站颜色和公共元素                 |
| `static/decision.css`      | AI 聊天区、资料卡、弹窗、移动端布局      | 组件样式                           |
| `static/wuhan_map.js`      | 本地底图、在线街道回退、坐标定位与弹窗   | 地图样式和点位交互                 |
| `static/map/`              | 武汉地理数据、原始来源与许可             | 底图范围和数据更新                 |

最近 30 条对话、草稿和用餐条件在本机浏览器保留 24 小时；刷新后按保存的条件重新查询数据库，不把缓存的旧价格直接当作当前事实。当前选择和对比只保存门店 ID，恢复时重新读取有效资料。“重新聊”清除这段对话。收藏存入 SQLite，并按浏览器匿名访客 ID 隔离。清理浏览器存储会丢失该 ID；当前没有跨设备账号同步。

## 新流程 API

| 方法       | 路径                        | 说明                                                                                                                                                                |
| ---------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| POST       | `/api/decision`             | `message` + 可选 `context`、`location`、`previous_ids`、`seen_ids`、`keep_ids`；直接编辑可传 `preferences` 与 `intent=plan`；返回条件、追问、最多三家候选和排除原因 |
| GET        | `/api/map-config`           | 浏览器街道地图配置，不包含高德后端密钥                                                                                                                              |
| POST       | `/api/walking-route`        | `merchant_id` + `origin`；真实步行路线或外部导航入口                                                                                                                |
| GET        | `/api/real-merchants`       | 公开真实目录，支持 `keyword`、`district`、`limit`、`offset`                                                                                                         |
| GET        | `/api/real-merchants/{id}`  | 同一门店的来源、菜单、图片、导航和已知电话                                                                                                                          |
| GET        | `/api/real-compare?ids=1,2` | 对比 2–3 家真实门店                                                                                                                                                 |
| GET / POST | `/api/real-favorites`       | 读取收藏；写入 `{merchant_id, active}`                                                                                                                              |

决策和收藏请求使用 `X-Session` 请求头。匿名 ID 用于收藏隔离，不是账号认证。`context` 只接受已定义的条件字段；每轮重新校验，不接受前端提供的商家事实。

## 验证

```sh
python3 -m unittest discover -s tests -v
node tests/session_store.test.mjs
python3 -m compileall -q *.py tests
for file in static/*.js; do node --check "$file" || exit 1; done
```

`tests/test_real_catalog_workflow.py` 覆盖五年证据、归档校验、停止模拟数据、迁移备份、地图全量点位、真实菜单查询和采集失败保护。`tests/test_decision.py` 覆盖预算单位、多轮修正、过敏人员描述、日期与跨午夜营业、真实数据与演示数据隔离、硬条件、未知项、换一批、收藏、分页、时效及完整 HTTP 链路。AI 测试使用模拟响应，不需要密钥。地图组件或外部图片不可用时，列表、对比和导航入口仍可使用。
````

<a id="source-14"></a>

## 14. catalog_language.py

[打开原文件](../catalog_language.py) · 51 行

SHA-256：`87c3c1ca753d7ce487830f8c18023607bbf00ed229a5d61593f24bf876df6fe7`

````python
"""Small, editable translations of OSM cuisine tags and common search aliases."""

CUISINE_TERMS = {
    "清淡": ("粥", "面", "清淡", "noodle"),
    "面食": ("面", "粉", "noodle"),
    "湖北菜": ("湖北", "鄂菜", "武汉菜", "hubei"),
    "素食": ("素食", "素菜", "vegetarian"),
    "咖啡": ("咖啡", "coffee", "cafe"),
    "奶茶": ("奶茶", "bubble_tea"),
    "汉堡": ("汉堡", "burger"),
    "披萨": ("披萨", "pizza"),
    "日料": ("日料", "日式", "japanese", "sushi"),
    "烧烤": ("烧烤", "barbecue", "bbq"),
    "中餐": ("中餐", "chinese"),
    "快餐": ("快餐", "fast_food", "burger", "chicken"),
}
BRAND_ALIASES = {
    "肯德基": ("肯德基", "KFC"),
    "麦当劳": ("麦当劳", "McDonald's", "McDonalds"),
    "星巴克": ("星巴克", "Starbucks"),
}
DISPLAY_LABELS = {
    "chinese": "中餐",
    "coffee_shop": "咖啡简餐",
    "coffee": "咖啡",
    "bubble_tea": "奶茶",
    "burger": "汉堡",
    "chicken": "鸡肉快餐",
    "pizza": "披萨",
    "japanese": "日料",
    "sushi": "寿司",
    "barbecue": "烧烤",
    "noodle": "面食",
    "noodles": "面食",
}


def search_terms(keyword):
    terms = [keyword]
    if keyword in CUISINE_TERMS:
        terms.extend(CUISINE_TERMS[keyword])
    for aliases in BRAND_ALIASES.values():
        if keyword.casefold() in {value.casefold() for value in aliases}:
            terms.extend(aliases)
    return list(dict.fromkeys(terms))[:12]


def display_cuisine(raw):
    return "、".join(
        DISPLAY_LABELS.get(part, part) for part in raw.replace(";", "、").split("、")
    )
````

<a id="source-15"></a>

## 15. catalog_policy.py

[打开原文件](../catalog_policy.py) · 34 行

SHA-256：`9200e749f445f2d6fbabbab59388b77af607452cdcb52cd7859a6d3499e9ea15`

````python
"""Dates describe different evidence: online collection is not a field survey."""

from datetime import date

CATALOG_YEARS = 5
PHOTO_YEARS = 2


def cutoff_date(years, reference=None):
    today = reference or date.today()
    try:
        return today.replace(year=today.year - years).isoformat()
    except ValueError:
        return today.replace(year=today.year - years, day=28).isoformat()


def catalog_cutoff(reference=None):
    return cutoff_date(CATALOG_YEARS, reference)


def photo_cutoff(reference=None):
    return cutoff_date(PHOTO_YEARS, reference)


def clean_date(raw, label):
    if not raw:
        return ""
    try:
        value = date.fromisoformat(str(raw))
    except ValueError as error:
        raise ValueError(label + " 必须为 YYYY-MM-DD") from error
    if value > date.today():
        raise ValueError(label + " 不能晚于今天")
    return value.isoformat()
````

<a id="source-16"></a>

## 16. comparison.py

[打开原文件](../comparison.py) · 80 行

SHA-256：`8006403f4c2071c3333c83925104244d8549ffc98ae52fa8827311881623f22d`

````python
"""Explainable side-by-side comparison of two or three demo merchants."""
import re

from database import get_merchant


def parse_merchant_ids(raw):
    """Accept only 2–3 unique positive decimal IDs, preserving selected order."""
    if not isinstance(raw, str) or not re.fullmatch(
        r"[1-9]\d*(?:,[1-9]\d*){1,2}", raw.strip()
    ):
        raise ValueError("请选择 2–3 家不同的商户进行对比")
    identifiers = [int(part) for part in raw.strip().split(",")]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("不能重复选择同一家商户")
    return identifiers


def compare_merchants(connection, raw_ids, scene=""):
    """Explain the trade-offs using known attributes, not imaginary reviews."""
    merchant_ids = parse_merchant_ids(raw_ids)
    items = [get_merchant(connection, merchant_id) for merchant_id in merchant_ids]
    if any(item is None for item in items):
        raise ValueError("所选商户已不存在，请重新选择")

    cheapest_price = min(item["price"] for item in items)
    shortest_wait = min(item["wait"] for item in items)
    top_rating = max(item["rating"] for item in items)

    for item in items:
        # Relative comparison only. All base scores/prices/waits are sample data.
        price_score = 40 * cheapest_price / max(item["price"], 1)
        wait_score = 35 * (shortest_wait + 10) / (item["wait"] + 10)
        rating_score = 15 * item["rating"] / 5
        scene_score = 10 if scene and scene in item["tags"] else 0
        item["comparison_score"] = round(
            price_score + wait_score + rating_score + scene_score, 1
        )
        item["highlights"] = []
        if item["price"] == cheapest_price:
            item["highlights"].append("人均较省")
        if item["wait"] == shortest_wait:
            item["highlights"].append("等位较短")
        if item["rating"] == top_rating:
            item["highlights"].append("演示评分较高")
        if scene and scene in item["tags"]:
            item["highlights"].append("符合就餐场景")

    recommended = max(items, key=lambda item: item["comparison_score"])
    price_gap = max(item["price"] for item in items) - cheapest_price
    wait_gap = max(item["wait"] for item in items) - shortest_wait
    reasons = [
        "人均价格最多相差 {} 元".format(price_gap),
        "预计等位时间最多相差 {} 分钟".format(wait_gap),
    ]
    if scene:
        reasons.append("已考虑「{}」的标签匹配".format(scene))

    return {
        "items": items,
        "summary": {
            "recommended_id": recommended["id"],
            "recommended_name": recommended["name"],
            "reason": "综合价格、等待和演示评分，{}的平衡性更好。"
            "也可以根据最看重的指标作自己的选择。".format(
                recommended["name"]
            ),
            "details": reasons,
            "cheapest_ids": [
                item["id"] for item in items if item["price"] == cheapest_price
            ],
            "fastest_ids": [
                item["id"] for item in items if item["wait"] == shortest_wait
            ],
            "sample_notice": (
                "以上价格、营业时间、等位与基础评分均为研究演示数据。"
                "排序是透明规则比较，不代表真实商户体验或实时情况。"
            ),
        },
    }
````

<a id="source-17"></a>

## 17. conversation.py

[打开原文件](../conversation.py) · 116 行

SHA-256：`6429726e030d7f66a1d833fcfdbe5d532950e2d623bf84c89636b83ce2ee8bb4`

````python
"""Conversation refinement and contextual follow-up suggestions.

These are lightweight, transparent conversation helpers. The restaurant facts and
ranking still come from the database/recommendation service, not an LLM.
"""
import re

FIELDS = ("district", "budget", "wait", "hour", "scene", "cuisine")


def refine_preferences(message, prior_context, preferences, districts):
    """Remember explicit choices across turns and apply short change requests.

    The returned \`known\` flags distinguish user-supplied preferences from defaults.
    Never assume that a default district/budget was explicitly chosen.
    """
    prior = prior_context if isinstance(prior_context, dict) else {}
    known = {
        field for field in prior.get("known", [])
        if isinstance(field, str) and field in FIELDS
    } if isinstance(prior.get("known"), list) else set()

    if any(item["name"] in message for item in districts):
        known.add("district")
    if re.search(r"(?:人均|预算|每人|每位|¥|￥)\s*(?:在|为|约)?\s*\d{1,3}", message) or re.search(r"\d{1,3}\s*(?:元|块)", message):
        known.add("budget")
    if re.search(r"(?:等位|排队|等待|不想等|不排队|少等|分钟)", message):
        known.add("wait")
    if re.search(r"\d{1,2}\s*(?:[:：]\d{2}|点)", message) or re.search(
        r"[零一二两三四五六七八九十]{1,3}点", message
    ):
        known.add("hour")
    if any(word in message for word in ("一个人", "独自", "单人", "自己吃", "朋友", "聚会", "同事", "多人", "夜宵", "出游", "逛街")):
        known.add("scene")
    if any(word in message for word in ("小龙虾", "烧烤", "烤肉", "烤串", "清淡", "粥", "粉面", "家常菜", "湖北菜", "武汉特色")):
        known.add("cuisine")

    if any(word in message for word in ("便宜一点", "再便宜点", "省一点", "降低预算")):
        preferences["budget"] = max(10, preferences["budget"] - 20)
        known.add("budget")
    if any(word in message for word in ("少等一会", "等位短一点", "不想久等")):
        preferences["wait"] = max(0, preferences["wait"] - 10)
        known.add("wait")
    if any(word in message for word in ("放宽预算", "预算高一点", "贵一点也行")):
        preferences["budget"] = min(500, preferences["budget"] + 20)
        known.add("budget")
    if "不限制口味" in message or "不限口味" in message:
        preferences["cuisine"] = "不限"
        known.add("cuisine")

    return preferences, sorted(known)


def follow_up_suggestions(preferences, known, districts, items):
    """Ask for a useful missing preference, then offer concrete adjustments."""
    if "district" not in known:
        return {
            "question": "你现在更方便去哪个商圈？选一个就行。",
            "actions": [
                {"label": district["name"], "message": district["name"]}
                for district in districts[:4]
            ],
        }
    if "budget" not in known:
        return {
            "question": "人均大概想花多少？我可以再帮你缩小范围。",
            "actions": [
                {"label": "50 元以内", "message": "人均 50 元以内"},
                {"label": "80 元以内", "message": "人均 80 元以内"},
                {"label": "120 元以内", "message": "人均 120 元以内"},
            ],
        }
    if "cuisine" not in known:
        return {
            "question": "口味上有没有特别想吃的？也可以先不限制。",
            "actions": [
                {"label": "想吃烧烤", "message": "想吃烧烤"},
                {"label": "清淡一点", "message": "想吃清淡一点"},
                {"label": "不限口味", "message": "不限口味"},
            ],
        }

    if not items:
        return {
            "question": "这些条件有点紧，要不要换个方向再看看？",
            "actions": [
                {"label": "预算高一点", "message": "放宽预算"},
                {"label": "多等一会儿", "message": "等位最多 40 分钟"},
                {"label": "不限口味", "message": "不限口味"},
            ],
        }
    return {
        "question": "还想怎么调整？我可以接着帮你挑。",
        "actions": [
            {"label": "便宜一点", "message": "便宜一点"},
            {"label": "少等一会", "message": "少等一会"},
            {"label": "换一批", "message": "换一批"},
        ],
    }


def choose_candidate_round(items, message, already_seen):
    """Rotate among eligible merchants only when the visitor requests another batch."""
    if not any(phrase in message for phrase in ("换一批", "再换几家", "看看别的")):
        return items, False
    previous_ids = set()
    if isinstance(already_seen, list):
        for value in already_seen[:80]:
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if number > 0:
                previous_ids.add(number)
    fresh = [merchant for merchant in items if merchant["id"] not in previous_ids]
    return (fresh if fresh else items), not bool(fresh)
````

<a id="source-18"></a>

## 18. geo_coordinates.py

[打开原文件](../geo_coordinates.py) · 43 行

SHA-256：`7a6212a1e73cf3e89fb0eee68428fae2dab65d9bca501d851bef1b1db3a8f907`

````python
"""WGS84 ↔ GCJ-02 conversion for explicitly labelled mainland map coordinates."""

import math


def wgs84_to_gcj02(latitude, longitude):
    if not (72.004 <= longitude <= 137.8347 and 0.8293 <= latitude <= 55.8271):
        return latitude, longitude
    x, y = longitude - 105, latitude - 35
    dlat = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    dlng = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    wave = (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
    dlat += wave + (20 * math.sin(y * math.pi) + 40 * math.sin(y * math.pi / 3)) * 2 / 3
    dlat += (
        (160 * math.sin(y * math.pi / 12) + 320 * math.sin(y * math.pi / 30)) * 2 / 3
    )
    dlng += wave + (20 * math.sin(x * math.pi) + 40 * math.sin(x * math.pi / 3)) * 2 / 3
    dlng += (
        (150 * math.sin(x * math.pi / 12) + 300 * math.sin(x * math.pi / 30)) * 2 / 3
    )
    radians = latitude / 180 * math.pi
    magic = 1 - 0.00669342162296594323 * math.sin(radians) ** 2
    dlat = (
        dlat
        * 180
        / (
            (6378245 * (1 - 0.00669342162296594323))
            / (magic * math.sqrt(magic))
            * math.pi
        )
    )
    dlng = dlng * 180 / (6378245 / math.sqrt(magic) * math.cos(radians) * math.pi)
    return latitude + dlat, longitude + dlng


def gcj02_to_wgs84(latitude, longitude):
    """Invert by iteration; do not apply this to an already-WGS84 OSM point."""
    lat, lng = latitude, longitude
    for _ in range(5):
        projected_lat, projected_lng = wgs84_to_gcj02(lat, lng)
        lat -= projected_lat - latitude
        lng -= projected_lng - longitude
    return round(lat, 7), round(lng, 7)
````

<a id="source-19"></a>

## 19. geofabrik_sync.py

[打开原文件](../geofabrik_sync.py) · 135 行

SHA-256：`c0d82167d56ec27d9315e72ebeb6678fd1026b25189e9876eb0399ca50f02ea9`

````python
"""Download Wuhan OSM restaurants from the provincial Geofabrik PBF extract.

This is a fallback when public Overpass servers are busy. The data file is
OpenStreetMap ODbL. Use only within the Wuhan administrative polygon (OSM
relation 3076268), not a guessed rectangular bounding box.

Requires osmium and shapely only during OFFLINE collection, not for site use.
"""
import argparse
import json
import tempfile
import urllib.request
from pathlib import Path

from osm_sync import (
    MAX_RECORDS, SNAPSHOT, convert_osm_element,
)

PBF_URL = "https://download.geofabrik.de/asia/china/hubei-latest.osm.pbf"
WUHAN_BOUNDARY_URL = (
    "https://raw.githubusercontent.com/whuyao/GeoClaw_Claude/main/"
    "data/wuhan/boundary.geojson"
)


def collect_from_extract(pbf_path, boundary_json):
    """Filter mapped food venues by true Wuhan polygon, using OSM node/way IDs."""
    import osmium
    from shapely.geometry import Point, shape

    features = boundary_json.get("features", [])
    if len(features) != 1:
        raise ValueError("武汉市行政边界必须恰好包含一个要素")
    properties = features[0].get("properties") or {}
    if properties.get("osm_id") != 3076268:
        raise ValueError("武汉行政区边界来源 ID 不匹配")
    polygon = shape(features[0]["geometry"])
    if not polygon.is_valid:
        raise ValueError("武汉市行政边界无效")

    class WuhanFoodHandler(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.records = {}

        def add(self, type_name, osm_id, tags, lat, lon):
            if (
                tags.get("amenity") not in
                ("restaurant", "fast_food", "cafe", "food_court")
                or not tags.get("name")
                or not polygon.covers(Point(lon, lat))
            ):
                return
            record = convert_osm_element({
                "type": type_name,
                "id": osm_id,
                "lat": lat,
                "lon": lon,
                "tags": tags,
            })
            if record:
                self.records[record["external_id"]] = record

        def node(self, node):
            if not node.location.valid():
                return
            tags = {tag.k: tag.v for tag in node.tags}
            self.add("node", node.id, tags, node.location.lat, node.location.lon)

        def way(self, way):
            tags = {tag.k: tag.v for tag in way.tags}
            if tags.get("amenity") not in (
                "restaurant", "fast_food", "cafe", "food_court"
            ) or not tags.get("name"):
                return
            coords = []
            for nd in way.nodes:
                if nd.location.valid():
                    coords.append((nd.location.lat, nd.location.lon))
            if coords:
                # This is an average of tagged way nodes, not a precise entrance.
                lat = sum(pair[0] for pair in coords) / len(coords)
                lon = sum(pair[1] for pair in coords) / len(coords)
                self.add("way", way.id, tags, lat, lon)

    handler = WuhanFoodHandler()
    handler.apply_file(str(pbf_path), locations=True)
    records = [
        handler.records[key] for key in sorted(handler.records)
    ][:MAX_RECORDS]
    if not records:
        raise ValueError("省级数据提取后未得到武汉餐饮场所，不导入空快照")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=SNAPSHOT)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        pbf_path = Path(tmp) / "hubei.osm.pbf"
        request = urllib.request.Request(
            PBF_URL, headers={"User-Agent": "NightFindOSMImporter/1.0"}
        )
        with urllib.request.urlopen(request, timeout=150) as response:
            with pbf_path.open("wb") as destination:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    destination.write(chunk)
                    if destination.tell() > 150 * 1024 * 1024:
                        raise ValueError("Hubei extract exceeded 150 MB")
        with urllib.request.urlopen(WUHAN_BOUNDARY_URL, timeout=45) as resp:
            boundary_json = json.loads(resp.read(5_000_000).decode("utf-8"))
        records = collect_from_extract(pbf_path, boundary_json)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "已从 Geofabrik 湖北 OSM 提取中按武汉行政区边界得到 {} 条餐饮场所。".format(
            len(records)
        ), flush=True,
    )
    print(
        "© OpenStreetMap contributors · ODbL。"
        "社区数据未经人工核实，不应宣称价格、评分或实时营业。",
        flush=True,
    )


if __name__ == "__main__":
    main()
````

<a id="source-20"></a>

## 20. import_merchants.py

[打开原文件](../import_merchants.py) · 36 行

SHA-256：`7d6f1fb1f0b47aa81f03efe80ce0203b57a9ab9f641868fb68db3b3a7a21c383`

````python
"""Offline authorized merchant-data import tool.

Examples:
    python3 import_merchants.py data/authorized_merchants.csv --dry-run
    python3 import_merchants.py data/authorized_merchants.csv

Only import information you are licensed or otherwise permitted to use.
"""
import argparse
import json
import sys

from database import connect, initialize_database
from real_catalog import import_real_merchants, read_import_file


def main():
    parser = argparse.ArgumentParser(description="导入武汉真实餐厅资料（CSV/JSON）")
    parser.add_argument("path", help="已获得使用权的 CSV/JSON 数据文件")
    parser.add_argument("--dry-run", action="store_true", help="只校验，不写入")
    args = parser.parse_args()
    try:
        records = read_import_file(args.path)
        initialize_database()
        with connect() as connection:
            result = import_real_merchants(connection, records, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("提示：只有 status=verified 且具有核验日期/方式的记录会公开。")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print("导入失败：" + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
````

<a id="source-21"></a>

## 21. import_wuhan_catalog.py

[打开原文件](../import_wuhan_catalog.py) · 183 行

SHA-256：`b2a8e743b5610efc0502b3dc011bbb3f7b597c5f158ec551eb213428bf858d8d`

````python
"""Import the bundled Wuhan restaurant data and optionally add map coordinates.

Normal app startup imports the three checked-in CSV files automatically.
Run this file with --geocode once to fill coordinates for addresses that can
be matched confidently by OpenStreetMap Nominatim.
"""
import argparse
import json
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from database import connect, initialize_database
from real_catalog import seed_bundled_catalog

WUHAN_VIEWBOX = "113.65,31.05,114.85,30.15"
USER_AGENT = "NightFind-WuhanCatalog/1.0 (+https://github.com/2472099715liangren-ship-it/nightfood-ai)"


def _address_is_specific(address):
    vague_words = ("商圈", "附近", "待复核", "未披露", "待确认", "景区内")
    if any(word in address for word in vague_words):
        return False
    return bool(re.search(r"\d|天街|万达|中心|大厦|广场|商业街", address))


def _geocode_one(query):
    params = urlencode({
        "q": query,
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 1,
        "countrycodes": "cn",
        "viewbox": WUHAN_VIEWBOX,
        "bounded": 1,
    })
    request = Request(
        "https://nominatim.openstreetmap.org/search?" + params,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"},
    )
    with urlopen(request, timeout=20) as response:
        results = json.loads(response.read().decode("utf-8"))
    return results[0] if results else None


def geocode_missing(connection, limit=60):
    """Geocode specific street addresses only; vague locations remain unpinned."""
    rows = connection.execute(
        """
        SELECT id,name,district,address FROM real_merchants
        WHERE latitude IS NULL OR longitude IS NULL
        ORDER BY id LIMIT ?
        """,
        (max(1, min(int(limit), 100)),),
    ).fetchall()
    updated = 0
    skipped = 0
    for row in rows:
        address = row["address"]
        if not _address_is_specific(address):
            skipped += 1
            continue

        query = "{},{},{},武汉市,湖北省,中国".format(
            row["name"], address, row["district"]
        )
        cached = connection.execute(
            "SELECT latitude,longitude,display_name FROM real_merchant_geocode_cache WHERE query=?",
            (query,),
        ).fetchone()
        if cached:
            result = (
                {"lat": cached["latitude"], "lon": cached["longitude"],
                 "display_name": cached["display_name"]}
                if cached["latitude"] is not None and cached["longitude"] is not None
                else None
            )
        else:
            try:
                result = _geocode_one(query)
            except Exception as error:
                print("地理编码暂时失败：{} ({})".format(row["name"], error))
                result = None
            if result:
                latitude = float(result["lat"])
                longitude = float(result["lon"])
                display_name = result.get("display_name", "")
                # Keep only results inside the Wuhan city search box.
                if not (30.15 <= latitude <= 31.05 and 113.65 <= longitude <= 114.85):
                    result = None
                else:
                    result = {
                        "lat": latitude,
                        "lon": longitude,
                        "display_name": display_name,
                    }
            connection.execute(
                """
                INSERT INTO real_merchant_geocode_cache(
                    query,latitude,longitude,display_name,checked_at
                ) VALUES (?,?,?,?,DATE('now'))
                ON CONFLICT(query) DO UPDATE SET
                    latitude=excluded.latitude,longitude=excluded.longitude,
                    display_name=excluded.display_name,checked_at=excluded.checked_at
                """,
                (
                    query,
                    result["lat"] if result else None,
                    result["lon"] if result else None,
                    result["display_name"] if result else "",
                ),
            )
            connection.commit()
            time.sleep(1.1)

        if not result:
            skipped += 1
            continue

        display_name = result["display_name"]
        street_tokens = re.findall(
            r"[\u4e00-\u9fffA-Za-z0-9]+(?:路|街|大道|巷|天街|广场|中心|大厦)",
            address,
        )
        if street_tokens and not any(token in display_name for token in street_tokens):
            skipped += 1
            continue

        note = "WGS84坐标由OpenStreetMap Nominatim按门店地址匹配；地图点位仍建议人工复核。"
        connection.execute(
            "UPDATE real_merchants SET latitude=?,longitude=?,"
            "location_note=CASE WHEN location_note='' THEN ? "
            "ELSE location_note || '；' || ? END WHERE id=?",
            (result["lat"], result["lon"], note, note, row["id"]),
        )
        connection.commit()
        updated += 1
        print("已定位：{} → {}".format(row["name"], display_name))
    return {"geocoded": updated, "skipped": skipped, "checked": len(rows)}


def main():
    parser = argparse.ArgumentParser(description="导入武汉真实餐厅目录")
    parser.add_argument(
        "--geocode", action="store_true",
        help="使用 OpenStreetMap Nominatim 为具体地址补充 WGS84 坐标（约每秒一条）",
    )
    parser.add_argument(
        "--geocode-limit", type=int, default=60,
        help="本次最多尝试定位多少家门店，默认 60",
    )
    args = parser.parse_args()

    initialize_database()
    with connect() as connection:
        imported = seed_bundled_catalog(connection)
        summary = {
            "公开商家数": connection.execute(
                "SELECT COUNT(*) FROM real_merchants WHERE status='pending' "
                "AND external_id LIKE 'web:%' AND source_checked_at >= date('now','-2 years')"
            ).fetchone()[0],
            "图片数": connection.execute(
                "SELECT COUNT(*) FROM real_merchant_images"
            ).fetchone()[0],
            "菜品记录数": connection.execute(
                "SELECT COUNT(*) FROM real_merchant_menu_items"
            ).fetchone()[0],
            "有坐标门店数": connection.execute(
                "SELECT COUNT(*) FROM real_merchants WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
            ).fetchone()[0],
            "本次导入": imported,
        }
        if args.geocode:
            summary["地图定位"] = geocode_missing(connection, args.geocode_limit)
            summary["有坐标门店数"] = connection.execute(
                "SELECT COUNT(*) FROM real_merchants WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
            ).fetchone()[0]
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
````

<a id="source-22"></a>

## 22. manage_osm_photos.py

[打开原文件](../manage_osm_photos.py) · 58 行

SHA-256：`638c0b6c47dae1454bc85af2211abc7cdf1a84cbd30123b555d6b3a3b93a9602`

````python
"""Operator-only photo import and approval for the Wuhan OSM catalog."""
import argparse
from database import connect, initialize_database
from merchant_photos import add_photo, approve_photo


def main():
    parser = argparse.ArgumentParser(description="导入或审核近两年授权店面照片")
    actions = parser.add_subparsers(dest="command", required=True)
    add = actions.add_parser("add")
    add.add_argument("--merchant-id", type=int, required=True)
    add.add_argument("--file", required=True)
    add.add_argument("--taken-at", required=True, help="照片真实拍摄日 YYYY-MM-DD")
    add.add_argument("--source-url", required=True)
    add.add_argument("--copyright-holder", required=True)
    add.add_argument("--license-note", required=True)
    add.add_argument("--operator", required=True)
    add.add_argument("--rights-confirmed", action="store_true")
    for command in ("approve", "reject"):
        cmd = actions.add_parser(command)
        cmd.add_argument("--photo-id", type=int, required=True)
        cmd.add_argument("--reviewed-by", required=True)
    actions.add_parser("list")
    options = parser.parse_args()
    initialize_database()
    with connect() as db:
        if options.command == "add":
            photo_id = add_photo(
                db, options.merchant_id, options.file, options.taken_at,
                options.source_url, options.copyright_holder,
                options.license_note, options.operator, options.rights_confirmed,
            )
            db.commit()
            print("图片 #{} 已保存在待审核区，尚未公开。".format(photo_id))
        elif options.command in ("approve", "reject"):
            approve_photo(
                db, options.photo_id, options.reviewed_by,
                "verified" if options.command == "approve" else "rejected",
            )
            db.commit()
            print("图片 #{} 审核状态已更新。".format(options.photo_id))
        else:
            records = db.execute(
                "SELECT p.id,r.name,p.taken_at,p.copyright_holder,p.source_url "
                "FROM real_merchant_photos AS p JOIN real_merchants AS r "
                "ON r.id=p.merchant_id WHERE p.status='pending' ORDER BY p.id"
            ).fetchall()
            if not records:
                print("目前没有待审核照片。")
            for row in records:
                print("#{} {} | 拍摄于 {} | 权利人 {} | 来源 {}".format(
                    row["id"], row["name"], row["taken_at"],
                    row["copyright_holder"], row["source_url"],
                ))


if __name__ == "__main__":
    main()
````

<a id="source-23"></a>

## 23. map_services.py

[打开原文件](../map_services.py) · 147 行

SHA-256：`ffa3f7cec69e8cd71e50af8554e8315eb8618c35ee7088b523841de0930e217a`

````python
"""Optional map configuration and real walking routes. Web-service keys stay server-side."""

import json
import math
import os
import re
import time
from functools import lru_cache
from urllib.parse import urlencode
from urllib.request import urlopen

from geo_coordinates import gcj02_to_wgs84, wgs84_to_gcj02


def public_map_config():
    # TIANDITU_KEY is a browser map key: restrict its domain at the provider.
    # AMAP_WEB_KEY is private and deliberately absent from this response.
    key = os.environ.get("TIANDITU_KEY", "").strip()
    return dict(
        provider="tianditu" if key else "osm",
        tianditu_key=key,
        walking_enabled=bool(os.environ.get("AMAP_WEB_KEY", "").strip()),
    )


def coordinate(value):
    if not isinstance(value, dict):
        raise ValueError("请提供武汉范围的出发位置")
    try:
        lat, lng = float(value["latitude"]), float(value["longitude"])
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("位置需要有效的经纬度") from error
    if not (
        math.isfinite(lat)
        and math.isfinite(lng)
        and 29.8 <= lat <= 31.5
        and 113.5 <= lng <= 115.2
    ):
        raise ValueError("路线目前仅支持武汉范围")
    return lat, lng


def amap_navigation(origin, destination, name):
    start = wgs84_to_gcj02(*origin)
    end = wgs84_to_gcj02(*destination)
    return "https://uri.amap.com/navigation?" + urlencode(
        dict(
            **{"from": f"{start[1]:.6f},{start[0]:.6f},出发点"},
            to=f"{end[1]:.6f},{end[0]:.6f},{name}",
            mode="walk",
            coordinate="gaode",
            src="nightfind",
            callnative=0,
        )
    )


@lru_cache(maxsize=128)
def _fetch_route(origin, destination, key, time_bucket):
    start = wgs84_to_gcj02(*origin)
    end = wgs84_to_gcj02(*destination)
    query = urlencode(
        dict(
            key=key,
            origin=f"{start[1]:.6f},{start[0]:.6f}",
            destination=f"{end[1]:.6f},{end[0]:.6f}",
        )
    )
    # Fixed host and endpoint: neither credentials nor target URLs come from a visitor.
    with urlopen(
        "https://restapi.amap.com/v3/direction/walking?" + query, timeout=8
    ) as response:
        data = json.loads(response.read(2_000_000))
    if data.get("status") != "1":
        raise ValueError("路线服务暂不可用")
    paths = (data.get("route") or {}).get("paths") or []
    if not paths:
        raise ValueError("服务未找到步行路线")
    path = paths[0]
    distance, duration = float(path["distance"]), float(path["duration"])
    if (
        not math.isfinite(distance)
        or not math.isfinite(duration)
        or distance <= 0
        or duration <= 0
    ):
        raise ValueError("路线数据无效")
    points, steps = [], []
    for step in path.get("steps", []):
        instruction = re.sub(r"<[^>]*>", "", str(step.get("instruction", "")))[:300]
        if instruction:
            steps.append(instruction)
        for pair in str(step.get("polyline", "")).split(";"):
            if not pair:
                continue
            lng, lat = map(float, pair.split(","))
            point = gcj02_to_wgs84(lat, lng)
            coordinate(dict(latitude=point[0], longitude=point[1]))
            if not points or points[-1] != point:
                points.append(point)
    return dict(
        status="ready",
        distance_m=round(distance),
        duration_seconds=round(duration),
        points=points,
        steps=steps,
        source_name="高德步行路线",
        coordinate_system="WGS84",
    )


def walking_route(origin_value, merchant):
    origin = coordinate(origin_value)
    if merchant.get("latitude") is None or merchant.get("longitude") is None:
        return dict(
            status="missing_destination",
            notice="这家门店尚无可靠坐标，请按店名和地址在地图中查找。",
            navigation_url=merchant.get("map_search_url"),
        )
    destination = coordinate(merchant)
    base = dict(
        navigation_url=amap_navigation(origin, destination, merchant["name"]),
        origin_name=str(origin_value.get("name") or "出发点")[:100],
        origin_note=str(origin_value.get("note") or "")[:200],
    )
    key = os.environ.get("AMAP_WEB_KEY", "").strip()
    if not key:
        return dict(
            **base,
            status="unconfigured",
            notice="打开高德可查看实际步行路线与预计时间。",
        )
    try:
        result = _fetch_route(
            tuple(round(x, 6) for x in origin),
            tuple(round(x, 6) for x in destination),
            key,
            int(time.time() // 600),
        )
        return dict(**base, **result)
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        # Do not return upstream URLs, keys, or stack traces to the browser.
        return dict(
            **base,
            status="unavailable",
            notice="暂时未能读取路线，可重试或在高德继续查看。",
        )
````

<a id="source-24"></a>

## 24. merchant_photos.py

[打开原文件](../merchant_photos.py) · 147 行

SHA-256：`336914c18d00bfdd7cec3593e5a4d7fc357461a01017bac50be0eff2786af01d`

````python
"""Operator-only storefront photo pipeline for the OSM Wuhan catalog.

Do not treat an OSM place tag or an image search result as a photo license.
Only a recently photographed, explicitly licensed, human-reviewed image can
appear on public merchant cards.
"""
import os
import re
import secrets
from pathlib import Path

from database import ROOT
from real_catalog import _fresh_cutoff

PHOTO_DIR = Path(os.environ.get("MERCHANT_PHOTO_DIR", ROOT / "data" / "merchant_photos"))
MAX_BYTES = 5 * 1024 * 1024


def recent_date(raw, label):
    from datetime import date
    try:
        value = date.fromisoformat(str(raw))
    except (TypeError, ValueError) as error:
        raise ValueError("{}必须是 YYYY-MM-DD 格式".format(label)) from error
    if value > date.today() or value.isoformat() < _fresh_cutoff():
        raise ValueError("{}必须在最近两个自然年内，且不能为未来日期".format(label))
    return value.isoformat()


def inspect_image(path):
    file_path = Path(path)
    if not file_path.is_file() or file_path.stat().st_size > MAX_BYTES:
        raise ValueError("店面照片不存在或超过 5 MB")
    data = file_path.read_bytes()
    if len(data) < 128:
        raise ValueError("店面照片文件不完整")
    if data.startswith(b"\xff\xd8\xff"):
        ext = ".jpg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        ext = ".png"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        ext = ".webp"
    else:
        raise ValueError("店面图片只能使用 JPEG、PNG 或 WebP")
    if any(token in data for token in (
        b"Exif\x00\x00", b"eXIf", b"iTXt", b"tEXt", b"zTXt",
        b"http://ns.adobe.com/xap/1.0/", b"XMP ",
    )):
        raise ValueError("图片含常见 EXIF/XMP 元数据，请先移除后再提交")
    return data, ext


def add_photo(
    connection, merchant_id, image_path, taken_at, source_url,
    copyright_holder, license_note, operator, rights_confirmed=False,
):
    if not rights_confirmed:
        raise ValueError("尚未明确确认图片复制、存储和展示的授权")
    taken_at = recent_date(taken_at, "拍摄日期")
    if not operator or not operator.strip():
        raise ValueError("操作员不能为空")
    if not copyright_holder or not copyright_holder.strip() or not license_note:
        raise ValueError("必须提供照片权利人和展示授权说明")
    if not re.match(r"^(https://\S+|merchant-submission:[A-Za-z0-9_-]+)$", source_url or ""):
        raise ValueError("需要可追溯的照片来源网址或商家提交凭证")
    merchant = connection.execute(
        "SELECT id,source_checked_at FROM real_merchants WHERE id=?",
        (merchant_id,),
    ).fetchone()
    if merchant is None:
        raise ValueError("未找到真实门店")
    # A photo can be prepared for a pending candidate; public serving remains gated.
    data, ext = inspect_image(image_path)
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    filename = secrets.token_hex(20) + ext
    target = PHOTO_DIR / filename
    with target.open("xb") as out:
        out.write(data)
    try:
        connection.execute(
            """
            INSERT INTO real_merchant_photos(
                merchant_id,image_filename,taken_at,source_url,
                copyright_holder,license_note,permission_confirmed,created_by
            ) VALUES (?,?,?,?,?,?,1,?)
            """,
            (
                merchant_id, filename, taken_at, source_url,
                copyright_holder.strip(), license_note.strip(), operator.strip(),
            ),
        )
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return connection.execute("SELECT last_insert_rowid()").fetchone()[0]


def approve_photo(connection, photo_id, reviewer, status="verified"):
    if status not in ("verified", "rejected"):
        raise ValueError("不支持的照片审核状态")
    if not reviewer or not reviewer.strip():
        raise ValueError("审核人不能为空")
    row = connection.execute(
        "SELECT taken_at,permission_confirmed FROM real_merchant_photos WHERE id=?",
        (photo_id,),
    ).fetchone()
    if row is None:
        raise ValueError("照片不存在")
    if status == "verified":
        recent_date(row["taken_at"], "照片拍摄日期")
        if row["permission_confirmed"] != 1:
            raise ValueError("缺少图片授权")
    connection.execute(
        """
        UPDATE real_merchant_photos SET status=?,verified_at=CURRENT_TIMESTAMP,
            reviewed_by=? WHERE id=?
        """,
        (status, reviewer.strip(), photo_id),
    )


def public_photo_file(connection, photo_id):
    """No image bytes may escape when merchant/photo evidence is stale."""
    boundary = _fresh_cutoff()
    row = connection.execute(
        """
        SELECT p.image_filename FROM real_merchant_photos AS p
        JOIN real_merchants AS r ON r.id=p.merchant_id
        WHERE p.id=? AND p.permission_confirmed=1 AND p.status='verified'
          AND p.taken_at >= ? AND substr(p.verified_at,1,10) >= ?
          AND r.source_checked_at >= ?
          AND ((r.status='verified' AND r.verified_at >= ?) OR
               (r.status='pending' AND r.source_name='OpenStreetMap'
                AND r.external_id LIKE 'osm:%'))
        """,
        (photo_id, boundary, boundary, boundary, boundary),
    ).fetchone()
    return row


def safe_image_path(filename):
    if not re.fullmatch(r"[a-f0-9]{40}\.(jpg|png|webp)", filename):
        raise ValueError("无效照片文件")
    path = PHOTO_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(filename)
    return path
````

<a id="source-25"></a>

## 25. osm_sync.py

[打开原文件](../osm_sync.py) · 377 行

SHA-256：`5f6ed5a92ce0a391dd62c5764ef98af7475cabff891be27317f6760d300b2e31`

````python
"""Fetch Wuhan food venues from the ODbL-licensed OpenStreetMap Overpass API.

Usage (network required):
    python3 osm_sync.py fetch --output data_sources/osm_wuhan_snapshot.json

The generated snapshot contains OSM community entries, not independently
verified businesses. It must be distributed with OpenStreetMap attribution.
"""

import argparse
import os
import hashlib
import json
import datetime as dt
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from real_catalog import (
    UNKNOWN_DISTRICT,
    WUHAN_DISTRICTS,
    import_real_merchants,
    validate_real_merchants,
)

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT / "data_sources" / "osm_wuhan_snapshot.json"
LIVE_SNAPSHOT = ROOT / "data_sources" / "wuhan_live_catalog.json"
ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
# Start with small, geographically separate Wuhan samples to respect public
# Overpass instance capacity. This is *not* full-city coverage.
SAMPLE_BBOXES = (
    (30.555, 114.245, 30.615, 114.315),  # Jianghan/Jiang'an central area
    (30.525, 114.305, 30.585, 114.385),  # Wuchang
    (30.475, 114.365, 30.535, 114.445),  # Guanggu/Hongshan
    (30.525, 114.205, 30.585, 114.285),  # Hanyang/Qiaokou
)


def overpass_query(bbox):
    south, west, north, east = bbox
    return (
        "[out:json][timeout:35];"
        "(nwr[amenity~'^(restaurant|fast_food|cafe|food_court)$']"
        "[name]({},{},{},{}););out meta center;".format(south, west, north, east)
    )


MAX_RECORDS = 2000


def convert_osm_element(element):
    """Make one source-attributed, explicitly unverified merchant record."""
    if not isinstance(element, dict):
        return None
    tags = element.get("tags") or {}
    name = (tags.get("name:zh") or tags.get("name") or "").strip()
    kind = element.get("type")
    identifier = element.get("id")
    location = element.get("center") or element
    lat, lon = location.get("lat"), location.get("lon")
    if kind not in ("node", "way", "relation") or not isinstance(identifier, int):
        return None
    if (
        not name
        or not isinstance(lat, (int, float))
        or not isinstance(lon, (int, float))
    ):
        return None
    # Safety bound in addition to the actual administrative-area query.
    if not (29.9 <= lat <= 31.5 and 113.5 <= lon <= 115.2):
        return None
    district = tags.get("addr:district") or tags.get("is_in:district") or ""
    if district not in WUHAN_DISTRICTS:
        district = UNKNOWN_DISTRICT

    street = (tags.get("addr:street") or "").strip()
    number = (tags.get("addr:housenumber") or "").strip()
    address = (
        "武汉市" + (district if district != UNKNOWN_DISTRICT else "") + street + number
        if street
        else ""
    )
    if not address:
        address = "详细地址待核实，请通过来源地图查看位置"

    cuisine = (tags.get("cuisine") or "").replace(";", "、").strip()
    if not cuisine:
        cuisine = {
            "restaurant": "餐厅",
            "fast_food": "快餐",
            "cafe": "咖啡简餐",
            "food_court": "美食广场",
        }.get(tags.get("amenity"), "餐饮")
    # Only OSM field-survey tags count as source checking evidence.
    # Element edit timestamps and the date this snapshot was downloaded do not.
    checked = tags.get("survey:date") or tags.get("check_date") or ""
    try:
        if checked and dt.date.fromisoformat(checked) > dt.date.today():
            checked = ""
        elif checked:
            dt.date.fromisoformat(checked)
    except (TypeError, ValueError):
        checked = ""

    return {
        "external_id": "osm:{}:{}".format(kind, identifier),
        "name": name[:120],
        "district": district,
        "address": address[:200],
        "cuisine": cuisine[:100],
        "latitude": lat,
        "longitude": lon,
        "phone": (tags.get("contact:phone") or tags.get("phone") or "")[:40],
        "price_per_person": None,  # Never invent price.
        "opening_hours": (tags.get("opening_hours") or "")[:200] or None,
        "source_name": "OpenStreetMap",
        "source_url": "https://www.openstreetmap.org/{}/{}".format(kind, identifier),
        "source_checked_at": checked,
        "source_updated_at": str(element.get("timestamp", ""))[:10],
        "verified_at": "",  # OSM community data is NOT business verification.
        "verification_method": "",
        "status": "pending",
    }


def parse_overpass_payload(payload):
    """Deduplicate by OSM type+id; reject missing/invalid upstream responses."""
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise ValueError("Overpass 返回数据格式不正确")
    results = {}
    for element in payload["elements"]:
        record = convert_osm_element(element)
        if record:
            results[record["external_id"]] = record
    if not results:
        raise ValueError("未找到可用的武汉商家记录，不写入空快照")
    return [results[key] for key in sorted(results)][:MAX_RECORDS]


def fetch_wuhan_osm():
    """Small, bounded Overpass queries. No continuous or aggressive scraping."""
    import time

    all_rows = {}
    errors = []
    for index, bbox in enumerate(SAMPLE_BBOXES, 1):
        form = urllib.parse.urlencode({"data": overpass_query(bbox)}).encode("utf-8")
        completed = False
        for endpoint in ENDPOINTS:
            request = urllib.request.Request(
                endpoint,
                data=form,
                method="POST",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "NightFindWuhanCatalog/1.1 (OSM ODbL snapshot)",
                    "Accept": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=40) as response:
                    raw = response.read(4_000_001)
                    if len(raw) > 4_000_000:
                        raise ValueError("单个分区响应超过 4 MB")
                    records = parse_overpass_payload(json.loads(raw.decode("utf-8")))
                    for record in records:
                        record["evidence_url"] = endpoint
                        record["source_collected_at"] = dt.date.today().isoformat()
                        all_rows[record["external_id"]] = record
                    print(
                        "区块 {}/{}：获取 {} 条开放地图餐饮场所".format(
                            index, len(SAMPLE_BBOXES), len(records)
                        ),
                        flush=True,
                    )
                    completed = True
                    break
            except (
                urllib.error.URLError,
                TimeoutError,
                ValueError,
                json.JSONDecodeError,
                OSError,
            ) as exc:
                errors.append("{}: {}".format(endpoint, exc))
        if not completed:
            print(
                "区块 {}/{} 获取失败（未包含在快照中）".format(
                    index, len(SAMPLE_BBOXES)
                ),
                flush=True,
            )
        time.sleep(1)  # Gentle pacing for community infrastructure.

    if not all_rows:
        raise RuntimeError(
            "未能从公开接口获取餐饮记录；不会生成虚假快照。"
            + " 最近错误："
            + (errors[-1] if errors else "无记录")
        )
    return [all_rows[key] for key in sorted(all_rows)][:MAX_RECORDS]


def read_snapshot(path):
    """Load source rows and verified batch provenance without inventing survey dates."""
    path = Path(path)
    payload = path.read_bytes()
    decoded = json.loads(payload.decode("utf-8"))
    metadata_bytes = b""
    if isinstance(decoded, dict):
        metadata = decoded.get("metadata", {})
        rows = decoded.get("records")
        if not isinstance(rows, list):
            raise ValueError("快照 records 必须为数组")
        evidence = json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()
    else:
        rows = decoded
        meta_path = path.with_suffix(".meta.json")
        metadata_bytes = meta_path.read_bytes() if meta_path.is_file() else b""
        metadata = json.loads(metadata_bytes) if metadata_bytes else {}
        evidence = payload
    if not isinstance(rows, list) or not rows:
        raise ValueError("OSM 快照必须包含实际来源记录")
    if metadata:
        if metadata.get("sha256") != hashlib.sha256(evidence).hexdigest():
            raise ValueError("OSM 快照与来源清单的 SHA-256 不一致")
        if metadata.get("record_count") != len(rows):
            raise ValueError("OSM 快照条数与清单不一致")
        kind = metadata.get("kind")
        if kind not in ("repository_archive", "live_osm"):
            raise ValueError("不支持的 OSM 来源证据类型")
        if not str(metadata.get("evidence_url", "")).startswith("https://"):
            raise ValueError("OSM 快照缺少 HTTPS 来源证据")
        field = (
            "source_archived_at"
            if kind == "repository_archive"
            else "source_collected_at"
        )
        date = metadata.get(
            "archived_at" if kind == "repository_archive" else "collected_at", ""
        )
        from catalog_policy import clean_date

        if not clean_date(date, field):
            raise ValueError("快照需要记录真实的采集或归档日期")
        rows = [
            dict(
                row,
                **{field: date},
                evidence_url=(row.get("evidence_url") if kind == "live_osm" else None)
                or metadata["evidence_url"],
            )
            for row in rows
        ]
    # Preserve the meaning of an absent survey date without substituting a batch date.
    rows = [
        dict(row, source_checked_at=row.get("source_checked_at", "")) for row in rows
    ]
    return rows, hashlib.sha256(payload + metadata_bytes).hexdigest()


def hydrate_osm_snapshot(connection, path=None):
    """Use a new live collection when present; otherwise retain the attributed archive."""
    path = (
        Path(path)
        if path is not None
        else (LIVE_SNAPSHOT if LIVE_SNAPSHOT.is_file() else SNAPSHOT)
    )
    if not path.is_file():
        return 0
    rows, digest = read_snapshot(path)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_import_state (
            source TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    current = connection.execute(
        "SELECT checksum FROM catalog_import_state WHERE source = 'osm_wuhan'"
    ).fetchone()
    if current is not None and current["checksum"] == digest:
        return 0
    result = import_real_merchants(connection, rows)
    connection.execute(
        "INSERT INTO catalog_import_state(source,checksum) VALUES ('osm_wuhan',?) "
        "ON CONFLICT(source) DO UPDATE SET checksum=excluded.checksum, imported_at=CURRENT_TIMESTAMP",
        (digest,),
    )
    return result["written"]


def collect_live_snapshot(output=LIVE_SNAPSHOT, minimum=100):
    """Fetch first, validate first; a failed collection never replaces a good file."""
    from catalog_policy import catalog_cutoff

    rows = fetch_wuhan_osm()
    today = dt.date.today().isoformat()
    # A successful live response proves online collection, not operating status.
    rows = [
        row
        for row in rows
        if not row.get("source_updated_at")
        or row["source_updated_at"] >= catalog_cutoff()
    ]
    rows = validate_real_merchants(
        [
            dict(
                row,
                source_collected_at=today,
                evidence_url=row.get("evidence_url") or ENDPOINTS[0],
            )
            for row in rows
        ]
    )
    if len(rows) < minimum:
        raise ValueError(
            "实际获取的近五年来源记录只有 {} 条，未达到 {} 条；保留已有数据".format(
                len(rows), minimum
            )
        )
    metadata = dict(
        schema_version=1,
        kind="live_osm",
        collected_at=today,
        record_count=len(rows),
        license="ODbL-1.0",
        evidence_url=rows[0]["evidence_url"],
        sha256=hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
        notice="日期为在线采集时间，元素更新和逐店调查日期单独保留；当前营业及价格需核实。",
    )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(metadata=metadata, records=rows), ensure_ascii=False, indent=2)
        + "\n", encoding="utf-8"
    )
    os.replace(temporary, output)
    return dict(
        merchants=len(rows),
        mapped=len(rows),
        output=str(output),
        menu_prices="OSM 未提供的菜品价格不补造，需从可核验门店菜单另行补充",
    )


def main():
    parser = argparse.ArgumentParser(
        description="采集近五年武汉公开地图门店，保留来源和真实坐标"
    )
    parser.add_argument("action", choices=("fetch",))
    parser.add_argument("--output", type=Path, default=LIVE_SNAPSHOT)
    parser.add_argument("--minimum", type=int, default=100)
    args = parser.parse_args()
    if not 100 <= args.minimum <= MAX_RECORDS:
        parser.error("minimum 必须在 100–{} 之间".format(MAX_RECORDS))
    print(
        json.dumps(
            collect_live_snapshot(args.output, args.minimum),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
````

<a id="source-26"></a>

## 26. refresh_wuhan_catalog.py

[打开原文件](../refresh_wuhan_catalog.py) · 328 行

SHA-256：`ce1546425bfdcdedc520bf6c267e176f075c6d0db8d37a23fb2134dd4a2f5ed1`

````python
"""Refresh existing Ctrip branches from public, server-rendered merchant pages.

python3 refresh_wuhan_catalog.py --apply
No login, private API, review workflow, image copying, or price inference.
"""

import argparse
import csv
import hashlib
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from geo_coordinates import gcj02_to_wgs84

ROOT = Path(__file__).resolve().parent
USER_AGENT = "NightFind-WuhanCatalog/1.0 (+https://github.com/2472099715liangren-ship-it/nightfood-ai)"


def normalize_name(value):
    return re.sub(r"[\W_]", "", value.removeprefix("武汉")).casefold()


def parse_page(html, expected):
    match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        raise ValueError("页面没有公开的商家结构化资料")
    state = json.loads(match[1])["props"]["pageProps"]["initialState"]
    info = (state.get("mainInfoData") or {}).get("RestaurantInfo") or {}
    if info.get("DistrictName") != "武汉":
        raise ValueError("来源不属于武汉，跳过")
    actual_name = info.get("Name") or ""
    branch = re.search(r"[（(](.*?)[）)]", expected["name"])
    actual_branch = re.search(r"[（(](.*?)[）)]", actual_name)
    same_branch = (
        branch
        and actual_branch
        and normalize_name(branch[1]) == normalize_name(actual_branch[1])
        and normalize_name(expected["name"])[:3] == normalize_name(actual_name)[:3]
    )
    if (
        normalize_name(actual_name) != normalize_name(expected["name"])
        and not same_branch
    ):
        raise ValueError("来源分店名不一致，跳过：" + str(actual_name))
    source_id = re.search(r"/(\d+)\.html", expected["source_url"])
    if not source_id or int(source_id[1]) != info.get("RestaurantId"):
        raise ValueError("来源商家 ID 不一致")
    checked = date.today().isoformat()
    changes = {
        "source_checked_at": checked,
        "verification_method": "公开分店页面自动采集",
        "status": "pending",
    }
    if info.get("Address"):
        changes["address"] = info["Address"]
        if expected.get("district") in ("", "待确认区县"):
            from real_catalog import WUHAN_DISTRICTS

            changes["district"] = next(
                (
                    district
                    for district in WUHAN_DISTRICTS
                    if district in info["Address"]
                ),
                "待确认区县",
            )
    average = info.get("AveragePrice")
    if isinstance(average, (int, float)) and 0 < average <= 10000:
        changes["price_per_person"] = round(average)
    phones = [
        phone
        for phone in (info.get("BookTelList") or [])
        if isinstance(phone, str) and re.fullmatch(r"\+?[\d ()-]{5,30}", phone)
    ]
    if phones:
        changes["phone"] = phones[0]
    # Keep weekly schedules; never copy the transient "营业中" status.
    schedules = []
    for day in info.get("WeekdayDtoList") or info.get("MergeWeekdayDtoList") or []:
        if not isinstance(day, dict):
            continue
        intervals = [
            f'{slot["BeginTime"]}-{slot["EndTime"]}'
            for slot in (day.get("OpenTimeList") or [])
            if isinstance(slot, dict)
            and re.fullmatch(r"\d{2}:\d{2}", str(slot.get("BeginTime") or ""))
            and re.fullmatch(r"\d{2}:\d{2}", str(slot.get("EndTime") or ""))
        ]
        if intervals:
            schedules.append((day.get("Weekday", ""), ", ".join(intervals)))
    weekdays = dict(
        zip(
            ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
            ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
        )
    )
    if schedules:
        if (
            len({day for day, _ in schedules}) == 7
            and len({hours for _, hours in schedules}) == 1
        ):
            changes["opening_hours"] = schedules[0][1]
        else:
            known = [
                (weekdays[day], hours) for day, hours in schedules if day in weekdays
            ]
            if known:
                changes["opening_hours"] = "; ".join(
                    f"{day} {hours}" for day, hours in known
                )
    point = info.get("GDCoord") or {}
    lat, lng = point.get("Lat"), point.get("Lon")
    if lat is None or lng is None:
        lng = point.get("Lng")
    if (
        isinstance(lat, (int, float))
        and isinstance(lng, (int, float))
        and 29.8 <= lat <= 31.5
        and 113.5 <= lng <= 115.2
    ):
        latitude, longitude = gcj02_to_wgs84(lat, lng)
        changes.update(
            latitude=latitude,
            longitude=longitude,
            location_note="携程分店 GDCoord（GCJ-02）转换为 WGS84；来源商家点位，非精确入口。",
        )
    menus = []
    for dish in info.get("RestaurantRecommendedFoodList") or []:
        title = str(dish.get("Title") or "").strip()
        if not title:
            continue
        raw_price = str(dish.get("Price") or "").strip()
        price_match = re.fullmatch(r"[¥￥]\s*(\d+(?:\.\d{1,2})?)", raw_price)
        price = float(price_match[1]) if price_match else None
        menus.append(
            dict(
                external_id=expected["external_id"],
                dish_name=title,
                price=price if price and 0 < price <= 10000 else "",
                price_unit="元（来源未注明份量）",
                price_source_url=expected["source_url"],
                price_checked_at=checked,
                price_note=(
                    "公开分店推荐菜单参考价，来源未注明份量；实际售价以门店为准。"
                    if price
                    else "来源列出菜名，未提供单品价格。"
                ),
            )
        )
    if menus:
        changes["signature_dishes"] = ";".join(d["dish_name"] for d in menus[:8])
    # Store only the factual source fields used, not page tracking or signatures.
    evidence = {
        key: info.get(key)
        for key in (
            "RestaurantId",
            "Name",
            "DistrictName",
            "Address",
            "AveragePrice",
            "BookTelList",
            "GDCoord",
            "WeekdayDtoList",
            "MergeWeekdayDtoList",
        )
    }
    evidence["menu"] = [
        {"name": d.get("Title"), "price": d.get("Price")}
        for d in info.get("RestaurantRecommendedFoodList") or []
    ]
    return changes, menus, evidence


def write_csv(path, rows, fields):
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def refresh(apply=False, limit=50, discover=False):
    merchants_path = ROOT / "data" / "wuhan_restaurants.csv"
    menu_path = ROOT / "data" / "wuhan_menu_items.csv"
    with merchants_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames)
        merchants = list(reader)
    with menu_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        menu_fields = list(reader.fieldnames)
        menus = list(reader)
    for field in ("phone", "opening_hours", "price_range_basis"):
        if field not in fields:
            fields.append(field)
    menu_index = {(item["external_id"], item["dish_name"]): item for item in menus}
    report, errors = [], []
    candidates = [
        row
        for row in merchants
        if urlsplit(row["source_url"]).hostname == "gs.ctrip.com"
    ][:limit]
    known_ids = {
        int(match[1])
        for row in merchants
        if (match := re.search(r"/(\d+)\.html", row["source_url"]))
    }
    by_name = {normalize_name(row["name"]): row for row in merchants}
    for row in candidates:
        try:
            request = Request(row["source_url"], headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=20) as response:
                raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise ValueError("页面超过大小上限")
            changes, dishes, evidence = parse_page(raw.decode("utf-8"), row)
            row.update(changes)
            if not any(old["external_id"] == row["external_id"] for old in merchants):
                merchants.append(row)
                by_name[normalize_name(row["name"])] = row
            else:
                for old in merchants:
                    if old["external_id"] == row["external_id"]:
                        old.update(row)
                        break
            if discover and len(candidates) < limit:
                match = re.search(
                    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                    raw.decode("utf-8"),
                    re.S,
                )
                related = json.loads(match[1])["props"]["pageProps"][
                    "initialState"
                ].get("waterFallList", [])
                for item in related:
                    identifier, name = item.get("restaurantId"), item.get(
                        "restaurantName"
                    )
                    if (
                        not identifier
                        or not name
                        or identifier in known_ids
                        or len(candidates) >= limit
                    ):
                        continue
                    known_ids.add(identifier)
                    existing = by_name.get(normalize_name(name))
                    candidate = (
                        dict(existing) if existing else {field: "" for field in fields}
                    )
                    candidate.update(
                        external_id=(
                            existing["external_id"]
                            if existing
                            else f"web:ctrip:{identifier}"
                        ),
                        name=name,
                        district=candidate.get("district") or "待确认区县",
                        cuisine=candidate.get("cuisine")
                        or str(item.get("cuisine") or "餐厅"),
                        source_name="携程美食林",
                        source_url=f"https://gs.ctrip.com/html5/you/foods/fooddetail/145/{identifier}.html",
                    )
                    candidates.append(candidate)
            for dish in dishes:
                key = (dish["external_id"], dish["dish_name"])
                old = menu_index.get(key)
                if not old or dish["price"] != "" or old["price"] == "":
                    menu_index[key] = dish
            report.append(
                dict(
                    external_id=row["external_id"],
                    source_url=row["source_url"],
                    html_sha256=hashlib.sha256(raw).hexdigest(),
                    fields=changes,
                    evidence=evidence,
                )
            )
            print(
                f'已读取：{row["name"]} · {sum(d["price"] != "" for d in dishes)} 条单价',
                flush=True,
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(dict(external_id=row["external_id"], reason=str(error)))
            print(f'跳过：{row["name"]} · {error}', flush=True)
        time.sleep(0.5)
    result = dict(
        collected_at=datetime.now(timezone.utc).isoformat(),
        records=report,
        errors=errors,
    )
    if apply and report:
        write_csv(merchants_path, merchants, fields)
        write_csv(menu_path, list(menu_index.values()), menu_fields)
        (ROOT / "data_sources" / "wuhan_web_refresh.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        )
    return {
        "updated": len(report),
        "skipped": len(errors),
        "applied": bool(apply and report),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="补充已有武汉分店资料，保持来源和分店一致"
    )
    parser.add_argument("--apply", action="store_true", help="写入 CSV；默认只检查来源")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--discover",
        action="store_true",
        help="从公开相关推荐补充武汉分店，仍逐店校验；总请求不超过 limit",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            refresh(args.apply, max(1, min(args.limit, 50)), args.discover),
            ensure_ascii=False,
        )
    )
````

<a id="source-27"></a>

## 27. services.py

[打开原文件](../services.py) · 441 行

SHA-256：`78068e9964d914dc4bfcc149394d0321d70aad56fc0c48082c66aa4f4404b0a0`

````python
"""Recommendation and conversational assistant services.

This module owns product rules. HTTP handlers should only validate and call services.
"""
import json
import math
import os
import re
import urllib.error
import urllib.request

from database import list_merchants, save_recommendation_run
from real_catalog import public_real_merchants
from conversation import choose_candidate_round, follow_up_suggestions, refine_preferences


SCENES = ("朋友聚会", "独自用餐", "出游夜宵")
CUISINES = ("不限", "烧烤", "小龙虾", "湖北菜", "家常菜", "粥粉面")


def _valid_context(context):
    context = context if isinstance(context, dict) else {}
    return {
        "district": str(context.get("district", "")),
        "budget": _bounded_int(context.get("budget"), 100, 10, 500),
        "wait": _bounded_int(context.get("wait"), 40, 0, 120),
        "hour": _bounded_hour(context.get("hour", 21)),
        "scene": context.get("scene") if context.get("scene") in SCENES else "朋友聚会",
        "cuisine": context.get("cuisine") if context.get("cuisine") in CUISINES else "不限",
    }


def _bounded_int(value, default, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if minimum <= number <= maximum else default


def _bounded_hour(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 21.0
    return number if 0 <= number < 24 else 21.0


def _chinese_digits_to_arabic(message):
    """Handle common short forms such as 九点半 and 十点."""
    digits = {
        "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3,
        "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    }

    def replace(match):
        text = match.group(0)
        if text == "十":
            return "10"
        if text.startswith("十"):
            return str(10 + digits.get(text[1], 0))
        if text.endswith("十"):
            return str(digits.get(text[0], 0) * 10)
        if "十" in text:
            left, right = text.split("十", 1)
            return str(digits.get(left, 1) * 10 + digits.get(right, 0))
        return str(digits[text])

    return re.sub(r"[零〇一二两三四五六七八九十]{1,3}(?=点)", replace, message)


def parse_preferences(message, context, districts):
    """Merge new natural-language details into the current conversation context."""
    preferences = _valid_context(context)
    message = _chinese_digits_to_arabic(message)

    for district in districts:
        if district["name"] in message:
            preferences["district"] = district["name"]
            break

    budget_match = re.search(
        r"(?:人均|预算|每人|每位|控制在)(?:在|为|约)?\s*[¥￥]?\s*(\d{1,3})",
        message,
    )
    if not budget_match:
        budget_match = re.search(r"[¥￥]\s*(\d{1,3})", message)
    if not budget_match:
        budget_match = re.search(r"(\d{1,3})\s*(?:元|块)(?:以内|左右)?", message)
    if budget_match:
        value = int(budget_match.group(1))
        if 10 <= value <= 500:
            preferences["budget"] = value

    wait_patterns = (
        r"(?:等位|等待|等)\s*(?:不超过|最多|控制在)?\s*(\d{1,3})\s*分钟",
        r"(?:最多|不超过)\s*等\s*(\d{1,3})\s*分钟",
    )
    for pattern in wait_patterns:
        match = re.search(pattern, message)
        if match:
            value = int(match.group(1))
            if 0 <= value <= 120:
                preferences["wait"] = value
            break
    if any(word in message for word in ("不想排队", "不想等", "不排队")):
        preferences["wait"] = min(preferences["wait"], 10)

    time_match = re.search(
        r"(凌晨|早上|上午|中午|下午|傍晚|晚上|今晚)?\s*"
        r"(\d{1,2})(?::|：)(\d{2})|"
        r"(凌晨|早上|上午|中午|下午|傍晚|晚上|今晚)?\s*"
        r"(\d{1,2})点(半|(\d{1,2})分?)?",
        message,
    )
    if time_match:
        groups = time_match.groups()
        if groups[1] is not None:
            period, hour, minute = groups[0], int(groups[1]), int(groups[2])
        else:
            period, hour = groups[3], int(groups[4])
            minute = 30 if groups[5] == "半" else int(groups[6] or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            parsed_hour = hour + minute / 60
            if period in ("晚上", "傍晚", "下午", "今晚") and hour < 12:
                parsed_hour += 12
            if period in ("凌晨", "早上", "上午") and hour == 12:
                parsed_hour = minute / 60
            if period == "中午" and hour < 11:
                parsed_hour += 12
            preferences["hour"] = parsed_hour % 24

    if any(word in message for word in ("一个人", "独自", "单人", "自己吃")):
        preferences["scene"] = "独自用餐"
    elif any(word in message for word in ("朋友", "聚会", "同事", "多人")):
        preferences["scene"] = "朋友聚会"
    elif any(word in message for word in ("夜宵", "出游", "逛街", "散步")):
        preferences["scene"] = "出游夜宵"

    if any(word in message for word in ("小龙虾", "虾")):
        preferences["cuisine"] = "小龙虾"
    elif any(word in message for word in ("烧烤", "烤肉", "烤串")):
        preferences["cuisine"] = "烧烤"
    elif any(word in message for word in ("清淡", "粥", "面条", "粉面")):
        preferences["cuisine"] = "粥粉面"
    elif any(word in message for word in ("家常菜", "家常口味")):
        preferences["cuisine"] = "家常菜"
    elif any(word in message for word in ("湖北菜", "武汉特色", "本地菜")):
        preferences["cuisine"] = "湖北菜"

    return preferences


def recommend(connection, preferences, session_id):
    """Filter impossible options first, then rank feasible merchants transparently."""
    districts = {
        row["name"]: (row["lat"], row["lng"])
        for row in connection.execute("SELECT name, lat, lng FROM districts")
    }
    selected_district = preferences["district"]
    if selected_district not in districts:
        selected_district = next(iter(districts), "")
        preferences["district"] = selected_district

    origin = districts.get(selected_district, (None, None))
    merchants = list_merchants(
        connection,
        district=selected_district,
        cuisine=preferences["cuisine"],
        max_price=preferences["budget"],
        limit=200,
    )
    feasible = []
    requested_hour = preferences["hour"]
    business_hour = requested_hour + 24 if requested_hour < 12 else requested_hour

    for merchant in merchants:
        if merchant["wait"] > preferences["wait"]:
            continue
        if merchant["opens"] is None or not (
            merchant["opens"] <= business_hour < merchant["closes"]
        ):
            continue

        distance = 0.0
        if origin[0] is not None and merchant["lat"] is not None:
            distance = round(
                math.hypot(
                    (merchant["lat"] - origin[0]) * 111,
                    (merchant["lng"] - origin[1]) * 96,
                ),
                1,
            )

        budget_score = 25 * (1 - merchant["price"] / preferences["budget"] * 0.5)
        distance_score = 25 / (1 + distance / 2)
        wait_score = 20 * (
            1 - merchant["wait"] / max(preferences["wait"], 1) * 0.6
        )
        scene_score = 20 if preferences["scene"] in merchant["tags"] else 8
        rating_score = merchant["rating"] / 5 * 10
        parts = {
            "预算": round(budget_score, 1),
            "距离": round(distance_score, 1),
            "等待": round(wait_score, 1),
            "场景": round(scene_score, 1),
            "评分": round(rating_score, 1),
        }
        merchant["distance"] = distance
        merchant["score"] = round(sum(parts.values()), 1)
        merchant["parts"] = parts
        merchant["reasons"] = [
            "人均约 ¥{}，在当前预算内".format(merchant["price"]),
            "预计等位 {} 分钟".format(merchant["wait"]),
            "距所选商圈中心约 {} 公里（直线估算）".format(distance),
        ]
        merchant["explanation"] = json.dumps(parts, ensure_ascii=False)
        feasible.append(merchant)

    feasible.sort(key=lambda item: item["score"], reverse=True)
    save_recommendation_run(connection, session_id, preferences, feasible)
    return feasible


def _local_reply(preferences, items):
    district = preferences["district"] or "你选择的商圈"
    if not items:
        return (
            "我按你的条件看了一遍，目前没有合适的演示商户。"
            "可以试着放宽一点预算或等待时间，也可以换个商圈再看看。"
        )

    first = items[0]
    return (
        "我先帮你从{}附近挑了一轮。按人均{}元、等位{}分钟以内的条件，"
        "目前有{}家可以考虑。{}人均约{}元，预计等位{}分钟，"
        "和你刚才说的需求比较接近。".format(
            district,
            preferences["budget"],
            preferences["wait"],
            len(items),
            first["name"],
            first["price"],
            first["wait"],
        )
    )


def _build_tips(preferences, items):
    tips = []
    if preferences["budget"] <= 50:
        tips.append("预算比较精简，可以先看人均价格，再给饮料或加菜留一点余量。")
    if preferences["wait"] <= 20:
        tips.append("如果不想久等，出发前最好再问一下现场排队情况。")
    if preferences["scene"] == "朋友聚会":
        tips.append("多人一起吃的话，可以提前确认座位和是否方便拼桌。")
    elif preferences["scene"] == "独自用餐":
        tips.append("一个人吃饭，可以优先考虑上菜节奏和单人份菜品。")
    if preferences["hour"] >= 23 or preferences["hour"] < 5:
        tips.append("现在选择的是较晚时段，营业时间是演示数据，出发前请核实。")
    if not tips:
        tips.append("可以先看两三家商户的介绍和菜单，再按当晚心情决定。")
    if not items:
        tips.append("可以先把预算提高 10–20 元，或把等待时间放宽到 40 分钟。")
    return tips[:3]


def _response_text(response_data):
    direct_text = response_data.get("output_text")
    if direct_text:
        return direct_text.strip()

    parts = []
    for output_item in response_data.get("output", []):
        if output_item.get("type") != "message":
            continue
        for content in output_item.get("content", []):
            if content.get("type") == "output_text":
                parts.append(content.get("text", ""))
    return "\n".join(parts).strip()


def _ask_openai(message, history, preferences, items):
    """Call the OpenAI Responses API only from the server, never expose the key."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    model = os.environ.get("OPENAI_MODEL", "gpt-5.5").strip()
    base_url = os.environ.get(
        "OPENAI_BASE_URL", "https://api.openai.com/v1/responses"
    ).strip()
    if not base_url.startswith("https://"):
        raise ValueError("AI 服务地址必须使用 HTTPS")

    safe_history = []
    for entry in history[-8:]:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        content = str(entry.get("content", "")).strip()[:500]
        if role in ("user", "assistant") and content:
            safe_history.append({"role": role, "content": content})

    candidates = [
        {
            "name": item["name"],
            "district": item["district"],
            "cuisine": item["cuisine"],
            "price_per_person": item["price"],
            "wait_minutes": item["wait"],
            "match_score": item["score"],
            "description": item["description"],
        }
        for item in items[:8]
    ]
    context_text = (
        "用户最新需求：{}\n"
        "已解析条件：{}\n"
        "数据库中符合条件的商户：{}\n"
        "请结合这些候选商户回答。若列表为空，诚实说明没有符合项并建议放宽条件。"
        "不要虚构商家、地址、营业状态、电话、评价或实时排队信息。"
    ).format(
        message,
        json.dumps(preferences, ensure_ascii=False),
        json.dumps(candidates, ensure_ascii=False),
    )
    input_messages = safe_history + [
        {"role": "user", "content": context_text}
    ]
    request_body = {
        "model": model,
        "instructions": (
            "你是夜寻的餐饮规划助手。用自然、轻松、真诚的中文交流，"
            "像熟悉本地生活的朋友一样给建议，不要使用夸张营销话术。"
            "优先回应用户真正关心的事，简短说明推荐理由，并给出一到两条实用建议。"
            "只能推荐数据库候选列表中的商家；所有价格、评分和等待信息都要以候选数据为准。"
            "本项目的商户数据是演示数据，不能暗示它们是真实商家。"
        ),
        "input": input_messages,
        "max_output_tokens": 420,
        "store": False,
    }
    request = urllib.request.Request(
        base_url,
        data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        data = json.loads(response.read().decode("utf-8"))
    text = _response_text(data)
    return text or None


def chat(connection, payload, session_id, districts):
    """Build a grounded recommendation, then add natural-language AI guidance."""
    message = str(payload.get("message", "")).strip()
    if not message or len(message) > 2000:
        raise ValueError("请写下你的需求（最多 2000 个字符）")

    previous_context = payload.get("context")
    preferences = parse_preferences(message, previous_context, districts)
    preferences, known = refine_preferences(
        message, previous_context, preferences, districts
    )
    all_items = recommend(connection, preferences, session_id)
    # Finish the short database write before waiting for an external AI response.
    connection.commit()

    visible_items, exhausted = choose_candidate_round(
        all_items, message, payload.get("seen_ids", [])
    )
    follow_up = follow_up_suggestions(preferences, known, districts, all_items)
    tips = _build_tips(preferences, all_items)
    history = payload.get("history", [])
    if not isinstance(history, list):
        history = []

    mode = "local"
    is_help_request = any(
        word in message for word in ("怎么用", "帮助", "你能做什么", "功能介绍")
    )
    reply = _local_reply(preferences, visible_items)
    if any(word in message for word in ("换一批", "再换几家", "看看别的")):
        if exhausted:
            reply = "当前条件下可选的演示商家已经看过一轮啦。我再把符合条件的选项列出来，你也可以放宽预算或换个口味。"
        elif visible_items:
            reply = "好呀，我换几家还没展示过、也符合条件的演示商家。你可以接着比较价格和等待时间。"
    if is_help_request:
        reply = (
            "你可以像和朋友商量晚饭一样告诉我：想去哪一片、人均大概多少、"
            "几点到、能等多久，以及喜欢什么口味。我会先按这些条件筛选，"
            "再把合适的商家和推荐理由列给你。"
        )

    if os.environ.get("OPENAI_API_KEY", "").strip():
        try:
            ai_reply = _ask_openai(message, history, preferences, visible_items)
            if ai_reply:
                reply = ai_reply
                mode = "openai"
            else:
                mode = "fallback"
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            mode = "fallback"

    # OSM data may enrich chat without inheriting fabricated demo metrics.
    real_query = public_real_merchants(
        connection,
        keyword=preferences["cuisine"] if preferences["cuisine"] != "不限" else "",
        limit=4,
    )
    real_places = real_query["items"]
    if real_places:
        reply = (
            "已找到武汉开放地图的社区商家资料，具体位置和营业情况请打开地图来源核实。"
            "下面提到的价格、等位和匹配度仍是模拟推荐，只用于测试。\n\n"
            + reply
        )

    return {
        "reply": reply,
        "items": visible_items[:3] if (
            any(word in message for word in ("换一批", "再换几家", "看看别的"))
        ) else visible_items[:8],
        "total": len(all_items),
        "constraints": {**preferences, "known": known},
        "tips": tips,
        "follow_up": follow_up,
        "mode": mode,
        "sample_data": True,
        "real_places": real_places,
        "real_places_notice": (
            "以下是武汉开放地图社区收录的餐饮场所，未按商圈精确定位，"
            "未经人工核实且不提供实时价格或等位。请查看地图来源。"
        ),
    }
````

<a id="source-28"></a>

## 28. start.sh

[打开原文件](../start.sh) · 45 行

SHA-256：`43313561c038f64455b3cb7222a0aee9e0f6f457271c80d34c9dbf13706b4546`

````sh
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
````

<a id="source-29"></a>

## 29. static/api-client.js

[打开原文件](../static/api-client.js) · 41 行

SHA-256：`5ff5093ec0e3194720c63311e46cd32d6c41be28a89b197444efa3ad94803d5c`

````javascript
/* The browser keeps only an anonymous visitor ID. No API keys live here. */
const sessionKey = "nightfind-session";
let sessionId;
try {
  sessionId = localStorage.getItem(sessionKey);
  if (!sessionId) {
    sessionId = crypto.randomUUID();
    localStorage.setItem(sessionKey, sessionId);
  }
} catch {
  sessionId = `nf-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export async function request(path, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      signal: controller.signal,
      headers: { "X-Session": sessionId, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data;
    try {
      data = await response.json();
    } catch {
      throw new Error("服务响应暂时无法读取，请重试。");
    }
    if (!response.ok) throw new Error(data.error || "请求失败，请稍后重试。");
    return data;
  } catch (error) {
    if (error.name === "AbortError")
      throw new Error("查询超时，已保留用餐需求，可以重试。");
    if (error instanceof TypeError)
      throw new Error("连接失败，请确认夜寻仍在运行后重试。");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
````

<a id="source-30"></a>

## 30. static/app.js

[打开原文件](../static/app.js) · 771 行

SHA-256：`1fce414fb9b273a9d3a0c5b593ad2f8308e9b655baa00161efb4197c09f883ca`

````javascript
/* Page state and user actions. Rendering lives in decision-view.js. */
import { request } from "./api-client.js";
import {
  loadConversation,
  saveConversation,
  clearConversation,
} from "./session-store.js";
import {
  escapeHtml as e,
  constraintsView,
  merchantCards,
  candidateResultsView,
  detailsView,
  choiceView,
  comparisonView,
  preferencesEditor,
  walkingRouteView,
} from "./decision-view.js";

const root = document.getElementById("app");
const dialog = document.getElementById("merchant-dialog");
const detail = document.getElementById("merchant-detail");
const state = {
  page: "decision",
  catalogStats: null,
  result: null,
  preferences: {},
  editingNeeds: false,
  draft: "",
  lastRequest: null,
  failedRequest: false,
  lookupMessage: "",
  route: null,
  routeBusy: false,
  mapViews: {},
  scrollPositions: {},
  history: [],
  saved: new Set(),
  compared: new Map(),
  seen: new Set(),
  selected: null,
  busy: false,
  directory: [],
  directoryTotal: 0,
  directoryPage: 0,
  keyword: "",
  district: "",
  focusMerchant: null,
};
let toastTimer;
let pageVersion = 0;

function toast(message) {
  const element = document.getElementById("toast");
  element.textContent = message;
  element.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => element.classList.remove("visible"), 3500);
}

function clearToast() {
  clearTimeout(toastTimer);
  const element = document.getElementById("toast");
  element.classList.remove("visible");
  element.textContent = "";
}

function renderTray() {
  const tray = document.getElementById("compare-tray");
  tray.hidden = !state.compared.size;
  tray.innerHTML = `<span>已选 ${state.compared.size}/3 家</span><button class="button-primary" data-open-compare ${state.compared.size < 2 ? "disabled" : ""}>对比一下</button><button data-clear-compare>清空</button>`;
  document.getElementById("saved-count").textContent = state.saved.size;
}

function catalogSummary() {
  const stats = state.catalogStats;
  if (!stats) return '<p class="source-note">正在读取武汉商家资料…</p>';
  return `<div class="catalog-summary" data-catalog-count="${stats.public_total}">
    <span><strong>${stats.public_total}</strong> 家真实来源商家</span>
    <span><strong>${stats.mapped_total}</strong> 个地图点位</span>
    <details><summary>资料覆盖说明 ↗</summary><p>近五年来源资料。已收录 ${stats.priced_merchant_total} 家门店的 ${stats.priced_menu_items} 条菜品单价，其中 ${stats.priced_mapped_total} 家有坐标。未收录的价格、电话和营业时间会在资料卡中注明；记录不代表实时营业。</p></details></div>`;
}

function hasRecommendations() {
  return state.result?.stage === "candidates" && state.result.items.length > 0;
}

function selectedPlaceView() {
  return `<section id="selected-place" ${state.selected ? "" : "hidden"}>${state.selected ? choiceView(state.selected) + `<div id="walking-route">${walkingRouteView(state.selected, state.route, state.routeBusy, state.preferences.location)}</div>` : ""}</section>`;
}

function renderRecommendations() {
  window.NightFindWuhanMap?.dispose();
  const result = hasRecommendations() ? state.result : null;
  root.innerHTML = `<section class="page-intro"><span class="eyebrow">YOUR RESTAURANT PICKS</span>
    <h1 id="recommendations-title" tabindex="-1">本轮推荐商家</h1>
    <p>${result ? `已为你找到 ${result.items.length} 家候选商家，可以查看菜单、比较位置，再决定去哪。` : "先说说你的用餐打算，夜寻会在这里展示本轮推荐。"}</p>
    <div class="card-actions"><button type="button" data-page="decision">← 返回对话，调整需求</button></div></section>
    ${result ? `<section class="recommendation-summary" aria-label="本轮用餐条件">${constraintsView(result.constraints, result.budget_per_person)}</section>${selectedPlaceView()}${candidateResultsView(result, state.saved, state.compared)}` : '<div class="empty-state">还没有可展示的推荐，补充用餐条件后再试试。</div>'}`;
}

async function showDecisionResult(succeeded, requestVersion) {
  // A delayed response must not pull the visitor away from another page.
  if (state.page === "decision") {
    if (succeeded && requestVersion === pageVersion && hasRecommendations()) {
      toast(`推荐成功，已为你找到 ${state.result.items.length} 家候选商家`);
      state.scrollPositions.recommendations = 0;
      await navigate("recommendations");
      document
        .getElementById("recommendations-title")
        ?.focus({ preventScroll: true });
    } else renderDecision();
  } else if (state.page === "recommendations") renderRecommendations();
}

function renderDecision() {
  window.NightFindWuhanMap?.dispose();
  const result = state.result;
  const mode = result?.mode === "ai" ? "AI 理解" : "本地解析";
  const greeting = [
    {
      role: "assistant",
      text: "你好，我是夜寻。\n告诉我人数、预算和位置，我来帮你挑一家合适的餐厅。",
    },
  ];
  const preferences = Object.keys(state.preferences).length
    ? state.preferences
    : null;
  const suggestions = result?.follow_up?.actions?.length
    ? result.follow_up.actions.map((message) => ({ label: message, message }))
    : [
        {
          label: "安排双人晚餐",
          message: "明天晚上七点，两个人在江汉路附近，总预算200元，想吃湖北菜",
        },
        { label: "找一家咖啡店", message: "江汉路附近有哪些咖啡店" },
        { label: "查菜单与价格", message: "查金贵源的菜单价格" },
      ];
  root.innerHTML = `<section class="page-intro decision-intro"><div><span class="eyebrow ai-intro-label">✦ 夜寻 AI · 武汉餐饮助手</span>
    <h1>和 AI 聊聊，<span>今晚吃什么？</span></h1><p>把人数、预算和口味告诉夜寻，一起找到合适的那家店。</p></div>
    <div class="hero-art" aria-hidden="true"><svg viewBox="0 0 220 150" fill="none"><ellipse cx="111" cy="132" rx="77" ry="8" fill="#dce7d3"/><path d="M38 74h145c-4 38-30 56-72 56S43 112 38 74Z" fill="#e1ebd5" stroke="#779773" stroke-width="2"/><ellipse cx="111" cy="74" rx="73" ry="17" fill="#fafbf3" stroke="#779773" stroke-width="2"/><path d="M60 76c25-21 60-20 99-2M62 82c34-23 63-21 96-2M75 85c20-14 48-18 73-3" stroke="#b8ba83" stroke-width="3"/><path d="M127 62 167 17m-29 47 43-43" stroke="#7e8966" stroke-width="4" stroke-linecap="round"/><path d="M86 43c-13-13 11-15 1-29m23 35c-10-12 10-16 3-29" stroke="#a4b79a" stroke-width="2" stroke-linecap="round"/><path d="M47 61C24 57 19 43 21 32c20 1 31 11 26 29Z" fill="#ccddba"/><path d="m27 39 21 24" stroke="#8daa7d"/></svg><span>好好吃饭 · 慢慢选择</span></div></section>
    <div class="decision-workspace"><section class="decision-input" aria-label="AI 对话区域">
      <header class="chat-heading"><span class="helper-avatar" aria-hidden="true">AI</span><div><h2>夜寻 AI 对话</h2><p>从你的想法开始，帮你一步步选好餐厅。</p></div><span class="mode-pill">${mode} · 真实资料库</span></header>
      <div id="conversation-log" class="chat-messages" role="log" aria-label="与夜寻的对话" aria-live="polite">${(state
        .history.length
        ? state.history
        : greeting
      )
        .slice(-10)
        .map(
          (entry) =>
            `<div class="message ${entry.role === "user" ? "user" : "assistant"}">${entry.role === "user" ? "" : '<span class="message-avatar" aria-hidden="true">夜</span>'}<div class="message-content"><span class="sr-only">${entry.role === "user" ? "你" : "夜寻"}：</span>${e(entry.text)}</div></div>`,
        )
        .join("")}
        ${state.busy ? '<div class="thinking" role="status">夜寻正在整理你的需求 <span>···</span></div>' : ""}</div>
      <div class="quick-actions"><span>一键试问</span>${suggestions.map(({ label, message }) => `<button type="button" data-message="${e(message)}" title="${e(message)}" ${state.busy ? "disabled" : ""}>${e(label)} ↗</button>`).join("")}</div>
      <form id="decision-form" class="chat-composer"><div class="composer-heading"><label for="request-message">说说你的用餐需求</label><span>人数 · 预算 · 位置 · 时间 · 口味</span></div><textarea id="request-message" name="message" maxlength="2000" required placeholder="比如：今晚七点，四个人在江汉路附近，总共三百元，想吃湖北菜…" ${state.busy ? "disabled" : ""}>${e(state.draft)}</textarea>
        <div class="composer-actions"><div><button type="button" data-location ${state.busy ? "disabled" : ""}>⌖ 我的位置</button><button type="button" data-reset ${state.busy ? "disabled" : ""}>↻ 重新聊</button></div><button type="submit" class="button-primary" ${state.busy ? "disabled" : ""}>${state.busy ? "正在寻找…" : "开始推荐 ↗"}</button></div></form>
      <p class="chat-footnote">条件明确后，为你推荐最多 3 家候选商家。</p>
      ${state.failedRequest ? '<div class="request-error" role="alert">这次查询未完成，已保留输入与对话。<button type="button" data-retry-decision>重试查询</button></div>' : ""}
      ${result?.mode === "fallback" ? '<p class="source-note">AI 暂不可用，已切换本地条件解析。</p>' : ""}
    </section><aside class="decision-aside"><section class="conditions" aria-label="已理解的条件"><span class="eyebrow">YOUR DINING NOTES</span><h2>今晚的用餐笔记</h2><button type="button" class="edit-needs-button" data-edit-needs ${state.busy ? "disabled" : ""}>${state.editingNeeds ? "收起编辑" : "编辑条件 ✎"}</button>${state.editingNeeds ? preferencesEditor(state.preferences) : constraintsView(preferences, result?.budget_per_person)}</section>
      <details class="journey-note" ${state.editingNeeds ? "hidden" : ""}><summary>从聊天到出发，怎么用？</summary><ol><li><span>01</span><div><strong>聊聊你的想法</strong><small>人数、预算、位置与口味</small></div></li><li><span>02</span><div><strong>看看适合的店</strong><small>比较菜单、价格和真实位置</small></div></li><li><span>03</span><div><strong>选好，就出发</strong><small>打开地图，或联系门店</small></div></li></ol><button type="button" data-page="directory">去武汉地图逛逛 ↗</button></details></aside></div>
    ${catalogSummary()}
    ${selectedPlaceView()}
    ${candidateResultsView(result, state.saved, state.compared, state.failedRequest || state.busy)}`;
  document
    .getElementById("decision-form")
    .addEventListener("submit", (event) => {
      event.preventDefault();
      sendMessage(new FormData(event.currentTarget).get("message"));
    });
  document
    .getElementById("request-message")
    .addEventListener("input", (event) => {
      state.draft = event.target.value;
      saveConversation(state);
    });
  document
    .getElementById("preferences-form")
    ?.addEventListener("submit", applyPreferences);
  const log = document.getElementById("conversation-log");
  log.scrollTop = log.scrollHeight;
}

async function sendMessage(message, location) {
  if (!String(message || "").trim()) return;
  return runDecision(
    {
      message,
      context: state.preferences,
      location,
      previous_ids: state.result?.items.map((item) => item.id) || [],
      seen_ids: [...state.seen].slice(-100),
      keep_ids:
        state.result?.items
          .filter((item) => item.kept)
          .map((item) => item.id) || [],
    },
    message,
  );
}

async function runDecision(payload, historyText, appendUser = true) {
  if (state.busy) return;
  clearToast();
  const requestVersion = pageVersion;
  let succeeded = false;
  state.busy = true;
  state.failedRequest = false;
  state.lastRequest = payload;
  state.draft = "";
  if (appendUser) state.history.push({ role: "user", text: historyText });
  saveConversation(state);
  renderDecision();
  try {
    const result = await request("/api/decision", payload);
    if (
      JSON.stringify(result.constraints) !== JSON.stringify(state.preferences)
    )
      state.seen.clear();
    result.items.forEach((item) => state.seen.add(item.id));
    state.result = result;
    state.preferences = result.constraints;
    state.lookupMessage = result.stage === "catalog" ? payload.message : "";
    if (result.catalog_stats) state.catalogStats = result.catalog_stats;
    state.history.push({ role: "assistant", text: result.reply });
    state.selected = null;
    state.route = null;
    succeeded = true;
  } catch (error) {
    state.failedRequest = true;
    toast(error.message);
  } finally {
    state.busy = false;
    saveConversation(state);
    await showDecisionResult(succeeded, requestVersion);
  }
}

async function applyPreferences(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const text = (key) => String(data.get(key) || "").trim();
  const number = (key) => (text(key) ? Number(text(key)) : null);
  const name = text("location_name");
  const preferences = {
    ...state.preferences,
    party_size: number("party_size"),
    budget: number("budget"),
    budget_kind: text("budget_kind") || null,
    location: name
      ? name === state.preferences.location?.name
        ? state.preferences.location
        : { name }
      : null,
    arrival: text("arrival") ? `${text("arrival")}+08:00` : null,
    arrival_date_inferred: false,
    cuisine: text("cuisine"),
    avoid: text("avoid")
      .split(/[、,，;；]/)
      .map((value) => value.trim())
      .filter(Boolean),
    radius_km: number("radius_km"),
    priority: text("priority"),
    provenance: {
      ...state.preferences.provenance,
      party_size: "user",
      budget: "user",
      location: "user",
      cuisine: "user",
    },
  };
  // Validate on the server before replacing the current results or hiding this editor.
  const error = document.getElementById("preferences-error");
  const submit = form.querySelector('button[type="submit"]');
  const requestVersion = pageVersion;
  clearToast();
  submit.disabled = true;
  state.busy = true;
  try {
    const payload = {
      message: "按修改后的用餐条件重新筛选餐厅",
      preferences,
      intent: "plan",
    };
    const result = await request("/api/decision", payload);
    state.preferences = result.constraints;
    state.result = result;
    state.lastRequest = payload;
    state.lookupMessage = "";
    state.failedRequest = false;
    state.editingNeeds = false;
    state.selected = null;
    state.route = null;
    state.seen = new Set(result.items.map((item) => item.id));
    state.history.push(
      { role: "user", text: "我修改了用餐条件，请按新的条件筛选。" },
      { role: "assistant", text: result.reply },
    );
    saveConversation(state);
    state.busy = false;
    await showDecisionResult(true, requestVersion);
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
  } finally {
    state.busy = false;
    submit.disabled = false;
  }
}

async function loadWalkingRoute() {
  if (!state.selected || state.routeBusy) return;
  const id = state.selected.id;
  state.routeBusy = true;
  renderRoute();
  try {
    const route = await request("/api/walking-route", {
      merchant_id: id,
      origin: state.preferences.location,
    });
    if (state.selected?.id !== id) return;
    state.route = route;
  } catch (error) {
    if (state.selected?.id === id)
      state.route = { status: "unavailable", notice: error.message };
  } finally {
    state.routeBusy = false;
    renderRoute();
  }
}

async function renderRoute() {
  const container = document.getElementById("walking-route");
  if (!container || !state.selected) return;
  container.innerHTML = walkingRouteView(
    state.selected,
    state.route,
    state.routeBusy,
    state.preferences.location,
  );
  if (state.route?.status === "ready" && state.route.points.length) {
    const map = document.getElementById("route-map");
    map.hidden = false;
    const route = state.route;
    await window.NightFindWuhanMap?.draw(map, [state.selected]);
    if (route !== state.route || !map.isConnected) return;
    window.NightFindWuhanMap?.showRoute(route.points);
  }
}

async function renderDirectory(version) {
  root.innerHTML = `<section class="page-intro"><span class="eyebrow">${state.page === "saved" ? "YOUR LITTLE COLLECTION" : "EXPLORE WUHAN"}</span><h1>${state.page === "saved" ? "心仪的店，留给今晚。" : "沿着武汉，寻一口喜欢。"}</h1><p>${state.page === "saved" ? "把喜欢的店放在一起，下一顿就有了灵感。" : "看真实位置，翻翻菜单，再决定往哪走。"}</p></section>${catalogSummary()}
    ${state.page === "directory" ? `<form id="directory-form" class="directory-search"><label>店名、菜系或地址<input name="keyword" value="${e(state.keyword)}" maxlength="80"></label><label>行政区<input name="district" value="${e(state.district)}" placeholder="例如：江汉区"></label><button class="button-primary">搜索</button></form>` : ""}
    ${state.page === "directory" ? '<section class="directory-map-section"><div class="section-heading"><div><span class="eyebrow">WUHAN FOOD MAP</span><h2>武汉寻味地图</h2></div><button type="button" data-map-all>查看全部点位 ⤢</button></div><p id="directory-map-status" class="source-note">正在加载武汉底图和商家坐标…</p><div id="directory-map" class="decision-map" role="region" aria-label="武汉真实商家地图"></div><div class="map-caption"><span><i></i> 真实来源商家 · 点击查看资料</span><span>在线街道图不可用时显示武汉离线简图 · 可拖动缩放</span></div></section><div class="section-heading"><h2>发现武汉的味道</h2><span>每家店，资料有出处</span></div>' : ""}
    <div id="directory-results" class="decision-grid"><p>正在读取门店资料…</p></div><div id="directory-pagination" class="card-actions"></div>`;
  const form = document.getElementById("directory-form");
  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    const data = new FormData(form);
    state.keyword = data.get("keyword");
    state.district = data.get("district");
    state.directoryPage = 0;
    state.mapViews.directory = null;
    window.NightFindWuhanMap?.dispose();
    saveConversation(state);
    navigate("directory");
  });
  try {
    const query = new URLSearchParams({
      keyword: state.keyword,
      district: state.district,
      limit: "30",
      offset: String(state.directoryPage * 30),
    });
    const [listResult, mapResult] = await Promise.allSettled([
      request(
        state.page === "saved"
          ? "/api/real-favorites"
          : `/api/real-merchants?${query}`,
      ),
      state.page === "directory"
        ? request(
            `/api/real-map?${new URLSearchParams({ keyword: state.keyword, district: state.district })}`,
          )
        : Promise.resolve(null),
    ]);
    if (version !== pageVersion) return;
    if (listResult.status === "rejected") throw listResult.reason;
    const response = listResult.value;
    if (state.page === "directory") {
      const container = document.getElementById("directory-map");
      const status = document.getElementById("directory-map-status");
      if (mapResult.status === "fulfilled") {
        const mapped = mapResult.value;
        const drawn = await window.NightFindWuhanMap?.draw(
          container,
          mapped.items,
          { overview: !state.keyword && !state.district },
        );
        if (version !== pageVersion) return;
        container.dataset.pins = drawn?.pins || 0;
        status.textContent = `找到 ${mapped.total} 家商家，已载入 ${drawn?.pins || 0} 个来源坐标；地图展示全部筛选点位，不受列表分页限制。`;
        if (state.focusMerchant != null) {
          window.NightFindWuhanMap?.focus(state.focusMerchant);
          state.focusMerchant = null;
        } else
          window.NightFindWuhanMap?.restoreView(state.mapViews[state.page]);
      } else status.textContent = "地图资料暂不可用，仍可浏览下方列表。";
    }
    if (version !== pageVersion) return;
    state.directory = response.items;
    state.directoryTotal = response.total || 0;
    document.getElementById("directory-results").innerHTML = merchantCards(
      response.items,
      state.saved,
      state.compared,
    );
    if (state.page === "directory" && response.total > 30) {
      document.getElementById("directory-pagination").innerHTML =
        `<button data-directory-page="${state.directoryPage - 1}" ${state.directoryPage === 0 ? "disabled" : ""}>上一页</button><span>第 ${state.directoryPage + 1} 页 · 共 ${response.total} 家</span><button data-directory-page="${state.directoryPage + 1}" ${(state.directoryPage + 1) * 30 >= response.total ? "disabled" : ""}>下一页</button>`;
    }
  } catch (error) {
    if (version === pageVersion)
      document.getElementById("directory-results").textContent = error.message;
  }
}

async function navigate(page) {
  const focusing = state.focusMerchant != null;
  state.scrollPositions[state.page] = window.scrollY;
  const view = window.NightFindWuhanMap?.view();
  if (view) state.mapViews[state.page] = view;
  state.page = page;
  pageVersion += 1;
  window.NightFindWuhanMap?.dispose();
  document
    .querySelectorAll(".main-nav [data-page]")
    .forEach((button) =>
      button.classList.toggle("active", button.dataset.page === page),
    );
  if (page === "decision") renderDecision();
  else if (page === "recommendations") renderRecommendations();
  renderTray();
  if (!state.busy && (state.history.length || state.draft))
    saveConversation(state);
  if (page === "directory" || page === "saved")
    await renderDirectory(pageVersion);
  if (state.page === page && !focusing)
    window.scrollTo({
      top: state.scrollPositions[page] || 0,
      behavior: "instant",
    });
}

async function merchantById(id) {
  const detail = await request(`/api/real-merchants/${id}`);
  const candidate = state.result?.items.find((item) => item.id === id);
  return {
    ...detail,
    ...(candidate
      ? {
          questions: candidate.questions,
          distance_km: candidate.distance_km,
          reasons: candidate.reasons,
          estimated_total: candidate.estimated_total,
        }
      : {}),
  };
}

async function choose(id) {
  state.selected = await merchantById(id);
  state.route = null;
  saveConversation(state);
  dialog.close();
  await navigate(
    state.page === "recommendations" && hasRecommendations()
      ? "recommendations"
      : "decision",
  );
  document
    .getElementById("selected-place")
    .scrollIntoView({ behavior: "smooth", block: "center" });
}

function updateCardActions() {
  document.querySelectorAll("[data-save]").forEach((button) => {
    const active = state.saved.has(Number(button.dataset.save));
    button.setAttribute("aria-pressed", active);
    const name =
      button.closest("article")?.querySelector("h2")?.textContent || "门店";
    button.setAttribute("aria-label", `${active ? "取消收藏" : "收藏"}${name}`);
    button.textContent = active ? "♥" : "♡";
  });
  document.querySelectorAll("[data-compare]").forEach((button) => {
    const active = state.compared.has(Number(button.dataset.compare));
    button.setAttribute("aria-pressed", active);
    button.textContent = active ? "✓ 已选对比" : "+ 加入对比";
  });
  renderTray();
  saveConversation(state);
}

async function toggleSave(id) {
  const active = !state.saved.has(id);
  await request("/api/real-favorites", { merchant_id: id, active });
  if (active) state.saved.add(id);
  else state.saved.delete(id);
  if (state.page === "saved" && !active) {
    document.querySelector(`[data-card="${id}"]`)?.remove();
    if (!document.querySelector("[data-card]"))
      document.getElementById("directory-results").innerHTML = merchantCards(
        [],
        state.saved,
        state.compared,
      );
  }
  updateCardActions();
  toast(active ? "已保存到今晚清单" : "已取消收藏");
}

async function toggleCompare(id) {
  if (state.compared.has(id)) state.compared.delete(id);
  else {
    if (state.compared.size >= 3) return toast("最多比较三家，请先取消一项。");
    state.compared.set(id, await merchantById(id));
  }
  updateCardActions();
}

async function openComparison() {
  if (state.compared.size < 2) return;
  const ids = Array.from(state.compared.keys());
  const result = await request(`/api/real-compare?ids=${ids.join(",")}`);
  const items = result.items.map((item) => ({
    ...item,
    ...{
      distance_km: state.result?.items.find(
        (candidate) => candidate.id === item.id,
      )?.distance_km,
      questions: state.result?.items.find(
        (candidate) => candidate.id === item.id,
      )?.questions,
    },
  }));
  detail.innerHTML = comparisonView(items);
  dialog.showModal();
}

function locate() {
  if (state.busy) return;
  if (!navigator.geolocation)
    return toast("浏览器不支持定位，请输入出发商圈。");
  toast("请在浏览器中选择是否允许定位。");
  navigator.geolocation.getCurrentPosition(
    (position) => {
      sendMessage("使用我提供的当前位置", {
        name: "我的位置",
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      });
    },
    () => toast("未获取到位置，可以直接输入商圈或行政区。"),
    { timeout: 10000, maximumAge: 60000 },
  );
}

// One delegated action handler keeps dynamic cards and dialogs consistent.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button || button.disabled) return;
  try {
    if (button.dataset.page) return navigate(button.dataset.page);
    if (button.hasAttribute("data-close")) return dialog.close();
    if (button.hasAttribute("data-reset")) {
      state.result = null;
      state.history = [];
      state.seen.clear();
      state.selected = null;
      state.preferences = {};
      state.route = null;
      state.lastRequest = null;
      state.failedRequest = false;
      state.lookupMessage = "";
      state.draft = "";
      state.editingNeeds = false;
      clearConversation();
      return navigate("decision");
    }
    if (button.hasAttribute("data-location")) return locate();
    if (button.hasAttribute("data-edit-needs")) {
      state.editingNeeds = !state.editingNeeds;
      if (state.page !== "decision") await navigate("decision");
      else renderDecision();
      if (state.editingNeeds)
        document
          .getElementById("preferences-form")
          .scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    if (button.hasAttribute("data-retry-decision") && state.lastRequest)
      return await runDecision(state.lastRequest, "", false);
    if (button.hasAttribute("data-load-route")) return await loadWalkingRoute();
    if (button.dataset.message)
      return await sendMessage(button.dataset.message);
    if (button.dataset.detail) {
      detail.innerHTML = detailsView(
        await merchantById(Number(button.dataset.detail)),
      );
      return dialog.showModal();
    }
    if (button.dataset.choose)
      return await choose(Number(button.dataset.choose));
    if (button.dataset.save)
      return await toggleSave(Number(button.dataset.save));
    if (button.dataset.compare)
      return await toggleCompare(Number(button.dataset.compare));
    if (button.dataset.keep) {
      const item = state.result.items.find(
        (item) => item.id === Number(button.dataset.keep),
      );
      item.kept = !item.kept;
      button.setAttribute("aria-pressed", item.kept);
      button.textContent = item.kept ? "✓ 已保留" : "下轮保留";
      return;
    }
    if (button.hasAttribute("data-open-compare")) return await openComparison();
    if (button.hasAttribute("data-clear-compare")) {
      state.compared.clear();
      updateCardActions();
      return;
    }
    if (button.dataset.directoryPage != null) {
      state.directoryPage = Number(button.dataset.directoryPage);
      return navigate("directory");
    }
    if (button.hasAttribute("data-map-all"))
      return window.NightFindWuhanMap?.fitAll();
    if (button.dataset.mapMerchant) {
      const id = Number(button.dataset.mapMerchant);
      dialog.close();
      if (window.NightFindWuhanMap?.focus(id)) return;
      state.keyword = "";
      state.district = "";
      state.directoryPage = 0;
      state.focusMerchant = id;
      return await navigate("directory");
    }
    if (button.hasAttribute("data-show-map")) {
      const container = document.getElementById("decision-map");
      container.hidden = false;
      const result = await window.NightFindWuhanMap?.draw(
        container,
        state.result.items,
      );
      if (!result?.available)
        container.textContent =
          "地图暂不可用。选定门店后仍可打开导航，或在高德核对具体分店。";
      else if (!result.pins)
        toast("这些候选暂无可用坐标；选定后可按名称和地址在地图中查找。");
      container.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    // Map popups use the real merchant action generated by wuhan_map.js.
    if (button.dataset.realMerchant) {
      detail.innerHTML = detailsView(
        await merchantById(Number(button.dataset.realMerchant)),
      );
      dialog.showModal();
    }
  } catch (error) {
    toast(error.message);
  }
});

dialog.addEventListener("click", (event) => {
  if (event.target === dialog) dialog.close();
});
const restored = loadConversation();
if (restored) {
  state.history = (Array.isArray(restored.history) ? restored.history : [])
    .filter(
      (entry) =>
        entry &&
        ["user", "assistant"].includes(entry.role) &&
        typeof entry.text === "string",
    )
    .slice(-30);
  state.preferences =
    restored.preferences && typeof restored.preferences === "object"
      ? restored.preferences
      : {};
  state.draft =
    typeof restored.draft === "string" ? restored.draft.slice(0, 2000) : "";
  state.keyword =
    typeof restored.keyword === "string" ? restored.keyword.slice(0, 80) : "";
  state.district =
    typeof restored.district === "string" ? restored.district : "";
  state.lookupMessage = restored.lookupMessage || "";
  state.lastRequest = restored.lastRequest;
  state.failedRequest = !!restored.failedRequest;
}
const restorePageVersion = pageVersion;
state.busy = true;
renderDecision();
try {
  const [response, coverage] = await Promise.all([
    request("/api/real-favorites"),
    request("/api/real-merchants/coverage"),
  ]);
  state.saved = new Set(response.items.map((item) => item.id));
  state.catalogStats = coverage;
  if (
    restored &&
    state.history.length &&
    Object.keys(state.preferences).length &&
    !state.failedRequest
  ) {
    state.result = await request("/api/decision", {
      preferences: state.preferences,
      message: state.lookupMessage || "按已保存的条件继续选店",
      intent: restored.stage === "catalog" ? "lookup" : "plan",
    });
    state.preferences = state.result.constraints;
    if (Number.isInteger(restored.selectedId))
      state.selected = await merchantById(restored.selectedId).catch(
        () => null,
      );
    for (const id of (Array.isArray(restored.comparedIds)
      ? restored.comparedIds
      : []
    ).slice(0, 3)) {
      if (!Number.isInteger(id)) continue;
      const item = await merchantById(id).catch(() => null);
      if (item) state.compared.set(id, item);
    }
  }
} catch (error) {
  state.failedRequest = !!state.lastRequest;
  toast(error.message);
}
state.busy = false;
if (state.page === "decision") {
  if (
    restorePageVersion === pageVersion &&
    restored?.page === "recommendations" &&
    !state.failedRequest &&
    hasRecommendations()
  )
    await navigate("recommendations");
  else renderDecision();
}
renderTray();

// A blocked external image should leave the designed cover, not a broken-image icon.
document.addEventListener(
  "error",
  (event) => {
    if (!(event.target instanceof HTMLImageElement)) return;
    event.target.hidden = true;
    const caption = event.target.parentElement.querySelector(".image-caption");
    if (caption) caption.hidden = true;
    const credit = event.target
      .closest(".decision-card")
      ?.querySelector(".image-credit");
    if (credit) credit.hidden = true;
  },
  true,
);
````

<a id="source-31"></a>

## 31. static/botanical.svg

[打开原文件](../static/botanical.svg) · 9 行

SHA-256：`dc146944312747c4ad5479f4d6cf41ad3b4bdc3f1b8c4d243e6273180c2a19ce`

````xml
<svg xmlns="http://www.w3.org/2000/svg" width="180" height="660" viewBox="0 0 180 660" fill="none">
  <g stroke="#90ad85" stroke-width="1.2" stroke-linecap="round">
    <path d="M31 646C96 551 34 474 86 371S83 174 141 22"/>
    <path d="M74 504C30 502 8 460 12 428C50 433 76 460 74 504ZM76 431C112 421 144 388 143 355C108 366 78 395 76 431ZM86 365C43 345 34 312 41 283C75 296 93 328 86 365ZM99 263C137 247 160 213 154 183C118 199 99 231 99 263ZM104 217C67 195 65 161 72 132C105 153 112 183 104 217ZM124 85C155 76 170 50 167 29C139 39 125 60 124 85Z"/>
    <path d="M31 646C19 595 26 567 48 547C64 583 54 621 31 646ZM94 569C124 555 144 529 139 505C110 520 96 547 94 569Z"/>
    <circle cx="29" cy="329" r="3"/><circle cx="143" cy="293" r="4"/><circle cx="49" cy="85" r="3"/>
    <path d="M153 600v12m-6-6h12M28 218v12m-6-6h12"/>
  </g>
</svg>
````

<a id="source-32"></a>

## 32. static/decision-view.js

[打开原文件](../static/decision-view.js) · 281 行

SHA-256：`bc8067e37e44636ba2f764a75523c56c4b93ceb287d279cda33442fd22134f6a`

````javascript
/* Pure HTML renderers. API calls and mutable page state belong in app.js. */
export function escapeHtml(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
}
const e = escapeHtml;

export function externalLink(url, label, className = "") {
  try {
    if (!["https:", "http:", "tel:"].includes(new URL(url).protocol)) return "";
  } catch {
    return "";
  }
  return `<a class="${e(className)}" href="${e(url)}" target="_blank" rel="noopener noreferrer">${e(label)}</a>`;
}

export function priceLabel(item) {
  if (item.price_range_min != null && item.price_range_max != null) {
    const basis =
      item.price_range_basis === "per_person"
        ? "参考人均"
        : item.price_range_basis === "dish"
          ? "菜品参考价"
          : "来源参考价（单位未注明）";
    return `${basis} ¥${item.price_range_min}–${item.price_range_max}`;
  }
  return item.price_per_person != null
    ? `参考人均 ¥${item.price_per_person}`
    : "人均价格暂未收录";
}

function hasCoordinates(item) {
  return item.latitude != null && item.longitude != null;
}
function districtLabel(item) {
  return !item.district || item.district.includes("待确认")
    ? "武汉"
    : item.district;
}
function dishes(item) {
  return (item.signature_dishes || "").split(/[;；]/).filter(Boolean);
}
function mapAction(item) {
  return hasCoordinates(item)
    ? `<button type="button" data-map-merchant="${item.id}">⌖ 在地图查看</button>`
    : externalLink(item.map_search_url, "↗ 按店名查地图", "button-secondary");
}

export function constraintsView(context, budgetPerPerson) {
  if (!context)
    return `<div class="needs-empty"><span class="needs-symbol" aria-hidden="true">⌁</span>
    <p>先聊聊想吃什么，<br>我会帮你理清用餐需求。</p></div>
    <div class="condition-tags"><span>几个人</span><span>花多少钱</span><span>在哪吃</span><span>什么口味</span></div>`;
  const labels = [
    context.party_size ? `${context.party_size} 人同行` : "人数待补充",
    context.budget != null
      ? `${context.budget_kind === "total" ? "总预算" : context.budget_kind === "per_person" ? "人均" : "预算单位待补充"} ¥${context.budget}`
      : "预算待补充",
    context.location?.name || "出发位置待补充",
    context.arrival
      ? `${context.arrival.slice(0, 16).replace("T", " ")}（北京时间${context.arrival_date_inferred ? "，按今天推定" : ""}）`
      : "用餐时间待补充",
    context.cuisine || "不限口味",
    context.radius_km ? `直线距离 ≤ ${context.radius_km} km` : "",
    context.avoid?.length ? `忌口：${context.avoid.join("、")}` : "",
    context.wait_minutes != null
      ? `期望等位 ≤ ${context.wait_minutes} 分钟`
      : "",
  ].filter(Boolean);
  const derived =
    context.budget_kind === "total" && budgetPerPerson != null
      ? `<p class="source-note">按 ${context.party_size} 人计算，人均预算约 ¥${budgetPerPerson.toFixed(2)}。</p>`
      : "";
  return `<div class="condition-tags">${labels.map((label) => `<span>${e(label)}</span>`).join("")}</div>${derived}
    ${context.location?.note ? `<p class="source-note">${e(context.location.note)}</p>` : ""}`;
}

function coverView(item) {
  const cuisine = item.cuisine_display || item.cuisine || "风味餐饮";
  const category = /咖啡|coffee/i.test(cuisine)
    ? "咖"
    : /茶|tea/i.test(cuisine)
      ? "茶"
      : /面|noodle/i.test(cuisine)
        ? "面"
        : "食";
  const image = item.photo_url || item.cover_image_url;
  const caption = item.photo_url
    ? "门店照片"
    : item.cover_image_type === "dish_reference"
      ? "菜品参考图 · 非分店实拍"
      : item.cover_image_type === "storefront"
        ? "来源门店图"
        : "来源菜品图";
  return `<div class="merchant-cover" aria-label="${e(cuisine)}">
    <span class="cover-letter" aria-hidden="true">${category}</span><span class="cover-caption">${e(cuisine)}</span>
    ${image ? `<img src="${e(image)}" alt="${e(item.cover_image_caption || item.name)}" loading="lazy" referrerpolicy="no-referrer"><span class="image-caption">${caption}</span>` : ""}
    <span class="cover-location">${e(districtLabel(item))}</span></div>`;
}

export function merchantCards(items, saved, compared, showKeep = false) {
  if (!items.length)
    return '<div class="empty-state"><strong>还没有找到合适的门店</strong><p>试试更换关键词，或放宽预算和距离条件。</p></div>';
  return items
    .map(
      (item, index) => `<article class="decision-card" data-card="${item.id}">
    ${coverView(item)}<div class="merchant-card-body">
    ${item.cover_image_url && !item.photo_url ? `<div class="image-credit">${e(item.cover_image_author)} · ${externalLink(item.cover_image_license_url, item.cover_image_license)} · ${externalLink(item.cover_image_source_url, "图片来源")}</div>` : ""}
    <div class="merchant-title-row"><span class="eyebrow">${showKeep ? `候选 0${index + 1}` : e(item.source_name || "真实商家")}</span>
      <button type="button" class="save-icon" data-save="${item.id}" aria-label="${saved.has(item.id) ? "取消收藏" : "收藏"}${e(item.name)}" aria-pressed="${saved.has(item.id)}">${saved.has(item.id) ? "♥" : "♡"}</button></div>
    <h2>${e(item.name)}</h2>
    <div class="merchant-meta"><span>${e(item.cuisine_display || item.cuisine || "菜系暂未收录")}</span><span>${item.distance_km != null ? `距你约 ${e(item.distance_km)} km · 直线` : hasCoordinates(item) ? "已收录地图坐标" : "可按地址查找"}</span></div>
    <p class="merchant-price">${e(priceLabel(item))}</p>
    <dl class="card-facts"><div><dt>地址</dt><dd>${e(item.address || "来源未提供门牌地址，可查看坐标位置")}</dd></div>
      <div><dt>营业</dt><dd>${e(item.opening_hours || "时间暂未收录")}</dd></div>
      <div><dt>电话</dt><dd>${item.phone_url ? externalLink(item.phone_url, item.phone) : e(item.phone || "电话暂未收录")}</dd></div></dl>
    <div class="menu-preview"><h3>招牌与菜单</h3>${
      (item.priced_menu || []).length
        ? item.priced_menu
            .map(
              (dish) =>
                `<div class="menu-preview-row"><span>${e(dish.dish_name)}</span><strong>¥${e(dish.price)}<small> ${e(dish.price_unit)}</small></strong></div>`,
            )
            .join("")
        : dishes(item).length
          ? `<p>${dishes(item).slice(0, 4).map(e).join(" / ")}</p><small>菜品单价暂未收录</small>`
          : '<p class="muted">菜单与单价暂未收录，可查看商家来源。</p>'
    }</div>
    ${item.reasons?.length ? `<div class="recommendation-reason"><span>为什么选它</span><p>${item.reasons.map(e).join("；")}</p></div>` : ""}
    ${item.estimated_total != null ? `<p class="source-note">本次来源参考价估算 ¥${e(item.estimated_total)}，以实际消费为准。</p>` : ""}
    ${item.questions?.length ? `<details class="preflight-note"><summary>出发前的小提醒 · ${item.questions.length} 项</summary><ul>${item.questions.map((text) => `<li>${e(text)}</li>`).join("")}</ul></details>` : ""}
    <div class="merchant-source">${e(item.source_name || "公开资料")} · ${item.source_checked_at ? "来源日期 " : item.source_collected_at ? "采集 " : item.source_archived_at ? "归档 " : ""}${e(item.source_checked_at || item.source_collected_at || item.source_archived_at || "日期未注明")}</div>
    <div class="card-actions card-main-actions"><button type="button" class="button-primary" data-detail="${item.id}">查看菜单与资料 ↗</button>${mapAction(item)}</div>
    <div class="card-actions card-minor-actions"><button type="button" data-compare="${item.id}" aria-pressed="${compared.has(item.id)}">${compared.has(item.id) ? "✓ 已选对比" : "+ 加入对比"}</button>
    ${showKeep ? `<button type="button" data-keep="${item.id}" aria-pressed="${!!item.kept}">${item.kept ? "✓ 已保留" : "下轮保留"}</button>` : ""}
    <button type="button" data-choose="${item.id}">就选这家 →</button></div></div></article>`,
    )
    .join("");
}

export function detailsView(item) {
  const images =
    (item.photos || [])
      .map(
        (photo) =>
          `<figure><img src="${e(photo.photo_url)}" alt="${e(item.name)}的门店照片" loading="lazy"><figcaption>拍摄 ${e(photo.taken_at)} · ${e(photo.copyright_holder)}</figcaption></figure>`,
      )
      .join("") +
    (item.images || [])
      .map(
        (image) =>
          `<figure><img src="${e(image.image_url)}" alt="${e(image.caption)}" loading="lazy"><figcaption>${image.image_type === "dish_reference" ? "菜品参考图，非该分店实拍 · " : ""}${e(image.caption)} · ${e(image.author)} · ${externalLink(image.license_url, image.license) || e(image.license)}${image.taken_at ? ` · 拍摄 ${e(image.taken_at)}` : ""} · ${externalLink(image.source_url, "图片来源")}</figcaption></figure>`,
      )
      .join("");
  const menu = (item.menu_items || [])
    .map(
      (
        dish,
      ) => `<li class="detail-menu-row"><div><strong>${e(dish.dish_name)}</strong><span>${dish.price == null ? "单价暂未收录" : `¥${e(dish.price)} ${e(dish.price_unit)}`}</span></div>
    <small>${e(dish.price_note)} ${externalLink(dish.price_source_url, `价格来源 ${dish.price_checked_at || "日期未注明"}`)}</small></li>`,
    )
    .join("");
  return `<div class="detail-heading"><span class="eyebrow">RESTAURANT NOTES · 商家资料</span><h2>${e(item.name)}</h2><p>${e(districtLabel(item))} · ${e(item.cuisine_display || item.cuisine)}</p><strong class="merchant-price">${e(priceLabel(item))}</strong></div>
    <section class="detail-section"><h3>到店信息</h3><dl class="detail-facts">
      <div><dt>详细地址</dt><dd>${e(item.address || "门牌地址暂未收录")}</dd></div>
      <div><dt>营业时间</dt><dd>${e(item.opening_hours || "时间暂未收录，请联系门店确认")}</dd></div>
      <div><dt>联系电话</dt><dd>${item.phone_url ? externalLink(item.phone_url, item.phone) : e(item.phone || "电话暂未收录")}</dd></div>
      <div><dt>经纬坐标</dt><dd>${hasCoordinates(item) ? `${e(item.longitude)}, ${e(item.latitude)}（经度、纬度 · WGS84）` : "来源未提供可靠坐标，可按店名和地址查找"}</dd></div>
    </dl>${item.location_note ? `<p class="source-note">${e(item.location_note)}</p>` : ""}<div class="card-actions">${mapAction(item)}${externalLink(item.navigation_url, "打开导航 ↗", "button-secondary")}</div></section>
    <section class="detail-section"><div class="section-heading"><h3>菜单与参考价格</h3><span>按门店来源展示</span></div>
      ${
        dishes(item).length
          ? `<div class="condition-tags">${dishes(item)
              .map((dish) => `<span>${e(dish)}</span>`)
              .join("")}</div>`
          : ""
      }
      <ul class="detail-menu">${menu || '<li class="muted">该门店暂未收录有来源的菜单，可前往原始网页查看。</li>'}</ul><p class="source-note">来源参考价，实际售价、菜品供应及营业时间以门店为准。</p></section>
    ${images ? `<section class="detail-section"><h3>图片资料</h3><div class="evidence-gallery">${images}</div></section>` : ""}
    <details class="detail-provenance"><summary>资料来源与更新日期</summary><p>${e(item.quality_label)} · ${e(item.evidence_label)}</p>
      <p>${externalLink(item.source_url, item.source_name || "商家原始来源")}</p>
      ${item.evidence_url ? `<p>${externalLink(item.evidence_url, "查看归档证据")}</p>` : ""}
      ${item.source_updated_at ? `<p>源记录更新：${e(item.source_updated_at)}</p>` : ""}<p>网上收录不代表实时营业；资料未注明的内容保留为空。</p></details>
    <div class="detail-footer"><span>喜欢这家？把今晚的去处定下来。</span><button type="button" class="button-primary" data-choose="${item.id}">就选这家 →</button></div>`;
}

export function choiceView(item) {
  return `<span class="eyebrow">TONIGHT'S CHOICE · 今晚有着落了</span><h2>${e(item.name)}</h2><p>${e(item.address || item.district)} · ${e(priceLabel(item))}</p>
    <p class="source-note">${e(item.navigation_notice)}</p><div class="card-actions">${externalLink(item.navigation_url, "打开导航 ↗", "button-primary")}${externalLink(item.map_search_url, "在高德查看分店", "button-secondary")}
    ${item.phone_url ? externalLink(item.phone_url, `联系门店 ${item.phone}`, "button-secondary") : '<span class="source-note">门店电话暂未收录</span>'}${externalLink(item.source_url, "商家来源 ↗")}</div>
    <p class="source-note">营业与座位可在出发前向门店确认。导航和预订由外部平台提供，当前操作不会代为订座。</p>`;
}

export function comparisonView(items) {
  const rows = [
    ["参考价格", priceLabel],
    ["详细地址", (item) => item.address || "暂未收录"],
    ["菜系", (item) => item.cuisine_display || item.cuisine],
    ["招牌菜", (item) => dishes(item).join("、") || "暂未收录"],
    [
      "菜单价格",
      (item) =>
        (item.menu_items || [])
          .filter((dish) => dish.price != null)
          .map((dish) => `${dish.dish_name} ¥${dish.price} ${dish.price_unit}`)
          .join("；") || "单价暂未收录",
    ],
    [
      "直线距离",
      (item) =>
        item.distance_km != null ? `${item.distance_km} km` : "待提供出发位置",
    ],
    ["营业时间", (item) => item.opening_hours || "暂未收录"],
    ["联系电话", (item) => item.phone || "暂未收录"],
    ["资料来源", (item) => `${item.source_name} · ${item.evidence_label}`],
  ];
  return `<span class="eyebrow">SIDE BY SIDE · 一起比一比</span><h2>哪一家，更合今晚的心意？</h2><p class="muted">把价格、位置和口味放在一起，慢慢选。</p>
    <div class="comparison-scroll"><table><thead><tr><th>比较项目</th>${items.map((item) => `<th>${e(item.name)}</th>`).join("")}</tr></thead><tbody>
    ${rows.map(([label, render]) => `<tr><th>${label}</th>${items.map((item) => `<td>${e(render(item))}</td>`).join("")}</tr>`).join("")}
    <tr><th>作出选择</th>${items.map((item) => `<td><button type="button" class="button-primary" data-choose="${item.id}">就选这家</button></td>`).join("")}</tr></tbody></table></div>`;
}

export function preferencesEditor(preferences = {}) {
  return `<form id="preferences-form" class="preferences-form">
    <label>用餐人数<input name="party_size" type="number" min="1" max="50" step="1" value="${e(preferences.party_size)}" placeholder="几个人"></label>
    <label>预算金额<input name="budget" type="number" min="1" max="100000" value="${e(preferences.budget)}" placeholder="多少元"></label>
    <label>预算单位<select name="budget_kind"><option value="">请选择</option><option value="per_person" ${preferences.budget_kind === "per_person" ? "selected" : ""}>每人预算</option><option value="total" ${preferences.budget_kind === "total" ? "selected" : ""}>全部人的总预算</option></select></label>
    <label>出发位置<input name="location_name" value="${e(preferences.location?.name)}" placeholder="江汉路、光谷或武汉行政区"></label>
    <label>到店时间（北京时间）<input name="arrival" type="datetime-local" value="${e(preferences.arrival?.slice(0, 16))}"></label>
    <label>口味偏好<input name="cuisine" maxlength="40" value="${e(preferences.cuisine)}" placeholder="例如湖北菜，留空则不限"></label>
    <label>忌口 / 过敏<input name="avoid" maxlength="400" value="${e((preferences.avoid || []).join("、"))}" placeholder="例如花生、海鲜"></label>
    <label>最大直线距离（km）<input name="radius_km" type="number" step="0.1" min="0.1" max="100" value="${e(preferences.radius_km)}" placeholder="留空则不限"></label>
    <label>更看重什么<select name="priority">${[
      ["balanced", "综合考虑"],
      ["distance", "距离更近"],
      ["budget", "价格更低"],
    ]
      .map(
        ([value, label]) =>
          `<option value="${value}" ${preferences.priority === value ? "selected" : ""}>${label}</option>`,
      )
      .join("")}</select></label>
    <p id="preferences-error" class="form-error" role="alert" hidden></p>
    <div class="card-actions"><button class="button-primary" type="submit">保存并重新筛选</button><button type="button" data-edit-needs>取消</button></div>
    <p class="source-note">修改条件会保留对话。已识别的商圈中心用于直线估算，不代表精确出发地址。</p></form>`;
}

export function walkingRouteView(item, route, busy, origin) {
  if (!hasCoordinates(item))
    return '<p class="source-note">该门店尚无可靠坐标，可按店名与地址在外部地图查找。</p>';
  if (!origin || origin.latitude == null || origin.longitude == null)
    return '<div class="route-empty"><p>设置出发位置，就能继续查看步行路线。</p><button type="button" data-edit-needs>设置出发位置</button></div>';
  const actions = `<div class="card-actions"><button type="button" data-load-route ${busy ? "disabled" : ""}>${busy ? "正在查询…" : route ? "重新查询路线" : "查询步行路线"}</button>${route?.navigation_url ? externalLink(route.navigation_url, "在高德继续导航 ↗", "button-secondary") : ""}</div>`;
  if (!route || route.status !== "ready")
    return `<div class="route-empty"><p>${e(route?.notice || `从${origin.name}出发，查询实际步行距离与预计用时。`)}</p>${actions}</div>`;
  return `<section class="walking-route"><div class="route-facts"><strong>${route.distance_m >= 1000 ? `${(route.distance_m / 1000).toFixed(1)} km` : `${route.distance_m} m`}</strong><span>预计步行 ${Math.max(1, Math.ceil(route.duration_seconds / 60))} 分钟</span></div>
    <p class="source-note">${e(route.source_name)} · ${e(route.origin_name)}出发。${e(route.origin_note)} 路线与时间为服务估计，以实际道路情况为准。</p>
    ${actions}${route.steps?.length ? `<details><summary>查看步行指引</summary><ol>${route.steps.map((step) => `<li>${e(step)}</li>`).join("")}</ol></details>` : ""}
    <div id="route-map" class="decision-map" role="region" aria-label="选定餐厅步行路线地图" hidden></div></section>`;
}

export function candidateResultsView(result, saved, compared, stale = false) {
  if (!result) return "";
  return `<section class="candidate-section" aria-live="polite"><div class="section-heading"><div><span class="eyebrow">PICK YOUR FAVORITE</span><h2>${result.stage === "clarify" ? "再补充一点，就更合适了" : result.stage === "catalog" ? "在武汉，为你找到这些店" : "这几家，值得你看看"}</h2></div>${result.items.length ? '<button type="button" data-show-map>⌖ 在地图上比较</button>' : ""}</div>
      ${stale ? '<p class="source-note">以下保留上一轮结果，本次查询尚未完成。</p>' : ""}<p class="reply-text muted">${e(result.reply)}</p>
      ${result.items.length ? `<div class="decision-grid">${merchantCards(result.items, saved, compared, true)}</div><div id="decision-map" class="decision-map" hidden role="region" aria-label="候选餐厅地图"></div>` : ""}
      ${
        Object.keys(result.excluded).length
          ? `<details class="filter-explanation"><summary>查看其他门店的筛选原因</summary><ul>${Object.entries(
              result.excluded,
            )
              .map(([reason, count]) => `<li>${e(reason)}：${count} 家</li>`)
              .join("")}</ul></details>`
          : ""
      }</section>`;
}
````

<a id="source-33"></a>

## 33. static/decision.css

[打开原文件](../static/decision.css) · 1250 行

SHA-256：`43af9005e4635c02c80a6f8725e00fd8a350698170f239b0b383e79d55775e79`

````css
/* AI workspace, merchant dossiers, and Wuhan map. Shared tokens: style.css. */
.decision-intro {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
  margin-bottom: 24px;
}
.ai-intro-label {
  padding: 5px 11px;
  border: 1px solid var(--green-deep);
  border-radius: 20px;
  background: var(--green-deep);
  color: #e1f5a6;
  letter-spacing: 1px;
}
.hero-art {
  width: 150px;
  flex-shrink: 0;
  margin-right: 20px;
  padding: 12px;
  border: 1px solid #b4d877;
  border-radius: 32px 16px 32px 16px;
  background: #d7ee9f;
  text-align: center;
}
.hero-art svg {
  width: 100%;
  display: block;
}
.hero-art span {
  font-size: 10px;
  color: #536d43;
  letter-spacing: 2px;
}
.decision-workspace {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(220px, 1fr);
  gap: 22px;
  align-items: start;
}
.decision-input {
  border: 1px solid #96c6aa;
  border-top: 4px solid var(--green);
  border-radius: 24px;
  background: var(--surface);
  box-shadow: 0 20px 55px #125a3922;
  padding: 26px;
  min-width: 0;
}
.chat-heading {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding-bottom: 18px;
  border-bottom: 1px solid #e9eedf;
}
.helper-avatar,
.message-avatar {
  display: grid;
  place-items: center;
  flex-shrink: 0;
  background: var(--green-pale);
  color: var(--green-dark);
  font-family: serif;
}
.helper-avatar {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  font:
    650 19px system-ui,
    sans-serif;
  background: var(--green-dark);
  color: #fbfff5;
}
.chat-heading h2 {
  font-size: 21px;
  margin: 0 0 2px;
}
.chat-heading p {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
}
.mode-pill {
  font-size: 10px;
  background: #f0f5e9;
  color: #708561;
  border-radius: 20px;
  padding: 6px 10px;
  white-space: nowrap;
}
.chat-messages {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-height: 180px;
  max-height: 360px;
  overflow-y: auto;
  padding: 24px 0 20px;
  scrollbar-width: thin;
}
.message {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.message-avatar {
  width: 28px;
  height: 28px;
  border-radius: 10px;
  font-size: 13px;
}
.message-content {
  padding: 13px 17px;
  max-width: 87%;
  border-radius: 3px 16px 16px;
  background: #f0f4e9;
  font-size: 14px;
  line-height: 1.9;
  white-space: pre-line;
  overflow-wrap: anywhere;
}
.message.user {
  justify-content: flex-end;
}
.message.user .message-content {
  background: #e0ecd6;
  border-radius: 16px 3px 16px 16px;
}
.thinking {
  color: var(--muted);
  font-size: 12px;
}
.thinking span {
  letter-spacing: 4px;
}
.quick-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 7px;
  margin-bottom: 16px;
}
.quick-actions > span {
  font-size: 11px;
  color: var(--muted);
}
.quick-actions button {
  padding: 7px 11px;
  font-size: 12px;
  border-radius: 20px;
  background: #fafbf5;
}
.chat-composer {
  padding: 16px;
  border: 1px solid #b9cfa9;
  background: #f5f9ef;
  border-radius: 16px;
}
.chat-composer:focus-within {
  border-color: #709762;
  box-shadow: 0 0 0 4px #70976214;
}
.composer-heading {
  display: flex;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 4px 12px;
  margin-bottom: 9px;
}
.composer-heading label {
  font-size: 12px;
  font-weight: 600;
  color: var(--green-dark);
}
.composer-heading span {
  font-size: 10px;
  color: var(--muted);
}
.chat-footnote {
  font-size: 10px;
  color: var(--muted);
  margin: 12px 0 0;
}
#request-message {
  display: block;
  width: 100%;
  height: 100px;
  min-height: 80px;
  max-height: 250px;
  resize: vertical;
  padding: 2px 2px 10px;
  border: 0;
  background: transparent;
  color: var(--ink);
  font-size: 15px;
  line-height: 1.8;
}
#request-message::placeholder {
  color: #98a18f;
}
#request-message:focus-visible {
  outline-offset: 2px;
}
.composer-actions {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}
.composer-actions > div {
  display: flex;
  gap: 4px;
}
.composer-actions > div button {
  border: 0;
  padding: 5px 6px;
  background: transparent;
  color: var(--muted);
  font-size: 11px;
}
.composer-actions > .button-primary {
  padding: 11px 21px;
  font-size: 14px;
}
.decision-aside {
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 16px;
}
.conditions {
  padding: 23px;
  border: 1px solid #d6e1cb;
  border-radius: 22px;
  background: #f5f8ef;
}
.conditions h2 {
  margin: 6px 0 14px;
  font-size: 15px;
}
.needs-empty {
  display: flex;
  gap: 12px;
  align-items: center;
}
.needs-empty p {
  color: #7b8a70;
  font-size: 12px;
  margin: 0;
}
.needs-symbol {
  color: #a0b28c;
  font-size: 40px;
}
.condition-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin: 14px 0 0;
}
.condition-tags span {
  border: 1px solid #dbe5d2;
  background: #f7faf2;
  padding: 4px 9px;
  border-radius: 7px;
  font-size: 11px;
}
.journey-note {
  padding: 20px 23px;
  border: 1px solid var(--green-line);
  border-radius: 22px;
  background: #fffefa99;
}
.journey-note summary {
  cursor: pointer;
  color: var(--muted);
  font-size: 12px;
}
.journey-note ol {
  list-style: none;
  padding: 0;
  margin: 16px 0;
}
.journey-note li {
  display: flex;
  gap: 14px;
  align-items: center;
  margin: 12px 0;
}
.journey-note li > span {
  color: #a2b38a;
  font-family: Georgia, serif;
  font-size: 21px;
}
.journey-note strong {
  display: block;
  font-size: 12px;
  font-weight: 500;
}
.journey-note small {
  display: block;
  color: var(--muted);
  font-size: 10px;
}
.journey-note > button {
  padding: 0;
  border: 0;
  background: transparent;
  font-size: 11px;
}
.catalog-summary {
  position: relative;
  display: flex;
  align-items: center;
  gap: 25px;
  flex-wrap: wrap;
  color: var(--muted);
  font-size: 11px;
  padding: 18px 0;
  margin: 8px 0 22px;
  border-bottom: 1px solid var(--green-line);
}
.catalog-summary strong {
  font-size: 16px;
  color: #6a805b;
  font-family: Georgia, serif;
  font-weight: 500;
  margin-right: 3px;
}
.catalog-summary details {
  margin-left: auto;
  max-width: 100%;
}
.catalog-summary summary {
  cursor: pointer;
  font-size: 10px;
}
.catalog-summary details p {
  margin: 10px 0 0;
  max-width: 420px;
  font-size: 11px;
}
.section-heading {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-bottom: 16px;
}
.section-heading h2,
.section-heading h3 {
  margin: 0;
}
.section-heading h2 {
  margin-top: 6px;
}
.section-heading > span {
  color: var(--muted);
  font-size: 11px;
}
.section-heading > button {
  font-size: 12px;
}
.reply-text {
  white-space: pre-line;
  font-size: 13px;
  margin-bottom: 22px;
}
.candidate-section {
  margin-top: 32px;
}
.recommendation-summary {
  padding: 18px 22px;
  border: 1px solid var(--green-line);
  border-radius: 18px;
  background: var(--surface);
}
.recommendation-summary .condition-tags {
  margin-top: 0;
}

/* Merchant cards expose useful facts; provenance and longer reminders can expand. */
.decision-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
  align-items: stretch;
}
.decision-card {
  border: 1px solid var(--green-line);
  border-radius: 20px;
  background: var(--surface);
  min-width: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow);
}
.merchant-cover {
  position: relative;
  height: 105px;
  overflow: hidden;
  background:
    radial-gradient(circle at 80% 0, #f0edce 0, transparent 60%), #e5eddc;
}
.merchant-cover::before,
.merchant-cover::after {
  content: "";
  position: absolute;
  width: 150px;
  height: 150px;
  border: 1px solid #a8bd9560;
  border-radius: 50%;
  top: 22px;
  right: 18px;
}
.merchant-cover::after {
  width: 116px;
  height: 116px;
  top: 39px;
  right: 35px;
}
.cover-letter {
  position: absolute;
  right: 67px;
  top: 13px;
  color: #71866c;
  opacity: 0.55;
  font-family: serif;
  font-size: 57px;
}
.cover-caption {
  position: absolute;
  left: 20px;
  bottom: 21px;
  color: #76886b;
  font-size: 11px;
  letter-spacing: 2px;
  max-width: 55%;
}
.merchant-cover img {
  position: absolute;
  width: 100%;
  height: 100%;
  object-fit: cover;
  z-index: 1;
}
.cover-location,
.image-caption {
  position: absolute;
  z-index: 2;
  top: 12px;
  left: 15px;
  border-radius: 6px;
  padding: 3px 8px;
  background: #fffefaeb;
  color: #68795f;
  font-size: 10px;
}
.image-caption {
  top: auto;
  bottom: 9px;
  font-size: 9px;
  background: #fffefae0;
}
.merchant-card-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  padding: 18px 20px 14px;
}
.merchant-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.merchant-title-row .eyebrow {
  font-size: 9px;
  letter-spacing: 1px;
}
.save-icon {
  border: 0;
  background: transparent;
  border-radius: 50%;
  padding: 0;
  width: 28px;
  height: 28px;
  font-size: 22px;
  line-height: 1;
  color: #8a9b7b;
}
.decision-card h2 {
  font-size: 18px;
  margin: 3px 0 7px;
  overflow-wrap: anywhere;
}
.merchant-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px 12px;
  font-size: 10px;
  color: #819075;
}
.merchant-price {
  display: block;
  font-size: 15px;
  font-weight: 600;
  color: #56794c;
  margin: 14px 0;
}
.card-facts {
  margin: 0 0 14px;
  font-size: 11px;
}
.card-facts > div,
.detail-facts > div {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 10px;
  margin-bottom: 7px;
}
.card-facts dt,
.detail-facts dt {
  color: #8b9683;
}
.card-facts dd,
.detail-facts dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.menu-preview {
  padding: 12px 13px;
  border-radius: 12px;
  background: #f4f7ee;
  margin-bottom: 14px;
}
.menu-preview h3 {
  font-size: 10px;
  color: #849278;
  font-weight: 500;
  margin: 0 0 7px;
}
.menu-preview p {
  font-size: 11px;
  margin: 0;
}
.menu-preview small {
  color: var(--muted);
  font-size: 10px;
  font-weight: 400;
}
.menu-preview-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  margin-top: 5px;
}
.menu-preview-row strong {
  white-space: nowrap;
  font-weight: 500;
  color: var(--green);
}
.recommendation-reason {
  margin: 0 0 12px;
  padding-left: 10px;
  border-left: 2px solid #b7cba4;
}
.recommendation-reason > span {
  font-size: 10px;
  color: #6e865e;
}
.recommendation-reason p {
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--muted);
}
.preflight-note {
  font-size: 10px;
  color: #8e805c;
  margin-bottom: 12px;
}
.preflight-note summary,
.filter-explanation summary {
  cursor: pointer;
}
.preflight-note ul {
  padding-left: 16px;
}
.merchant-source {
  margin-top: auto;
  padding-top: 10px;
  border-top: 1px dashed var(--green-line);
  font-size: 9px;
  color: #8c9883;
}
.card-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 14px 0;
}
.card-main-actions {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 7px;
  margin: 12px 0;
}
.card-main-actions button,
.card-main-actions a {
  padding: 9px 5px;
  font-size: 10px;
  border-radius: 9px;
}
.card-minor-actions {
  justify-content: space-between;
  gap: 6px;
  margin: 0;
}
.card-minor-actions button {
  padding: 2px 3px;
  background: transparent;
  border: 0;
  font-size: 10px;
  color: #7b8d70;
}
.card-minor-actions button[aria-pressed="true"] {
  color: var(--green-deep);
}
.filter-explanation {
  font-size: 12px;
  color: var(--muted);
  margin-top: 18px;
}
#selected-place {
  border: 1px solid #b4cba1;
  border-radius: 20px;
  background: #e8f0df;
  padding: 25px;
  margin-top: 24px;
}
#selected-place h2 {
  margin: 8px 0 12px;
}
#selected-place > p {
  font-size: 13px;
}

/* Directory and locally served geographic map. */
.directory-search {
  display: flex;
  align-items: end;
  gap: 14px;
  padding: 20px;
  border: 1px solid var(--green-line);
  border-radius: 18px;
  background: var(--surface);
  margin-bottom: 28px;
}
.directory-search label {
  display: grid;
  gap: 7px;
  font-size: 11px;
  color: var(--muted);
  min-width: 0;
}
.directory-search label:first-child {
  flex: 1;
}
.directory-search input {
  min-width: 0;
  width: 100%;
  padding: 9px 12px;
  border: 1px solid var(--green-line);
  border-radius: 10px;
  background: #fafcf5;
  color: var(--ink);
}
.directory-map-section {
  padding: 22px;
  border: 1px solid var(--green-line);
  border-radius: 22px;
  background: var(--surface);
  margin-bottom: 32px;
}
.directory-map-section .section-heading {
  margin-bottom: 8px;
}
.decision-map {
  height: 440px;
  border: 1px solid #d4dfcb;
  border-radius: 16px;
  background: #e6eddf;
  z-index: 0;
}
#decision-map {
  margin-top: 22px;
}
.directory-map-section .decision-map {
  height: 480px;
}
.map-caption {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
  color: var(--muted);
  font-size: 10px;
  flex-wrap: wrap;
}
.map-caption i {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #4f805f;
  margin-right: 4px;
}
.map-place-label {
  font-family: "Microsoft YaHei", sans-serif;
  color: #7c8370;
  font-size: 10px;
  text-align: center;
  white-space: nowrap;
  text-shadow:
    0 0 3px #fff,
    1px 1px 2px #fff;
}
.label-water_label {
  color: #527c8e;
  font-size: 12px;
  letter-spacing: 2px;
}
.label-park {
  color: #547c4b;
}
.label-station {
  color: #7b7890;
}
.real-map-popup {
  font-family: "Microsoft YaHei", sans-serif;
}
.real-map-popup h3 {
  font-size: 17px;
  margin: 8px 0;
  color: var(--green-deep);
}
.real-map-popup p {
  margin: 8px 0 !important;
  font-size: 12px;
  line-height: 1.7;
}
.real-map-popup small {
  font-size: 10px;
  color: var(--muted);
  line-height: 1.8;
}
.real-map-popup button {
  width: 100%;
  margin-top: 12px;
  padding: 8px;
}
.map-popup-price {
  color: var(--green);
}
.map-load-error {
  background: #fff9e7;
  color: #826b35;
  padding: 12px;
  border-radius: 10px;
  max-width: 240px;
}
.leaflet-control-attribution {
  font-size: 9px !important;
}

/* Modal dossier, comparison table and floating collection tray. */
.detail-heading {
  padding: 6px 25px 20px 0;
  border-bottom: 1px solid var(--green-line);
}
.detail-heading h2 {
  font-size: 26px;
  margin: 10px 0;
}
.detail-heading p {
  font-size: 12px;
  color: var(--muted);
}
.detail-heading .merchant-price {
  margin: 12px 0 0;
}
.detail-section {
  margin: 23px 0;
}
.detail-section h3 {
  margin-bottom: 14px;
  font-size: 15px;
}
.detail-facts {
  padding: 0;
  background: transparent;
}
.detail-facts > div {
  grid-template-columns: 70px minmax(0, 1fr);
  font-size: 13px;
  margin-bottom: 12px;
}
.detail-menu {
  list-style: none;
  padding: 0;
  margin: 14px 0;
}
.detail-menu-row {
  padding: 13px 0;
  border-bottom: 1px solid #e8eddf;
}
.detail-menu-row > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}
.detail-menu-row strong {
  font-weight: 500;
}
.detail-menu-row span {
  color: var(--green);
  white-space: nowrap;
}
.detail-menu-row small {
  font-size: 10px;
  color: var(--muted);
}
.detail-provenance {
  border: 1px solid var(--green-line);
  background: #f6f9f0;
  border-radius: 12px;
  padding: 14px;
  font-size: 11px;
}
.detail-provenance summary {
  cursor: pointer;
}
.detail-provenance p {
  margin: 10px 0 0;
  overflow-wrap: anywhere;
}
.detail-footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-top: 24px;
}
.detail-footer > span {
  color: var(--muted);
  font-size: 12px;
}
.evidence-gallery {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}
.evidence-gallery figure {
  width: min(220px, 100%);
  margin: 0;
}
.evidence-gallery img {
  width: 100%;
  max-height: 170px;
  object-fit: cover;
  border-radius: 10px;
}
.evidence-gallery figcaption {
  margin-top: 8px;
  font-size: 9px;
}
.comparison-scroll {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
th,
td {
  padding: 14px;
  border: 1px solid var(--green-line);
  min-width: 145px;
  text-align: left;
  vertical-align: top;
}
th {
  background: #f0f5e8;
  font-weight: 500;
}
.compare-tray {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 12px 20px;
  border: 1px solid #c6d8b6;
  border-radius: 18px;
  background: #fffefaf5;
  box-shadow: 0 8px 30px #3c593420;
  font-size: 12px;
}
#directory-pagination {
  justify-content: center;
  margin-top: 28px;
}
@media (max-width: 950px) {
  .decision-workspace {
    grid-template-columns: minmax(0, 2.6fr) 220px;
    gap: 16px;
  }
  .decision-input,
  .conditions,
  .journey-note {
    padding: 18px;
  }
  .mode-pill {
    font-size: 9px;
    padding: 4px 6px;
  }
  .decision-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .hero-art {
    margin-right: 0;
    width: 125px;
  }
}
/* Keep the composer in view on shorter laptop screens. */
@media (min-width: 701px) and (max-height: 800px) {
  .decision-intro {
    margin-bottom: 18px;
  }
  .decision-intro h1 {
    font-size: 34px;
    margin: 8px 0;
  }
  .hero-art {
    width: 120px;
  }
  .decision-input {
    padding: 18px;
  }
  .chat-messages {
    min-height: 120px;
    padding: 18px 0;
  }
  #request-message {
    height: 85px;
  }
}
@media (max-width: 700px) {
  .decision-workspace {
    grid-template-columns: 1fr;
  }
  .decision-aside {
    grid-template-columns: 1fr 1fr;
    grid-template-rows: auto;
    gap: 12px;
  }
  .hero-art {
    display: none;
  }
  .conditions,
  .journey-note {
    padding: 16px;
  }
  .journey-note li {
    gap: 8px;
  }
  .journey-note small {
    font-size: 9px;
  }
  .catalog-summary {
    gap: 10px 18px;
  }
  .catalog-summary details {
    margin-left: 0;
  }
  .directory-search {
    flex-wrap: wrap;
    padding: 16px;
  }
  .directory-search label:first-child {
    flex-basis: 100%;
  }
  .directory-search label {
    flex: 1;
  }
  .directory-map-section {
    padding: 16px;
  }
  .directory-map-section .decision-map,
  .decision-map {
    height: 370px;
  }
}
@media (max-width: 480px) {
  .decision-intro .ai-intro-label {
    font-size: 9px;
  }
  .decision-intro h1 {
    font-size: 27px;
    line-height: 1.3;
    letter-spacing: 0;
  }
  .decision-intro p {
    font-size: 12px;
  }
  .chat-heading {
    grid-template-columns: 42px minmax(0, 1fr);
    gap: 5px 10px;
    padding-bottom: 14px;
  }
  .helper-avatar {
    width: 42px;
    height: 42px;
  }
  .chat-heading h2 {
    font-size: 19px;
  }
  .chat-heading p {
    font-size: 10px;
  }
  .decision-grid {
    grid-template-columns: 1fr;
  }
  .decision-card h2 {
    font-size: 19px;
  }
  .card-facts,
  .menu-preview p,
  .menu-preview-row {
    font-size: 12px;
  }
  .card-main-actions button,
  .card-main-actions a {
    font-size: 12px;
  }
  .card-minor-actions button {
    font-size: 11px;
  }
  .mode-pill {
    grid-column: 2;
    justify-self: start;
    max-width: none;
    white-space: normal;
    text-align: left;
  }
  .chat-messages {
    min-height: 120px;
    padding: 18px 0;
  }
  .message-content {
    max-width: 86%;
    padding: 12px;
  }
  .composer-actions > div button {
    font-size: 10px;
    padding: 4px;
  }
  .composer-actions > .button-primary {
    padding: 8px 10px;
    font-size: 12px;
  }
  .chat-composer {
    padding: 13px;
  }
  #request-message {
    height: 85px;
    font-size: 14px;
  }
  .quick-actions {
    gap: 6px;
    margin-bottom: 12px;
  }
  .quick-actions button {
    font-size: 10px;
    padding: 5px 8px;
  }
  .decision-aside {
    grid-template-columns: 1fr;
  }
  .journey-note {
    display: none;
  }
  .section-heading {
    gap: 8px;
  }
  .section-heading h2 {
    font-size: 17px;
  }
  .section-heading > button {
    padding: 8px;
    font-size: 10px;
    white-space: nowrap;
  }
  .catalog-summary {
    font-size: 10px;
  }
  .detail-menu-row > div {
    font-size: 12px;
  }
  .detail-menu-row small a {
    overflow-wrap: anywhere;
  }
  .detail-footer {
    flex-direction: column;
    align-items: stretch;
  }
  .compare-tray {
    width: calc(100% - 24px);
    padding: 10px;
    gap: 10px;
    justify-content: center;
  }
}

@media (max-width: 360px) {
  .decision-intro .ai-intro-label,
  .decision-intro p,
  .chat-heading p,
  .quick-actions > span {
    display: none;
  }
  .decision-intro {
    margin-bottom: 18px;
  }
  .decision-intro h1 {
    margin: 8px 0;
    font-size: 25px;
  }
  .chat-heading {
    row-gap: 2px;
    padding-bottom: 10px;
  }
  .message-content {
    font-size: 13px;
    line-height: 1.75;
  }
}

.image-credit {
  font-size: 9px;
  color: var(--muted);
  margin: -5px 0 8px;
}

/* Editable notes and route feedback share the existing palette. */
.edit-needs-button {
  padding: 4px 8px;
  font-size: 11px;
  margin: 0 0 8px;
  background: #f8fbf2;
}
.preferences-form {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}
.preferences-form label {
  display: grid;
  gap: 4px;
  font-size: 11px;
  color: var(--muted);
}
.preferences-form input,
.preferences-form select {
  width: 100%;
  min-width: 0;
  border: 1px solid #cad9bc;
  border-radius: 8px;
  padding: 8px;
  background: #fffefa;
  color: var(--ink);
  font: inherit;
  font-size: 12px;
}
.preferences-form .card-actions {
  margin: 4px 0;
  gap: 6px;
}
.preferences-form .card-actions button {
  padding: 8px;
  font-size: 11px;
}
.form-error,
.request-error {
  color: #8a603e;
  font-size: 12px;
}
.request-error {
  padding: 10px;
  background: #faf3e5;
  border-radius: 10px;
  margin-top: 12px;
}
.request-error button {
  padding: 5px 8px;
  margin-left: 8px;
  font-size: 11px;
}
.route-empty {
  padding-top: 12px;
  border-top: 1px solid #cbdcbc;
  font-size: 12px;
}
.walking-route {
  padding-top: 16px;
  border-top: 1px solid #cbdcbc;
}
.route-facts {
  display: flex;
  align-items: baseline;
  gap: 15px;
  flex-wrap: wrap;
}
.route-facts strong {
  font-size: 26px;
  color: var(--green-dark);
  font-weight: 500;
}
.route-facts span {
  font-size: 14px;
}
.walking-route details {
  font-size: 12px;
  margin-bottom: 16px;
}
.walking-route ol {
  padding-left: 20px;
  line-height: 1.9;
}
````

<a id="source-34"></a>

## 34. static/decorations.js

[打开原文件](../static/decorations.js) · 39 行

SHA-256：`a9eeea614facdceabde9907e922451c107d1a8f156401465263c4241fffd1f1c`

````javascript
/* Optional decorative motion is independent of chat and merchant state. */
(() => {
  const button = document.querySelector("[data-decoration-toggle]");
  if (!button) return;
  const storageKey = "nightfind-decoration-motion";
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  let paused = false;
  try {
    paused = localStorage.getItem(storageKey) === "paused";
  } catch {
    /* Decoration still works when browser storage is unavailable. */
  }

  function render() {
    document.body.classList.toggle(
      "decorations-paused",
      paused || document.hidden,
    );
    button.disabled = reducedMotion.matches;
    button.textContent = reducedMotion.matches
      ? "装饰动效已随系统关闭"
      : paused
        ? "开启装饰动效"
        : "暂停装饰动效";
  }

  button.addEventListener("click", () => {
    paused = !paused;
    try {
      localStorage.setItem(storageKey, paused ? "paused" : "running");
    } catch {
      /* Keep this tab's preference even without persistent storage. */
    }
    render();
  });
  reducedMotion.addEventListener("change", render);
  document.addEventListener("visibilitychange", render);
  render();
})();
````

<a id="source-35"></a>

## 35. static/experience.css

[打开原文件](../static/experience.css) · 424 行

SHA-256：`7fc175e4a88fdb5811d91cb3853be74abc790538d4eee8c17ea2c85766d7ec6a`

````css
/* Interaction layer for the chat-first NightFind experience.
 * These additions inherit the natural green tokens from style.css.
 * All motion is subtle and respects reduced-motion preferences.
 */
[hidden] { display: none !important; }

.nav-count {
  display: inline-grid;
  place-items: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  margin-left: 3px;
  border-radius: 20px;
  background: #e1ecda;
  color: #55775c;
  font-size: 10px;
  font-weight: 650;
}
.nav-link.active .nav-count { background: #cee1c2; }

.merchant-card { position: relative; }
.merchant-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 12px;
}
.merchant-actions .quiet-link { margin-top: 0; margin-right: auto; }
.soft-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: 1px solid #dbe7d7;
  border-radius: 16px;
  background: #f8faf4;
  color: #607763;
  padding: 6px 9px;
  line-height: 1.3;
  font-size: 10px;
  font-weight: 500;
  transition: background .2s, border-color .2s, transform .2s;
}
.soft-action:hover { background: #ecf4e7; transform: translateY(-1px); }
.soft-action.is-active {
  background: #e2eddb;
  border-color: #b5cda9;
  color: #426648;
}
.soft-action:focus-visible, .followup-chip:focus-visible {
  outline: 2px solid #668c70;
  outline-offset: 3px;
}

.context-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  padding: 12px 0 0;
}
.context-label { font-size: 10px; color: #8b9b87; margin-right: 3px; }
.context-pill {
  color: #5e785e;
  background: #edf4e8;
  padding: 5px 10px;
  border-radius: 20px;
  font-size: 10px;
}
.reset-chat {
  border: 0;
  background: transparent;
  color: #849783;
  font-size: 10px;
  text-decoration: underline;
  text-underline-offset: 3px;
  padding: 3px 4px;
  margin-left: auto;
}
.followup-section {
  padding: 12px 0 0;
  border-top: 1px solid #dce8d6;
  margin-top: 12px;
}
.followup-question { color: #627d63; font-size: 11px; font-weight: 600; margin: 0 0 8px !important; }
.followup-options { display: flex; flex-wrap: wrap; gap: 7px; }
.followup-chip {
  border: 1px solid #cddfc4;
  background: #fff;
  border-radius: 20px;
  color: #4e7157;
  padding: 6px 10px;
  font-size: 10px;
  line-height: 1.5;
  transition: background .2s, transform .2s;
}
.followup-chip:hover { background: #e5efdd; transform: translateY(-1px); }
.chat-merchant-actions {
  display: flex;
  gap: 7px;
  margin-left: auto;
  align-items: center;
}
.chat-merchant-actions button {
  border: 1px solid #dce9d7;
  border-radius: 12px;
  background: #fff;
  color: #56765b;
  font-size: 10px;
  padding: 5px 8px;
  white-space: nowrap;
}
.chat-merchant-actions button.is-active { background: #dcebd3; }

.compare-tray {
  position: fixed;
  bottom: 18px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 8;
  width: min(680px, calc(100% - 30px));
  border-radius: 18px;
  padding: 14px 16px;
  background: rgba(251, 253, 248, .97);
  border: 1px solid #cddfc5;
  box-shadow: 0 14px 44px rgba(52, 80, 54, .18);
  backdrop-filter: blur(14px);
  display: flex;
  align-items: center;
  gap: 13px;
  animation: fade-up .22s ease both;
}
.compare-tray-summary { flex: 1; min-width: 0; }
.compare-tray-summary b, .compare-tray-summary small { display: block; }
.compare-tray-summary b { color: #355b40; font-size: 12px; }
.compare-tray-summary small {
  color: #899984;
  font-size: 10px;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.compare-tray button { white-space: nowrap; }
.compare-dialog {
  border: 1px solid #dce7d6;
  border-radius: 23px;
  background: #fffefa;
  color: var(--ink);
  padding: 25px;
  width: min(860px, calc(100% - 24px));
  max-height: 90vh;
  overflow: auto;
  box-shadow: 0 28px 85px #30452d30;
}
.compare-dialog::backdrop { background: rgba(50, 67, 48, .28); backdrop-filter: blur(4px); }
.compare-dialog h2 { margin: 12px 0 6px; font-size: 23px; color: #355640; }
.compare-intro { font-size: 11px; color: #81917e; margin: 0 0 18px; }
.compare-columns { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 12px; }
.compare-columns.two { grid-template-columns: repeat(2, minmax(0,1fr)); }
.compare-column {
  min-width: 0;
  background: #f8faf5;
  border: 1px solid #dfe9d9;
  border-radius: 17px;
  padding: 15px;
}
.compare-column.top { background: #edf4e7; border-color: #a8c49d; }
.compare-column h3 {
  font-size: 13px;
  line-height: 1.5;
  margin: 12px 0 11px;
  font-weight: 650;
}
.compare-column .dish-emoji { font-size: 26px; }
.compare-metric {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  border-top: 1px solid #e3ebdf;
  padding: 9px 0;
  font-size: 10px;
  line-height: 1.5;
}
.compare-metric span { color: #829180; }
.compare-metric b { color: #4d6652; text-align: right; }
.compare-tags { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 9px; }
.compare-tags span {
  color: #587959;
  background: #e2efdc;
  border-radius: 16px;
  padding: 4px 8px;
  font-size: 9px;
}
.compare-conclusion {
  background: #edf5e8;
  border-radius: 17px;
  padding: 15px 18px;
  margin-top: 17px;
}
.compare-conclusion strong { color: #456a4b; font-size: 13px; }
.compare-conclusion p { font-size: 11px; margin: 7px 0; color: #617763; }
.compare-conclusion ul { padding-left: 18px; color: #788c75; font-size: 10px; line-height: 1.8; }
.compare-disclaimer { color: #929e8d; font-size: 10px; margin-top: 16px; }

.saved-hero {
  display: flex;
  align-items: center;
  gap: 16px;
  justify-content: space-between;
  margin: 20px 0 24px;
  border-radius: 20px;
  background: #e7f0df;
  border: 1px solid #d5e5cd;
  padding: 21px 24px;
}
.saved-hero strong { display: block; font-size: 18px; color: #41664a; font-weight: 600; }
.saved-hero p { margin: 6px 0 0; font-size: 11px; color: #769177; }
.saved-hero .saved-illustration { font-size: 40px; animation: gentle-float 5s ease-in-out infinite; }
.saved-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 17px; }
.saved-empty {
  padding: 52px 24px;
  text-align: center;
  background: #fcfdf9;
  border: 1px dashed #c4d9bd;
  border-radius: 22px;
}
.saved-empty .empty-icon { font-size: 38px; display: block; margin-bottom: 10px; }
.saved-empty h2 { margin: 0 0 6px; color: #52735a; font-size: 19px; }
.saved-empty p { margin: 0 0 19px; color: #839483; font-size: 11px; }
.saved-actions { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 17px; }
.saved-actions .button-primary { padding: 11px 16px; }
@keyframes fade-up {
  from { opacity: 0; transform: translate(-50%, 12px); }
  to { opacity: 1; transform: translate(-50%, 0); }
}
@keyframes gentle-float {
  0%,100% { transform: translateY(0) rotate(-3deg); }
  50% { transform: translateY(-7px) rotate(4deg); }
}

@media (max-width: 900px) {
  .saved-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
}
@media (max-width: 680px) {
  .saved-grid { grid-template-columns: 1fr; }
  .compare-columns, .compare-columns.two { grid-template-columns: 1fr; }
  .compare-dialog { padding: 18px; }
  .compare-tray { bottom: 10px; padding: 12px; gap: 8px; }
  .compare-tray .button-primary { padding: 10px 13px; }
  .compare-tray-summary small { max-width: 140px; }
  .chat-merchant { flex-wrap: wrap; }
  .chat-merchant-actions { margin-left: 43px; }
  .saved-hero { padding: 17px; }
}
@media (prefers-reduced-motion: reduce) {
  .saved-hero .saved-illustration, .compare-tray {
    animation: none;
  }
}

/* Verified real directory: softly separated from the demonstration cards. */
.real-catalog-panel { border-radius: 22px; padding: 22px; margin-bottom: 34px; border: 1px solid #d5e4cf; background: #f8fcf5; }
.real-catalog-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; flex-wrap: wrap; }
.real-catalog-title h2 { color: #3e6047; font-size: 21px; font-weight: 600; margin: 6px 0; }
.real-catalog-title p { color: #778975; font-size: 11px; margin: 0; }
.real-catalog-title > span { border-radius: 24px; padding: 8px 12px; background: #e4eedf; color: #52745a; font-size: 10px; }
.real-search { display: flex; gap: 9px; margin: 19px 0; }
.real-search input, .real-search select { min-width: 0; border: 1px solid #d5e2ce; background: white; border-radius: 11px; padding: 10px 12px; color: #526a54; font: inherit; font-size: 12px; }
.real-search input { flex: 1; }
.real-shop { background: white; border: 1px solid #e3ebdf; border-radius: 15px; padding: 15px 17px; margin-top: 10px; display: flex; justify-content: space-between; gap: 18px; }
.real-shop strong { font-size: 13px; color: #385940; }
.real-shop p { margin: 5px 0; color: #6e806d; font-size: 11px; }
.real-shop small { color: #98a193; font-size: 10px; }
.real-shop-meta { display: flex; flex-direction: column; gap: 8px; align-items: flex-end; color: #82927c; font-size: 10px; min-width: 110px; }
.real-shop-meta a { color: #4d7957; text-decoration: underline; text-underline-offset: 3px; }
@media(max-width:680px) { .real-catalog-panel { padding: 15px; } .real-search { flex-wrap: wrap; } .real-search input { flex-basis: 100%; } .real-search select { flex: 1; } .real-shop { flex-direction: column; } .real-shop-meta { flex-direction: row; justify-content: space-between; align-items: center; } }

.real-license {
  color: #708570;
  font-size: 10px;
  line-height: 1.75;
  margin: 10px 0 15px;
}
.real-license a {
  color: #456a52;
  text-decoration: underline;
  text-underline-offset: 3px;
}
.real-pagination {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  padding: 15px 0 1px;
}
.real-pagination > span { margin-right: auto; color: #718574; font-size: 11px; }
.real-pagination button:disabled { opacity: .45; cursor: not-allowed; }
.chat-merchant-actions a { color: #507957; font-size: 10px; text-decoration: underline; }
@media (max-width: 680px) {
  .real-pagination { justify-content: center; }
  .real-pagination > span { width: 100%; text-align: center; }
}


/* Recent, licensed storefront photographs and user-controlled Wuhan map. */
.real-shop-main { flex: 1; min-width: 0; }
.real-shop-photo, .real-shop-photo-placeholder {
  flex: 0 0 116px;
  width: 116px;
  height: 98px;
  border-radius: 12px;
  object-fit: cover;
  background: #e9f1e5;
}
.real-shop-photo-placeholder {
  display: grid;
  place-items: center;
  color: #829a7d;
  font-size: 10px;
  text-align: center;
  padding: 8px;
}
.real-map-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 7px 0 13px;
}
.real-map-actions span { color: #80947a; font-size: 10px; margin-left: auto; }
.real-osm-map {
  height: clamp(340px, 48vw, 485px);
  min-height: 340px;
  background: #e8f0e3;
  border-radius: 14px;
  overflow: hidden;
  width: 100%;
}
.real-map-caption { color: #899a85; font-size: 10px; margin: 9px 2px; }
.real-map-popup { color: #47644b; max-width: 240px; }
.real-map-popup p { color: #718571; font-size: 10px; }
.real-map-popup button {
  border: 1px solid #cadfbe;
  background: #e5efdd;
  color: #446c4c;
  border-radius: 10px;
  padding: 7px 10px;
  font-size: 11px;
  cursor: pointer;
  display: block;
  margin-top: 8px;
}
.real-shop-gallery { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 11px; margin: 15px 0; }
.real-shop-gallery-item { margin: 0; border-radius: 13px; overflow: hidden; background: #f1f6ed; }
.real-shop-gallery-item img { display: block; width: 100%; aspect-ratio: 4/3; object-fit: cover; }
.real-shop-gallery-item figcaption { color: #7f947d; font-size: 10px; padding: 8px; }
.real-photo-empty { padding: 16px; background: #f2f7ed; border-radius: 13px; color: #81977d; font-size: 11px; }
@media (max-width: 680px) {
  .real-shop-photo, .real-shop-photo-placeholder { width: 100%; flex-basis: auto; height: 140px; }
  .real-map-actions span { width: 100%; margin-left: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .real-shop-photo { transition: none; }
}

.real-shop-photo-figure {
  flex: 0 0 132px;
  width: 132px;
  margin: 0;
}
.real-shop-photo-figure .real-shop-photo {
  display: block;
  width: 132px;
  height: 98px;
}
.real-shop-photo-figure figcaption {
  color: #81927d;
  font-size: 9px;
  line-height: 1.45;
  padding-top: 5px;
}
.real-map-legend {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 18px;
  padding: 10px 4px 2px;
  color: #738771;
  font-size: 10px;
}
.real-map-legend span { display: inline-flex; align-items: center; gap: 7px; }
.real-map-legend i {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
.real-map-legend .verified-dot { background: #80a97e; border: 2px solid #3f6a49; }
.real-map-legend .community-dot { background: #a9c1d0; border: 2px solid #718a9c; }
.real-map-quality {
  display: inline-block;
  border-radius: 999px;
  padding: 4px 7px;
  font-size: 10px;
}
.real-map-quality.verified { color: #456c4c; background: #e8f1e3; }
.real-map-quality.community { color: #5f7888; background: #edf3f7; }
.real-map-quality.web-listing { color: #80683f; background: #f5f0e5; }
.real-map-legend .web-listing-dot { background: #d8c39b; border: 2px solid #9b8058; }
.real-shop-dishes { color: #617b5e !important; line-height: 1.6; }
.real-menu-list { list-style: none; margin: 10px 0 18px; padding: 0; }
.real-menu-list li { padding: 11px 0; border-bottom: 1px solid #e7eee3; }
.real-menu-list li > div { display: flex; justify-content: space-between; gap: 14px; color: #45674b; font-size: 12px; }
.real-menu-list li > div span { flex: 0 0 auto; font-weight: 650; }
.real-menu-list li small { display: block; color: #899887; font-size: 10px; line-height: 1.6; margin-top: 4px; }
.real-menu-list a { color: #4d7957; text-decoration: underline; text-underline-offset: 2px; }
@media (max-width: 680px) {
  .real-shop-photo-figure { width: 100%; flex-basis: auto; }
  .real-shop-photo-figure .real-shop-photo { width: 100%; height: 145px; }
}
````

<a id="source-36"></a>

## 36. static/index.html

[打开原文件](../static/index.html) · 73 行

SHA-256：`b2e61fb7fb6e24f3df4925ba638fc9c0a1b417b02493e975bf87797e810c5040`

````html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="theme-color" content="#dcf3e6" />
    <title>夜寻 · AI 餐饮助手</title>
    <link rel="stylesheet" href="/style.css" />
    <link rel="stylesheet" href="/decision.css" />
    <link rel="stylesheet" href="/vendor/leaflet/leaflet.css" />
  </head>
  <body>
    <div class="side-botanical botanical-left" aria-hidden="true">
      <span class="botanical-leaf leaf-one"></span>
      <span class="botanical-leaf leaf-two"></span>
      <span class="botanical-leaf leaf-three"></span>
      <span class="botanical-spark spark-one"></span>
      <span class="botanical-spark spark-two"></span>
    </div>
    <div class="side-botanical botanical-right" aria-hidden="true">
      <span class="botanical-leaf leaf-one"></span>
      <span class="botanical-leaf leaf-two"></span>
      <span class="botanical-leaf leaf-three"></span>
      <span class="botanical-spark spark-one"></span>
      <span class="botanical-spark spark-two"></span>
    </div>
    <header class="site-header">
      <a class="brand" href="/"
        ><span class="brand-mark">夜</span
        ><span class="brand-copy"
          ><strong>夜寻</strong><small>从想吃什么，到决定去哪</small></span
        ></a
      >
      <nav class="main-nav" aria-label="主导航">
        <button class="nav-link active" data-page="decision">
          <span class="nav-ai-mark" aria-hidden="true">✦</span> AI 对话
        </button>
        <button class="nav-link" data-page="recommendations">推荐商家</button>
        <button class="nav-link" data-page="directory">真实商家</button>
        <button class="nav-link" data-page="saved">
          今晚清单 <span id="saved-count">0</span>
        </button>
      </nav>
      <span class="header-location"
        ><span class="status-dot"></span> 武汉 · 今晚好好吃饭</span
      >
    </header>
    <main id="app" class="page-shell"><p>正在准备门店资料…</p></main>
    <div id="compare-tray" class="compare-tray" aria-live="polite" hidden></div>
    <footer class="site-footer">
      <span>夜寻 NIGHTFIND · 在武汉，发现一顿好饭</span
      ><span class="footer-details"
        ><span>跟着心意挑选，带着依据出发。</span
        ><button type="button" class="decoration-toggle" data-decoration-toggle>
          暂停装饰动效
        </button></span
      >
    </footer>
    <dialog
      id="merchant-dialog"
      class="merchant-dialog"
      aria-label="商家资料与对比"
    >
      <button class="dialog-close" data-close aria-label="关闭">×</button>
      <div id="merchant-detail"></div>
    </dialog>
    <div id="toast" class="toast" role="status" aria-live="polite"></div>
    <script src="/vendor/leaflet/leaflet.js" defer></script>
    <script src="/wuhan_map.js" defer></script>
    <script src="/decorations.js" defer></script>
    <script type="module" src="/app.js"></script>
  </body>
</html>
````

<a id="source-37"></a>

## 37. static/session-store.js

[打开原文件](../static/session-store.js) · 53 行

SHA-256：`536876ed55b1f45f863608b7e1a4edefc65e968abe1edb9e7fc368ad037dc5c7`

````javascript
/* Short-lived browser history. Store IDs and preferences; reload merchant facts from the API. */
const storageKey = "nightfind-conversation-v1";
const maxAge = 24 * 60 * 60 * 1000;

export function loadConversation() {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey));
    if (
      !value ||
      value.version !== 1 ||
      !Number.isFinite(value.savedAt) ||
      Date.now() - value.savedAt > maxAge
    )
      return null;
    return value;
  } catch {
    return null;
  }
}

export function saveConversation(state) {
  try {
    localStorage.setItem(
      storageKey,
      JSON.stringify({
        version: 1,
        savedAt: Date.now(),
        page: state.page,
        history: state.history.slice(-30),
        preferences: state.preferences,
        stage: state.result?.stage,
        lookupMessage: state.lookupMessage,
        selectedId: state.selected?.id,
        comparedIds: [...state.compared.keys()],
        lastRequest: state.lastRequest,
        failedRequest: state.failedRequest || state.busy,
        draft: state.draft,
        keyword: state.keyword,
        district: state.district,
      }),
    );
  } catch {
    /* Private browsing or full storage must not block dining decisions. */
  }
}

export function clearConversation() {
  try {
    localStorage.removeItem(storageKey);
  } catch {
    /* Storage may be unavailable. */
  }
}
````

<a id="source-38"></a>

## 38. static/style.css

[打开原文件](../static/style.css) · 639 行

SHA-256：`6f311f1f2860cbd219e426a002c94302ca86fd1f63a26a24565a151c5138b2a1`

````css
/* Shared visual tokens and page shell. Component layouts live in decision.css. */
:root {
  color-scheme: light;
  --page: #dcf3e6;
  --paper: #f5fbf3;
  --surface: #fffef8;
  --surface-soft: #e8f6e8;
  --green: #16845e;
  --green-dark: #126247;
  --green-deep: #0b4436;
  --green-pale: #d1f1bc;
  --green-line: #bcdcc8;
  --accent: #d2ef78;
  --ink: #21483b;
  --muted: #536d60;
  --shadow: 0 16px 44px #154f3620;
}
* {
  box-sizing: border-box;
}
html {
  scroll-behavior: smooth;
}
body {
  --decoration-play-state: running;
  isolation: isolate;
  margin: 0;
  min-height: 100vh;
  background:
    radial-gradient(ellipse at 88% 0, #e9f5ad, transparent 46%),
    radial-gradient(ellipse at 0 70%, #a4dfc7, transparent 48%), var(--page);
  color: var(--ink);
  font-family:
    -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Microsoft YaHei", sans-serif;
  font-size: 14px;
  line-height: 1.7;
}
button,
input,
textarea {
  font: inherit;
}
button,
.button-primary,
.button-secondary {
  border: 1px solid var(--green-line);
  border-radius: 11px;
  padding: 9px 14px;
  background: var(--surface);
  color: var(--green-dark);
  font-size: 13px;
  cursor: pointer;
  text-align: center;
  transition:
    background 0.18s,
    border-color 0.18s;
}
button:hover,
.button-secondary:hover {
  background: var(--surface-soft);
  border-color: #a8bfa0;
}
button:disabled {
  opacity: 0.55;
  cursor: default;
}
button[aria-pressed="true"] {
  background: var(--green-pale);
  color: var(--green-deep);
}
a {
  color: var(--green-dark);
  text-underline-offset: 3px;
}
a.button-primary,
a.button-secondary {
  display: inline-block;
  text-decoration: none;
}
.button-primary {
  background: linear-gradient(135deg, #16845e, var(--green-deep));
  border-color: var(--green-dark);
  color: #fffef8;
}
.button-primary:hover {
  background: var(--green-deep);
  border-color: var(--green-deep);
}
:focus-visible {
  outline: 2px solid #5c8659;
  outline-offset: 4px;
}
h1,
h2,
h3,
p {
  margin-top: 0;
}
h2 {
  font-size: 20px;
  font-weight: 600;
  line-height: 1.5;
  margin-bottom: 12px;
}
h3 {
  font-size: 14px;
  font-weight: 600;
}
p {
  margin-bottom: 12px;
}
[hidden] {
  display: none !important;
}
.eyebrow {
  color: #758a66;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 1.8px;
}
.muted,
.source-note,
figcaption {
  color: var(--muted);
}
.source-note,
figcaption {
  font-size: 11px;
  line-height: 1.8;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
}

/* All ambient motion shares one pause state. Content and form controls stay still. */
body::before,
body::after {
  content: "";
  position: fixed;
  width: min(68vw, 800px);
  height: min(85vh, 800px);
  border-radius: 50%;
  pointer-events: none;
  z-index: -2;
  animation: ambient-flow 10s ease-in-out infinite alternate;
  animation-play-state: var(--decoration-play-state);
}
body::before {
  left: -20%;
  top: 8%;
  background: radial-gradient(ellipse, #43ce9a88, transparent 68%);
}
body::after {
  right: -18%;
  top: 22%;
  background: radial-gradient(ellipse, #d2ef78cc, transparent 68%);
  animation-delay: -6s;
  animation-direction: alternate-reverse;
}

/* Botanical margins use only transforms and opacity, without animation libraries. */
.side-botanical {
  --side-phase: 0s;
  position: fixed;
  width: clamp(120px, 12vw, 200px);
  height: 760px;
  top: 110px;
  overflow: hidden;
  opacity: 0.95;
  pointer-events: none;
  z-index: -1;
}
.side-botanical::before,
.side-botanical::after {
  content: "";
  position: absolute;
  pointer-events: none;
}
.side-botanical::before {
  inset: 0;
  z-index: 1;
  background: linear-gradient(170deg, #078565, #2b9c60 55%, #82ad2c);
  mask: url("/botanical.svg") center / contain no-repeat;
  transform-origin: 50% 95%;
  animation: botanical-sway 4s ease-in-out infinite alternate;
  animation-delay: var(--side-phase);
}
.side-botanical::after {
  inset: 15% 14% 24%;
  border: 2px solid #48aa7280;
  border-radius: 50%;
  background: radial-gradient(ellipse, #ceef7b80, transparent 70%);
  box-shadow: 0 0 30px #4cbf7820;
  opacity: 0.7;
  animation: botanical-breathe 5s ease-in-out infinite alternate;
  animation-delay: var(--side-phase);
}
.botanical-left {
  left: max(0px, calc((100vw - 1460px) / 2));
}
.botanical-right {
  --side-phase: -3s;
  right: max(0px, calc((100vw - 1460px) / 2));
  transform: scaleX(-1) translateY(90px);
}
.botanical-right::before {
  animation-duration: 5s;
}
.botanical-leaf,
.botanical-spark {
  position: absolute;
  z-index: 2;
}
.botanical-leaf {
  width: 24px;
  height: 46px;
  border: 1px solid #16845e;
  border-radius: 100% 0 100% 0;
  background: linear-gradient(140deg, #2da46b, #d2ef78);
  box-shadow: 0 7px 15px #12624720;
  opacity: 0.9;
  transform: rotate(var(--leaf-angle));
  animation: botanical-drift var(--leaf-duration) ease-in-out infinite;
  animation-delay: calc(var(--leaf-delay) + var(--side-phase));
}
.leaf-one {
  left: 23%;
  top: 23%;
  --leaf-angle: -25deg;
  --leaf-duration: 6s;
  --leaf-delay: -2s;
}
.leaf-two {
  left: 66%;
  top: 49%;
  --leaf-angle: 28deg;
  --leaf-duration: 7.5s;
  --leaf-delay: -5s;
}
.leaf-three {
  left: 40%;
  top: 77%;
  --leaf-angle: -12deg;
  --leaf-duration: 9s;
  --leaf-delay: -7s;
}
.botanical-spark {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f3c74b;
  box-shadow:
    0 0 0 5px #e5bf4c20,
    0 0 18px #d3bd5f80;
  opacity: 0.9;
  animation: botanical-twinkle 3s ease-in-out infinite;
  animation-delay: var(--side-phase);
}
.spark-one {
  left: 72%;
  top: 17%;
}
.spark-two {
  left: 24%;
  top: 61%;
  animation-delay: calc(-3s + var(--side-phase));
}
.side-botanical::before,
.side-botanical::after,
.side-botanical span {
  animation-play-state: var(--decoration-play-state);
}
.decorations-paused {
  --decoration-play-state: paused;
}
@keyframes ambient-flow {
  from {
    transform: translate3d(-50px, -40px, 0) scale(0.85);
    opacity: 0.55;
  }
  to {
    transform: translate3d(90px, 100px, 0) scale(1.2);
    opacity: 1;
  }
}
@keyframes botanical-sway {
  from {
    transform: translate3d(-12px, 16px, 0) rotate(-9deg);
  }
  to {
    transform: translate3d(12px, -18px, 0) rotate(9deg);
  }
}
@keyframes botanical-drift {
  0% {
    opacity: 0;
    transform: translate3d(-18px, -70px, 0) rotate(var(--leaf-angle));
  }
  25%,
  65% {
    opacity: 1;
  }
  100% {
    opacity: 0;
    transform: translate3d(30px, 100px, 0)
      rotate(calc(var(--leaf-angle) + 140deg));
  }
}
@keyframes botanical-twinkle {
  0%,
  100% {
    opacity: 0.4;
    transform: translate3d(0, 0, 0) scale(0.8);
  }
  50% {
    opacity: 1;
    transform: translate3d(-12px, -40px, 0) scale(1.4);
  }
}
@keyframes botanical-breathe {
  from {
    opacity: 0.4;
    transform: translate3d(-14px, 25px, 0) rotate(-14deg) scale(0.85);
  }
  to {
    opacity: 0.9;
    transform: translate3d(14px, -30px, 0) rotate(14deg) scale(1.1);
  }
}
.site-header {
  width: min(1180px, calc(100% - 64px));
  min-height: 100px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  border-bottom: 1px solid var(--green-line);
}
.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  text-decoration: none;
}
.brand-mark {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 14px 14px 14px 4px;
  background: var(--green-dark);
  color: var(--accent);
  font-family: serif;
  font-size: 23px;
}
.brand-copy {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}
.brand-copy strong {
  font-size: 22px;
  letter-spacing: 4px;
  font-weight: 600;
}
.brand-copy small {
  font-size: 10px;
  color: var(--muted);
  margin-top: 4px;
}
.main-nav {
  display: flex;
  gap: 5px;
  padding: 5px;
  border: 1px solid #125940;
  border-radius: 30px;
  background: var(--green-deep);
  box-shadow: 0 8px 22px #0b44361a;
}
.nav-link {
  border: 0;
  background: transparent;
  color: #d7e9dd;
  padding: 8px 22px;
  border-radius: 22px;
  white-space: nowrap;
}
.nav-link.active {
  color: var(--green-deep);
  background: var(--accent);
  box-shadow: 0 2px 8px #4a633410;
}
.nav-link[data-page="decision"] {
  font-weight: 600;
}
.nav-link[data-page="decision"].active {
  background: var(--accent);
  color: var(--green-deep);
}
.nav-link:hover {
  background: #27624e;
  color: #fffef8;
}
.nav-link.active:hover {
  background: #e1f5a6;
  color: var(--green-deep);
}
.nav-ai-mark {
  font-size: 11px;
}
#saved-count {
  display: inline-grid;
  place-items: center;
  min-width: 19px;
  height: 19px;
  margin-left: 3px;
  border-radius: 50%;
  background: #dfe9d5;
  color: var(--green-dark);
  font-size: 10px;
}
.header-location {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 11px;
  color: var(--muted);
}
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #86a378;
  box-shadow: 0 0 0 4px #86a37815;
}
.page-shell {
  width: min(1120px, calc(100% - 64px));
  min-height: calc(100vh - 205px);
  margin: 0 auto;
  padding: 42px 0 72px;
}
.page-intro {
  margin-bottom: 30px;
}
.page-intro h1 {
  margin: 12px 0 14px;
  color: var(--green-deep);
  font-family: "Noto Serif CJK SC", "Songti SC", "SimSun", serif;
  font-size: clamp(28px, 3.5vw, 44px);
  font-weight: 700;
  letter-spacing: 1px;
  line-height: 1.5;
}
.page-intro h1 span {
  color: #147957;
  background: linear-gradient(transparent 72%, #c9ec79 72%);
}
.page-intro p {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.9;
  margin-bottom: 0;
}
.site-footer {
  width: min(1120px, calc(100% - 64px));
  margin: 0 auto;
  padding: 25px 0 30px;
  border-top: 1px solid var(--green-line);
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 10px;
  color: var(--muted);
}
.footer-details {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px;
}
.decoration-toggle {
  padding: 2px 0;
  border: 0;
  background: transparent;
  color: var(--muted);
  font-size: 10px;
  text-decoration: underline;
  text-underline-offset: 4px;
}
.decoration-toggle:hover {
  background: transparent;
  color: var(--green-dark);
}
.empty-state {
  grid-column: 1 / -1;
  padding: 40px 24px;
  text-align: center;
  border: 1px dashed #bbcdb1;
  border-radius: 18px;
  color: var(--muted);
  background: #fffefa80;
}
.empty-state p {
  margin: 8px 0 0;
}

.merchant-dialog {
  width: min(790px, calc(100% - 32px));
  max-height: 88vh;
  overflow: auto;
  border: 1px solid var(--green-line);
  border-radius: 24px;
  padding: 30px;
  background: var(--surface);
  color: var(--ink);
  box-shadow: 0 24px 90px #30452d30;
}
.merchant-dialog::backdrop {
  background: #273e3155;
  backdrop-filter: blur(5px);
}
.dialog-close {
  position: sticky;
  top: 0;
  float: right;
  z-index: 2;
  width: 34px;
  height: 34px;
  padding: 0;
  border-radius: 50%;
  background: var(--surface-soft);
  font-size: 23px;
}
.toast {
  position: fixed;
  z-index: 1100;
  left: 50%;
  bottom: 94px;
  transform: translateX(-50%);
  max-width: calc(100% - 32px);
  width: max-content;
  padding: 12px 20px;
  border-radius: 14px;
  background: var(--green-deep);
  color: white;
  box-shadow: var(--shadow);
  font-size: 13px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s;
}
.toast.visible {
  opacity: 1;
}
@media (max-width: 1100px) {
  .header-location,
  .side-botanical {
    display: none;
  }
  .side-botanical {
    --decoration-play-state: paused;
  }
}
@media (max-width: 800px) {
  .site-header {
    flex-wrap: wrap;
    padding: 20px 0 16px;
    gap: 16px;
  }
  .main-nav {
    width: 100%;
    justify-content: space-between;
  }
  .nav-link {
    flex: 1;
    padding: 8px 6px;
  }
}
@media (max-width: 650px) {
  body::before,
  body::after {
    width: 90vw;
    height: 65vh;
  }
  .nav-ai-mark {
    display: none;
  }
  .site-header {
    width: calc(100% - 32px);
    min-height: 0;
    padding: 20px 0 16px;
    flex-wrap: wrap;
    gap: 20px;
  }
  .brand-copy small {
    font-size: 11px;
  }
  .main-nav {
    width: 100%;
    justify-content: space-between;
  }
  .nav-link {
    flex: 1;
    padding: 8px 6px;
    font-size: 12px;
  }
  .page-shell {
    width: calc(100% - 32px);
    padding: 26px 0 48px;
  }
  .page-intro h1 {
    font-size: 29px;
  }
  .site-footer {
    width: calc(100% - 32px);
    flex-direction: column;
  }
  .merchant-dialog {
    padding: 20px;
    border-radius: 18px;
  }
}
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    transition: none !important;
    animation: none !important;
  }
}
````

<a id="source-39"></a>

## 39. static/wuhan_map.js

[打开原文件](../static/wuhan_map.js) · 330 行

SHA-256：`ed76c9cadd1a28b8553ff021c9a73813963cc3ed4c4d5e73cc2db326014a0284`

````javascript
/* Local WGS84 basemap and source coordinates share one projection.
 * Geographic sources and limitations: static/map/README.md.
 * No API key, remote JavaScript, or online tiles are needed for the default map.
 */
window.NightFindWuhanMap = (() => {
  "use strict";
  let map, markerLayer, labelLayer, currentContainer, allBounds;
  let generation = 0;
  let basemapRequest;
  let settingsRequest;
  let routeLayer;
  const markers = new Map();
  const escape = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (char) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[char],
    );

  function dispose() {
    generation += 1;
    if (map) map.remove();
    map =
      markerLayer =
      labelLayer =
      currentContainer =
      allBounds =
      routeLayer =
        null;
    markers.clear();
  }

  function loadBasemap() {
    if (!basemapRequest) {
      basemapRequest = fetch("/map/wuhan-basemap.geojson")
        .then((response) => {
          if (!response.ok) throw new Error("武汉底图文件读取失败");
          return response.json();
        })
        .catch((error) => {
          basemapRequest = null; // Allow a retry after a temporary local server error.
          throw error;
        });
    }
    return basemapRequest;
  }

  function addBasemap(data) {
    const group = (layer) => ({
      type: "FeatureCollection",
      features: data.features.filter(
        (feature) => feature.properties.layer === layer,
      ),
    });
    const vector = (layer, style) =>
      L.geoJSON(group(layer), {
        style,
        interactive: false,
        pane: "basemap",
      }).addTo(map);
    vector("boundary", {
      color: "#b6c7ae",
      weight: 1,
      fillColor: "#edf1e7",
      fillOpacity: 0.7,
    });
    vector("lake", {
      color: "#a5cbd0",
      weight: 1,
      fillColor: "#b4d7d9",
      fillOpacity: 0.9,
    });
    vector("river", { color: "#afd0d6", weight: 12, opacity: 1 });
    vector("road", { color: "#d7d8c9", weight: 5, opacity: 1 });
    vector("road", { color: "#fffdf4", weight: 2.5, opacity: 1 });
    labelLayer = L.layerGroup().addTo(map);
    const labelFeatures = data.features.filter(
      (feature) =>
        ["road", "park", "station", "water_label"].includes(
          feature.properties.layer,
        ) && feature.properties.name,
    );

    // Screen-space spacing keeps place names readable at every zoom level.
    function updateLabels() {
      labelLayer.clearLayers();
      const occupied = new Set();
      const zoom = map.getZoom();
      for (const feature of labelFeatures) {
        const { layer, name } = feature.properties;
        if (zoom < (layer === "station" ? 14 : layer === "park" ? 13 : 10))
          continue;
        const coords =
          feature.geometry.type === "Point"
            ? feature.geometry.coordinates
            : feature.geometry.coordinates[
                Math.floor(feature.geometry.coordinates.length / 2)
              ];
        const point = L.latLng(coords[1], coords[0]);
        if (!map.getBounds().contains(point)) continue;
        const pixel = map.latLngToContainerPoint(point);
        const cell = `${Math.floor(pixel.x / 105)}:${Math.floor(pixel.y / 36)}`;
        if (occupied.has(cell)) continue;
        occupied.add(cell);
        L.marker(point, {
          interactive: false,
          pane: "placeLabels",
          icon: L.divIcon({
            className: `map-place-label label-${layer}`,
            html: escape(name),
            iconSize: [100, 20],
            iconAnchor: [50, 10],
          }),
        }).addTo(labelLayer);
      }
    }
    map.on("zoomend moveend", updateLabels);
    updateLabels();
  }

  async function tryStreetTiles(container, version) {
    if (!settingsRequest)
      settingsRequest = fetch("/api/map-config")
        .then((response) => (response.ok ? response.json() : {}))
        .catch(() => ({}));
    const settings = await settingsRequest;
    if (version !== generation) return;

    function addProvider(provider) {
      const options = { maxZoom: 18, pane: "streetTiles" };
      const layers =
        provider === "tianditu"
          ? ["vec", "cva"].map((layer) =>
              L.tileLayer(
                `https://t{s}.tianditu.gov.cn/${layer}_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=${layer}&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk=${encodeURIComponent(settings.tianditu_key)}`,
                {
                  ...options,
                  subdomains: "01234567",
                  attribution:
                    '© <a href="https://www.tianditu.gov.cn/" target="_blank" rel="noopener noreferrer">天地图</a>',
                },
              ),
            )
          : [
              L.tileLayer(
                "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                options,
              ),
            ];
      const group = L.layerGroup(layers);
      let failed = false;
      const ready = new Set();
      container.dataset.streets = "loading";
      for (const layer of layers) {
        layer.on("tileerror", () => {
          if (version !== generation || failed) return;
          failed = true;
          group.remove();
          map.getPane("placeLabels").style.opacity = "1";
          if (provider === "tianditu") return addProvider("osm");
          container.dataset.streets = "unavailable";
          container.dataset.provider = "offline";
        });
        layer.on("load", () => {
          if (version !== generation || failed) return;
          ready.add(layer);
          if (ready.size !== layers.length) return;
          map.getPane("placeLabels").style.opacity = "0";
          container.dataset.streets = "ready";
          container.dataset.provider = provider;
        });
      }
      group.addTo(map);
    }
    // Both TianDiTu's CGCS2000 Web Mercator and OSM align with our WGS84
    // geographic points at this scale. Never put GCJ-02 points on this map.
    addProvider(settings.tianditu_key ? "tianditu" : "osm");
  }

  function popup(item, lat, lng) {
    const price =
      item.price_per_person != null
        ? `参考人均 ¥${item.price_per_person}`
        : item.price_range_min != null && item.price_range_max != null
          ? `${item.price_range_basis === "dish" ? "菜品参考价" : "来源参考价"} ¥${item.price_range_min}–${item.price_range_max}`
          : "尚未收录参考价格";
    return `<div class="real-map-popup"><span class="eyebrow">武汉 · 真实商家</span>
      <h3>${escape(item.name)}</h3><p>${escape(item.address || item.district || "来源坐标点位")}</p>
      <p class="map-popup-price">${escape(price)}</p>
      ${(item.priced_menu || []).map((dish) => `<p>${escape(dish.dish_name)} ¥${escape(dish.price)} ${escape(dish.price_unit)}</p>`).join("")}
      <small>${lat.toFixed(6)}, ${lng.toFixed(6)} · WGS84<br>${escape(item.source_name || "公开来源")} · 非实时营业信息</small>
      <button type="button" class="button-primary" data-real-merchant="${Number(item.id)}">查看完整资料 ↗</button></div>`;
  }

  async function draw(container, restaurants, { overview = false } = {}) {
    if (!container || !window.L) return { available: false, pins: 0 };
    if (currentContainer && currentContainer !== container)
      currentContainer.hidden = true;
    dispose();
    container.hidden = false;
    const version = generation;
    currentContainer = container;
    container.dataset.basemap = "loading";
    map = L.map(container, {
      preferCanvas: true,
      minZoom: 9,
      maxZoom: 18,
      scrollWheelZoom: false,
    }).setView([30.585, 114.3], 11);
    map.createPane("basemap").style.zIndex = 200;
    map.createPane("streetTiles").style.zIndex = 250;
    map.createPane("placeLabels").style.zIndex = 450;
    map.getPane("placeLabels").style.pointerEvents = "none";
    map.attributionControl.addAttribution(
      '底图：© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> · <a href="https://www.naturalearthdata.com/about/terms-of-use/" target="_blank" rel="noopener noreferrer">Natural Earth</a>',
    );
    L.control.scale({ imperial: false, position: "bottomleft" }).addTo(map);
    markerLayer = L.layerGroup().addTo(map);
    const bounds = [];
    for (const item of restaurants) {
      const lat = Number(item.latitude),
        lng = Number(item.longitude);
      if (
        item.latitude == null ||
        item.longitude == null ||
        !Number.isFinite(lat) ||
        !Number.isFinite(lng) ||
        lat < 29.8 ||
        lat > 31.5 ||
        lng < 113.5 ||
        lng > 115.2
      )
        continue;
      const marker = L.circleMarker([lat, lng], {
        radius: 6,
        color: "#fffef9",
        weight: 2,
        fillColor: "#4f805f",
        fillOpacity: 0.9,
      }).addTo(markerLayer);
      marker.bindPopup(popup(item, lat, lng), { maxWidth: 290 });
      marker.on("popupopen", () =>
        marker.setStyle({ radius: 9, fillColor: "#244d3b" }),
      );
      marker.on("popupclose", () =>
        marker.setStyle({ radius: 6, fillColor: "#4f805f" }),
      );
      markers.set(Number(item.id), marker);
      bounds.push([lat, lng]);
    }
    allBounds = bounds.length ? L.latLngBounds(bounds).pad(0.12) : null;
    if (!overview && allBounds)
      map.fitBounds(allBounds, { maxZoom: 14, animate: false });
    container.dataset.pins = bounds.length;
    try {
      const data = await loadBasemap();
      if (version !== generation || !container.isConnected)
        return { available: false, pins: 0 };
      addBasemap(data);
      container.dataset.basemap = "ready";
      tryStreetTiles(container, version);
    } catch {
      if (version !== generation) return { available: false, pins: 0 };
      container.dataset.basemap = "error";
      // Clearly report a missing local asset; never present a blank canvas as a loaded map.
      const notice = L.control({ position: "topright" });
      notice.onAdd = () => {
        const element = L.DomUtil.create("div", "map-load-error");
        element.textContent =
          "武汉底图文件读取失败，请刷新页面；仍可打开商家导航。";
        return element;
      };
      notice.addTo(map);
    }
    map.invalidateSize();
    return { available: true, pins: bounds.length };
  }

  function focus(id) {
    const marker = markers.get(Number(id));
    if (!map || !marker) return false;
    map.setView(marker.getLatLng(), 15, { animate: false });
    marker.openPopup();
    currentContainer.scrollIntoView({ behavior: "smooth", block: "center" });
    return true;
  }

  function fitAll() {
    if (map && allBounds)
      map.fitBounds(allBounds, { maxZoom: 14, animate: false });
  }
  function view() {
    if (!map) return null;
    const center = map.getCenter();
    return { latitude: center.lat, longitude: center.lng, zoom: map.getZoom() };
  }

  function restoreView(value) {
    if (
      map &&
      value &&
      Number.isFinite(value.latitude) &&
      Number.isFinite(value.longitude)
    )
      map.setView([value.latitude, value.longitude], value.zoom, {
        animate: false,
      });
  }

  function showRoute(points) {
    if (!map || !points?.length) return;
    if (routeLayer) routeLayer.remove();
    routeLayer = L.polyline(points, {
      color: "#486d91",
      weight: 5,
      opacity: 0.85,
    }).addTo(map);
    map.fitBounds(routeLayer.getBounds().pad(0.15), {
      maxZoom: 16,
      animate: false,
    });
  }
  return { draw, dispose, focus, fitAll, view, restoreView, showRoute };
})();
````

<a id="source-40"></a>

## 40. tests/decorative_motion.cjs

[打开原文件](../tests/decorative_motion.cjs) · 196 行

SHA-256：`834661b0ce9c452591394b54f2810d793153b89b3034d93598e538041d4632d4`

````javascript
/* Optional browser check: start the app, then run with Playwright available. */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 900 },
      reducedMotion: "no-preference",
    });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("https://**/*", (route) => route.abort());
    const url = process.argv[2] || "http://127.0.0.1:8000";
    await page.goto(url);
    await page.locator("#request-message:not([disabled])").waitFor();
    const control = page.locator("[data-decoration-toggle]");
    const sample = () =>
      page.evaluate(() => ({
        stem: getComputedStyle(
          document.querySelector(".botanical-left"),
          "::before",
        ).transform,
        leaf: getComputedStyle(document.querySelector(".leaf-one")).transform,
        glow: getComputedStyle(
          document.querySelector(".botanical-left"),
          "::after",
        ).opacity,
        spark: getComputedStyle(document.querySelector(".spark-one")).transform,
        background: getComputedStyle(document.body, "::before").transform,
      }));
    const first = await sample();
    await page.waitForTimeout(700);
    assert.notDeepEqual(
      await sample(),
      first,
      "Decorations should actually move",
    );
    assert.ok(
      await page
        .locator(".botanical-right")
        .evaluate((el) =>
          getComputedStyle(el).transform.startsWith("matrix(-1,"),
        ),
      "Right side stays mirrored",
    );
    assert.equal(
      await page.locator(".side-botanical").first().getAttribute("aria-hidden"),
      "true",
    );
    assert.equal(
      await page
        .locator(".side-botanical")
        .first()
        .evaluate((el) => getComputedStyle(el).pointerEvents),
      "none",
    );
    await control.click();
    await control.filter({ hasText: "开启装饰动效" }).waitFor();
    const paused = await sample();
    await page.waitForTimeout(600);
    assert.deepEqual(
      await sample(),
      paused,
      "Pause should freeze every decoration layer",
    );
    await page.reload();
    await page.locator("#request-message:not([disabled])").waitFor();
    assert.equal(await control.innerText(), "开启装饰动效");
    assert.ok(
      await page
        .locator("body")
        .evaluate((el) => el.classList.contains("decorations-paused")),
    );
    await control.click();
    const resumed = await sample();
    await page.waitForTimeout(600);
    assert.notDeepEqual(await sample(), resumed);

    await page.emulateMedia({ reducedMotion: "reduce" });
    await control.filter({ hasText: "随系统关闭" }).waitFor();
    assert.ok(await control.isDisabled());
    assert.equal(
      await page
        .locator("body")
        .evaluate((el) => getComputedStyle(el, "::before").animationName),
      "none",
    );
    assert.equal(
      await page
        .locator(".botanical-left")
        .evaluate((el) => getComputedStyle(el, "::before").animationName),
      "none",
    );
    assert.ok(
      await page
        .locator(".botanical-left")
        .evaluate((el) =>
          getComputedStyle(el, "::before").maskImage.includes("botanical.svg"),
        ),
      "Static botanical artwork remains available",
    );
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await control.filter({ hasText: "暂停装饰动效" }).waitFor();

    // Background visibility uses the same pause state without persisting a manual pause.
    await page.evaluate(() => {
      Object.defineProperty(document, "hidden", {
        configurable: true,
        value: true,
      });
      document.dispatchEvent(new Event("visibilitychange"));
    });
    assert.ok(
      await page
        .locator("body")
        .evaluate((el) => el.classList.contains("decorations-paused")),
    );
    await page.evaluate(() => {
      delete document.hidden;
      document.dispatchEvent(new Event("visibilitychange"));
    });
    assert.equal(await control.innerText(), "暂停装饰动效");

    for (const width of [1440, 1366, 1280, 1100, 1024, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `overflow at ${width}`,
      );
      assert.equal(
        await page.locator(".side-botanical").first().isVisible(),
        width > 1100,
      );
      assert.ok(
        await control.isVisible(),
        "Background motion can be paused at every width",
      );
    }
    await page.locator("#request-message").scrollIntoViewIfNeeded();
    assert.ok(
      await page.locator("#request-message").evaluate((el) => {
        const r = el.getBoundingClientRect();
        return (
          document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2) ===
          el
        );
      }),
      "Decorations cannot cover the chat input",
    );
    assert.deepEqual(errors, []);

    // Private browsing may deny storage; the visual control still works for this tab.
    const privatePage = await browser.newPage({
      viewport: { width: 1440, height: 900 },
    });
    await privatePage.addInitScript(() => {
      const originalGet = Storage.prototype.getItem;
      const originalSet = Storage.prototype.setItem;
      Storage.prototype.getItem = function (key) {
        if (key === "nightfind-decoration-motion")
          throw Error("storage unavailable");
        return originalGet.call(this, key);
      };
      Storage.prototype.setItem = function (key, value) {
        if (key === "nightfind-decoration-motion")
          throw Error("storage unavailable");
        return originalSet.call(this, key, value);
      };
    });
    await privatePage.route("https://**/*", (route) => route.abort());
    await privatePage.goto(url);
    await privatePage.locator("#request-message:not([disabled])").waitFor();
    await privatePage.locator("[data-decoration-toggle]").click();
    assert.equal(
      await privatePage.locator("[data-decoration-toggle]").innerText(),
      "开启装饰动效",
    );
    await privatePage.close();
    console.log(
      "PASS: actual animation, mirrored margins, pause/resume and persistence, reduced motion, visibility pause, unavailable storage, responsive widths and unobstructed chat input.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
````

<a id="source-41"></a>

## 41. tests/recommendation_navigation.cjs

[打开原文件](../tests/recommendation_navigation.cjs) · 240 行

SHA-256：`2670031e7ee29401c3310f81ffcfd95c49515464a9f504ac04524839a48c2a9e`

````javascript
/* Optional browser regression: start the app, then run with Playwright available.
 * CHROMIUM_PATH=/usr/bin/chromium node tests/recommendation_navigation.cjs http://127.0.0.1:8000
 */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const { mkdirSync } = require("node:fs");
const { join } = require("node:path");

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1050 },
    });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("https://**/*", (route) => route.abort());
    await page.goto(process.argv[2] || "http://127.0.0.1:8000");
    await page.locator("#request-message:not([disabled])").waitFor();
    const snapshot = async (name) => {
      if (!process.env.SCREENSHOT_DIR) return;
      mkdirSync(process.env.SCREENSHOT_DIR, { recursive: true });
      await page.screenshot({
        path: join(process.env.SCREENSHOT_DIR, name),
        fullPage: true,
      });
    };
    const send = async (message) => {
      await page.locator("#request-message").fill(message);
      const response = page.waitForResponse((r) =>
        r.url().endsWith("/api/decision"),
      );
      await page.locator('#decision-form button[type="submit"]').click();
      return (await response).json();
    };
    const backToChat = async () => {
      await page.locator('.main-nav [data-page="decision"]').click();
      await page.locator("#request-message:not([disabled])").waitFor();
    };
    const expectRecommendations = async (result) => {
      assert.equal(result.stage, "candidates");
      assert.ok(result.items.length > 0);
      await page.locator("#recommendations-title").waitFor();
      await page
        .locator('.main-nav [data-page="recommendations"].active')
        .waitFor();
      assert.equal(await page.locator("#conversation-log").count(), 0);
      assert.deepEqual(
        await page
          .locator("[data-card]")
          .evaluateAll((cards) =>
            cards.map((card) => Number(card.dataset.card)),
          ),
        result.items.map((item) => item.id),
      );
      assert.match(
        await page.locator("#toast.visible").innerText(),
        /^推荐成功/,
      );
      await page.waitForFunction(() => {
        const title = document.getElementById("recommendations-title");
        const bounds = title?.getBoundingClientRect();
        return (
          bounds &&
          bounds.top >= 0 &&
          bounds.bottom <= innerHeight &&
          document.activeElement === title
        );
      });
    };

    // Clarification and a factual lookup remain in the conversation.
    const clarify = await send("我想找个地方吃晚饭");
    assert.equal(clarify.stage, "clarify");
    await page.locator("#request-message:not([disabled])").waitFor();
    assert.equal(await page.locator("#recommendations-title").count(), 0);
    assert.equal(await page.locator("#toast.visible").count(), 0);
    const lookup = await send("查金贵源的菜单价格");
    assert.equal(lookup.stage, "catalog");
    await page.locator("[data-card]").first().waitFor();
    assert.equal(await page.locator("#recommendations-title").count(), 0);

    const plan = "明天晚上七点，两个人在江汉路附近，总预算400元，想吃湖北菜";
    let result = await send(plan);
    await expectRecommendations(result);
    await snapshot("recommendations-desktop.png");

    // Existing card actions work without leaving the recommended list.
    const firstId = result.items[0].id;
    await page.locator(`[data-detail="${firstId}"]`).click();
    await page.getByRole("dialog").waitFor();
    assert.ok(
      (await page.locator("#merchant-detail").innerText()).includes(
        result.items[0].name,
      ),
    );
    await page.locator("[data-close]").click();
    await page.locator("[data-show-map]").click();
    await page.locator('#decision-map[data-basemap="ready"]').waitFor();
    assert.equal(
      Number(await page.locator("#decision-map").getAttribute("data-pins")),
      result.items.filter(
        (item) => item.latitude != null && item.longitude != null,
      ).length,
    );
    await page.locator(`[data-save="${firstId}"]`).click();
    await page
      .locator(`[data-save="${firstId}"][aria-pressed="true"]`)
      .waitFor();
    for (const item of result.items.slice(0, 2)) {
      await page.locator(`[data-compare="${item.id}"]`).click();
      await page
        .locator(`[data-compare="${item.id}"][aria-pressed="true"]`)
        .waitFor();
    }
    await page.locator("[data-open-compare]").click();
    await page.locator("dialog[open] table").waitFor();
    await page.locator("[data-close]").click();
    await page.locator("[data-clear-compare]").click();
    await page.locator(`[data-card="${firstId}"] [data-choose]`).click();
    await page.locator("#selected-place:not([hidden])").waitFor();
    assert.ok(
      (await page.locator("#selected-place").innerText()).includes(
        result.items[0].name,
      ),
    );
    assert.ok(
      await page.locator('#selected-place a[href*="uri.amap.com"]').count(),
    );
    assert.ok(await page.locator("#recommendations-title").isVisible());

    // Refresh reloads facts and restores the page without another success toast.
    await page.reload();
    await page.locator("#recommendations-title").waitFor();
    assert.equal(await page.locator("#toast.visible").count(), 0);
    await backToChat();
    assert.ok(
      (await page.locator("#conversation-log").innerText()).includes(plan),
    );

    // Structured edits use the same success-and-navigation behavior.
    await page.locator(".conditions [data-edit-needs]").click();
    await page.locator('#preferences-form [name="budget"]').fill("120");
    const editedResponse = page.waitForResponse((r) =>
      r.url().endsWith("/api/decision"),
    );
    await page.locator('#preferences-form button[type="submit"]').click();
    result = await (await editedResponse).json();
    assert.equal(result.budget_per_person, 60);
    await expectRecommendations(result);

    // A real empty result must not reuse the preceding success toast.
    await backToChat();
    await page.locator(".conditions [data-edit-needs]").click();
    await page
      .locator('#preferences-form [name="location_name"]')
      .fill("汉南区");
    const emptyResponse = page.waitForResponse((r) =>
      r.url().endsWith("/api/decision"),
    );
    await page.locator('#preferences-form button[type="submit"]').click();
    const empty = await (await emptyResponse).json();
    assert.equal(empty.items.length, 0);
    await page.locator("#request-message:not([disabled])").waitFor();
    assert.equal(await page.locator("#recommendations-title").count(), 0);
    assert.equal(await page.locator("#toast.visible").count(), 0);

    // Failure followed by retry only redirects when the retry actually succeeds.
    result = await send(plan);
    await expectRecommendations(result);
    await backToChat();
    await page.route("**/api/decision", (route) => route.abort());
    await page.locator("#request-message").fill("便宜一点");
    await page.locator('#decision-form button[type="submit"]').click();
    await page.locator("[data-retry-decision]").waitFor();
    assert.equal(await page.locator("#recommendations-title").count(), 0);
    assert.ok(!(await page.locator("#toast").innerText()).includes("推荐成功"));
    await page.unroute("**/api/decision");
    const retryResponse = page.waitForResponse((r) =>
      r.url().endsWith("/api/decision"),
    );
    await page.locator("[data-retry-decision]").click();
    result = await (await retryResponse).json();
    await expectRecommendations(result);

    // Navigating elsewhere while waiting is respected after a delayed response.
    await backToChat();
    let release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    await page.route("**/api/decision", async (route) => {
      await gate;
      await route.continue();
    });
    await page.locator("#request-message").fill(plan);
    const delayedResponse = page.waitForResponse((r) =>
      r.url().endsWith("/api/decision"),
    );
    await page.locator('#decision-form button[type="submit"]').click();
    await page.locator(".thinking").waitFor();
    await page.locator('.main-nav [data-page="saved"]').click();
    await page.locator('.main-nav [data-page="saved"].active').waitFor();
    release();
    await delayedResponse;
    await page.unroute("**/api/decision");
    await page.locator("[data-card]").first().waitFor();
    assert.equal(await page.locator("#recommendations-title").count(), 0);
    assert.equal(await page.locator("#toast.visible").count(), 0);

    await backToChat();
    result = await send(plan);
    await expectRecommendations(result);
    for (const width of [320, 390, 700, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      assert.ok(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `overflow at ${width}px`,
      );
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => scrollTo({ top: 0, behavior: "instant" }));
    await snapshot("recommendations-mobile.png");
    assert.deepEqual(errors, []);
    console.log(
      "PASS: success toast and dedicated recommendation page, exact candidate IDs, clarification/lookup/empty/failure safeguards, retry, structured edits, refresh, history, card actions, delayed navigation and responsive layout.",
    );
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
````

<a id="source-42"></a>

## 42. tests/session_store.test.mjs

[打开原文件](../tests/session_store.test.mjs) · 73 行

SHA-256：`a4d29e41659ccf8da96334e73e928cd08cea1c1417c2c031a0f49eb4266be7c3`

````javascript
import test from "node:test";
import assert from "node:assert/strict";
import {
  loadConversation,
  saveConversation,
  clearConversation,
} from "../static/session-store.js";

const key = "nightfind-conversation-v1";
function memoryStorage() {
  const values = new Map();
  globalThis.localStorage = {
    getItem: (name) => values.get(name) ?? null,
    setItem: (name, value) => values.set(name, value),
    removeItem: (name) => values.delete(name),
  };
}

test("persists preferences, draft and IDs without caching merchant prices", () => {
  memoryStorage();
  saveConversation({
    page: "recommendations",
    history: [{ role: "user", text: "江汉路两个人" }],
    preferences: { party_size: 2 },
    selected: { id: 7, price_per_person: 999 },
    compared: new Map([[7, { id: 7 }]]),
    draft: "还没发",
    result: { stage: "catalog" },
    busy: false,
    failedRequest: false,
  });
  const saved = loadConversation();
  assert.equal(saved.page, "recommendations");
  assert.equal(saved.preferences.party_size, 2);
  assert.equal(saved.selectedId, 7);
  assert.deepEqual(saved.comparedIds, [7]);
  assert.equal(saved.draft, "还没发");
  assert.ok(!localStorage.getItem(key).includes("price_per_person"));
  clearConversation();
  assert.equal(loadConversation(), null);
});

test("expires after 24 hours and rejects malformed timestamps", () => {
  memoryStorage();
  localStorage.setItem(
    key,
    JSON.stringify({ version: 1, savedAt: Date.now() - 25 * 3600000 }),
  );
  assert.equal(loadConversation(), null);
  localStorage.setItem(key, JSON.stringify({ version: 1 }));
  assert.equal(loadConversation(), null);
  localStorage.setItem(key, "invalid json");
  assert.equal(loadConversation(), null);
});

test("unavailable browser storage does not prevent application startup", () => {
  globalThis.localStorage = {
    getItem() {
      throw Error("disabled");
    },
    setItem() {
      throw Error("disabled");
    },
    removeItem() {
      throw Error("disabled");
    },
  };
  assert.equal(loadConversation(), null);
  assert.doesNotThrow(() =>
    saveConversation({ history: [], compared: new Map() }),
  );
  assert.doesNotThrow(() => clearConversation());
});
````

<a id="source-43"></a>

## 43. tests/test_app.py

[打开原文件](../tests/test_app.py) · 131 行

SHA-256：`311fd2dab4996d7512b6f8165aac2ad2ac13a2674b19b5a659f2a819d2f12bbc`

````python
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from services import chat, parse_preferences, recommend


class NightFindTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_path = database.DB_PATH
        database.DB_PATH = Path(self.temp_dir.name) / "nightfind-test.db"
        database.initialize_database(import_snapshot=False, import_bundled_catalog=False, include_demo=True)
        with database.connect() as connection:
            database.ensure_session(connection, "test-session")

    def tearDown(self):
        database.DB_PATH = self.original_path
        self.temp_dir.cleanup()

    def test_database_initializes_without_duplicate_seed_data(self):
        database.initialize_database(include_demo=True)
        with database.connect() as connection:
            merchant_count = connection.execute(
                "SELECT COUNT(*) FROM restaurants"
            ).fetchone()[0]
            dish_count = connection.execute(
                "SELECT COUNT(*) FROM dishes"
            ).fetchone()[0]
            self.assertEqual(merchant_count, 24)
            self.assertEqual(dish_count, 72)
            self.assertEqual(
                connection.execute("PRAGMA foreign_key_check").fetchall(), []
            )

    def test_merchant_search_filters_by_district_and_budget(self):
        with database.connect() as connection:
            merchants = database.list_merchants(
                connection, district="江汉路", max_price=50
            )
            self.assertTrue(merchants)
            self.assertTrue(all(item["district"] == "江汉路" for item in merchants))
            self.assertTrue(all(item["price"] <= 50 for item in merchants))

    def test_merchant_detail_contains_menu_and_demo_notice(self):
        with database.connect() as connection:
            merchant = database.get_merchant(connection, 1)
            self.assertIsNotNone(merchant)
            self.assertEqual(len(merchant["dishes"]), 3)
            self.assertTrue(merchant["is_demo"])
            self.assertIn("商圈", merchant["address_label"])

    def test_preferences_parse_chinese_time_and_budget(self):
        districts = [
            {"id": 1, "name": "江汉路"},
            {"id": 2, "name": "楚河汉街"},
        ]
        preferences = parse_preferences(
            "江汉路，人均 60 元，晚上九点半，一个人吃清淡一点",
            {},
            districts,
        )
        self.assertEqual(preferences["district"], "江汉路")
        self.assertEqual(preferences["budget"], 60)
        self.assertEqual(preferences["scene"], "独自用餐")
        self.assertEqual(preferences["cuisine"], "粥粉面")
        self.assertEqual(preferences["hour"], 21.5)

    def test_recommendations_obey_hard_constraints(self):
        with database.connect() as connection:
            preferences = {
                "district": "江汉路",
                "budget": 50,
                "wait": 20,
                "hour": 21,
                "scene": "独自用餐",
                "cuisine": "不限",
            }
            items = recommend(connection, preferences, "test-session")
            self.assertTrue(items)
            for item in items:
                self.assertLessEqual(item["price"], 50)
                self.assertLessEqual(item["wait"], 20)
                self.assertEqual(item["district"], "江汉路")

    def test_chat_works_without_api_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            with database.connect() as connection:
                result = chat(
                    connection,
                    {
                        "message": "江汉路人均 60 元，晚上九点，一个人吃清淡一点",
                        "context": {},
                        "history": [],
                    },
                    "test-session",
                    database.list_districts(connection),
                )
        self.assertEqual(result["mode"], "local")
        self.assertTrue(result["reply"])
        self.assertTrue(result["tips"])
        self.assertEqual(result["constraints"]["budget"], 60)

    def test_suggestion_is_saved_and_summary_is_aggregated(self):
        with database.connect() as connection:
            database.create_suggestion(
                connection, "test-session", "功能建议", "希望增加素食筛选。"
            )
            summary = database.suggestion_summary(connection)
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["categories"][0]["category"], "功能建议")

    def test_feedback_is_validated_and_appears_in_merchant_detail(self):
        with database.connect() as connection:
            database.create_feedback(
                connection, "test-session", 1, 5, "菜品介绍清楚。"
            )
            merchant = database.get_merchant(connection, 1)
        self.assertEqual(merchant["reviews"][0]["rating"], 5)
        with database.connect() as connection:
            with self.assertRaises(ValueError):
                database.create_feedback(
                    connection, "test-session", 9999, 5, "无效商家"
                )


if __name__ == "__main__":
    unittest.main()
````

<a id="source-44"></a>

## 44. tests/test_catalog_refresh.py

[打开原文件](../tests/test_catalog_refresh.py) · 84 行

SHA-256：`78ffd944f756fe940e43ad039b50bf77dda53276631b91e467ca036a80ef7a15`

````python
"""Only branch-matched source facts are imported; missing prices stay missing."""

import json
import unittest
from refresh_wuhan_catalog import parse_page


class CatalogRefreshTests(unittest.TestCase):
    def setUp(self):
        self.expected = dict(
            name="测试餐厅（武汉店）",
            external_id="web:test",
            source_url="https://gs.ctrip.com/html5/you/foods/fooddetail/145/123.html",
        )
        self.info = dict(
            Name="测试餐厅(武汉店)",
            RestaurantId=123,
            DistrictName="武汉",
            Address="武汉市江汉区某路10号",
            GDCoord=dict(Lat=30.6, Lng=114.3),
            AveragePrice=80,
            BookTelList=None,
            WeekdayDtoList=[
                dict(
                    Weekday="周一",
                    OpenTimeList=[dict(BeginTime="11:00", EndTime="14:00")],
                )
            ],
            RestaurantRecommendedFoodList=[
                dict(Title="来源菜品", Price="¥ 18"),
                dict(Title="无价菜品", Price=""),
            ],
        )

    def html(self):
        data = dict(
            props=dict(
                pageProps=dict(
                    initialState=dict(mainInfoData=dict(RestaurantInfo=self.info))
                )
            )
        )
        return (
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(data)
            + "</script>"
        )

    def test_prices_coordinates_and_weekday_hours_keep_provenance(self):
        fields, menu, evidence = parse_page(self.html(), self.expected)
        self.assertEqual(fields["opening_hours"], "Mo 11:00-14:00")
        self.assertEqual(fields["price_per_person"], 80)
        self.assertNotEqual(fields["latitude"], 30.6)
        self.assertIn("GCJ-02", fields["location_note"])
        self.assertEqual(menu[0]["price"], 18)
        self.assertEqual(menu[1]["price"], "")
        self.assertIn("未注明份量", menu[0]["price_unit"])
        self.assertEqual(evidence["GDCoord"]["Lat"], 30.6)

    def test_wrong_branch_city_or_source_id_is_rejected(self):
        for changes in [
            dict(Name="测试餐厅(另一家店)"),
            dict(DistrictName="上海"),
            dict(RestaurantId=999),
        ]:
            original = dict(self.info)
            self.info.update(changes)
            with self.assertRaises(ValueError):
                parse_page(self.html(), self.expected)
            self.info = original

    def test_recommendation_title_is_not_a_price(self):
        self.info["RestaurantRecommendedFoodList"][0]["Price"] = "人均 18 元"
        _, menu, _ = parse_page(self.html(), self.expected)
        self.assertEqual(menu[0]["price"], "")

    def test_incomplete_schedule_keeps_other_source_facts(self):
        self.info["WeekdayDtoList"] = [
            None,
            dict(Weekday="周一", OpenTimeList=[dict(BeginTime=None, EndTime=None)]),
        ]
        fields, menu, _ = parse_page(self.html(), self.expected)
        self.assertNotIn("opening_hours", fields)
        self.assertEqual(menu[0]["price"], 18)
````

<a id="source-45"></a>

## 45. tests/test_decision.py

[打开原文件](../tests/test_decision.py) · 483 行

SHA-256：`f97f5e80e703a1040a5c579ee310a0532555cf18dc0f062b1f3b87efe23761af`

````python
"""Decision journey: request parsing, real facts, hard limits and action APIs."""

import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

import database
from app import NightFindHandler
from decision_catalog import saved_real_merchants, set_real_favorite
from decision_preferences import (
    LOCAL_ZONE,
    next_question,
    parse_request,
    per_person_budget,
)
from dining_decision import make_decision, opening_status
from real_catalog import (
    import_real_merchants,
    get_public_real_merchant,
    public_real_merchants,
)

NOW = datetime(2026, 11, 4, 16, 0, tzinfo=LOCAL_ZONE)


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.no_ai = patch.dict(os.environ, {"OPENAI_API_KEY": ""})
        self.no_ai.start()
        self.addCleanup(self.no_ai.stop)

    def test_windows_without_iana_data_keeps_beijing_time(self):
        import importlib.util
        from zoneinfo import ZoneInfoNotFoundError

        path = Path(__file__).resolve().parents[1] / "decision_preferences.py"
        spec = importlib.util.spec_from_file_location("windows_preferences", path)
        module = importlib.util.module_from_spec(spec)
        with patch("zoneinfo.ZoneInfo", side_effect=ZoneInfoNotFoundError("missing")):
            spec.loader.exec_module(module)
        context, _ = module.parse_request(
            "今晚七点，四个人，江汉路，总预算300元", now=NOW
        )
        self.assertEqual(context["arrival"], "2026-11-04T19:00+08:00")
        self.assertEqual(module.per_person_budget(context), 75)

    def test_full_request_and_total_budget(self):
        context, mode = parse_request(
            "今晚七点，四个人在江汉路附近，总共三百元，想吃湖北菜", now=NOW
        )
        self.assertEqual(context["party_size"], 4)
        self.assertEqual(per_person_budget(context), 75)
        self.assertEqual(context["arrival"], "2026-11-04T19:00+08:00")
        self.assertEqual(context["location"]["name"], "江汉路")
        self.assertEqual(context["cuisine"], "湖北菜")
        self.assertIsNone(next_question(context, NOW))
        self.assertEqual(mode, "local")

    def test_ambiguous_budget_asks_unit_then_preserves_it(self):
        context, _ = parse_request("江汉路，两个人，明天七点，预算200", now=NOW)
        self.assertIn("每个人", next_question(context, NOW)["question"])
        context, _ = parse_request("是总预算", context, now=NOW)
        self.assertEqual(per_person_budget(context), 100)
        context, _ = parse_request("预算降到160", context, now=NOW)
        self.assertEqual(per_person_budget(context), 80)

    def test_waiting_minutes_are_not_a_budget(self):
        context, _ = parse_request("江汉路，等位最多20分钟", now=NOW)
        self.assertIsNone(context["budget"])
        self.assertEqual(context["wait_minutes"], 20)

    def test_multi_turn_does_not_turn_one_allergic_diner_into_group_size(self):
        context, _ = parse_request("江汉路，四个人，总预算300，今晚七点", now=NOW)
        context, _ = parse_request("我们有一个人不吃辣", context, now=NOW)
        self.assertEqual(context["party_size"], 4)
        self.assertEqual(context["avoid"], ["辣"])
        self.assertEqual(per_person_budget(context), 75)
        context, _ = parse_request("改成两个人，明天同一时间", context, now=NOW)
        self.assertEqual(context["party_size"], 2)
        self.assertEqual(per_person_budget(context), 150)
        self.assertEqual(context["arrival"], "2026-11-05T19:00+08:00")

    def test_unknown_new_location_is_not_silently_ignored(self):
        context, _ = parse_request("江汉路", now=NOW)
        context, _ = parse_request("改成在武汉站附近吃饭", context, now=NOW)
        self.assertIsNone(context["location"])
        self.assertIn("哪里", next_question(context, NOW)["question"])

    def test_invalid_values_and_unrecognised_time_remain_visible(self):
        for text in ("江汉路，0个人", "江汉路，晚上25点", "总预算0元"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_request(text, now=NOW)
        context, _ = parse_request("江汉路，一人，人均50元，晚上七点", now=NOW)
        self.assertTrue(context["arrival_date_inferred"])
        context, _ = parse_request("江汉路，一人，人均50元，今天上午九点", now=NOW)
        self.assertIn("过去", next_question(context, NOW)["question"])

    def test_landmark_origin_survives_followups_without_becoming_device_coordinates(
        self,
    ):
        context, _ = parse_request("江汉路", now=NOW)
        context, _ = parse_request("四个人", context, now=NOW)
        self.assertEqual(context["location"]["district"], "江汉区")
        self.assertIn("商圈中心", context["location"]["note"])

    def test_unsupported_weekday_does_not_silently_become_today(self):
        context, _ = parse_request("江汉路，一个人，人均50元，下周五晚上七点", now=NOW)
        self.assertIsNone(context["arrival"])
        self.assertIn("什么时候", next_question(context, NOW)["question"])

    def test_preference_followups_do_not_become_one_oclock(self):
        original, _ = parse_request(
            "明天晚上七点，两个人，江汉路，总预算400元", now=NOW
        )
        for message, priority in (("便宜一点", "budget"), ("找近一点", "distance")):
            with self.subTest(message=message):
                context, _ = parse_request(message, original, now=NOW)
                self.assertEqual(context["arrival"], original["arrival"])
                self.assertEqual(context["budget"], original["budget"])
                self.assertEqual(context["priority"], priority)
                self.assertIsNone(next_question(context, NOW))
        context, _ = parse_request("找近一点，改到明天晚上八点", original, now=NOW)
        self.assertEqual(context["arrival"], "2026-11-05T20:00+08:00")

    def test_device_location_is_wuhan_bounded_and_labelled(self):
        location = {"name": "我的位置", "latitude": 30.586, "longitude": 114.291}
        context, _ = parse_request("当前位置", location=location, now=NOW)
        self.assertEqual(context["provenance"]["location"], "device")
        with self.assertRaises(ValueError):
            parse_request("当前位置", location={**location, "latitude": 40}, now=NOW)

    def test_ai_only_extracts_request_fields_with_local_fallback(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}):
            with patch(
                "decision_preferences._extract_with_ai",
                return_value={
                    "party_size": 3,
                    "budget": 80,
                    "budget_kind": "per_person",
                },
            ):
                context, mode = parse_request("三位朋友想吃点东西", now=NOW)
                self.assertEqual(mode, "ai")
                self.assertEqual(context["party_size"], 3)
            with patch(
                "decision_preferences._extract_with_ai",
                side_effect=ValueError("bad JSON"),
            ):
                context, mode = parse_request("江汉路，两个人，人均80元", now=NOW)
                self.assertEqual(mode, "fallback")
                self.assertEqual(context["budget"], 80)

    def test_opening_hours_respect_midnight_and_weekday(self):
        self.assertEqual(
            opening_status("17:00-02:00", "2026-11-05T01:30+08:00"), "open"
        )
        self.assertEqual(
            opening_status("17:00-02:00", "2026-11-05T02:00+08:00"), "closed"
        )
        self.assertEqual(
            opening_status("Mo-Fr 17:00-02:00", "2026-11-07T01:00+08:00"), "open"
        )
        self.assertEqual(
            opening_status("Mo-Fr 17:00-02:00", "2026-11-08T01:00+08:00"), "closed"
        )
        self.assertEqual(
            opening_status("节假日另行安排", "2026-11-05T19:00+08:00"), "unknown"
        )


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = database.DB_PATH
        database.DB_PATH = Path(self.temp.name) / "decision.db"
        self.no_ai = patch.dict(os.environ, {"OPENAI_API_KEY": ""})
        self.no_ai.start()
        database.initialize_database(
            import_snapshot=False, import_bundled_catalog=False
        )
        self.connection = database.connect()
        database.ensure_session(self.connection, "visitor-a")
        database.ensure_session(self.connection, "visitor-b")
        self.arrival = (
            (datetime.now(LOCAL_ZONE) + timedelta(days=1))
            .replace(hour=19, minute=0)
            .isoformat()
        )
        self.preferences, _ = parse_request(
            "江汉路，四个人，总预算300，湖北菜", {"arrival": self.arrival}
        )

    def tearDown(self):
        self.connection.close()
        database.DB_PATH = self.old_path
        self.no_ai.stop()
        self.temp.cleanup()

    def add_merchant(self, external_id, **overrides):
        today = datetime.now().date().isoformat()
        record = dict(
            external_id=external_id,
            name="真实门店-" + external_id,
            district="江汉区",
            address="武汉市江汉区测试街1号",
            cuisine="湖北菜",
            latitude=30.586,
            longitude=114.291,
            price_per_person=58,
            opening_hours="17:00-23:00",
            source_name="商家授权资料",
            source_url="https://example.org/store/" + external_id,
            verified_at=today,
            source_checked_at=today,
            verification_method="商家确认",
            status="verified",
        )
        record.update(overrides)
        import_real_merchants(self.connection, [record])
        return self.connection.execute(
            "SELECT id FROM real_merchants WHERE external_id=?", (external_id,)
        ).fetchone()[0]

    def decide(self, **payload):
        return make_decision(
            self.connection, self.preferences, {"message": "帮我挑选", **payload}
        )

    def test_only_three_real_candidates_and_known_hard_failures_excluded(self):
        ids = [self.add_merchant(str(i)) for i in range(5)]
        expensive = self.add_merchant("expensive", price_per_person=100)
        closed = self.add_merchant("closed", opening_hours="08:00-12:00")
        result = self.decide()
        self.assertEqual(len(result["items"]), 3)
        self.assertTrue({item["id"] for item in result["items"]} <= set(ids))
        self.assertNotIn(expensive, [item["id"] for item in result["items"]])
        self.assertNotIn(closed, [item["id"] for item in result["items"]])
        self.assertEqual(result["eligible_total"], 5)
        self.assertTrue(
            all(item["name"].startswith("真实门店") for item in result["items"])
        )

    def test_unknown_facts_are_conditional_not_fabricated(self):
        self.add_merchant(
            "unknown",
            price_per_person=None,
            opening_hours=None,
            latitude=None,
            longitude=None,
        )
        self.preferences["wait_minutes"] = 15
        item = self.decide()["items"][0]
        self.assertTrue(item["needs_confirmation"])
        self.assertEqual(item["opening_status"], "unknown")
        self.assertIsNone(item["estimated_total"])
        self.assertIsNone(item["distance_km"])
        self.assertTrue(any("实时排队" in value for value in item["questions"]))
        self.assertIn("navigation_url", item)
        self.assertNotIn("score", item)

    def test_radius_uses_unrounded_distance_and_keeps_unknown_explicit(self):
        near = self.add_merchant("near")
        self.add_merchant("far", latitude=30.9)
        self.preferences["radius_km"] = 1
        result = self.decide()
        self.assertEqual([item["id"] for item in result["items"]], [near])
        self.assertEqual(result["excluded"]["超过指定直线距离"], 1)

    def test_budget_uses_upper_end_of_source_range(self):
        self.add_merchant(
            "range",
            price_per_person=None,
            price_range_min=20,
            price_range_max=100,
            price_range_basis="per_person",
        )
        self.assertEqual(self.decide()["items"], [])

    def test_dish_price_range_is_never_used_as_per_person_budget(self):
        self.add_merchant(
            "dish-band",
            price_per_person=None,
            price_range_min=20,
            price_range_max=50,
            price_range_basis="dish",
        )
        item = self.decide()["items"][0]
        self.assertIsNone(item["estimated_total"])
        self.assertTrue(any("缺少可靠人均" in value for value in item["questions"]))
        self.assertFalse(any("预算内" in value for value in item["reasons"]))

    def test_allergy_conflicts_and_unverified_ingredients(self):
        self.add_merchant("spicy", cuisine="香辣湖北菜")
        safe_unknown = self.add_merchant("plain")
        self.preferences["avoid"] = ["辣"]
        result = self.decide()
        self.assertEqual([item["id"] for item in result["items"]], [safe_unknown])
        self.assertTrue(
            any("不能证明" in value for value in result["items"][0]["questions"])
        )

    def test_rotation_keeps_requested_store_and_never_repeats_seen_as_new(self):
        ids = [self.add_merchant(str(i)) for i in range(4)]
        result = self.decide(message="换一批", seen_ids=ids[:3], keep_ids=[ids[0]])
        self.assertEqual({item["id"] for item in result["items"]}, {ids[0], ids[3]})
        empty = self.decide(message="换一批", seen_ids=ids)
        self.assertEqual(empty["items"], [])
        self.assertTrue(empty["exhausted"])

    def test_numbered_followup_preserves_or_replaces_correct_candidate(self):
        ids = [self.add_merchant(str(i)) for i in range(4)]
        result = self.decide(message="第二家太贵，换一家", previous_ids=ids[:3])
        self.assertNotIn(ids[1], [item["id"] for item in result["items"]])
        result = self.decide(
            message="保留第三家，换一批", previous_ids=ids[:3], seen_ids=ids[:3]
        )
        self.assertEqual(result["items"][0]["id"], ids[2])
        self.assertTrue(result["items"][0]["kept"])

    def test_real_favorites_are_separate_idempotent_and_session_scoped(self):
        merchant_id = self.add_merchant("saved")
        set_real_favorite(self.connection, "visitor-a", merchant_id, True)
        set_real_favorite(self.connection, "visitor-a", merchant_id, True)
        self.assertEqual(len(saved_real_merchants(self.connection, "visitor-a")), 1)
        self.assertEqual(saved_real_merchants(self.connection, "visitor-b"), [])
        self.assertEqual(database.list_favorites(self.connection, "visitor-a"), [])
        set_real_favorite(self.connection, "visitor-a", merchant_id, False)
        self.assertEqual(saved_real_merchants(self.connection, "visitor-a"), [])

    def test_ranking_reads_beyond_first_catalog_page(self):
        for index in range(101):
            self.add_merchant(str(index), price_per_person=100 if index else 50)
        # The oldest, only affordable record is outside the first descending page.
        self.assertEqual(self.decide()["items"][0]["name"], "真实门店-0")

    def test_public_reads_hide_expired_images_and_menu_even_without_reimport(self):
        merchant_id = self.add_merchant("dated")
        c = self.connection
        c.execute(
            "INSERT INTO real_merchant_images(merchant_id,image_url,taken_at) VALUES (?,?,?)",
            (merchant_id, "https://example.org/old.jpg", "2020-01-01"),
        )
        c.execute(
            "INSERT INTO real_merchant_menu_items(merchant_id,dish_name,price,price_checked_at) VALUES (?,?,?,?)",
            (merchant_id, "旧价格", 20, "2020-01-01"),
        )
        detail = get_public_real_merchant(c, merchant_id)
        self.assertEqual(detail["images"], [])
        self.assertEqual(detail["menu_items"], [])
        self.assertIsNone(public_real_merchants(c)["items"][0]["cover_image_url"])


class DecisionHttpTests(unittest.TestCase):
    def test_request_to_real_comparison_collection_and_navigation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            database, "DB_PATH", Path(tmp) / "http.db"
        ), patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            database.initialize_database()
            server = ThreadingHTTPServer(("127.0.0.1", 0), NightFindHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = "http://127.0.0.1:" + str(server.server_port)

            def call(path, body=None, visitor="journey-a"):
                request = Request(
                    base + path,
                    data=json.dumps(body).encode() if body is not None else None,
                    headers={"X-Session": visitor, "Content-Type": "application/json"},
                )
                with urlopen(request, timeout=5) as response:
                    return json.load(response)

            try:
                result = call(
                    "/api/decision",
                    {
                        "message": "明天晚上七点，四个人，江汉路附近，总预算300元，湖北菜"
                    },
                )
                self.assertEqual(len(result["items"]), 3)
                self.assertEqual(result["budget_per_person"], 75)
                ids = [item["id"] for item in result["items"]]
                comparison = call(
                    "/api/real-compare?ids=" + ",".join(map(str, ids[:2]))
                )
                self.assertEqual(len(comparison["items"]), 2)
                item = comparison["items"][0]
                self.assertIn("to=", item["navigation_url"])
                self.assertIn("coordinate=gaode", item["navigation_url"])
                self.assertIn("uri.amap.com", item["map_search_url"])
                detail = call("/api/real-merchants/" + str(item["id"]))
                self.assertEqual(detail["name"], item["name"])
                self.assertIn("menu_items", detail)
                with patch.dict(os.environ, {"AMAP_WEB_KEY": ""}):
                    config = call("/api/map-config")
                    self.assertFalse(config["walking_enabled"])
                    route = call(
                        "/api/walking-route",
                        {
                            "merchant_id": item["id"],
                            "origin": {
                                "name": "江汉路",
                                "latitude": 30.586,
                                "longitude": 114.291,
                            },
                        },
                    )
                    self.assertEqual(route["status"], "unconfigured")
                    self.assertIn("uri.amap.com/navigation", route["navigation_url"])
                edited = call(
                    "/api/decision",
                    {
                        "message": "修改用餐条件",
                        "intent": "plan",
                        "preferences": {
                            "party_size": 3,
                            "budget": 180,
                            "budget_kind": "total",
                            "location": {"name": "江汉路"},
                            "arrival": (
                                datetime.now(LOCAL_ZONE) + timedelta(hours=2)
                            ).isoformat(),
                        },
                    },
                )
                self.assertEqual(edited["constraints"]["party_size"], 3)
                self.assertEqual(edited["budget_per_person"], 60)
                call("/api/real-favorites", {"merchant_id": item["id"], "active": True})
                self.assertEqual(
                    call("/api/real-favorites")["items"][0]["name"], item["name"]
                )
                self.assertEqual(
                    call("/api/real-favorites", visitor="journey-b")["items"], []
                )
                with self.assertRaises(HTTPError) as error:
                    call("/api/real-compare?ids=1,1")
                self.assertEqual(error.exception.code, 400)
                for asset in (
                    "/",
                    "/app.js",
                    "/api-client.js",
                    "/session-store.js",
                    "/decision-view.js",
                    "/decision.css",
                    "/wuhan_map.js",
                    "/botanical.svg",
                    "/decorations.js",
                    "/map/wuhan-basemap.geojson",
                ):
                    with urlopen(base + asset) as response:
                        self.assertEqual(response.status, 200)
                        if asset.endswith(".geojson"):
                            basemap = json.load(response)
                            self.assertEqual(basemap["type"], "FeatureCollection")
                            roads = [
                                feature
                                for feature in basemap["features"]
                                if feature["properties"]["layer"] == "road"
                            ]
                            self.assertGreaterEqual(len(roads), 500)
                            self.assertIn(
                                "徐东大街",
                                [road["properties"]["name"] for road in roads],
                            )
                            self.assertTrue(
                                any(
                                    feature["properties"]["layer"] == "lake"
                                    and feature["geometry"]["type"] == "Polygon"
                                    for feature in basemap["features"]
                                )
                            )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
````

<a id="source-46"></a>

## 46. tests/test_experience.py

[打开原文件](../tests/test_experience.py) · 120 行

SHA-256：`423e82f9bf5e2d083eabf6126a2e8247f35d508c66581bfd14f9d0f612b5e108`

````python
"""Tests for the conversational experience, comparisons, and saved list."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from comparison import compare_merchants, parse_merchant_ids
from conversation import choose_candidate_round, follow_up_suggestions
from services import chat


class ExperienceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.previous_database = database.DB_PATH
        database.DB_PATH = Path(self.temporary.name) / "experience.db"
        database.initialize_database(import_snapshot=False, import_bundled_catalog=False, include_demo=True)
        with database.connect() as connection:
            database.ensure_session(connection, "visitor-a")
            database.ensure_session(connection, "visitor-b")

    def tearDown(self):
        database.DB_PATH = self.previous_database
        self.temporary.cleanup()

    def ask(self, message, context=None, seen=None):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            with database.connect() as connection:
                return chat(
                    connection,
                    {
                        "message": message,
                        "context": context or {},
                        "seen_ids": seen or [],
                    },
                    "visitor-a",
                    database.list_districts(connection),
                )

    def test_missing_preferences_generate_useful_followup(self):
        result = self.ask("晚上想吃点热乎的")
        self.assertIn("商圈", result["follow_up"]["question"])
        self.assertTrue(result["follow_up"]["actions"])
        self.assertNotIn("district", result["constraints"]["known"])

    def test_multi_turn_preserves_district_budget_and_scene(self):
        first = self.ask("江汉路附近，跟朋友吃点烧烤")
        self.assertEqual(first["constraints"]["district"], "江汉路")
        self.assertIn("district", first["constraints"]["known"])
        second = self.ask("人均 100 元以内", first["constraints"])
        self.assertEqual(second["constraints"]["district"], "江汉路")
        self.assertEqual(second["constraints"]["budget"], 100)
        self.assertEqual(second["constraints"]["cuisine"], "烧烤")
        self.assertIn("budget", second["constraints"]["known"])
        third = self.ask("便宜一点", second["constraints"])
        self.assertEqual(third["constraints"]["budget"], 80)
        self.assertEqual(third["constraints"]["scene"], "朋友聚会")

    def test_waiting_minutes_do_not_become_budget(self):
        result = self.ask("江汉路，等位最多 20 分钟")
        self.assertEqual(result["constraints"]["wait"], 20)
        self.assertEqual(result["constraints"]["budget"], 100)
        self.assertNotIn("budget", result["constraints"]["known"])

    def test_short_wait_followup_updates_existing_preference(self):
        first = self.ask("江汉路，人均 100 元，等位最多 40 分钟")
        next_turn = self.ask("少等一会", first["constraints"])
        self.assertEqual(next_turn["constraints"]["wait"], 30)
        self.assertEqual(next_turn["constraints"]["district"], "江汉路")

    def test_another_batch_avoids_previously_displayed_ids(self):
        first = self.ask("江汉路，预算 120 元，等位 40 分钟")
        initial_ids = [item["id"] for item in first["items"][:3]]
        other = self.ask("换一批", first["constraints"], initial_ids)
        other_ids = [item["id"] for item in other["items"]]
        self.assertTrue(other_ids)
        self.assertTrue(set(other_ids).isdisjoint(initial_ids))
        self.assertEqual(other["total"], first["total"])

    def test_invalid_compare_selection_is_rejected(self):
        for ids in ("", "1", "1,1", "1,2,3,4", "1,-2", "a,b", "0,1"):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                parse_merchant_ids(ids)
        with database.connect() as connection:
            with self.assertRaises(ValueError):
                compare_merchants(connection, "1,9999")

    def test_compare_two_or_three_with_transparent_trades(self):
        with database.connect() as connection:
            two = compare_merchants(connection, "1,2", scene="朋友聚会")
            three = compare_merchants(connection, "1,2,3")
        self.assertEqual(len(two["items"]), 2)
        self.assertEqual(len(three["items"]), 3)
        self.assertIn(two["summary"]["recommended_id"], [1, 2])
        self.assertTrue(two["summary"]["cheapest_ids"])
        self.assertTrue(two["summary"]["fastest_ids"])
        self.assertIn("演示数据", two["summary"]["sample_notice"])
        self.assertTrue(all("comparison_score" in item for item in two["items"]))

    def test_saved_items_persist_in_sqlite_and_are_session_isolated(self):
        with database.connect() as connection:
            database.set_favorite(connection, "visitor-a", 3, True)
            database.set_favorite(connection, "visitor-a", 1, True)
            connection.commit()
            one = database.list_saved_merchants(connection, "visitor-a")
            other = database.list_saved_merchants(connection, "visitor-b")
            self.assertEqual({item["id"] for item in one}, {1, 3})
            self.assertEqual(other, [])
            database.set_favorite(connection, "visitor-a", 3, False)
            connection.commit()
            self.assertEqual(
                [item["id"] for item in database.list_saved_merchants(connection, "visitor-a")],
                [1],
            )


if __name__ == "__main__":
    unittest.main()
````

<a id="source-47"></a>

## 47. tests/test_http.py

[打开原文件](../tests/test_http.py) · 165 行

SHA-256：`efdab4a9c6ae6cfcbbbb0429e3fcd1314cf429b67409c4f0ee0dfb1e54f35cfb`

````python
import json
import os
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path

import database
from app import NightFindHandler


class HttpApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        self.original_api_key = os.environ.get("OPENAI_API_KEY")
        database.DB_PATH = Path(self.temp_dir.name) / "http-test.db"
        os.environ["OPENAI_API_KEY"] = ""
        database.initialize_database(
            import_snapshot=False, import_bundled_catalog=False, include_demo=True
        )

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), NightFindHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = "http://127.0.0.1:{}".format(self.server.server_port)
        self.headers = {"X-Session": "http-test-session"}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        database.DB_PATH = self.original_db_path
        if self.original_api_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = self.original_api_key
        self.temp_dir.cleanup()

    def call_api(self, path, payload=None):
        body = None
        headers = dict(self.headers)
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers=headers,
            method="POST" if payload is not None else "GET",
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_primary_user_journey(self):
        health = self.call_api("/api/health")
        self.assertEqual(health["status"], "ok")

        bootstrap = self.call_api("/api/bootstrap")
        self.assertEqual(len(bootstrap["districts"]), 4)
        self.assertFalse(bootstrap["ai_enabled"])

        directory = self.call_api("/api/merchants?district=%E6%B1%9F%E6%B1%89%E8%B7%AF")
        self.assertTrue(directory["items"])
        self.assertTrue(
            all(item["district"] == "江汉路" for item in directory["items"])
        )

        merchant = self.call_api("/api/merchants/1")
        self.assertEqual(len(merchant["dishes"]), 3)

        chat_result = self.call_api(
            "/api/chat",
            {
                "message": "江汉路，人均 50 元，一个人吃饭",
                "context": {},
                "history": [],
            },
        )
        self.assertEqual(chat_result["mode"], "local")
        self.assertTrue(chat_result["reply"])

        self.call_api(
            "/api/suggestions",
            {"category": "功能建议", "message": "希望增加素食筛选。"},
        )
        summary = self.call_api("/api/suggestions/summary")
        self.assertEqual(summary["total"], 1)

        self.call_api(
            "/api/feedback",
            {
                "merchant_id": 1,
                "rating": 5,
                "comment": "商家介绍看起来很清楚。",
            },
        )
        updated_merchant = self.call_api("/api/merchants/1")
        self.assertEqual(updated_merchant["reviews"][0]["rating"], 5)

    def test_chat_followups_have_actionable_prompts(self):
        first = self.call_api(
            "/api/chat",
            {
                "message": "今晚想吃烧烤",
                "context": {},
                "history": [],
            },
        )
        self.assertTrue(first["follow_up"]["actions"])
        self.assertIn("江汉路附近", first["follow_up"]["actions"])
        next_turn = self.call_api(
            "/api/chat",
            {
                "message": "江汉路",
                "context": first["constraints"],
                "history": [],
            },
        )
        self.assertEqual(next_turn["constraints"]["location"]["name"], "江汉路")
        self.assertEqual(next_turn["constraints"]["provenance"]["location"], "user")

    def test_compare_endpoint_rejects_bad_ids(self):
        result = self.call_api(
            "/api/compare?ids=1%2C2&scene=%E6%9C%8B%E5%8F%8B%E8%81%9A%E4%BC%9A"
        )
        self.assertEqual(len(result["items"]), 2)
        self.assertIn(result["summary"]["recommended_id"], (1, 2))
        for path in (
            "/api/compare?ids=1%2C1",
            "/api/compare?ids=1",
            "/api/compare?ids=1%2C2%2C3%2C4",
        ):
            with self.subTest(path=path), self.assertRaises(
                urllib.error.HTTPError
            ) as caught:
                self.call_api(path)
            self.assertEqual(caught.exception.code, 400)

    def test_save_view_remove_and_session_isolation(self):
        self.call_api("/api/favorites", {"merchant_id": 2, "active": True})
        saved = self.call_api("/api/saved")
        self.assertEqual([item["id"] for item in saved["items"]], [2])
        self.assertEqual(self.call_api("/api/favorites"), [2])
        old_headers = self.headers
        self.headers = {"X-Session": "another-visitor"}
        try:
            self.assertEqual(self.call_api("/api/saved")["items"], [])
        finally:
            self.headers = old_headers
        self.call_api("/api/favorites", {"merchant_id": 2, "active": False})
        self.assertEqual(self.call_api("/api/saved")["items"], [])

    def test_experience_stylesheet_is_served(self):
        with urllib.request.urlopen(self.base_url + "/experience.css") as response:
            content = response.read().decode("utf-8")
            self.assertIn("compare-tray", content)
            self.assertIn("saved-grid", content)


if __name__ == "__main__":
    unittest.main()
````

<a id="source-48"></a>

## 48. tests/test_map_services.py

[打开原文件](../tests/test_map_services.py) · 130 行

SHA-256：`57c7ce335277745bfe15fa7b46017f80c957a5e0fe9f0d6aaa5544641798a51b`

````python
"""Coordinates, optional keys and real provider responses; no live network required."""

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

from geo_coordinates import wgs84_to_gcj02, gcj02_to_wgs84
from map_services import public_map_config, walking_route, _fetch_route
from dining_decision import opening_status, prepare_decision


class MapServiceTests(unittest.TestCase):
    def setUp(self):
        _fetch_route.cache_clear()
        self.origin = dict(name="江汉路", latitude=30.586, longitude=114.291)
        self.merchant = dict(
            id=1,
            name="测试分店",
            latitude=30.6,
            longitude=114.3,
            map_search_url="https://uri.amap.com/search",
        )

    def test_known_conversion_and_round_trip(self):
        lat, lng = wgs84_to_gcj02(39.916527, 116.397128)
        self.assertAlmostEqual(lat, 39.91793074924595, places=7)
        self.assertAlmostEqual(lng, 116.40337249402477, places=7)
        self.assertEqual(gcj02_to_wgs84(lat, lng), (39.916527, 116.397128))
        self.assertEqual(wgs84_to_gcj02(48.85, 2.35), (48.85, 2.35))

    def test_private_route_key_never_appears_in_public_config(self):
        with patch.dict(
            "os.environ",
            {"TIANDITU_KEY": "browser-test", "AMAP_WEB_KEY": "private-test"},
        ):
            config = public_map_config()
        self.assertEqual(config["provider"], "tianditu")
        self.assertNotIn("private-test", json.dumps(config))
        self.assertTrue(config["walking_enabled"])

    def test_missing_key_provides_external_route_without_fabricated_duration(self):
        with patch.dict("os.environ", {"AMAP_WEB_KEY": ""}), patch(
            "map_services.urlopen"
        ) as network:
            result = walking_route(self.origin, self.merchant)
        network.assert_not_called()
        self.assertEqual(result["status"], "unconfigured")
        self.assertIn("from=", result["navigation_url"])
        self.assertIn("coordinate=gaode", result["navigation_url"])
        self.assertNotIn("duration_seconds", result)

    def test_real_provider_response_is_converted_and_cached(self):
        lat, lng = wgs84_to_gcj02(30.6, 114.3)
        response = dict(
            status="1",
            route=dict(
                paths=[
                    dict(
                        distance="1600",
                        duration="1234",
                        steps=[
                            dict(
                                instruction="沿<b>道路</b>前行", polyline=f"{lng},{lat}"
                            )
                        ],
                    )
                ]
            ),
        )
        with patch.dict("os.environ", {"AMAP_WEB_KEY": "private-test"}), patch(
            "map_services.urlopen",
            return_value=io.BytesIO(json.dumps(response).encode()),
        ) as network:
            first = walking_route(self.origin, self.merchant)
            second = walking_route(self.origin, self.merchant)
        self.assertEqual(first, second)
        self.assertEqual(network.call_count, 1)
        self.assertEqual(first["distance_m"], 1600)
        self.assertEqual(first["duration_seconds"], 1234)
        self.assertEqual(first["points"], [(30.6, 114.3)])
        self.assertEqual(first["steps"], ["沿道路前行"])

    def test_provider_failure_does_not_expose_secret_or_make_up_eta(self):
        with patch.dict("os.environ", {"AMAP_WEB_KEY": "private-test"}), patch(
            "map_services.urlopen", side_effect=URLError("private-test")
        ):
            result = walking_route(self.origin, self.merchant)
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("private-test", json.dumps(result))
        self.assertNotIn("duration_seconds", result)

    def test_invalid_origin_and_missing_destination(self):
        with self.assertRaises(ValueError):
            walking_route(dict(latitude=float("nan"), longitude=114), self.merchant)
        result = walking_route(self.origin, dict(self.merchant, latitude=None))
        self.assertEqual(result["status"], "missing_destination")

    def test_multiple_opening_intervals_keep_weekday_restrictions(self):
        hours = "Mo-Fr 11:00-14:00, 17:00-23:00"
        self.assertEqual(opening_status(hours, "2026-11-06T18:00+08:00"), "open")
        self.assertEqual(opening_status(hours, "2026-11-06T15:00+08:00"), "closed")
        self.assertEqual(opening_status(hours, "2026-11-07T18:00+08:00"), "closed")

    def test_explicit_preferences_skip_model_and_validate_user_edits(self):
        with patch("decision_preferences._extract_with_ai") as model:
            context, mode = prepare_decision(
                dict(
                    message="按修改条件筛选",
                    preferences=dict(
                        party_size=4,
                        budget=300,
                        budget_kind="total",
                        location={"name": "江汉路"},
                    ),
                )
            )
        model.assert_not_called()
        self.assertEqual(context["party_size"], 4)
        self.assertEqual(mode, "local")
        with self.assertRaises(ValueError):
            prepare_decision(dict(message="修改", preferences=dict(party_size=2.5)))
        with self.assertRaises(ValueError):
            prepare_decision(
                dict(
                    message="修改",
                    preferences=dict(location={"name": "不存在的具体位置"}),
                )
            )
````

<a id="source-49"></a>

## 49. tests/test_osm_photos.py

[打开原文件](../tests/test_osm_photos.py) · 93 行

SHA-256：`c1bfce8fcac039e295a05069c18bf00962ef77674a0e6e5c401618e917ca79d3`

````python
"""Recent storefront photo rights, moderation and public visibility tests."""
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import database
import merchant_photos
from real_catalog import _fresh_cutoff, import_real_merchants, public_real_merchants


class OsmPhotoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = Path(self.temp.name) / "photo-test.db"
        database.initialize_database(import_snapshot=False, import_bundled_catalog=False)
        self.db = database.connect()
        import_real_merchants(self.db, [{
            "external_id": "test:photo-merchant",
            "name": "图片测试门店",
            "district": "江汉区",
            "address": "武汉市江汉区测试街 7 号",
            "cuisine": "面食",
            "source_name": "商家授权资料",
            "source_url": "https://example.org/merchant/photo",
            "source_checked_at": date.today().isoformat(),
            "verified_at": date.today().isoformat(),
            "verification_method": "经营者书面确认",
            "status": "verified",
        }])
        self.db.commit()
        self.merchant_id = self.db.execute(
            "SELECT id FROM real_merchants WHERE external_id='test:photo-merchant'"
        ).fetchone()["id"]
        self.image = Path(self.temp.name) / "storefront.jpg"
        self.image.write_bytes(b"\xff\xd8\xff" + b"\x00" * 200 + b"\xff\xd9")

    def tearDown(self):
        self.db.close()
        database.DB_PATH = self.original_db_path
        self.temp.cleanup()

    def _add(self, taken_at=None, consent=True):
        return merchant_photos.add_photo(
            self.db, self.merchant_id, self.image,
            taken_at or date.today().isoformat(),
            "merchant-submission:photo1", "商家经营者",
            "允许夜寻存储并展示这张店面图片",
            "operator", consent,
        )

    def test_photo_remains_private_until_approved(self):
        with patch.object(merchant_photos, "PHOTO_DIR", Path(self.temp.name) / "photos"):
            photo_id = self._add()
            self.db.commit()
            self.assertIsNone(merchant_photos.public_photo_file(self.db, photo_id))
            merchant_photos.approve_photo(self.db, photo_id, "editor")
            self.db.commit()
            filename = merchant_photos.public_photo_file(self.db, photo_id)
            self.assertIsNotNone(filename)
            self.assertTrue(merchant_photos.safe_image_path(filename["image_filename"]).is_file())
            result = public_real_merchants(self.db)
            self.assertEqual(result["items"][0]["photo_url"], "/real-photo/" + str(photo_id))

    def test_old_photo_and_missing_rights_are_rejected(self):
        with self.assertRaises(ValueError):
            self._add(consent=False)
        yesterday_before_cutoff = (
            date.fromisoformat(_fresh_cutoff()) - timedelta(days=1)
        ).isoformat()
        with self.assertRaises(ValueError):
            self._add(taken_at=yesterday_before_cutoff)
        self.image.write_bytes(b"\xff\xd8\xff" + b"Exif\x00\x00" + b"\x00" * 240)
        with self.assertRaises(ValueError):
            self._add()

    def test_photo_is_hidden_if_merchant_record_expires(self):
        with patch.object(merchant_photos, "PHOTO_DIR", Path(self.temp.name) / "photos"):
            photo_id = self._add()
            merchant_photos.approve_photo(self.db, photo_id, "editor")
            self.db.commit()
            self.db.execute(
                "UPDATE real_merchants SET source_checked_at='' WHERE id=?",
                (self.merchant_id,),
            )
            self.db.commit()
            self.assertIsNone(merchant_photos.public_photo_file(self.db, photo_id))


if __name__ == "__main__":
    unittest.main()
````

<a id="source-50"></a>

## 50. tests/test_osm_sync.py

[打开原文件](../tests/test_osm_sync.py) · 114 行

SHA-256：`ac3ba144c8fd1d6a6d8ec093959b8ff07f622c841317b7c9e6eb688ad9f571a6`

````python
"""OSM transform, community safety and snapshot replay tests."""
import json
import tempfile
from datetime import date
import unittest
from pathlib import Path
import database
from osm_sync import convert_osm_element, parse_overpass_payload, hydrate_osm_snapshot
from real_catalog import public_real_merchants, catalog_coverage, import_real_merchants


OSM_SAMPLE = {
    "type": "node", "id": 12345, "lat": 30.56, "lon": 114.30,
    "tags": {
        "name": "单元测试餐馆（虚构，仅用于测试）",
        "amenity": "restaurant",
        "addr:district": "江汉区",
        "survey:date": date.today().isoformat(),
    },
}


class OsmTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = database.DB_PATH
        database.DB_PATH = Path(self.tmp.name) / "test.db"
        database.initialize_database(import_snapshot=False, import_bundled_catalog=False, include_demo=True)

    def tearDown(self):
        database.DB_PATH = self.old_path
        self.tmp.cleanup()

    def test_conversion_is_explicitly_unverified_and_attributed(self):
        record = convert_osm_element(OSM_SAMPLE)
        self.assertEqual(record["status"], "pending")
        self.assertEqual(record["source_name"], "OpenStreetMap")
        self.assertEqual(record["verified_at"], "")
        self.assertIsNone(record["price_per_person"])
        self.assertEqual(
            record["source_url"], "https://www.openstreetmap.org/node/12345"
        )

    def test_osm_edit_without_survey_date_is_not_recent_evidence(self):
        sample = dict(OSM_SAMPLE)
        sample["tags"] = {
            "name": "无核查日期的候选餐厅",
            "amenity": "restaurant",
            "addr:district": "江汉区",
        }
        record = convert_osm_element(sample)
        self.assertEqual(record["source_checked_at"], "")
        with database.connect() as connection:
            import_real_merchants(connection, [record])
            self.assertEqual(public_real_merchants(connection)["total"], 0)

    def test_missing_district_is_not_guessed(self):
        element = dict(OSM_SAMPLE)
        element["tags"] = {"name": "测试食堂", "amenity": "restaurant"}
        self.assertEqual(
            convert_osm_element(element)["district"], "待确认区县"
        )

    def test_missing_location_and_empty_response_rejected(self):
        self.assertIsNone(convert_osm_element({"type": "node", "id": 3, "tags": {"name": "X"}}))
        with self.assertRaises(ValueError):
            parse_overpass_payload({"elements": []})

    def test_only_attributed_osm_pending_visible(self):
        sample = convert_osm_element(OSM_SAMPLE)
        with database.connect() as connection:
            import_real_merchants(connection, [sample])
            result = public_real_merchants(connection)
            self.assertEqual(result["total"], 1)
            self.assertEqual(result["items"][0]["data_quality"], "community")
            self.assertEqual(catalog_coverage(connection)["community_total"], 1)
            # A different unreviewed provider must not be published.
            hidden = dict(sample, external_id="private:1", source_name="商家资料", status="pending")
            import_real_merchants(connection, [hidden])
            self.assertEqual(public_real_merchants(connection)["total"], 1)

    def test_hydrate_snapshot_is_checksum_idempotent(self):
        snapshot = Path(self.tmp.name) / "snapshot.json"
        snapshot.write_text(
            json.dumps([convert_osm_element(OSM_SAMPLE)], ensure_ascii=False),
            encoding="utf-8",
        )
        with database.connect() as connection:
            first = hydrate_osm_snapshot(connection, snapshot)
            second = hydrate_osm_snapshot(connection, snapshot)
            self.assertEqual((first, second), (1, 0))
            self.assertEqual(public_real_merchants(connection)["total"], 1)
            self.assertEqual(len(database.list_merchants(connection)), 24)

    def test_osm_refresh_cannot_downgrade_verified_record(self):
        record = convert_osm_element(OSM_SAMPLE)
        verified = dict(
            record,
            status="verified",
            verified_at="2026-08-14",
            verification_method="商户书面确认",
        )
        with database.connect() as connection:
            import_real_merchants(connection, [verified])
            import_real_merchants(connection, [record])
            state = connection.execute(
                "SELECT status FROM real_merchants WHERE external_id=?",
                (record["external_id"],),
            ).fetchone()
            self.assertEqual(state["status"], "verified")


if __name__ == "__main__":
    unittest.main()
````

<a id="source-51"></a>

## 51. tests/test_real_catalog.py

[打开原文件](../tests/test_real_catalog.py) · 211 行

SHA-256：`bb1dd269a7ac860392a962dbbbbe29a7c25946bb00ddb045bf874e8c44b6f60e`

````python
"""Real-merchant catalog tests: publication gates, import, coverage and isolation."""

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import database
from real_catalog import (
    WUHAN_DISTRICTS,
    catalog_coverage,
    import_real_merchants,
    public_real_merchants,
    read_import_file,
    seed_bundled_catalog,
    get_public_real_merchant,
)


def record(external_id="partner-1", status="verified"):
    return {
        "external_id": external_id,
        "name": "测试核验餐厅",
        "district": "江汉区",
        "address": "武汉市江汉区测试地址（仅用于测试）",
        "cuisine": "湖北菜",
        "source_name": "商家授权资料",
        "source_url": "https://example.org/merchant/1",
        "verified_at": date.today().isoformat(),
        "source_checked_at": date.today().isoformat(),
        "verification_method": "商家书面确认",
        "status": status,
        "price_per_person": "58",
    }


class RealCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = database.DB_PATH
        database.DB_PATH = Path(self.tmp.name) / "catalog.db"
        database.initialize_database(
            import_snapshot=False, import_bundled_catalog=False, include_demo=True
        )

    def tearDown(self):
        database.DB_PATH = self.old_path
        self.tmp.cleanup()

    def test_expired_and_undated_records_are_hidden(self):
        from catalog_policy import catalog_cutoff

        checked = record("old-check")
        cutoff = date.fromisoformat(catalog_cutoff())
        checked["source_checked_at"] = (cutoff - timedelta(days=1)).isoformat()
        with database.connect() as connection:
            with self.assertRaises(ValueError):
                import_real_merchants(connection, [checked])
            pending = record("undated-osm", status="pending")
            pending["source_name"] = "OpenStreetMap"
            pending["external_id"] = "osm:node:909"
            pending["source_checked_at"] = ""
            import_real_merchants(connection, [pending])
            self.assertEqual(public_real_merchants(connection)["total"], 0)
            self.assertEqual(catalog_coverage(connection)["candidate_total"], 1)

    def test_all_wuhan_districts_supported(self):
        self.assertEqual(len(WUHAN_DISTRICTS), 13)

    def test_bundled_catalog_has_real_records_images_and_menu_prices(self):
        with database.connect() as connection:
            result = seed_bundled_catalog(connection)
            self.assertEqual(result["merchants"], 68)
            public = public_real_merchants(connection, limit=100)
            self.assertEqual(public["total"], 68)
            self.assertGreater(result["images"], 50)
            self.assertGreater(result["menu_items"], 60)
            self.assertTrue(any(item["cover_image_url"] for item in public["items"]))
            first = next(item for item in public["items"] if item["cover_image_url"])
            detail = get_public_real_merchant(connection, first["id"])
            self.assertTrue(detail["images"])
            self.assertTrue(detail["menu_items"])

    def test_real_and_demo_separated(self):
        with database.connect() as connection:
            self.assertEqual(public_real_merchants(connection)["total"], 0)
            self.assertEqual(len(database.list_merchants(connection)), 24)
            result = import_real_merchants(connection, [record()])
            self.assertEqual(result["written"], 1)
            self.assertEqual(public_real_merchants(connection)["total"], 1)
            self.assertEqual(len(database.list_merchants(connection)), 24)
            self.assertEqual(catalog_coverage(connection)["verified_total"], 1)

    def test_only_verified_are_public(self):
        with database.connect() as connection:
            import_real_merchants(connection, [record("pending-1", "pending")])
            self.assertEqual(public_real_merchants(connection)["total"], 0)

    def test_pending_csv_refresh_preserves_enriched_fields(self):
        """Partial CSV rows must not erase values enriched after import."""
        initial = record("web:wuhan-local", status="pending")
        initial["latitude"] = ""
        initial["longitude"] = ""
        initial["location_note"] = ""
        initial["phone"] = ""
        initial["opening_hours"] = ""
        initial["price_per_person"] = ""

        with database.connect() as connection:
            import_real_merchants(connection, [initial])
            connection.execute(
                """UPDATE real_merchants
                   SET latitude=?, longitude=?, location_note=?,
                       phone=?, opening_hours=?, price_per_person=?
                   WHERE external_id=?""",
                (
                    30.59,
                    114.30,
                    "地理编码后人工复核",
                    "027-12345678",
                    "17:00-23:00",
                    76,
                    "web:wuhan-local",
                ),
            )

            refreshed = dict(initial)
            refreshed["name"] = "更新后的餐厅名称"
            import_real_merchants(connection, [refreshed])

            item = connection.execute(
                """SELECT name, latitude, longitude, location_note,
                          phone, opening_hours, price_per_person
                   FROM real_merchants WHERE external_id=?""",
                ("web:wuhan-local",),
            ).fetchone()
            self.assertEqual(item["name"], "更新后的餐厅名称")
            self.assertAlmostEqual(item["latitude"], 30.59)
            self.assertAlmostEqual(item["longitude"], 114.30)
            self.assertEqual(item["location_note"], "地理编码后人工复核")
            self.assertEqual(item["phone"], "027-12345678")
            self.assertEqual(item["opening_hours"], "17:00-23:00")
            self.assertEqual(item["price_per_person"], 76)

    def test_explicit_csv_coordinates_can_update_existing_coordinates(self):
        """A corrected, explicit source coordinate should still be accepted."""
        initial = record("web:wuhan-position", status="pending")
        initial.update(latitude="30.59", longitude="114.30")
        changed = dict(initial)
        changed.update(latitude="30.60", longitude="114.31")

        with database.connect() as connection:
            import_real_merchants(connection, [initial])
            import_real_merchants(connection, [changed])
            item = connection.execute(
                "SELECT latitude, longitude FROM real_merchants WHERE external_id=?",
                ("web:wuhan-position",),
            ).fetchone()
            self.assertAlmostEqual(item["latitude"], 30.60)
            self.assertAlmostEqual(item["longitude"], 114.31)

    def test_rejects_half_filled_coordinates(self):
        incomplete = record("web:wuhan-incomplete", status="pending")
        incomplete["latitude"] = "30.59"
        incomplete["longitude"] = ""

        with database.connect() as connection:
            with self.assertRaisesRegex(ValueError, "纬度和经度必须"):
                import_real_merchants(connection, [incomplete])
            self.assertIsNone(
                connection.execute(
                    "SELECT id FROM real_merchants WHERE external_id=?",
                    ("web:wuhan-incomplete",),
                ).fetchone()
            )

    def test_upsert_is_idempotent(self):
        with database.connect() as connection:
            import_real_merchants(connection, [record()])
            import_real_merchants(connection, [record()])
            self.assertEqual(public_real_merchants(connection)["total"], 1)

    def test_dry_run_no_write(self):
        with database.connect() as connection:
            result = import_real_merchants(connection, [record()], dry_run=True)
            self.assertEqual(result["written"], 0)
            self.assertEqual(public_real_merchants(connection)["total"], 0)

    def test_rejects_invalid_or_unverified_records(self):
        bad = record()
        bad["source_url"] = "http://example.org"
        with database.connect() as connection:
            with self.assertRaises(ValueError):
                import_real_merchants(connection, [bad])
        bad = record()
        bad["verified_at"] = ""
        with database.connect() as connection:
            with self.assertRaises(ValueError):
                import_real_merchants(connection, [bad])

    def test_batch_is_atomic_on_validation_failure(self):
        invalid = record("partner-2")
        invalid["district"] = "上海市"
        with database.connect() as connection:
            with self.assertRaises(ValueError):
                import_real_merchants(connection, [record(), invalid])
            self.assertEqual(public_real_merchants(connection)["total"], 0)


if __name__ == "__main__":
    unittest.main()
````

<a id="source-52"></a>

## 52. tests/test_real_catalog_workflow.py

[打开原文件](../tests/test_real_catalog_workflow.py) · 248 行

SHA-256：`f98e1f7d4db89d569877e33047092f9187642274a875e5235dfe753fe31afe8e`

````python
"""Real-only data, five-year provenance, whole-directory map and grounded queries."""

import json
import hashlib
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import database
from catalog_policy import catalog_cutoff, photo_cutoff
from decision_catalog import real_map_catalog, set_real_favorite
from dining_decision import prepare_decision, make_decision
from osm_sync import (
    SNAPSHOT,
    collect_live_snapshot,
    hydrate_osm_snapshot,
    read_snapshot,
)
from real_catalog import catalog_coverage, import_real_merchants, public_real_merchants


class RealCatalogWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = database.DB_PATH
        database.DB_PATH = Path(self.temp.name) / "catalog.db"
        self.no_ai = patch.dict("os.environ", {"OPENAI_API_KEY": ""})
        self.no_ai.start()
        database.initialize_database(import_snapshot=False)
        with database.connect() as connection:
            hydrate_osm_snapshot(connection, SNAPSHOT)

    def tearDown(self):
        database.DB_PATH = self.old_path
        self.no_ai.stop()
        self.temp.cleanup()

    def ask(self, message):
        preferences, mode = prepare_decision(dict(message=message))
        with database.connect() as connection:
            return make_decision(connection, preferences, dict(message=message), mode)

    def test_real_only_initialization_preserves_original_fifty_five_and_hundred_plus_points(
        self,
    ):
        with database.connect() as connection:
            self.assertEqual(
                connection.execute("SELECT count(*) FROM restaurants").fetchone()[0], 0
            )
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) FROM real_merchants WHERE external_id LIKE 'web:%'"
                ).fetchone()[0],
                68,
            )
            coverage = catalog_coverage(connection)
            self.assertEqual(coverage["community_total"], 834)
            self.assertEqual(coverage["public_total"], 902)
            self.assertGreaterEqual(coverage["mapped_total"], 100)
            self.assertEqual(coverage["priced_menu_items"], 74)
            self.assertEqual(coverage["verified_total"], 0)

    def test_archive_date_never_becomes_a_survey_or_a_new_live_collection(self):
        with database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM real_merchants WHERE external_id LIKE 'osm:%' LIMIT 1"
            ).fetchone()
            self.assertEqual(row["source_archived_at"], "2026-11-02")
            self.assertEqual(row["source_checked_at"], "")
            self.assertEqual(row["source_collected_at"], "")
            self.assertEqual(row["verified_at"], "")
            self.assertIn("5389d9b", row["evidence_url"])

    def test_map_is_not_limited_by_directory_pagination_and_keeps_source_coordinates(
        self,
    ):
        original = json.loads(SNAPSHOT.read_text())
        source_coordinates = {(row["latitude"], row["longitude"]) for row in original}
        with database.connect() as connection:
            page = public_real_merchants(connection, limit=30)
            mapped = real_map_catalog(connection)
            self.assertEqual(len(page["items"]), 30)
            self.assertGreater(mapped["mapped_total"], 846)
            self.assertGreater(mapped["mapped_total"], len(page["items"]))
            osm = [
                row for row in mapped["items"] if row["source_name"] == "OpenStreetMap"
            ]
            self.assertEqual(len(osm), 834)
            self.assertTrue(
                all(
                    (row["latitude"], row["longitude"]) in source_coordinates
                    for row in osm
                )
            )
            # Refreshed branch-specific prices now join to real source coordinates.
            self.assertGreaterEqual(
                sum(bool(row["priced_menu"]) for row in mapped["items"]), 15
            )
            # A test-only menu record checks the map join, without inventing production prices.
            mapped_id = osm[0]["id"]
            connection.execute(
                "INSERT INTO real_merchant_menu_items(merchant_id,dish_name,price,price_unit,price_source_url,price_checked_at) VALUES (?,?,?,?,?,?)",
                (
                    mapped_id,
                    "测试菜品，非真实售价",
                    8,
                    "元/份",
                    "https://example.org/test-menu",
                    date.today().isoformat(),
                ),
            )
            with_test_evidence = real_map_catalog(connection)
            target = next(
                row for row in with_test_evidence["items"] if row["id"] == mapped_id
            )
            self.assertEqual(target["priced_menu"][0]["price"], 8)

    def test_lookup_returns_actual_menu_prices_without_planning_questionnaire(self):
        result = self.ask("查金贵源的菜单价格")
        self.assertEqual(result["stage"], "catalog")
        self.assertEqual(result["items"][0]["name"], "金贵源食神酒店（外摆超市）")
        self.assertIn("凉拌毛豆 ¥8/斤", result["reply"])
        self.assertTrue(result["items"][0]["menu_items"])
        self.assertIsNone(result["constraints"]["party_size"])

    def test_lookup_without_menu_says_unknown_and_never_borrows_a_chain_price(self):
        result = self.ask("查蔡林记北湖店的菜单价格")
        self.assertTrue(result["items"])
        self.assertIn("尚无带来源的菜单单价", result["reply"])
        self.assertTrue(all("蔡林记" in row["name"] for row in result["items"]))
        self.assertTrue(
            all(
                dish["price"] is None
                for item in result["items"]
                for dish in item["menu_items"]
            )
        )

    def test_explicit_branch_query_does_not_return_another_branch(self):
        result = self.ask("查蔡林记北湖店的菜单价格")
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["name"], "蔡林记（北湖店）")

    def test_coffee_alias_and_nearby_lookup_search_the_real_database(self):
        coffee = self.ask("有哪些咖啡店")
        self.assertGreater(coffee["eligible_total"], 30)
        nearby = self.ask("江汉路附近有哪些餐厅")
        self.assertTrue(nearby["items"])
        self.assertTrue(all(row["distance_km"] < 2 for row in nearby["items"]))
        missing = self.ask("搜索不存在的测试门店")
        self.assertEqual(missing["items"], [])

    def test_five_year_window_is_independent_of_the_photo_window(self):
        self.assertEqual(catalog_cutoff(date(2026, 11, 5)), "2021-11-05")
        self.assertEqual(photo_cutoff(date(2026, 11, 5)), "2024-11-05")
        self.assertEqual(catalog_cutoff(date(2024, 2, 29)), "2019-02-28")
        sample = json.loads(SNAPSHOT.read_text())[0]
        old = date.fromisoformat(catalog_cutoff()) - timedelta(days=1)
        sample.update(
            external_id="osm:node:999999999",
            source_archived_at=old.isoformat(),
            evidence_url="https://example.org/archive",
            source_checked_at="",
        )
        with database.connect() as connection:
            import_real_merchants(connection, [sample])
            self.assertFalse(
                any(
                    row["name"] == sample["name"]
                    and row["source_archived_at"] == old.isoformat()
                    for row in public_real_merchants(connection)["items"]
                )
            )

    def test_known_demo_upgrade_has_a_recoverable_backup_and_preserves_real_favorites(
        self,
    ):
        database.initialize_database(include_demo=True)
        with database.connect() as connection:
            real_id = connection.execute(
                "SELECT id FROM real_merchants LIMIT 1"
            ).fetchone()[0]
            database.ensure_session(connection, "upgrade-visitor")
            set_real_favorite(connection, "upgrade-visitor", real_id, True)
        database.initialize_database()
        backups = list((database.DB_PATH.parent / "backups").glob("*.db"))
        self.assertEqual(len(backups), 1)
        import sqlite3

        with sqlite3.connect(backups[0]) as backup:
            self.assertEqual(
                backup.execute("SELECT count(*) FROM restaurants").fetchone()[0], 24
            )
        with database.connect() as connection:
            self.assertEqual(
                connection.execute("SELECT count(*) FROM restaurants").fetchone()[0], 0
            )
            self.assertEqual(
                connection.execute("SELECT merchant_id FROM real_favorites").fetchone()[
                    0
                ],
                real_id,
            )
            self.assertEqual(
                connection.execute("PRAGMA foreign_key_check").fetchall(), []
            )

    def test_snapshot_metadata_is_verified_and_changes_the_replay_checksum(self):
        rows = json.loads(SNAPSHOT.read_text())
        path = Path(self.temp.name) / "snapshot.json"
        path.write_bytes(SNAPSHOT.read_bytes())
        bare, old_checksum = read_snapshot(path)
        self.assertNotIn("source_archived_at", bare[0])
        path.with_suffix(".meta.json").write_bytes(
            SNAPSHOT.with_suffix(".meta.json").read_bytes()
        )
        dated, new_checksum = read_snapshot(path)
        self.assertNotEqual(new_checksum, old_checksum)
        self.assertEqual(dated[0]["source_archived_at"], "2026-11-02")
        path.write_text(json.dumps(rows[:-1]))
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            read_snapshot(path)

    def test_failed_or_small_collection_cannot_replace_existing_data(self):
        path = Path(self.temp.name) / "live.json"
        path.write_text("existing data")
        rows = json.loads(SNAPSHOT.read_text())
        with patch("osm_sync.fetch_wuhan_osm", return_value=rows[:99]):
            with self.assertRaisesRegex(ValueError, "未达到"):
                collect_live_snapshot(path)
        self.assertEqual(path.read_text(), "existing data")
        with patch("osm_sync.fetch_wuhan_osm", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                collect_live_snapshot(path)
        self.assertEqual(path.read_text(), "existing data")

    def test_successful_collection_preserves_online_and_survey_date_meanings(self):
        path = Path(self.temp.name) / "live.json"
        rows = json.loads(SNAPSHOT.read_text())[:100]
        with patch("osm_sync.fetch_wuhan_osm", return_value=rows):
            result = collect_live_snapshot(path)
        self.assertEqual(result["mapped"], 100)
        loaded, checksum = read_snapshot(path)
        self.assertEqual(loaded[0]["source_collected_at"], date.today().isoformat())
        self.assertEqual(loaded[0]["source_checked_at"], "")
        self.assertEqual(loaded[0]["source_archived_at"], "")
````

<a id="source-53"></a>

## 53. 启动网页.bat

[打开原文件](../启动网页.bat) · 9 行

SHA-256：`03d3cea59c80aa58316e2ed2ca81029371f012521a5f4ba3783172d360fb8cfb`

````bat
@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 "%~dp0run.py" %*
) else (
  python "%~dp0run.py" %*
)
pause
````
