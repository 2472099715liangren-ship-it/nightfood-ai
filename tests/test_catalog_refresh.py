"""Only branch-matched source facts are imported; missing prices stay missing."""

import json
import unittest
from refresh_wuhan_catalog import parse_page


class CatalogRefreshTests(unittest.TestCase):
    def setUp(self):
        self.expected = dict(
            name="测试餐厅（武汉店）",
            external_id="web:test",
            source_url="https://gs.ctrip.com/html5/you/foods/fooddetail/145/123.html",
        )
        self.info = dict(
            Name="测试餐厅(武汉店)",
            RestaurantId=123,
            DistrictName="武汉",
            Address="武汉市江汉区某路10号",
            GDCoord=dict(Lat=30.6, Lng=114.3),
            AveragePrice=80,
            BookTelList=None,
            WeekdayDtoList=[
                dict(
                    Weekday="周一",
                    OpenTimeList=[dict(BeginTime="11:00", EndTime="14:00")],
                )
            ],
            RestaurantRecommendedFoodList=[
                dict(Title="来源菜品", Price="¥ 18"),
                dict(Title="无价菜品", Price=""),
            ],
        )

    def html(self):
        data = dict(
            props=dict(
                pageProps=dict(
                    initialState=dict(mainInfoData=dict(RestaurantInfo=self.info))
                )
            )
        )
        return (
            '<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(data)
            + "</script>"
        )

    def test_prices_coordinates_and_weekday_hours_keep_provenance(self):
        fields, menu, evidence = parse_page(self.html(), self.expected)
        self.assertEqual(fields["opening_hours"], "Mo 11:00-14:00")
        self.assertEqual(fields["price_per_person"], 80)
        self.assertNotEqual(fields["latitude"], 30.6)
        self.assertIn("GCJ-02", fields["location_note"])
        self.assertEqual(menu[0]["price"], 18)
        self.assertEqual(menu[1]["price"], "")
        self.assertIn("未注明份量", menu[0]["price_unit"])
        self.assertEqual(evidence["GDCoord"]["Lat"], 30.6)

    def test_wrong_branch_city_or_source_id_is_rejected(self):
        for changes in [
            dict(Name="测试餐厅(另一家店)"),
            dict(DistrictName="上海"),
            dict(RestaurantId=999),
        ]:
            original = dict(self.info)
            self.info.update(changes)
            with self.assertRaises(ValueError):
                parse_page(self.html(), self.expected)
            self.info = original

    def test_recommendation_title_is_not_a_price(self):
        self.info["RestaurantRecommendedFoodList"][0]["Price"] = "人均 18 元"
        _, menu, _ = parse_page(self.html(), self.expected)
        self.assertEqual(menu[0]["price"], "")

    def test_incomplete_schedule_keeps_other_source_facts(self):
        self.info["WeekdayDtoList"] = [
            None,
            dict(Weekday="周一", OpenTimeList=[dict(BeginTime=None, EndTime=None)]),
        ]
        fields, menu, _ = parse_page(self.html(), self.expected)
        self.assertNotIn("opening_hours", fields)
        self.assertEqual(menu[0]["price"], 18)
