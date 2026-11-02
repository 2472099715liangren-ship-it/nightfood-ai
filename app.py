"""NightFind HTTP application.

Routes are intentionally small and explicit. Database queries live in database.py;
recommendation and AI behavior live in services.py.
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
from services import SCENES, chat
from comparison import compare_merchants
from real_catalog import public_real_merchants, catalog_coverage, get_public_real_merchant
from merchant_photos import public_photo_file, safe_image_path


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
                ".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"
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
            with connect() as connection:
                if path == "/api/health":
                    self._send_json({"status": "ok", "app": "NightFind"})
                    return

                if path == "/api/bootstrap":
                    self._send_json(
                        {
                            "districts": list_districts(connection),
                            "favorites": list_favorites(connection, session_id)
                            if session_id else [],
                            "ai_enabled": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
                        }
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
                        self._send_json(item)
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
                    self._send_json({
                        "items": list_saved_merchants(connection, session_id)
                    })
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
        value = path[len(prefix):]
        if not value.isdigit():
            raise ValueError("商户编号无效")
        return int(value)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            session_id = self._session_id()

            with connect() as connection:
                ensure_session(connection, session_id)

                if path == "/api/chat":
                    result = chat(
                        connection,
                        payload,
                        session_id,
                        list_districts(connection),
                    )
                    connection.commit()
                    self._send_json(result)
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
                    set_favorite(
                        connection, session_id, merchant_id, active
                    )
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
