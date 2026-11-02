"""Verified-real-merchant catalog, separate from demonstration merchants.

Only explicitly verified records are public. Import is an offline CLI workflow,
not an unauthenticated HTTP endpoint. Source attribution and review timestamps
are mandatory for every published record.
"""
import csv
import datetime as dt
import json
import re
import sqlite3
from pathlib import Path

from database import connect

WUHAN_DISTRICTS = (
    "江岸区", "江汉区", "硚口区", "汉阳区", "武昌区", "青山区",
    "洪山区", "东西湖区", "蔡甸区", "江夏区", "黄陂区", "新洲区",
    "汉南区",
)
UNKNOWN_DISTRICT = "待确认区县"
VALID_STATUSES = ("draft", "pending", "verified", "rejected")
REQUIRED_COLUMNS = (
    "external_id", "name", "district", "address", "cuisine",
    "source_name", "source_url", "verified_at", "verification_method",
)


def initialize_real_catalog(connection):
    """Additive migration; original demo restaurants remain untouched."""
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS real_merchants (
            id INTEGER PRIMARY KEY,
            external_id TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            district TEXT NOT NULL,
            address TEXT NOT NULL,
            cuisine TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            phone TEXT,
            price_per_person INTEGER,
            opening_hours TEXT,
            source_name TEXT NOT NULL,
            source_url TEXT NOT NULL,
            verified_at TEXT,
            source_checked_at TEXT NOT NULL DEFAULT '',
            verification_method TEXT,
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK(status IN ('draft','pending','verified','rejected')),
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_real_merchants_district_status
            ON real_merchants(district,status);
        CREATE INDEX IF NOT EXISTS idx_real_merchants_name
            ON real_merchants(name);
    """)
    columns = {item["name"] for item in connection.execute("PRAGMA table_info(real_merchants)")}
    if "source_checked_at" not in columns:
        connection.execute(
            "ALTER TABLE real_merchants ADD COLUMN source_checked_at TEXT NOT NULL DEFAULT ''"
        )


def _clean(value, maximum=200):
    return str(value or "").strip()[:maximum]


def _validate(record):
    if not isinstance(record, dict):
        raise ValueError("每条记录必须为对象")
    item = {field: _clean(record.get(field)) for field in REQUIRED_COLUMNS}
    for key in ("external_id", "name", "district", "address", "cuisine", "source_name", "source_url"):
        if not item[key]:
            raise ValueError("缺少必填字段：" + key)
    if item["district"] not in WUHAN_DISTRICTS and item["district"] != UNKNOWN_DISTRICT:
        raise ValueError("行政区不属于武汉市：" + item["district"])
    if item["district"] == "待确认区县" and item["source_name"] != "OpenStreetMap":
        raise ValueError("待确认区县仅允许用于开放地图导入")
    url = item["source_url"]
    if not re.match(r"^https://[^\s/]+\.[^\s/]+", url):
        raise ValueError("来源链接必须为有效 HTTPS URL")
    checked_at = _clean(record.get("source_checked_at"), 10)
    if checked_at:
        try:
            checked = dt.date.fromisoformat(checked_at)
        except ValueError as error:
            raise ValueError("source_checked_at 必须为 YYYY-MM-DD") from error
        if checked > dt.date.today():
            raise ValueError("来源核验日期不能晚于今天")
    item["source_checked_at"] = checked_at
    verified_at = item["verified_at"]
    if verified_at:
        try:
            dt.date.fromisoformat(verified_at)
        except ValueError as exc:
            raise ValueError("verified_at 必须使用 YYYY-MM-DD") from exc
        if dt.date.fromisoformat(verified_at) > dt.date.today():
            raise ValueError("核验时间不能晚于今天")
    item["phone"] = _clean(record.get("phone"), 40) or None
    item["opening_hours"] = _clean(record.get("opening_hours"), 300) or None
    item["verification_method"] = _clean(item["verification_method"], 160) or None
    item["latitude"] = item["longitude"] = None
    for field, low, high in (("latitude", -90, 90), ("longitude", -180, 180)):
        raw = record.get(field)
        if raw not in (None, ""):
            try:
                val = float(raw)
            except (ValueError, TypeError) as exc:
                raise ValueError(field + " 必须为数字") from exc
            if not low <= val <= high:
                raise ValueError(field + " 超出合法范围")
            item[field] = val
    raw_price = record.get("price_per_person")
    try:
        item["price_per_person"] = int(raw_price) if raw_price not in ("", None) else None
    except (TypeError, ValueError) as exc:
        raise ValueError("人均价格必须为整数") from exc
    if item["price_per_person"] is not None and not 0 < item["price_per_person"] <= 2000:
        raise ValueError("人均价格超出允许范围")
    status = _clean(record.get("status", "pending")) or "pending"
    if status not in VALID_STATUSES:
        raise ValueError("status 不合法")
    if status == "verified":
        if not verified_at or not item["verification_method"]:
            raise ValueError("发布真实商家前必须填写核验日期和核验方式")
        if not checked_at:
            raise ValueError("已核验门店需要单独的来源核查日期")
        boundary = _fresh_cutoff()
        if checked_at < boundary or verified_at < boundary:
            raise ValueError("餐厅资料或人工核验超过两年，不能公开")
    item["status"] = status
    return item


def import_real_merchants(connection, records, dry_run=False):
    """Validate entire batch before writing. Upsert by provider external_id."""
    prepared = [_validate(record) for record in records]
    if len({row["external_id"] for row in prepared}) != len(prepared):
        raise ValueError("同一批次 external_id 不能重复")
    if dry_run:
        return {"validated": len(prepared), "written": 0}
    for item in prepared:
        # Do not downgrade independently verified records when refreshing OSM.
        if item["source_name"] == "OpenStreetMap" and item["status"] == "pending":
            existing = connection.execute(
                "SELECT status FROM real_merchants WHERE external_id=?",
                (item["external_id"],),
            ).fetchone()
            if existing and existing["status"] == "verified":
                continue
        connection.execute("""
            INSERT INTO real_merchants (
                external_id,name,district,address,cuisine,latitude,longitude,
                phone,price_per_person,opening_hours,source_name,source_url,
                verified_at,source_checked_at,verification_method,status
            ) VALUES (
                :external_id,:name,:district,:address,:cuisine,:latitude,:longitude,
                :phone,:price_per_person,:opening_hours,:source_name,:source_url,
                :verified_at,:source_checked_at,:verification_method,:status
            )
            ON CONFLICT(external_id) DO UPDATE SET
                name=excluded.name, district=excluded.district,
                address=excluded.address, cuisine=excluded.cuisine,
                latitude=excluded.latitude, longitude=excluded.longitude,
                phone=excluded.phone, price_per_person=excluded.price_per_person,
                opening_hours=excluded.opening_hours, source_name=excluded.source_name,
                source_url=excluded.source_url, verified_at=excluded.verified_at,
                source_checked_at=excluded.source_checked_at,
                verification_method=excluded.verification_method,
                status=excluded.status, updated_at=CURRENT_TIMESTAMP
        """, item)
    return {"validated": len(prepared), "written": len(prepared)}


def read_import_file(path):
    """Read UTF-8 CSV or JSON file; never fetch arbitrary URLs or scrape sites."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ValueError("导入文件不存在")
    if file_path.stat().st_size > 5_000_000:
        raise ValueError("单次导入文件不得超过 5 MB")
    if file_path.suffix.lower() == ".csv":
        with file_path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    if file_path.suffix.lower() == ".json":
        with file_path.open(encoding="utf-8-sig") as handle:
            values = json.load(handle)
        if not isinstance(values, list):
            raise ValueError("JSON 顶层必须为数组")
        return values
    raise ValueError("仅支持 CSV 或 JSON")


def _fresh_cutoff(reference=None):
    """Two calendar years ago, inclusive; leap-day safe."""
    current = reference or dt.date.today()
    try:
        return current.replace(year=current.year - 2).isoformat()
    except ValueError:
        return current.replace(year=current.year - 2, day=28).isoformat()


def _public_filter():
    """Only OSM entries with recent survey dates or recently verified businesses."""
    return (
        "(source_checked_at >= ? AND ("
        "(status='verified' AND verified_at >= ?) OR "
        "(status='pending' AND source_name='OpenStreetMap' "
        "AND external_id LIKE 'osm:%')))"
    )


def public_real_merchants(connection, district="", keyword="", limit=100, offset=0):
    """Expose independently verified or attributed OSM community entries only."""
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    conditions = [_public_filter()]
    parameters = [_fresh_cutoff(), _fresh_cutoff()]
    if district:
        if district not in WUHAN_DISTRICTS:
            return {"items": [], "total": 0}
        conditions.append("district = ?")
        parameters.append(district)
    if keyword:
        conditions.append("(name LIKE ? ESCAPE '\\' OR address LIKE ? ESCAPE '\\' OR cuisine LIKE ? ESCAPE '\\')")
        term = "%" + keyword[:80].replace("%", r"\%").replace("_", r"\_") + "%"
        parameters.extend([term] * 3)
    where = " AND ".join(conditions)
    total = connection.execute(
        "SELECT COUNT(*) FROM real_merchants WHERE " + where, parameters
    ).fetchone()[0]
    results = connection.execute(
        "SELECT id,name,district,address,cuisine,latitude,longitude,"
        "phone,price_per_person,opening_hours,source_name,source_url,"
        "verified_at,source_checked_at,verification_method,"
        "CASE WHEN status='verified' THEN 'verified' ELSE 'community' END AS data_quality "
        "FROM real_merchants WHERE " + where + " ORDER BY updated_at DESC,id DESC "
        "LIMIT ? OFFSET ?", parameters + [limit, offset],
    ).fetchall()
    return {
        "items": [dict(row) for row in results],
        "total": total,
        "notice": "OSM 社区收录不代表已人工核实；营业状态和地址请向商家确认。",
        "license": "© OpenStreetMap contributors · ODbL (www.openstreetmap.org/copyright)",
    }


def catalog_coverage(connection):
    """Count independently verified and community-mapped records separately."""
    counts = {row: 0 for row in WUHAN_DISTRICTS}
    boundary = _fresh_cutoff()
    for item in connection.execute(
        "SELECT district,COUNT(*) AS n FROM real_merchants "
        "WHERE status='verified' AND verified_at >= ? AND source_checked_at >= ? "
        "GROUP BY district", (boundary, boundary)
    ):
        counts[item["district"]] = item["n"]
    community = connection.execute(
        "SELECT COUNT(*) FROM real_merchants WHERE status='pending' "
        "AND source_name='OpenStreetMap' AND external_id LIKE 'osm:%' "
        "AND source_checked_at >= ?", (boundary,)
    ).fetchone()[0]
    candidate_total = connection.execute(
        "SELECT COUNT(*) FROM real_merchants WHERE status='pending' "
        "AND source_name='OpenStreetMap' AND external_id LIKE 'osm:%'"
    ).fetchone()[0]
    return {
        "city": "武汉市",
        "verified_total": sum(counts.values()),
        "community_total": community,
        "candidate_total": candidate_total,
        "freshness_cutoff": boundary,
        "districts": [{"name": key, "verified_count": value} for key, value in counts.items()],
        "notice": "仅公开最近两年有来源逐店核查日期的资料；没有日期的 OSM 候选暂不展示，不能按快照下载日当作现场核验日期。",
    }
