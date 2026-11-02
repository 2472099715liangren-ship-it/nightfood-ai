"""Tests for the permission-aware Wuhan real restaurant catalog."""
import tempfile
import unittest
from pathlib import Path

import database
from restaurant_catalog import (
    CatalogValidationError,
    import_rows,
    list_real_restaurants,
    read_csv,
    register_source,
    review_queue,
    set_review_status,
)


class RealRestaurantCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.previous_db = database.DB_PATH
        database.DB_PATH = Path(self.temporary.name) / "real-catalog.db"
        database.initialize_database()

    def tearDown(self):
        database.DB_PATH = self.previous_db
        self.temporary.cleanup()

    def register(self, code="merchant_test"):
        return register_source(
            self.connection,
            code,
            "商家授权提交测试来源",
            "merchant_submission",
            "",
            "",
            "商家明确授权夜寻存储和展示其提交的门店资料；仅用于测试。",
            "test-operator",
            rights_confirmed=True,
        )

    def setUpConnection(self):
        self.connection = database.connect()
        self.addCleanup(self.connection.close)

    def csv_file(self, rows):
        path = Path(self.temporary.name) / "restaurants.csv"
        header = (
            "external_id,name,branch_name,district,business_area,address,latitude,"
            "longitude,phone,website,cuisine,price_per_person,business_status,"
            "description,source_url,source_updated_at\n"
        )
        lines = [header]
        for row in rows:
            lines.append(",".join('"' + str(value).replace('"', '""') + '"' for value in row) + "\n")
        path.write_text("".join(lines), encoding="utf-8")
        return path

    def sample_row(self, external_id="shop-001", name="真实测试餐厅", district="江岸区"):
        return {
            "external_id": external_id,
            "name": name,
            "branch_name": "测试分店",
            "district": district,
            "business_area": "吉庆街",
            "address": "武汉市江岸区吉庆街 1 号",
            "latitude": "30.60",
            "longitude": "114.30",
            "phone": "",
            "website": "",
            "cuisine": "湖北菜",
            "price_per_person": "",
            "business_status": "unknown",
            "description": "由商家授权提交的测试资料",
            "source_url": "merchant-submission:test-001",
            "source_updated_at": "",
        }

    def import_sample(self, rows):
        self.setUpConnection()
        self.register()
        allowed = {
            row["name"] for row in self.connection.execute(
                "SELECT name FROM wuhan_areas WHERE area_type = 'administrative_district'"
            )
        }
        validated = []
        errors = []
        for index, row in enumerate(rows, start=2):
            from restaurant_catalog import validate_restaurant_row
            try:
                validated.append((index, validate_restaurant_row(row, allowed)))
            except CatalogValidationError as error:
                errors.append({
                    "row_number": index, "external_id": row.get("external_id", ""),
                    "error_code": "invalid_row", "detail": str(error),
                })
        return import_rows(
            self.connection, "merchant_test", validated, errors,
            "restaurants.csv", "a" * 64, "test-operator",
        )

    def test_wuhan_coverage_has_thirteen_districts_and_separate_zones(self):
        with database.connect() as connection:
            districts = connection.execute(
                "SELECT name FROM wuhan_areas WHERE area_type = 'administrative_district'"
            ).fetchall()
            zones = connection.execute(
                "SELECT name FROM wuhan_areas WHERE area_type = 'development_zone'"
            ).fetchall()
        self.assertEqual(len(districts), 13)
        self.assertEqual(len(zones), 4)

    def test_source_requires_explicit_rights_confirmation(self):
        self.setUpConnection()
        with self.assertRaises(CatalogValidationError):
            register_source(
                self.connection, "unapproved", "未知来源", "manual_research",
                "", "", "尚未核验授权", "operator", rights_confirmed=False,
            )

    def test_csv_preview_validates_district_and_keeps_missing_prices_null(self):
        path = self.csv_file([
            ["a1", "餐厅甲", "", "江岸区", "", "江岸区道路 1 号", "", "", "", "", "湖北菜", "", "unknown", "", "merchant-submission:1", ""],
            ["a2", "餐厅乙", "", "上海市", "", "上海市道路 1 号", "", "", "", "", "川菜", "60", "unknown", "", "merchant-submission:2", ""],
        ])
        with database.connect() as connection:
            allowed = {
                row["name"] for row in connection.execute(
                    "SELECT name FROM wuhan_areas WHERE area_type = 'administrative_district'"
                )
            }
            rows, errors = read_csv(path, allowed)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0][1]["price_per_person"])
        self.assertEqual(len(errors), 1)
        self.assertIn("13 个区", errors[0]["detail"])

    def test_imported_rows_are_pending_and_not_public_until_reviewed(self):
        result = self.import_sample([self.sample_row()])
        self.assertEqual(result["inserted_rows"], 1)
        with database.connect() as connection:
            self.assertEqual(list_real_restaurants(connection), [])
            queue = review_queue(connection)
            self.assertEqual(len(queue), 1)
            self.assertEqual(queue[0]["record_status"], "pending")
            set_review_status(connection, [queue[0]["id"]], "verified", "reviewer", "核对门店地址")
            connection.commit()
            public = list_real_restaurants(connection)
        self.assertEqual(len(public), 1)
        self.assertEqual(public[0]["name"], "真实测试餐厅")
        self.assertIsNone(public[0]["price_per_person"])

    def test_exact_duplicate_from_another_source_requires_manual_review(self):
        self.import_sample([self.sample_row()])
        self.connection.execute(
            """
            INSERT INTO restaurant_sources (
                source_code, source_name, source_type, license_note, permission_status
            ) VALUES ('licensed_test', '授权测试来源', 'licensed_provider',
                      '测试用授权', 'approved')
            """
        )
        self.connection.commit()
        self.connection.execute(
            """
            INSERT INTO real_restaurants (
                source_id, external_id, name, district, address, source_url, record_status
            ) VALUES (2, 'another-id', '真实测试餐厅', '江岸区',
                      '武汉市江岸区吉庆街 1 号', 'https://example.com/store', 'pending')
            """
        )
        self.connection.commit()
        row = self.sample_row("shop-002")
        allowed = {"江岸区"}
        from restaurant_catalog import validate_restaurant_row
        clean = validate_restaurant_row(row, allowed)
        result = import_rows(
            self.connection, "merchant_test", [(2, clean)], [],
            "duplicate.csv", "b" * 64, "operator",
        )
        self.connection.commit()
        self.assertEqual(result["review_rows"], 1)
        status = self.connection.execute(
            "SELECT record_status FROM real_restaurants WHERE source_id = 1 AND external_id = 'shop-002'"
        ).fetchone()["record_status"]
        self.assertEqual(status, "needs_review")

    def test_reimport_of_same_file_is_rejected_by_unique_batch(self):
        self.import_sample([self.sample_row()])
        from sqlite3 import IntegrityError
        from restaurant_catalog import validate_restaurant_row
        clean = validate_restaurant_row(self.sample_row(), {"江岸区"})
        with self.assertRaises(IntegrityError):
            import_rows(
                self.connection, "merchant_test", [(2, clean)], [],
                "restaurants.csv", "a" * 64, "operator",
            )

    def test_suspended_source_hides_previously_verified_records(self):
        self.import_sample([self.sample_row()])
        row = review_queue(self.connection)[0]
        set_review_status(self.connection, [row["id"]], "verified", "reviewer")
        self.connection.execute(
            "UPDATE restaurant_sources SET permission_status = 'suspended' WHERE source_code = 'merchant_test'"
        )
        self.connection.commit()
        self.assertEqual(list_real_restaurants(self.connection), [])


if __name__ == "__main__":
    unittest.main()
