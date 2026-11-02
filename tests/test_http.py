import json
import os
from datetime import date
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


    def test_real_catalog_api_keeps_demo_data_separate(self):
        areas = self.call_api("/api/real-areas")
        districts = [item for item in areas["items"]
                     if item["area_type"] == "administrative_district"]
        self.assertEqual(len(districts), 13)
        summary = self.call_api("/api/real-catalog/summary")
        self.assertEqual(summary["total_verified"], 0)
        self.assertEqual(self.call_api("/api/real-restaurants")["items"], [])

        from restaurant_catalog import (
            import_rows, register_source, set_review_status, validate_restaurant_row
        )
        row = {
            "external_id": "http-real-1",
            "name": "HTTP 真实餐厅测试",
            "district": "江岸区",
            "address": "武汉市江岸区测试路 1 号",
            "source_url": "merchant-submission:http-test-1",
            "business_status": "unknown",
            "source_updated_at": date.today().isoformat(),
        }
        with database.connect() as connection:
            register_source(
                connection, "http_merchant", "HTTP 商家授权测试",
                "merchant_submission", "", "",
                "测试使用的商家授权记录", "test-operator", rights_confirmed=True,
            )
            clean = validate_restaurant_row(row, {"江岸区"})
            result = import_rows(
                connection, "http_merchant", [(2, clean)], [],
                "http-test.csv", "c" * 64, "test-operator",
            )
            self.assertEqual(result["inserted_rows"], 1)
            pending = connection.execute(
                "SELECT id FROM real_restaurants WHERE external_id = 'http-real-1'"
            ).fetchone()
            changed = set_review_status(
                connection, [pending["id"]], "verified", "reviewer", "HTTP integration test"
            )
            self.assertEqual(changed, 1)
            stored = connection.execute(
                "SELECT record_status, district FROM real_restaurants WHERE id = ?",
                (pending["id"],),
            ).fetchone()
            self.assertEqual(stored["record_status"], "verified")
            self.assertEqual(stored["district"], "江岸区")
            source_status = connection.execute(
                "SELECT permission_status FROM restaurant_sources WHERE source_code = 'http_merchant'"
            ).fetchone()["permission_status"]
            self.assertEqual(source_status, "approved")
            from restaurant_catalog import list_real_restaurants
            direct_listing = list_real_restaurants(connection, district="江岸区")
            self.assertEqual(len(direct_listing), 1)
            connection.commit()

        from restaurant_catalog import list_real_restaurants
        with database.connect() as verification_connection:
            self.assertEqual(len(list_real_restaurants(verification_connection)), 1)
        from app import connect as handler_connect
        self.assertIs(handler_connect.__globals__, database.__dict__)
        with handler_connect() as handler_connection:
            self.assertEqual(len(list_real_restaurants(handler_connection)), 1)

        unfiltered = self.call_api("/api/real-restaurants")
        self.assertEqual(unfiltered["total"], 1)
        listing = self.call_api("/api/real-restaurants?district=%E6%B1%9F%E5%B2%B8%E5%8C%BA")
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["name"], "HTTP 真实餐厅测试")
        detail = self.call_api("/api/real-restaurants/" + str(listing["items"][0]["id"]))
        self.assertEqual(detail["source_name"], "HTTP 商家授权测试")
        self.assertIsNone(detail["price_per_person"])

    def test_chat_followups_have_actionable_prompts(self):
        first = self.call_api("/api/chat", {
            "message": "今晚想吃烧烤",
            "context": {},
            "history": [],
        })
        self.assertTrue(first["follow_up"]["actions"])
        self.assertTrue(any(
            item["message"] == "江汉路"
            for item in first["follow_up"]["actions"]
        ))
        next_turn = self.call_api("/api/chat", {
            "message": "江汉路",
            "context": first["constraints"],
            "history": [],
        })
        self.assertEqual(next_turn["constraints"]["district"], "江汉路")
        self.assertIn("district", next_turn["constraints"]["known"])

    def test_compare_endpoint_rejects_bad_ids(self):
        result = self.call_api("/api/compare?ids=1%2C2&scene=%E6%9C%8B%E5%8F%8B%E8%81%9A%E4%BC%9A")
        self.assertEqual(len(result["items"]), 2)
        self.assertIn(result["summary"]["recommended_id"], (1, 2))
        for path in ("/api/compare?ids=1%2C1", "/api/compare?ids=1",
                     "/api/compare?ids=1%2C2%2C3%2C4"):
            with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as caught:
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
