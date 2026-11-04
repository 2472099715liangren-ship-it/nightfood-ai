"""Real-merchant catalog tests: publication gates, import, coverage and isolation."""
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import database
from real_catalog import (
    WUHAN_DISTRICTS, catalog_coverage, import_real_merchants,
    public_real_merchants, read_import_file, seed_bundled_catalog, get_public_real_merchant,
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
        database.initialize_database(import_snapshot=False, import_bundled_catalog=False)

    def tearDown(self):
        database.DB_PATH = self.old_path
        self.tmp.cleanup()

    def test_expired_and_undated_records_are_hidden(self):
        from real_catalog import _fresh_cutoff
        checked = record("old-check")
        cutoff = date.fromisoformat(_fresh_cutoff())
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
            self.assertEqual(result["merchants"], 55)
            public = public_real_merchants(connection, limit=100)
            self.assertEqual(public["total"], 55)
            self.assertGreater(result["images"], 50)
            self.assertGreater(result["menu_items"], 60)
            self.assertTrue(any(item["cover_image_url"] for item in public["items"]))
            first = public["items"][0]
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
                (30.59, 114.30, "地理编码后人工复核",
                 "027-12345678", "17:00-23:00", 76, "web:wuhan-local"),
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
