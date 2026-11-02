import json
import os
import tempfile
import threading
import unittest
import urllib.request
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
        database.initialize_database()

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
        self.assertTrue(all(item["district"] == "江汉路" for item in directory["items"]))

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


if __name__ == "__main__":
    unittest.main()
