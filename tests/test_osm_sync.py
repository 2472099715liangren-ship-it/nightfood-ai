"""OSM transform, community safety and snapshot replay tests."""
import json
import tempfile
import unittest
from pathlib import Path
import database
from osm_sync import convert_osm_element, parse_overpass_payload, hydrate_osm_snapshot
from real_catalog import public_real_merchants, catalog_coverage, import_real_merchants


OSM_SAMPLE = {
    "type": "node", "id": 12345, "lat": 30.56, "lon": 114.30,
    "tags": {
        "name": "单元测试餐馆（虚构，仅用于测试）",
        "amenity": "restaurant",
        "addr:district": "江汉区",
    },
}


class OsmTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = database.DB_PATH
        database.DB_PATH = Path(self.tmp.name) / "test.db"
        database.initialize_database()

    def tearDown(self):
        database.DB_PATH = self.old_path
        self.tmp.cleanup()

    def test_conversion_is_explicitly_unverified_and_attributed(self):
        record = convert_osm_element(OSM_SAMPLE)
        self.assertEqual(record["status"], "pending")
        self.assertEqual(record["source_name"], "OpenStreetMap")
        self.assertEqual(record["verified_at"], "")
        self.assertIsNone(record["price_per_person"])
        self.assertEqual(
            record["source_url"], "https://www.openstreetmap.org/node/12345"
        )

    def test_missing_district_is_not_guessed(self):
        element = dict(OSM_SAMPLE)
        element["tags"] = {"name": "测试食堂", "amenity": "restaurant"}
        self.assertEqual(
            convert_osm_element(element)["district"], "待确认区县"
        )

    def test_missing_location_and_empty_response_rejected(self):
        self.assertIsNone(convert_osm_element({"type": "node", "id": 3, "tags": {"name": "X"}}))
        with self.assertRaises(ValueError):
            parse_overpass_payload({"elements": []})

    def test_only_attributed_osm_pending_visible(self):
        sample = convert_osm_element(OSM_SAMPLE)
        with database.connect() as connection:
            import_real_merchants(connection, [sample])
            result = public_real_merchants(connection)
            self.assertEqual(result["total"], 1)
            self.assertEqual(result["items"][0]["data_quality"], "community")
            self.assertEqual(catalog_coverage(connection)["community_total"], 1)
            # A different unreviewed provider must not be published.
            hidden = dict(sample, external_id="private:1", source_name="商家资料", status="pending")
            import_real_merchants(connection, [hidden])
            self.assertEqual(public_real_merchants(connection)["total"], 1)

    def test_hydrate_snapshot_is_checksum_idempotent(self):
        snapshot = Path(self.tmp.name) / "snapshot.json"
        snapshot.write_text(
            json.dumps([convert_osm_element(OSM_SAMPLE)], ensure_ascii=False),
            encoding="utf-8",
        )
        with database.connect() as connection:
            first = hydrate_osm_snapshot(connection, snapshot)
            second = hydrate_osm_snapshot(connection, snapshot)
            self.assertEqual((first, second), (1, 0))
            self.assertEqual(public_real_merchants(connection)["total"], 1)
            self.assertEqual(len(database.list_merchants(connection)), 24)

    def test_osm_refresh_cannot_downgrade_verified_record(self):
        record = convert_osm_element(OSM_SAMPLE)
        verified = dict(
            record,
            status="verified",
            verified_at="2026-08-14",
            verification_method="商户书面确认",
        )
        with database.connect() as connection:
            import_real_merchants(connection, [verified])
            import_real_merchants(connection, [record])
            state = connection.execute(
                "SELECT status FROM real_merchants WHERE external_id=?",
                (record["external_id"],),
            ).fetchone()
            self.assertEqual(state["status"], "verified")


if __name__ == "__main__":
    unittest.main()
