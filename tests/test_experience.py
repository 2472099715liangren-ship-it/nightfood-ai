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
        database.initialize_database(import_snapshot=False)
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
