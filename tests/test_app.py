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
        database.initialize_database()
        with database.connect() as connection:
            database.ensure_session(connection, "test-session")

    def tearDown(self):
        database.DB_PATH = self.original_path
        self.temp_dir.cleanup()

    def test_database_initializes_without_duplicate_seed_data(self):
        database.initialize_database()
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
