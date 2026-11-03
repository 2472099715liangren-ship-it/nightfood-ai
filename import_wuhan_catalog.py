"""Import the bundled Wuhan restaurant data and optionally add map coordinates.

Normal app startup imports the three checked-in CSV files automatically.
Run this file with --geocode once to fill coordinates for addresses that can
be matched confidently by OpenStreetMap Nominatim.
"""
import argparse
import json
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from database import connect, initialize_database
from real_catalog import seed_bundled_catalog

WUHAN_VIEWBOX = "113.65,31.05,114.85,30.15"
USER_AGENT = "NightFind-WuhanCatalog/1.0 (+https://github.com/2472099715liangren-ship-it/nightfood-ai)"


def _address_is_specific(address):
    vague_words = ("商圈", "附近", "待复核", "未披露", "待确认", "景区内")
    if any(word in address for word in vague_words):
        return False
    return bool(re.search(r"\d|天街|万达|中心|大厦|广场|商业街", address))


def _geocode_one(query):
    params = urlencode({
        "q": query,
        "format": "jsonv2",
        "limit": 1,
        "addressdetails": 1,
        "countrycodes": "cn",
        "viewbox": WUHAN_VIEWBOX,
        "bounded": 1,
    })
    request = Request(
        "https://nominatim.openstreetmap.org/search?" + params,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"},
    )
    with urlopen(request, timeout=20) as response:
        results = json.loads(response.read().decode("utf-8"))
    return results[0] if results else None


def geocode_missing(connection, limit=60):
    """Geocode specific street addresses only; vague locations remain unpinned."""
    rows = connection.execute(
        """
        SELECT id,name,district,address FROM real_merchants
        WHERE latitude IS NULL OR longitude IS NULL
        ORDER BY id LIMIT ?
        """,
        (max(1, min(int(limit), 100)),),
    ).fetchall()
    updated = 0
    skipped = 0
    for row in rows:
        address = row["address"]
        if not _address_is_specific(address):
            skipped += 1
            continue

        query = "{},{},{},武汉市,湖北省,中国".format(
            row["name"], address, row["district"]
        )
        cached = connection.execute(
            "SELECT latitude,longitude,display_name FROM real_merchant_geocode_cache WHERE query=?",
            (query,),
        ).fetchone()
        if cached:
            result = (
                {"lat": cached["latitude"], "lon": cached["longitude"],
                 "display_name": cached["display_name"]}
                if cached["latitude"] is not None and cached["longitude"] is not None
                else None
            )
        else:
            try:
                result = _geocode_one(query)
            except Exception as error:
                print("地理编码暂时失败：{} ({})".format(row["name"], error))
                result = None
            if result:
                latitude = float(result["lat"])
                longitude = float(result["lon"])
                display_name = result.get("display_name", "")
                # Keep only results inside the Wuhan city search box.
                if not (30.15 <= latitude <= 31.05 and 113.65 <= longitude <= 114.85):
                    result = None
                else:
                    result = {
                        "lat": latitude,
                        "lon": longitude,
                        "display_name": display_name,
                    }
            connection.execute(
                """
                INSERT INTO real_merchant_geocode_cache(
                    query,latitude,longitude,display_name,checked_at
                ) VALUES (?,?,?,?,DATE('now'))
                ON CONFLICT(query) DO UPDATE SET
                    latitude=excluded.latitude,longitude=excluded.longitude,
                    display_name=excluded.display_name,checked_at=excluded.checked_at
                """,
                (
                    query,
                    result["lat"] if result else None,
                    result["lon"] if result else None,
                    result["display_name"] if result else "",
                ),
            )
            connection.commit()
            time.sleep(1.1)

        if not result:
            skipped += 1
            continue

        display_name = result["display_name"]
        street_tokens = re.findall(
            r"[\u4e00-\u9fffA-Za-z0-9]+(?:路|街|大道|巷|天街|广场|中心|大厦)",
            address,
        )
        if street_tokens and not any(token in display_name for token in street_tokens):
            skipped += 1
            continue

        note = "WGS84坐标由OpenStreetMap Nominatim按门店地址匹配；地图点位仍建议人工复核。"
        connection.execute(
            "UPDATE real_merchants SET latitude=?,longitude=?,"
            "location_note=CASE WHEN location_note='' THEN ? "
            "ELSE location_note || '；' || ? END WHERE id=?",
            (result["lat"], result["lon"], note, note, row["id"]),
        )
        connection.commit()
        updated += 1
        print("已定位：{} → {}".format(row["name"], display_name))
    return {"geocoded": updated, "skipped": skipped, "checked": len(rows)}


def main():
    parser = argparse.ArgumentParser(description="导入武汉真实餐厅目录")
    parser.add_argument(
        "--geocode", action="store_true",
        help="使用 OpenStreetMap Nominatim 为具体地址补充 WGS84 坐标（约每秒一条）",
    )
    parser.add_argument(
        "--geocode-limit", type=int, default=60,
        help="本次最多尝试定位多少家门店，默认 60",
    )
    args = parser.parse_args()

    initialize_database()
    with connect() as connection:
        imported = seed_bundled_catalog(connection)
        summary = {
            "公开商家数": connection.execute(
                "SELECT COUNT(*) FROM real_merchants WHERE status='pending' "
                "AND external_id LIKE 'web:%' AND source_checked_at >= date('now','-2 years')"
            ).fetchone()[0],
            "图片数": connection.execute(
                "SELECT COUNT(*) FROM real_merchant_images"
            ).fetchone()[0],
            "菜品记录数": connection.execute(
                "SELECT COUNT(*) FROM real_merchant_menu_items"
            ).fetchone()[0],
            "有坐标门店数": connection.execute(
                "SELECT COUNT(*) FROM real_merchants WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
            ).fetchone()[0],
            "本次导入": imported,
        }
        if args.geocode:
            summary["地图定位"] = geocode_missing(connection, args.geocode_limit)
            summary["有坐标门店数"] = connection.execute(
                "SELECT COUNT(*) FROM real_merchants WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
            ).fetchone()[0]
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
