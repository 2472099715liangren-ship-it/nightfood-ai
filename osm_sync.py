"""Fetch Wuhan food venues from the ODbL-licensed OpenStreetMap Overpass API.

Usage (network required):
    python3 osm_sync.py fetch --output data_sources/osm_wuhan_snapshot.json

The generated snapshot contains OSM community entries, not independently
verified businesses. It must be distributed with OpenStreetMap attribution.
"""
import argparse
import hashlib
import json
import datetime as dt
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from real_catalog import UNKNOWN_DISTRICT, WUHAN_DISTRICTS, import_real_merchants

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT / "data_sources" / "osm_wuhan_snapshot.json"
ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
# Start with small, geographically separate Wuhan samples to respect public
# Overpass instance capacity. This is *not* full-city coverage.
SAMPLE_BBOXES = (
    (30.555, 114.245, 30.615, 114.315),  # Jianghan/Jiang'an central area
    (30.525, 114.305, 30.585, 114.385),  # Wuchang
    (30.475, 114.365, 30.535, 114.445),  # Guanggu/Hongshan
    (30.525, 114.205, 30.585, 114.285),  # Hanyang/Qiaokou
)


def overpass_query(bbox):
    south, west, north, east = bbox
    return (
        "[out:json][timeout:35];"
        "(nwr[amenity~'^(restaurant|fast_food|cafe|food_court)$']"
        "[name]({},{},{},{}););out center tags;".format(
            south, west, north, east
        )
    )


MAX_RECORDS = 2000


def convert_osm_element(element):
    """Make one source-attributed, explicitly unverified merchant record."""
    if not isinstance(element, dict):
        return None
    tags = element.get("tags") or {}
    name = (tags.get("name:zh") or tags.get("name") or "").strip()
    kind = element.get("type")
    identifier = element.get("id")
    location = element.get("center") or element
    lat, lon = location.get("lat"), location.get("lon")
    if kind not in ("node", "way", "relation") or not isinstance(identifier, int):
        return None
    if not name or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    # Safety bound in addition to the actual administrative-area query.
    if not (29.9 <= lat <= 31.5 and 113.5 <= lon <= 115.2):
        return None
    district = tags.get("addr:district") or tags.get("is_in:district") or ""
    if district not in WUHAN_DISTRICTS:
        district = UNKNOWN_DISTRICT

    street = (tags.get("addr:street") or "").strip()
    number = (tags.get("addr:housenumber") or "").strip()
    address = "武汉市" + (district if district != UNKNOWN_DISTRICT else "") + street + number if street else ""
    if not address:
        address = "详细地址待核实，请通过来源地图查看位置"

    cuisine = (tags.get("cuisine") or "").replace(";", "、").strip()
    if not cuisine:
        cuisine = {
            "restaurant": "餐厅",
            "fast_food": "快餐",
            "cafe": "咖啡简餐",
            "food_court": "美食广场",
        }.get(tags.get("amenity"), "餐饮")
    # Only OSM field-survey tags count as source checking evidence.
    # Element edit timestamps and the date this snapshot was downloaded do not.
    checked = tags.get("survey:date") or tags.get("check_date") or ""
    try:
        if checked and dt.date.fromisoformat(checked) > dt.date.today():
            checked = ""
        elif checked:
            dt.date.fromisoformat(checked)
    except (TypeError, ValueError):
        checked = ""

    return {
        "external_id": "osm:{}:{}".format(kind, identifier),
        "name": name[:120],
        "district": district,
        "address": address[:200],
        "cuisine": cuisine[:100],
        "latitude": lat,
        "longitude": lon,
        "phone": (tags.get("contact:phone") or tags.get("phone") or "")[:40],
        "price_per_person": None,  # Never invent price.
        "opening_hours": (tags.get("opening_hours") or "")[:200] or None,
        "source_name": "OpenStreetMap",
        "source_url": "https://www.openstreetmap.org/{}/{}".format(kind, identifier),
        "source_checked_at": checked,
        "verified_at": "",  # OSM community data is NOT business verification.
        "verification_method": "",
        "status": "pending",
    }


def parse_overpass_payload(payload):
    """Deduplicate by OSM type+id; reject missing/invalid upstream responses."""
    if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
        raise ValueError("Overpass 返回数据格式不正确")
    results = {}
    for element in payload["elements"]:
        record = convert_osm_element(element)
        if record:
            results[record["external_id"]] = record
    if not results:
        raise ValueError("未找到可用的武汉商家记录，不写入空快照")
    return [results[key] for key in sorted(results)][:MAX_RECORDS]


def fetch_wuhan_osm():
    """Small, bounded Overpass queries. No continuous or aggressive scraping."""
    import time

    all_rows = {}
    errors = []
    for index, bbox in enumerate(SAMPLE_BBOXES, 1):
        form = urllib.parse.urlencode(
            {"data": overpass_query(bbox)}
        ).encode("utf-8")
        completed = False
        for endpoint in ENDPOINTS:
            request = urllib.request.Request(
                endpoint, data=form, method="POST",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "NightFindWuhanCatalog/1.1 (OSM ODbL snapshot)",
                    "Accept": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=40) as response:
                    raw = response.read(4_000_001)
                    if len(raw) > 4_000_000:
                        raise ValueError("单个分区响应超过 4 MB")
                    records = parse_overpass_payload(
                        json.loads(raw.decode("utf-8"))
                    )
                    for record in records:
                        all_rows[record["external_id"]] = record
                    print(
                        "区块 {}/{}：获取 {} 条开放地图餐饮场所".format(
                            index, len(SAMPLE_BBOXES), len(records)
                        ), flush=True,
                    )
                    completed = True
                    break
            except (urllib.error.URLError, TimeoutError, ValueError,
                    json.JSONDecodeError, OSError) as exc:
                errors.append("{}: {}".format(endpoint, exc))
        if not completed:
            print("区块 {}/{} 获取失败（未包含在快照中）".format(
                index, len(SAMPLE_BBOXES)
            ), flush=True)
        time.sleep(1)  # Gentle pacing for community infrastructure.

    if not all_rows:
        raise RuntimeError(
            "未能从公开接口获取餐饮记录；不会生成虚假快照。"
            + " 最近错误：" + (errors[-1] if errors else "无记录")
        )
    return [all_rows[key] for key in sorted(all_rows)][:MAX_RECORDS]


def hydrate_osm_snapshot(connection, path=SNAPSHOT):
    """Load a committed snapshot into SQLite once per file revision.

    This is safe on every startup and does not replace independently verified
    records. Existing demonstration restaurants remain in their original table.
    """
    path = Path(path)
    if not path.is_file():
        return 0
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    connection.execute("""
        CREATE TABLE IF NOT EXISTS catalog_import_state (
            source TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    current = connection.execute(
        "SELECT checksum FROM catalog_import_state WHERE source = 'osm_wuhan'"
    ).fetchone()
    if current is not None and current["checksum"] == digest:
        return 0
    rows = json.loads(payload.decode("utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("OSM 快照必须是非空 JSON 数组")
    result = import_real_merchants(connection, rows)
    connection.execute(
        "INSERT INTO catalog_import_state(source,checksum) VALUES ('osm_wuhan',?) "
        "ON CONFLICT(source) DO UPDATE SET "
        "checksum=excluded.checksum, imported_at=CURRENT_TIMESTAMP",
        (digest,),
    )
    return result["written"]


def main():
    parser = argparse.ArgumentParser(description="获取武汉 OSM 社区餐饮场所")
    parser.add_argument("action", choices=("fetch",))
    parser.add_argument("--output", type=Path, default=SNAPSHOT)
    args = parser.parse_args()
    rows = fetch_wuhan_osm()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("从武汉部分城市区块的 OpenStreetMap 获取 {} 条带名称餐饮场所。".format(len(rows)))
    print("注意：城市区块抽样并非全市完整覆盖；社区数据未核验，保留 ODbL 署名。")


if __name__ == "__main__":
    main()
