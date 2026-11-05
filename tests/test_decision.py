"""Decision journey: request parsing, real facts, hard limits and action APIs."""

import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

import database
from app import NightFindHandler
from decision_catalog import saved_real_merchants, set_real_favorite
from decision_preferences import (
    LOCAL_ZONE,
    next_question,
    parse_request,
    per_person_budget,
)
from dining_decision import make_decision, opening_status
from real_catalog import (
    import_real_merchants,
    get_public_real_merchant,
    public_real_merchants,
)

NOW = datetime(2026, 11, 4, 16, 0, tzinfo=LOCAL_ZONE)


class PreferenceTests(unittest.TestCase):
    def setUp(self):
        self.no_ai = patch.dict(os.environ, {"OPENAI_API_KEY": ""})
        self.no_ai.start()
        self.addCleanup(self.no_ai.stop)

    def test_windows_without_iana_data_keeps_beijing_time(self):
        import importlib.util
        from zoneinfo import ZoneInfoNotFoundError

        path = Path(__file__).resolve().parents[1] / "decision_preferences.py"
        spec = importlib.util.spec_from_file_location("windows_preferences", path)
        module = importlib.util.module_from_spec(spec)
        with patch("zoneinfo.ZoneInfo", side_effect=ZoneInfoNotFoundError("missing")):
            spec.loader.exec_module(module)
        context, _ = module.parse_request(
            "今晚七点，四个人，江汉路，总预算300元", now=NOW
        )
        self.assertEqual(context["arrival"], "2026-11-04T19:00+08:00")
        self.assertEqual(module.per_person_budget(context), 75)

    def test_full_request_and_total_budget(self):
        context, mode = parse_request(
            "今晚七点，四个人在江汉路附近，总共三百元，想吃湖北菜", now=NOW
        )
        self.assertEqual(context["party_size"], 4)
        self.assertEqual(per_person_budget(context), 75)
        self.assertEqual(context["arrival"], "2026-11-04T19:00+08:00")
        self.assertEqual(context["location"]["name"], "江汉路")
        self.assertEqual(context["cuisine"], "湖北菜")
        self.assertIsNone(next_question(context, NOW))
        self.assertEqual(mode, "local")

    def test_ambiguous_budget_asks_unit_then_preserves_it(self):
        context, _ = parse_request("江汉路，两个人，明天七点，预算200", now=NOW)
        self.assertIn("每个人", next_question(context, NOW)["question"])
        context, _ = parse_request("是总预算", context, now=NOW)
        self.assertEqual(per_person_budget(context), 100)
        context, _ = parse_request("预算降到160", context, now=NOW)
        self.assertEqual(per_person_budget(context), 80)

    def test_waiting_minutes_are_not_a_budget(self):
        context, _ = parse_request("江汉路，等位最多20分钟", now=NOW)
        self.assertIsNone(context["budget"])
        self.assertEqual(context["wait_minutes"], 20)

    def test_multi_turn_does_not_turn_one_allergic_diner_into_group_size(self):
        context, _ = parse_request("江汉路，四个人，总预算300，今晚七点", now=NOW)
        context, _ = parse_request("我们有一个人不吃辣", context, now=NOW)
        self.assertEqual(context["party_size"], 4)
        self.assertEqual(context["avoid"], ["辣"])
        self.assertEqual(per_person_budget(context), 75)
        context, _ = parse_request("改成两个人，明天同一时间", context, now=NOW)
        self.assertEqual(context["party_size"], 2)
        self.assertEqual(per_person_budget(context), 150)
        self.assertEqual(context["arrival"], "2026-11-05T19:00+08:00")

    def test_unknown_new_location_is_not_silently_ignored(self):
        context, _ = parse_request("江汉路", now=NOW)
        context, _ = parse_request("改成在武汉站附近吃饭", context, now=NOW)
        self.assertIsNone(context["location"])
        self.assertIn("哪里", next_question(context, NOW)["question"])

    def test_invalid_values_and_unrecognised_time_remain_visible(self):
        for text in ("江汉路，0个人", "江汉路，晚上25点", "总预算0元"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_request(text, now=NOW)
        context, _ = parse_request("江汉路，一人，人均50元，晚上七点", now=NOW)
        self.assertTrue(context["arrival_date_inferred"])
        context, _ = parse_request("江汉路，一人，人均50元，今天上午九点", now=NOW)
        self.assertIn("过去", next_question(context, NOW)["question"])

    def test_landmark_origin_survives_followups_without_becoming_device_coordinates(
        self,
    ):
        context, _ = parse_request("江汉路", now=NOW)
        context, _ = parse_request("四个人", context, now=NOW)
        self.assertEqual(context["location"]["district"], "江汉区")
        self.assertIn("商圈中心", context["location"]["note"])

    def test_unsupported_weekday_does_not_silently_become_today(self):
        context, _ = parse_request("江汉路，一个人，人均50元，下周五晚上七点", now=NOW)
        self.assertIsNone(context["arrival"])
        self.assertIn("什么时候", next_question(context, NOW)["question"])

    def test_device_location_is_wuhan_bounded_and_labelled(self):
        location = {"name": "我的位置", "latitude": 30.586, "longitude": 114.291}
        context, _ = parse_request("当前位置", location=location, now=NOW)
        self.assertEqual(context["provenance"]["location"], "device")
        with self.assertRaises(ValueError):
            parse_request("当前位置", location={**location, "latitude": 40}, now=NOW)

    def test_ai_only_extracts_request_fields_with_local_fallback(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}):
            with patch(
                "decision_preferences._extract_with_ai",
                return_value={
                    "party_size": 3,
                    "budget": 80,
                    "budget_kind": "per_person",
                },
            ):
                context, mode = parse_request("三位朋友想吃点东西", now=NOW)
                self.assertEqual(mode, "ai")
                self.assertEqual(context["party_size"], 3)
            with patch(
                "decision_preferences._extract_with_ai",
                side_effect=ValueError("bad JSON"),
            ):
                context, mode = parse_request("江汉路，两个人，人均80元", now=NOW)
                self.assertEqual(mode, "fallback")
                self.assertEqual(context["budget"], 80)

    def test_opening_hours_respect_midnight_and_weekday(self):
        self.assertEqual(
            opening_status("17:00-02:00", "2026-11-05T01:30+08:00"), "open"
        )
        self.assertEqual(
            opening_status("17:00-02:00", "2026-11-05T02:00+08:00"), "closed"
        )
        self.assertEqual(
            opening_status("Mo-Fr 17:00-02:00", "2026-11-07T01:00+08:00"), "open"
        )
        self.assertEqual(
            opening_status("Mo-Fr 17:00-02:00", "2026-11-08T01:00+08:00"), "closed"
        )
        self.assertEqual(
            opening_status("节假日另行安排", "2026-11-05T19:00+08:00"), "unknown"
        )


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = database.DB_PATH
        database.DB_PATH = Path(self.temp.name) / "decision.db"
        self.no_ai = patch.dict(os.environ, {"OPENAI_API_KEY": ""})
        self.no_ai.start()
        database.initialize_database(
            import_snapshot=False, import_bundled_catalog=False
        )
        self.connection = database.connect()
        database.ensure_session(self.connection, "visitor-a")
        database.ensure_session(self.connection, "visitor-b")
        self.arrival = (
            (datetime.now(LOCAL_ZONE) + timedelta(days=1))
            .replace(hour=19, minute=0)
            .isoformat()
        )
        self.preferences, _ = parse_request(
            "江汉路，四个人，总预算300，湖北菜", {"arrival": self.arrival}
        )

    def tearDown(self):
        self.connection.close()
        database.DB_PATH = self.old_path
        self.no_ai.stop()
        self.temp.cleanup()

    def add_merchant(self, external_id, **overrides):
        today = datetime.now().date().isoformat()
        record = dict(
            external_id=external_id,
            name="真实门店-" + external_id,
            district="江汉区",
            address="武汉市江汉区测试街1号",
            cuisine="湖北菜",
            latitude=30.586,
            longitude=114.291,
            price_per_person=58,
            opening_hours="17:00-23:00",
            source_name="商家授权资料",
            source_url="https://example.org/store/" + external_id,
            verified_at=today,
            source_checked_at=today,
            verification_method="商家确认",
            status="verified",
        )
        record.update(overrides)
        import_real_merchants(self.connection, [record])
        return self.connection.execute(
            "SELECT id FROM real_merchants WHERE external_id=?", (external_id,)
        ).fetchone()[0]

    def decide(self, **payload):
        return make_decision(
            self.connection, self.preferences, {"message": "帮我挑选", **payload}
        )

    def test_only_three_real_candidates_and_known_hard_failures_excluded(self):
        ids = [self.add_merchant(str(i)) for i in range(5)]
        expensive = self.add_merchant("expensive", price_per_person=100)
        closed = self.add_merchant("closed", opening_hours="08:00-12:00")
        result = self.decide()
        self.assertEqual(len(result["items"]), 3)
        self.assertTrue({item["id"] for item in result["items"]} <= set(ids))
        self.assertNotIn(expensive, [item["id"] for item in result["items"]])
        self.assertNotIn(closed, [item["id"] for item in result["items"]])
        self.assertEqual(result["eligible_total"], 5)
        self.assertTrue(
            all(item["name"].startswith("真实门店") for item in result["items"])
        )

    def test_unknown_facts_are_conditional_not_fabricated(self):
        self.add_merchant(
            "unknown",
            price_per_person=None,
            opening_hours=None,
            latitude=None,
            longitude=None,
        )
        self.preferences["wait_minutes"] = 15
        item = self.decide()["items"][0]
        self.assertTrue(item["needs_confirmation"])
        self.assertEqual(item["opening_status"], "unknown")
        self.assertIsNone(item["estimated_total"])
        self.assertIsNone(item["distance_km"])
        self.assertTrue(any("实时排队" in value for value in item["questions"]))
        self.assertIn("navigation_url", item)
        self.assertNotIn("score", item)

    def test_radius_uses_unrounded_distance_and_keeps_unknown_explicit(self):
        near = self.add_merchant("near")
        self.add_merchant("far", latitude=30.9)
        self.preferences["radius_km"] = 1
        result = self.decide()
        self.assertEqual([item["id"] for item in result["items"]], [near])
        self.assertEqual(result["excluded"]["超过指定直线距离"], 1)

    def test_budget_uses_upper_end_of_source_range(self):
        self.add_merchant(
            "range",
            price_per_person=None,
            price_range_min=20,
            price_range_max=100,
            price_range_basis="per_person",
        )
        self.assertEqual(self.decide()["items"], [])

    def test_dish_price_range_is_never_used_as_per_person_budget(self):
        self.add_merchant(
            "dish-band",
            price_per_person=None,
            price_range_min=20,
            price_range_max=50,
            price_range_basis="dish",
        )
        item = self.decide()["items"][0]
        self.assertIsNone(item["estimated_total"])
        self.assertTrue(any("缺少可靠人均" in value for value in item["questions"]))
        self.assertFalse(any("预算内" in value for value in item["reasons"]))

    def test_allergy_conflicts_and_unverified_ingredients(self):
        self.add_merchant("spicy", cuisine="香辣湖北菜")
        safe_unknown = self.add_merchant("plain")
        self.preferences["avoid"] = ["辣"]
        result = self.decide()
        self.assertEqual([item["id"] for item in result["items"]], [safe_unknown])
        self.assertTrue(
            any("不能证明" in value for value in result["items"][0]["questions"])
        )

    def test_rotation_keeps_requested_store_and_never_repeats_seen_as_new(self):
        ids = [self.add_merchant(str(i)) for i in range(4)]
        result = self.decide(message="换一批", seen_ids=ids[:3], keep_ids=[ids[0]])
        self.assertEqual({item["id"] for item in result["items"]}, {ids[0], ids[3]})
        empty = self.decide(message="换一批", seen_ids=ids)
        self.assertEqual(empty["items"], [])
        self.assertTrue(empty["exhausted"])

    def test_numbered_followup_preserves_or_replaces_correct_candidate(self):
        ids = [self.add_merchant(str(i)) for i in range(4)]
        result = self.decide(message="第二家太贵，换一家", previous_ids=ids[:3])
        self.assertNotIn(ids[1], [item["id"] for item in result["items"]])
        result = self.decide(
            message="保留第三家，换一批", previous_ids=ids[:3], seen_ids=ids[:3]
        )
        self.assertEqual(result["items"][0]["id"], ids[2])
        self.assertTrue(result["items"][0]["kept"])

    def test_real_favorites_are_separate_idempotent_and_session_scoped(self):
        merchant_id = self.add_merchant("saved")
        set_real_favorite(self.connection, "visitor-a", merchant_id, True)
        set_real_favorite(self.connection, "visitor-a", merchant_id, True)
        self.assertEqual(len(saved_real_merchants(self.connection, "visitor-a")), 1)
        self.assertEqual(saved_real_merchants(self.connection, "visitor-b"), [])
        self.assertEqual(database.list_favorites(self.connection, "visitor-a"), [])
        set_real_favorite(self.connection, "visitor-a", merchant_id, False)
        self.assertEqual(saved_real_merchants(self.connection, "visitor-a"), [])

    def test_ranking_reads_beyond_first_catalog_page(self):
        for index in range(101):
            self.add_merchant(str(index), price_per_person=100 if index else 50)
        # The oldest, only affordable record is outside the first descending page.
        self.assertEqual(self.decide()["items"][0]["name"], "真实门店-0")

    def test_public_reads_hide_expired_images_and_menu_even_without_reimport(self):
        merchant_id = self.add_merchant("dated")
        c = self.connection
        c.execute(
            "INSERT INTO real_merchant_images(merchant_id,image_url,taken_at) VALUES (?,?,?)",
            (merchant_id, "https://example.org/old.jpg", "2020-01-01"),
        )
        c.execute(
            "INSERT INTO real_merchant_menu_items(merchant_id,dish_name,price,price_checked_at) VALUES (?,?,?,?)",
            (merchant_id, "旧价格", 20, "2020-01-01"),
        )
        detail = get_public_real_merchant(c, merchant_id)
        self.assertEqual(detail["images"], [])
        self.assertEqual(detail["menu_items"], [])
        self.assertIsNone(public_real_merchants(c)["items"][0]["cover_image_url"])


class DecisionHttpTests(unittest.TestCase):
    def test_request_to_real_comparison_collection_and_navigation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            database, "DB_PATH", Path(tmp) / "http.db"
        ), patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            database.initialize_database()
            server = ThreadingHTTPServer(("127.0.0.1", 0), NightFindHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = "http://127.0.0.1:" + str(server.server_port)

            def call(path, body=None, visitor="journey-a"):
                request = Request(
                    base + path,
                    data=json.dumps(body).encode() if body is not None else None,
                    headers={"X-Session": visitor, "Content-Type": "application/json"},
                )
                with urlopen(request, timeout=5) as response:
                    return json.load(response)

            try:
                result = call(
                    "/api/decision",
                    {
                        "message": "明天晚上七点，四个人，江汉路附近，总预算300元，湖北菜"
                    },
                )
                self.assertEqual(len(result["items"]), 3)
                self.assertEqual(result["budget_per_person"], 75)
                ids = [item["id"] for item in result["items"]]
                comparison = call(
                    "/api/real-compare?ids=" + ",".join(map(str, ids[:2]))
                )
                self.assertEqual(len(comparison["items"]), 2)
                item = comparison["items"][0]
                self.assertIn("destination=", item["navigation_url"])
                self.assertIn("uri.amap.com", item["map_search_url"])
                detail = call("/api/real-merchants/" + str(item["id"]))
                self.assertEqual(detail["name"], item["name"])
                self.assertIn("menu_items", detail)
                call("/api/real-favorites", {"merchant_id": item["id"], "active": True})
                self.assertEqual(
                    call("/api/real-favorites")["items"][0]["name"], item["name"]
                )
                self.assertEqual(
                    call("/api/real-favorites", visitor="journey-b")["items"], []
                )
                with self.assertRaises(HTTPError) as error:
                    call("/api/real-compare?ids=1,1")
                self.assertEqual(error.exception.code, 400)
                for asset in (
                    "/",
                    "/app.js",
                    "/api-client.js",
                    "/decision-view.js",
                    "/decision.css",
                    "/wuhan_map.js",
                    "/botanical.svg",
                    "/map/wuhan-basemap.geojson",
                ):
                    with urlopen(base + asset) as response:
                        self.assertEqual(response.status, 200)
                        if asset.endswith(".geojson"):
                            basemap = json.load(response)
                            self.assertEqual(basemap["type"], "FeatureCollection")
                            roads = [
                                feature
                                for feature in basemap["features"]
                                if feature["properties"]["layer"] == "road"
                            ]
                            self.assertGreaterEqual(len(roads), 500)
                            self.assertIn(
                                "徐东大街",
                                [road["properties"]["name"] for road in roads],
                            )
                            self.assertTrue(
                                any(
                                    feature["properties"]["layer"] == "lake"
                                    and feature["geometry"]["type"] == "Polygon"
                                    for feature in basemap["features"]
                                )
                            )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
