"""Refresh existing Ctrip branches from public, server-rendered merchant pages.

python3 refresh_wuhan_catalog.py --apply
No login, private API, review workflow, image copying, or price inference.
"""

import argparse
import csv
import hashlib
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from geo_coordinates import gcj02_to_wgs84

ROOT = Path(__file__).resolve().parent
USER_AGENT = "NightFind-WuhanCatalog/1.0 (+https://github.com/2472099715liangren-ship-it/nightfood-ai)"


def normalize_name(value):
    return re.sub(r"[\W_]", "", value.removeprefix("武汉")).casefold()


def parse_page(html, expected):
    match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        raise ValueError("页面没有公开的商家结构化资料")
    state = json.loads(match[1])["props"]["pageProps"]["initialState"]
    info = (state.get("mainInfoData") or {}).get("RestaurantInfo") or {}
    if info.get("DistrictName") != "武汉":
        raise ValueError("来源不属于武汉，跳过")
    actual_name = info.get("Name") or ""
    branch = re.search(r"[（(](.*?)[）)]", expected["name"])
    actual_branch = re.search(r"[（(](.*?)[）)]", actual_name)
    same_branch = (
        branch
        and actual_branch
        and normalize_name(branch[1]) == normalize_name(actual_branch[1])
        and normalize_name(expected["name"])[:3] == normalize_name(actual_name)[:3]
    )
    if (
        normalize_name(actual_name) != normalize_name(expected["name"])
        and not same_branch
    ):
        raise ValueError("来源分店名不一致，跳过：" + str(actual_name))
    source_id = re.search(r"/(\d+)\.html", expected["source_url"])
    if not source_id or int(source_id[1]) != info.get("RestaurantId"):
        raise ValueError("来源商家 ID 不一致")
    checked = date.today().isoformat()
    changes = {
        "source_checked_at": checked,
        "verification_method": "公开分店页面自动采集",
        "status": "pending",
    }
    if info.get("Address"):
        changes["address"] = info["Address"]
        if expected.get("district") in ("", "待确认区县"):
            from real_catalog import WUHAN_DISTRICTS

            changes["district"] = next(
                (
                    district
                    for district in WUHAN_DISTRICTS
                    if district in info["Address"]
                ),
                "待确认区县",
            )
    average = info.get("AveragePrice")
    if isinstance(average, (int, float)) and 0 < average <= 10000:
        changes["price_per_person"] = round(average)
    phones = [
        phone
        for phone in (info.get("BookTelList") or [])
        if isinstance(phone, str) and re.fullmatch(r"\+?[\d ()-]{5,30}", phone)
    ]
    if phones:
        changes["phone"] = phones[0]
    # Keep weekly schedules; never copy the transient "营业中" status.
    schedules = []
    for day in info.get("WeekdayDtoList") or info.get("MergeWeekdayDtoList") or []:
        if not isinstance(day, dict):
            continue
        intervals = [
            f'{slot["BeginTime"]}-{slot["EndTime"]}'
            for slot in (day.get("OpenTimeList") or [])
            if isinstance(slot, dict)
            and re.fullmatch(r"\d{2}:\d{2}", str(slot.get("BeginTime") or ""))
            and re.fullmatch(r"\d{2}:\d{2}", str(slot.get("EndTime") or ""))
        ]
        if intervals:
            schedules.append((day.get("Weekday", ""), ", ".join(intervals)))
    weekdays = dict(
        zip(
            ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
            ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
        )
    )
    if schedules:
        if (
            len({day for day, _ in schedules}) == 7
            and len({hours for _, hours in schedules}) == 1
        ):
            changes["opening_hours"] = schedules[0][1]
        else:
            known = [
                (weekdays[day], hours) for day, hours in schedules if day in weekdays
            ]
            if known:
                changes["opening_hours"] = "; ".join(
                    f"{day} {hours}" for day, hours in known
                )
    point = info.get("GDCoord") or {}
    lat, lng = point.get("Lat"), point.get("Lon")
    if lat is None or lng is None:
        lng = point.get("Lng")
    if (
        isinstance(lat, (int, float))
        and isinstance(lng, (int, float))
        and 29.8 <= lat <= 31.5
        and 113.5 <= lng <= 115.2
    ):
        latitude, longitude = gcj02_to_wgs84(lat, lng)
        changes.update(
            latitude=latitude,
            longitude=longitude,
            location_note="携程分店 GDCoord（GCJ-02）转换为 WGS84；来源商家点位，非精确入口。",
        )
    menus = []
    for dish in info.get("RestaurantRecommendedFoodList") or []:
        title = str(dish.get("Title") or "").strip()
        if not title:
            continue
        raw_price = str(dish.get("Price") or "").strip()
        price_match = re.fullmatch(r"[¥￥]\s*(\d+(?:\.\d{1,2})?)", raw_price)
        price = float(price_match[1]) if price_match else None
        menus.append(
            dict(
                external_id=expected["external_id"],
                dish_name=title,
                price=price if price and 0 < price <= 10000 else "",
                price_unit="元（来源未注明份量）",
                price_source_url=expected["source_url"],
                price_checked_at=checked,
                price_note=(
                    "公开分店推荐菜单参考价，来源未注明份量；实际售价以门店为准。"
                    if price
                    else "来源列出菜名，未提供单品价格。"
                ),
            )
        )
    if menus:
        changes["signature_dishes"] = ";".join(d["dish_name"] for d in menus[:8])
    # Store only the factual source fields used, not page tracking or signatures.
    evidence = {
        key: info.get(key)
        for key in (
            "RestaurantId",
            "Name",
            "DistrictName",
            "Address",
            "AveragePrice",
            "BookTelList",
            "GDCoord",
            "WeekdayDtoList",
            "MergeWeekdayDtoList",
        )
    }
    evidence["menu"] = [
        {"name": d.get("Title"), "price": d.get("Price")}
        for d in info.get("RestaurantRecommendedFoodList") or []
    ]
    return changes, menus, evidence


def write_csv(path, rows, fields):
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def refresh(apply=False, limit=50, discover=False):
    merchants_path = ROOT / "data" / "wuhan_restaurants.csv"
    menu_path = ROOT / "data" / "wuhan_menu_items.csv"
    with merchants_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames)
        merchants = list(reader)
    with menu_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        menu_fields = list(reader.fieldnames)
        menus = list(reader)
    for field in ("phone", "opening_hours", "price_range_basis"):
        if field not in fields:
            fields.append(field)
    menu_index = {(item["external_id"], item["dish_name"]): item for item in menus}
    report, errors = [], []
    candidates = [
        row
        for row in merchants
        if urlsplit(row["source_url"]).hostname == "gs.ctrip.com"
    ][:limit]
    known_ids = {
        int(match[1])
        for row in merchants
        if (match := re.search(r"/(\d+)\.html", row["source_url"]))
    }
    by_name = {normalize_name(row["name"]): row for row in merchants}
    for row in candidates:
        try:
            request = Request(row["source_url"], headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=20) as response:
                raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise ValueError("页面超过大小上限")
            changes, dishes, evidence = parse_page(raw.decode("utf-8"), row)
            row.update(changes)
            if not any(old["external_id"] == row["external_id"] for old in merchants):
                merchants.append(row)
                by_name[normalize_name(row["name"])] = row
            else:
                for old in merchants:
                    if old["external_id"] == row["external_id"]:
                        old.update(row)
                        break
            if discover and len(candidates) < limit:
                match = re.search(
                    r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                    raw.decode("utf-8"),
                    re.S,
                )
                related = json.loads(match[1])["props"]["pageProps"][
                    "initialState"
                ].get("waterFallList", [])
                for item in related:
                    identifier, name = item.get("restaurantId"), item.get(
                        "restaurantName"
                    )
                    if (
                        not identifier
                        or not name
                        or identifier in known_ids
                        or len(candidates) >= limit
                    ):
                        continue
                    known_ids.add(identifier)
                    existing = by_name.get(normalize_name(name))
                    candidate = (
                        dict(existing) if existing else {field: "" for field in fields}
                    )
                    candidate.update(
                        external_id=(
                            existing["external_id"]
                            if existing
                            else f"web:ctrip:{identifier}"
                        ),
                        name=name,
                        district=candidate.get("district") or "待确认区县",
                        cuisine=candidate.get("cuisine")
                        or str(item.get("cuisine") or "餐厅"),
                        source_name="携程美食林",
                        source_url=f"https://gs.ctrip.com/html5/you/foods/fooddetail/145/{identifier}.html",
                    )
                    candidates.append(candidate)
            for dish in dishes:
                key = (dish["external_id"], dish["dish_name"])
                old = menu_index.get(key)
                if not old or dish["price"] != "" or old["price"] == "":
                    menu_index[key] = dish
            report.append(
                dict(
                    external_id=row["external_id"],
                    source_url=row["source_url"],
                    html_sha256=hashlib.sha256(raw).hexdigest(),
                    fields=changes,
                    evidence=evidence,
                )
            )
            print(
                f'已读取：{row["name"]} · {sum(d["price"] != "" for d in dishes)} 条单价',
                flush=True,
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(dict(external_id=row["external_id"], reason=str(error)))
            print(f'跳过：{row["name"]} · {error}', flush=True)
        time.sleep(0.5)
    result = dict(
        collected_at=datetime.now(timezone.utc).isoformat(),
        records=report,
        errors=errors,
    )
    if apply and report:
        write_csv(merchants_path, merchants, fields)
        write_csv(menu_path, list(menu_index.values()), menu_fields)
        (ROOT / "data_sources" / "wuhan_web_refresh.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        )
    return {
        "updated": len(report),
        "skipped": len(errors),
        "applied": bool(apply and report),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="补充已有武汉分店资料，保持来源和分店一致"
    )
    parser.add_argument("--apply", action="store_true", help="写入 CSV；默认只检查来源")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument(
        "--discover",
        action="store_true",
        help="从公开相关推荐补充武汉分店，仍逐店校验；总请求不超过 limit",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            refresh(args.apply, max(1, min(args.limit, 50)), args.discover),
            ensure_ascii=False,
        )
    )
