"""Real-merchant catalog tests: publication gates, import, coverage and isolation."""
import tempfile
import unittest
from pathlib import Path

import database
from real_catalog import (
    WUHAN_DISTRICTS, catalog_coverage, import_real_merchants,
    public_real_merchants, read_import_file,
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
        "verified_at": "2026-09-12",
        "verification_method": "商家书面确认",
        "status": status,
        "price_per_person": "58",
    }


class RealCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = database.DB_PATH
        database.DB_PATH = Path(self.tmp.name) / "catalog.db"
        database.initialize_database()

    def tearDown(self):
        database.DB_PATH = self.old_path
        self.tmp.cleanup()

    def test_all_wuhan_districts_supported(self):
        self.assertEqual(len(WUHAN_DISTRICTS), 13)

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
