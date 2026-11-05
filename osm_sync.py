"""Fetch Wuhan food venues from the ODbL-licensed OpenStreetMap Overpass API.

Usage (network required):
    python3 osm_sync.py fetch --output data_sources/osm_wuhan_snapshot.json

The generated snapshot contains OSM community entries, not independently
verified businesses. It must be distributed with OpenStreetMap attribution.
"""

import argparse
import os
import hashlib
import json
import datetime as dt
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from real_catalog import (
    UNKNOWN_DISTRICT,
    WUHAN_DISTRICTS,
    import_real_merchants,
    validate_real_merchants,
)

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT / "data_sources" / "osm_wuhan_snapshot.json"
LIVE_SNAPSHOT = ROOT / "data_sources" / "wuhan_live_catalog.json"
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
        "[name]({},{},{},{}););out meta center;".format(south, west, north, east)
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
    if (
        not name
        or not isinstance(lat, (int, float))
        or not isinstance(lon, (int, float))
    ):
        return None
    # Safety bound in addition to the actual administrative-area query.
    if not (29.9 <= lat <= 31.5 and 113.5 <= lon <= 115.2):
        return None
    district = tags.get("addr:district") or tags.get("is_in:district") or ""
    if district not in WUHAN_DISTRICTS:
        district = UNKNOWN_DISTRICT

    street = (tags.get("addr:street") or "").strip()
    number = (tags.get("addr:housenumber") or "").strip()
    address = (
        "武汉市" + (district if district != UNKNOWN_DISTRICT else "") + street + number
        if street
        else ""
    )
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
        "source_updated_at": str(element.get("timestamp", ""))[:10],
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
        form = urllib.parse.urlencode({"data": overpass_query(bbox)}).encode("utf-8")
        completed = False
        for endpoint in ENDPOINTS:
            request = urllib.request.Request(
                endpoint,
                data=form,
                method="POST",
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
                    records = parse_overpass_payload(json.loads(raw.decode("utf-8")))
                    for record in records:
                        record["evidence_url"] = endpoint
                        record["source_collected_at"] = dt.date.today().isoformat()
                        all_rows[record["external_id"]] = record
                    print(
                        "区块 {}/{}：获取 {} 条开放地图餐饮场所".format(
                            index, len(SAMPLE_BBOXES), len(records)
                        ),
                        flush=True,
                    )
                    completed = True
                    break
            except (
                urllib.error.URLError,
                TimeoutError,
                ValueError,
                json.JSONDecodeError,
                OSError,
            ) as exc:
                errors.append("{}: {}".format(endpoint, exc))
        if not completed:
            print(
                "区块 {}/{} 获取失败（未包含在快照中）".format(
                    index, len(SAMPLE_BBOXES)
                ),
                flush=True,
            )
        time.sleep(1)  # Gentle pacing for community infrastructure.

    if not all_rows:
        raise RuntimeError(
            "未能从公开接口获取餐饮记录；不会生成虚假快照。"
            + " 最近错误："
            + (errors[-1] if errors else "无记录")
        )
    return [all_rows[key] for key in sorted(all_rows)][:MAX_RECORDS]


def read_snapshot(path):
    """Load source rows and verified batch provenance without inventing survey dates."""
    path = Path(path)
    payload = path.read_bytes()
    decoded = json.loads(payload.decode("utf-8"))
    metadata_bytes = b""
    if isinstance(decoded, dict):
        metadata = decoded.get("metadata", {})
        rows = decoded.get("records")
        if not isinstance(rows, list):
            raise ValueError("快照 records 必须为数组")
        evidence = json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()
    else:
        rows = decoded
        meta_path = path.with_suffix(".meta.json")
        metadata_bytes = meta_path.read_bytes() if meta_path.is_file() else b""
        metadata = json.loads(metadata_bytes) if metadata_bytes else {}
        evidence = payload
    if not isinstance(rows, list) or not rows:
        raise ValueError("OSM 快照必须包含实际来源记录")
    if metadata:
        if metadata.get("sha256") != hashlib.sha256(evidence).hexdigest():
            raise ValueError("OSM 快照与来源清单的 SHA-256 不一致")
        if metadata.get("record_count") != len(rows):
            raise ValueError("OSM 快照条数与清单不一致")
        kind = metadata.get("kind")
        if kind not in ("repository_archive", "live_osm"):
            raise ValueError("不支持的 OSM 来源证据类型")
        if not str(metadata.get("evidence_url", "")).startswith("https://"):
            raise ValueError("OSM 快照缺少 HTTPS 来源证据")
        field = (
            "source_archived_at"
            if kind == "repository_archive"
            else "source_collected_at"
        )
        date = metadata.get(
            "archived_at" if kind == "repository_archive" else "collected_at", ""
        )
        from catalog_policy import clean_date

        if not clean_date(date, field):
            raise ValueError("快照需要记录真实的采集或归档日期")
        rows = [
            dict(
                row,
                **{field: date},
                evidence_url=(row.get("evidence_url") if kind == "live_osm" else None)
                or metadata["evidence_url"],
            )
            for row in rows
        ]
    # Preserve the meaning of an absent survey date without substituting a batch date.
    rows = [
        dict(row, source_checked_at=row.get("source_checked_at", "")) for row in rows
    ]
    return rows, hashlib.sha256(payload + metadata_bytes).hexdigest()


def hydrate_osm_snapshot(connection, path=None):
    """Use a new live collection when present; otherwise retain the attributed archive."""
    path = (
        Path(path)
        if path is not None
        else (LIVE_SNAPSHOT if LIVE_SNAPSHOT.is_file() else SNAPSHOT)
    )
    if not path.is_file():
        return 0
    rows, digest = read_snapshot(path)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_import_state (
            source TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            imported_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    current = connection.execute(
        "SELECT checksum FROM catalog_import_state WHERE source = 'osm_wuhan'"
    ).fetchone()
    if current is not None and current["checksum"] == digest:
        return 0
    result = import_real_merchants(connection, rows)
    connection.execute(
        "INSERT INTO catalog_import_state(source,checksum) VALUES ('osm_wuhan',?) "
        "ON CONFLICT(source) DO UPDATE SET checksum=excluded.checksum, imported_at=CURRENT_TIMESTAMP",
        (digest,),
    )
    return result["written"]


def collect_live_snapshot(output=LIVE_SNAPSHOT, minimum=100):
    """Fetch first, validate first; a failed collection never replaces a good file."""
    from catalog_policy import catalog_cutoff

    rows = fetch_wuhan_osm()
    today = dt.date.today().isoformat()
    # A successful live response proves online collection, not operating status.
    rows = [
        row
        for row in rows
        if not row.get("source_updated_at")
        or row["source_updated_at"] >= catalog_cutoff()
    ]
    rows = validate_real_merchants(
        [
            dict(
                row,
                source_collected_at=today,
                evidence_url=row.get("evidence_url") or ENDPOINTS[0],
            )
            for row in rows
        ]
    )
    if len(rows) < minimum:
        raise ValueError(
            "实际获取的近五年来源记录只有 {} 条，未达到 {} 条；保留已有数据".format(
                len(rows), minimum
            )
        )
    metadata = dict(
        schema_version=1,
        kind="live_osm",
        collected_at=today,
        record_count=len(rows),
        license="ODbL-1.0",
        evidence_url=rows[0]["evidence_url"],
        sha256=hashlib.sha256(
            json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
        notice="日期为在线采集时间，元素更新和逐店调查日期单独保留；当前营业及价格需核实。",
    )
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(metadata=metadata, records=rows), ensure_ascii=False, indent=2)
        + "\n", encoding="utf-8"
    )
    os.replace(temporary, output)
    return dict(
        merchants=len(rows),
        mapped=len(rows),
        output=str(output),
        menu_prices="OSM 未提供的菜品价格不补造，需从可核验门店菜单另行补充",
    )


def main():
    parser = argparse.ArgumentParser(
        description="采集近五年武汉公开地图门店，保留来源和真实坐标"
    )
    parser.add_argument("action", choices=("fetch",))
    parser.add_argument("--output", type=Path, default=LIVE_SNAPSHOT)
    parser.add_argument("--minimum", type=int, default=100)
    args = parser.parse_args()
    if not 100 <= args.minimum <= MAX_RECORDS:
        parser.error("minimum 必须在 100–{} 之间".format(MAX_RECORDS))
    print(
        json.dumps(
            collect_live_snapshot(args.output, args.minimum),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
