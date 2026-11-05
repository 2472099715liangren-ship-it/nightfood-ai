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
                55,
            )
            coverage = catalog_coverage(connection)
            self.assertEqual(coverage["community_total"], 834)
            self.assertEqual(coverage["public_total"], 889)
            self.assertGreaterEqual(coverage["mapped_total"], 100)
            self.assertEqual(coverage["priced_menu_items"], 16)
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
            self.assertEqual(mapped["mapped_total"], 846)
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
            # Production coverage is reported honestly: known prices currently lack exact store coordinates.
            self.assertEqual(
                sum(bool(row["priced_menu"]) for row in mapped["items"]), 0
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
        result = self.ask("查蔡林记的菜单价格")
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
