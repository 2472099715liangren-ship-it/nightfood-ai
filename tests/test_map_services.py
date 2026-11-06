"""Coordinates, optional keys and real provider responses; no live network required."""

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

from geo_coordinates import wgs84_to_gcj02, gcj02_to_wgs84
from map_services import public_map_config, walking_route, _fetch_route
from dining_decision import opening_status, prepare_decision


class MapServiceTests(unittest.TestCase):
    def setUp(self):
        _fetch_route.cache_clear()
        self.origin = dict(name="江汉路", latitude=30.586, longitude=114.291)
        self.merchant = dict(
            id=1,
            name="测试分店",
            latitude=30.6,
            longitude=114.3,
            map_search_url="https://uri.amap.com/search",
        )

    def test_known_conversion_and_round_trip(self):
        lat, lng = wgs84_to_gcj02(39.916527, 116.397128)
        self.assertAlmostEqual(lat, 39.91793074924595, places=7)
        self.assertAlmostEqual(lng, 116.40337249402477, places=7)
        self.assertEqual(gcj02_to_wgs84(lat, lng), (39.916527, 116.397128))
        self.assertEqual(wgs84_to_gcj02(48.85, 2.35), (48.85, 2.35))

    def test_private_route_key_never_appears_in_public_config(self):
        with patch.dict(
            "os.environ",
            {"TIANDITU_KEY": "browser-test", "AMAP_WEB_KEY": "private-test"},
        ):
            config = public_map_config()
        self.assertEqual(config["provider"], "tianditu")
        self.assertNotIn("private-test", json.dumps(config))
        self.assertTrue(config["walking_enabled"])

    def test_missing_key_provides_external_route_without_fabricated_duration(self):
        with patch.dict("os.environ", {"AMAP_WEB_KEY": ""}), patch(
            "map_services.urlopen"
        ) as network:
            result = walking_route(self.origin, self.merchant)
        network.assert_not_called()
        self.assertEqual(result["status"], "unconfigured")
        self.assertIn("from=", result["navigation_url"])
        self.assertIn("coordinate=gaode", result["navigation_url"])
        self.assertNotIn("duration_seconds", result)

    def test_real_provider_response_is_converted_and_cached(self):
        lat, lng = wgs84_to_gcj02(30.6, 114.3)
        response = dict(
            status="1",
            route=dict(
                paths=[
                    dict(
                        distance="1600",
                        duration="1234",
                        steps=[
                            dict(
                                instruction="沿<b>道路</b>前行", polyline=f"{lng},{lat}"
                            )
                        ],
                    )
                ]
            ),
        )
        with patch.dict("os.environ", {"AMAP_WEB_KEY": "private-test"}), patch(
            "map_services.urlopen",
            return_value=io.BytesIO(json.dumps(response).encode()),
        ) as network:
            first = walking_route(self.origin, self.merchant)
            second = walking_route(self.origin, self.merchant)
        self.assertEqual(first, second)
        self.assertEqual(network.call_count, 1)
        self.assertEqual(first["distance_m"], 1600)
        self.assertEqual(first["duration_seconds"], 1234)
        self.assertEqual(first["points"], [(30.6, 114.3)])
        self.assertEqual(first["steps"], ["沿道路前行"])

    def test_provider_failure_does_not_expose_secret_or_make_up_eta(self):
        with patch.dict("os.environ", {"AMAP_WEB_KEY": "private-test"}), patch(
            "map_services.urlopen", side_effect=URLError("private-test")
        ):
            result = walking_route(self.origin, self.merchant)
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("private-test", json.dumps(result))
        self.assertNotIn("duration_seconds", result)

    def test_invalid_origin_and_missing_destination(self):
        with self.assertRaises(ValueError):
            walking_route(dict(latitude=float("nan"), longitude=114), self.merchant)
        result = walking_route(self.origin, dict(self.merchant, latitude=None))
        self.assertEqual(result["status"], "missing_destination")

    def test_multiple_opening_intervals_keep_weekday_restrictions(self):
        hours = "Mo-Fr 11:00-14:00, 17:00-23:00"
        self.assertEqual(opening_status(hours, "2026-11-06T18:00+08:00"), "open")
        self.assertEqual(opening_status(hours, "2026-11-06T15:00+08:00"), "closed")
        self.assertEqual(opening_status(hours, "2026-11-07T18:00+08:00"), "closed")

    def test_explicit_preferences_skip_model_and_validate_user_edits(self):
        with patch("decision_preferences._extract_with_ai") as model:
            context, mode = prepare_decision(
                dict(
                    message="按修改条件筛选",
                    preferences=dict(
                        party_size=4,
                        budget=300,
                        budget_kind="total",
                        location={"name": "江汉路"},
                    ),
                )
            )
        model.assert_not_called()
        self.assertEqual(context["party_size"], 4)
        self.assertEqual(mode, "local")
        with self.assertRaises(ValueError):
            prepare_decision(dict(message="修改", preferences=dict(party_size=2.5)))
        with self.assertRaises(ValueError):
            prepare_decision(
                dict(
                    message="修改",
                    preferences=dict(location={"name": "不存在的具体位置"}),
                )
            )
