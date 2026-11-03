"""Recent storefront photo rights, moderation and public visibility tests."""
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import database
import merchant_photos
from real_catalog import _fresh_cutoff, import_real_merchants, public_real_merchants


class OsmPhotoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = Path(self.temp.name) / "photo-test.db"
        database.initialize_database(import_snapshot=False, import_bundled_catalog=False)
        self.db = database.connect()
        import_real_merchants(self.db, [{
            "external_id": "test:photo-merchant",
            "name": "图片测试门店",
            "district": "江汉区",
            "address": "武汉市江汉区测试街 7 号",
            "cuisine": "面食",
            "source_name": "商家授权资料",
            "source_url": "https://example.org/merchant/photo",
            "source_checked_at": date.today().isoformat(),
            "verified_at": date.today().isoformat(),
            "verification_method": "经营者书面确认",
            "status": "verified",
        }])
        self.db.commit()
        self.merchant_id = self.db.execute(
            "SELECT id FROM real_merchants WHERE external_id='test:photo-merchant'"
        ).fetchone()["id"]
        self.image = Path(self.temp.name) / "storefront.jpg"
        self.image.write_bytes(b"\xff\xd8\xff" + b"\x00" * 200 + b"\xff\xd9")

    def tearDown(self):
        self.db.close()
        database.DB_PATH = self.original_db_path
        self.temp.cleanup()

    def _add(self, taken_at=None, consent=True):
        return merchant_photos.add_photo(
            self.db, self.merchant_id, self.image,
            taken_at or date.today().isoformat(),
            "merchant-submission:photo1", "商家经营者",
            "允许夜寻存储并展示这张店面图片",
            "operator", consent,
        )

    def test_photo_remains_private_until_approved(self):
        with patch.object(merchant_photos, "PHOTO_DIR", Path(self.temp.name) / "photos"):
            photo_id = self._add()
            self.db.commit()
            self.assertIsNone(merchant_photos.public_photo_file(self.db, photo_id))
            merchant_photos.approve_photo(self.db, photo_id, "editor")
            self.db.commit()
            filename = merchant_photos.public_photo_file(self.db, photo_id)
            self.assertIsNotNone(filename)
            self.assertTrue(merchant_photos.safe_image_path(filename["image_filename"]).is_file())
            result = public_real_merchants(self.db)
            self.assertEqual(result["items"][0]["photo_url"], "/real-photo/" + str(photo_id))

    def test_old_photo_and_missing_rights_are_rejected(self):
        with self.assertRaises(ValueError):
            self._add(consent=False)
        yesterday_before_cutoff = (
            date.fromisoformat(_fresh_cutoff()) - timedelta(days=1)
        ).isoformat()
        with self.assertRaises(ValueError):
            self._add(taken_at=yesterday_before_cutoff)
        self.image.write_bytes(b"\xff\xd8\xff" + b"Exif\x00\x00" + b"\x00" * 240)
        with self.assertRaises(ValueError):
            self._add()

    def test_photo_is_hidden_if_merchant_record_expires(self):
        with patch.object(merchant_photos, "PHOTO_DIR", Path(self.temp.name) / "photos"):
            photo_id = self._add()
            merchant_photos.approve_photo(self.db, photo_id, "editor")
            self.db.commit()
            self.db.execute(
                "UPDATE real_merchants SET source_checked_at='' WHERE id=?",
                (self.merchant_id,),
            )
            self.db.commit()
            self.assertIsNone(merchant_photos.public_photo_file(self.db, photo_id))


if __name__ == "__main__":
    unittest.main()
