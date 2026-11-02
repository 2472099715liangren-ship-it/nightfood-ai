"""Regression tests: strict two-year evidence and licensed storefront photos."""
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

import database
import restaurant_photos
from freshness import cutoff_date, parse_recent_date
from restaurant_catalog import (
    CatalogValidationError, get_public_photo_file, import_rows,
    list_real_restaurants, public_catalog_summary, register_source,
    set_review_status, validate_restaurant_row,
)


class FreshnessAndPhotoTests(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.original_database = database.DB_PATH
        database.DB_PATH = Path(self.temporary.name) / "fresh.db"
        database.initialize_database()
        self.connection = database.connect()
        register_source(
            self.connection, "photo_src", "测试商家自主授权",
            "merchant_submission", "", "", "已取得合法使用与展示许可",
            "test-editor", rights_confirmed=True,
        )

    def tearDown(self):
        self.connection.close()
        database.DB_PATH = self.original_database
        self.temporary.cleanup()

    def restaurant(self, updated_at=None):
        return validate_restaurant_row(
            {
                "external_id": "photo-test-1",
                "name": "真实门店照片测试",
                "district": "江岸区",
                "address": "武汉市江岸区测试路 3 号",
                "source_url": "merchant-submission:source-1",
                "source_updated_at": updated_at or date.today().isoformat(),
                "business_status": "unknown",
            },
            {"江岸区"},
        )

    def import_and_verify(self):
        item = self.restaurant()
        import_rows(
            self.connection, "photo_src", [(2, item)], [],
            "restaurants.csv", "a" * 64, "editor",
        )
        self.connection.commit()
        identifier = self.connection.execute(
            "SELECT id FROM real_restaurants WHERE external_id = 'photo-test-1'"
        ).fetchone()["id"]
        set_review_status(
            self.connection, [identifier], "verified", "editor", "核验地址与来源"
        )
        self.connection.commit()
        return identifier

    def test_cutoff_includes_boundary_and_rejects_stale_future_or_missing(self):
        boundary = cutoff_date().isoformat()
        self.assertEqual(parse_recent_date(boundary), boundary)
        outdated = (cutoff_date() - timedelta(days=1)).isoformat()
        for value in ("", outdated, (date.today() + timedelta(days=1)).isoformat()):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_recent_date(value)
        with self.assertRaises(CatalogValidationError):
            self.restaurant(outdated)

    def test_expired_verified_shop_disappears_without_reimport(self):
        identifier = self.import_and_verify()
        self.assertEqual(len(list_real_restaurants(self.connection)), 1)
        self.connection.execute(
            "UPDATE real_restaurants SET source_updated_at = ? WHERE id = ?",
            ((cutoff_date() - timedelta(days=1)).isoformat(), identifier),
        )
        self.connection.commit()
        self.assertEqual(list_real_restaurants(self.connection), [])
        self.assertEqual(public_catalog_summary(self.connection)["total_verified"], 0)

    def test_storefront_photo_needs_recent_date_rights_and_manual_approval(self):
        identifier = self.import_and_verify()
        image = Path(self.temporary.name) / "shop.jpg"
        image.write_bytes(b"\xff\xd8\xff" + b"\x00" * 260 + b"\xff\xd9")
        photo_root = Path(self.temporary.name) / "photos"
        with mock.patch.object(restaurant_photos, "PHOTO_ROOT", photo_root):
            with self.assertRaises(ValueError):
                restaurant_photos.add_storefront_photo(
                    self.connection, identifier, image, date.today().isoformat(),
                    "merchant-submission:photo1", "商家", "许可说明", "editor", False,
                )
            with self.assertRaises(ValueError):
                restaurant_photos.add_storefront_photo(
                    self.connection, identifier, image,
                    (cutoff_date() - timedelta(days=1)).isoformat(),
                    "merchant-submission:photo1", "商家", "许可说明", "editor", True,
                )
            photo_id = restaurant_photos.add_storefront_photo(
                self.connection, identifier, image, date.today().isoformat(),
                "merchant-submission:photo1", "商家", "许可说明", "editor", True,
            )
            self.connection.commit()
            self.assertIsNone(get_public_photo_file(self.connection, photo_id))
            restaurant_photos.review_photo(self.connection, photo_id, "verified", "editor")
            self.connection.commit()
            self.assertIsNotNone(get_public_photo_file(self.connection, photo_id))
            self.connection.execute(
                "UPDATE real_restaurant_photos SET captured_at = ? WHERE id = ?",
                ((cutoff_date() - timedelta(days=1)).isoformat(), photo_id),
            )
            self.connection.commit()
            self.assertIsNone(get_public_photo_file(self.connection, photo_id))

    def test_metadata_bearing_image_is_rejected(self):
        identifier = self.import_and_verify()
        image = Path(self.temporary.name) / "metadata.jpg"
        image.write_bytes(b"\xff\xd8\xff" + b"Exif\x00\x00" + b"\x00" * 260)
        with self.assertRaises(ValueError):
            restaurant_photos.add_storefront_photo(
                self.connection, identifier, image, date.today().isoformat(),
                "merchant-submission:photo2", "商家", "许可说明", "editor", True,
            )

    def test_updated_source_keeps_auditable_change_log(self):
        identifier = self.import_and_verify()
        updated = self.restaurant()
        updated["description"] = "授权来源已更新门店描述"
        result = import_rows(
            self.connection, "photo_src", [(2, updated)], [],
            "updated.csv", "b" * 64, "editor",
        )
        self.connection.commit()
        self.assertEqual(result["updated_rows"], 1)
        self.assertEqual(
            self.connection.execute(
                "SELECT record_status FROM real_restaurants WHERE id = ?",
                (identifier,),
            ).fetchone()["record_status"],
            "pending",
        )
        changed = self.connection.execute(
            "SELECT COUNT(*) FROM restaurant_change_log WHERE restaurant_id = ?",
            (identifier,),
        ).fetchone()[0]
        self.assertGreaterEqual(changed, 1)


if __name__ == "__main__":
    import unittest
    unittest.main()
