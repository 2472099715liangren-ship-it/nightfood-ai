"""Real Wuhan merchant catalog, separate from demonstration merchants.

Public web listings are attributed and marked unverified until checked in person.
Only recent source records are shown; prices and images retain their own sources.
"""
import csv
import datetime as dt
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

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
            price_range_min INTEGER,
            price_range_max INTEGER,
            price_range_basis TEXT NOT NULL DEFAULT 'unknown',
            opening_hours TEXT,
            source_name TEXT NOT NULL,
            source_url TEXT NOT NULL,
            verified_at TEXT,
            source_checked_at TEXT NOT NULL DEFAULT '',
            source_published_at TEXT NOT NULL DEFAULT '',
            signature_dishes TEXT NOT NULL DEFAULT '',
            location_note TEXT NOT NULL DEFAULT '',
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

        CREATE TABLE IF NOT EXISTS real_catalog_seed_state (
            file_name TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS real_merchant_geocode_cache (
            query TEXT PRIMARY KEY,
            latitude REAL,
            longitude REAL,
            display_name TEXT NOT NULL DEFAULT '',
            checked_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS real_merchant_menu_items (
            id INTEGER PRIMARY KEY,
            merchant_id INTEGER NOT NULL REFERENCES real_merchants(id) ON DELETE CASCADE,
            dish_name TEXT NOT NULL,
            price REAL,
            price_unit TEXT NOT NULL DEFAULT '元/份',
            price_source_url TEXT NOT NULL DEFAULT '',
            price_checked_at TEXT NOT NULL DEFAULT '',
            price_note TEXT NOT NULL DEFAULT '',
            UNIQUE(merchant_id, dish_name)
        );
        CREATE TABLE IF NOT EXISTS real_merchant_images (
            id INTEGER PRIMARY KEY,
            merchant_id INTEGER NOT NULL REFERENCES real_merchants(id) ON DELETE CASCADE,
            image_url TEXT NOT NULL,
            image_type TEXT NOT NULL DEFAULT 'dish_reference',
            caption TEXT NOT NULL DEFAULT '',
            taken_at TEXT NOT NULL DEFAULT '',
            author TEXT NOT NULL DEFAULT '',
            license TEXT NOT NULL DEFAULT '',
            license_url TEXT NOT NULL DEFAULT '',
            source_url TEXT NOT NULL DEFAULT '',
            UNIQUE(merchant_id, image_url)
        );
        CREATE INDEX IF NOT EXISTS idx_merchant_menu ON real_merchant_menu_items(merchant_id);
        CREATE INDEX IF NOT EXISTS idx_merchant_images ON real_merchant_images(merchant_id);
        CREATE TABLE IF NOT EXISTS real_merchant_photos (
            id INTEGER PRIMARY KEY,
            merchant_id INTEGER NOT NULL REFERENCES real_merchants(id) ON DELETE CASCADE,
            image_filename TEXT NOT NULL UNIQUE,
            taken_at TEXT NOT NULL,
            source_url TEXT NOT NULL,
            copyright_holder TEXT NOT NULL,
            license_note TEXT NOT NULL,
            permission_confirmed INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','verified','rejected')),
            verified_at TEXT,
            reviewed_by TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_merchant_photos
            ON real_merchant_photos(merchant_id,status);
    """)
    photo_columns = {
        item["name"] for item in connection.execute("PRAGMA table_info(real_merchant_photos)")
    }
    if "created_by" not in photo_columns:
        connection.execute(
            "ALTER TABLE real_merchant_photos ADD COLUMN created_by TEXT NOT NULL DEFAULT ''"
        )
    columns = {item["name"] for item in connection.execute("PRAGMA table_info(real_merchants)")}
    merchant_migrations = {
        "source_published_at": "TEXT NOT NULL DEFAULT ''",
        "signature_dishes": "TEXT NOT NULL DEFAULT ''",
        "location_note": "TEXT NOT NULL DEFAULT ''",
        "price_range_min": "INTEGER",
        "price_range_max": "INTEGER",
        "price_range_basis": "TEXT NOT NULL DEFAULT 'unknown'",
    }
    for name, definition in merchant_migrations.items():
        if name not in columns:
            connection.execute("ALTER TABLE real_merchants ADD COLUMN " + name + " " + definition)

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
    published_at = _clean(record.get("source_published_at"), 10)
    if published_at:
        try:
            dt.date.fromisoformat(published_at)
        except ValueError as error:
            raise ValueError("source_published_at 必须为 YYYY-MM-DD") from error
    item["source_published_at"] = published_at
    item["signature_dishes"] = _clean(record.get("signature_dishes"), 500)
    item["location_note"] = _clean(record.get("location_note"), 240)
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
    # A coordinate is a WGS84 latitude/longitude pair. A half-filled
    # pair would otherwise combine an imported value with a stale value
    # during UPSERT, producing a location that was never verified.
    if (item["latitude"] is None) != (item["longitude"] is None):
        raise ValueError("纬度和经度必须同时填写或同时留空")
    raw_price = record.get("price_per_person")
    try:
        item["price_per_person"] = int(raw_price) if raw_price not in ("", None) else None
    except (TypeError, ValueError) as exc:
        raise ValueError("人均价格必须为整数") from exc
    if item["price_per_person"] is not None and not 0 < item["price_per_person"] <= 2000:
        raise ValueError("人均价格超出允许范围")
    for field in ("price_range_min", "price_range_max"):
        raw_range = record.get(field)
        try:
            item[field] = int(raw_range) if raw_range not in ("", None) else None
        except (TypeError, ValueError) as error:
            raise ValueError(field + " 必须为整数") from error
        if item[field] is not None and not 0 < item[field] <= 2000:
            raise ValueError(field + " 超出允许范围")
    if (item["price_range_min"] is not None and item["price_range_max"] is not None
            and item["price_range_min"] > item["price_range_max"]):
        raise ValueError("人均价格区间上下限不合法")
    item["price_range_basis"] = _clean(record.get("price_range_basis")) or "unknown"
    if item["price_range_basis"] not in ("per_person", "dish", "unknown"):
        raise ValueError("价格区间口径必须为 per_person、dish 或 unknown")
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
        # A refresh must never undo a manual verification.
        if item["status"] == "pending":
            existing = connection.execute(
                "SELECT status FROM real_merchants WHERE external_id=?",
                (item["external_id"],),
            ).fetchone()
            if existing and existing["status"] == "verified":
                continue
        connection.execute("""
            INSERT INTO real_merchants (
                external_id,name,district,address,cuisine,latitude,longitude,
                phone,price_per_person,price_range_min,price_range_max,price_range_basis,
                opening_hours,source_name,source_url,verified_at,source_checked_at,
                source_published_at,signature_dishes,location_note,verification_method,status
            ) VALUES (
                :external_id,:name,:district,:address,:cuisine,:latitude,:longitude,
                :phone,:price_per_person,:price_range_min,:price_range_max,:price_range_basis,
                :opening_hours,:source_name,:source_url,:verified_at,:source_checked_at,
                :source_published_at,:signature_dishes,:location_note,:verification_method,:status
            )
            ON CONFLICT(external_id) DO UPDATE SET
                name=excluded.name, district=excluded.district,
                address=excluded.address, cuisine=excluded.cuisine,
                -- A CSV refresh must not erase coordinates added by a later
                -- address geocoding or manual review. Explicit new coordinates
                -- are allowed to replace existing values.
                latitude=COALESCE(excluded.latitude, real_merchants.latitude),
                longitude=COALESCE(excluded.longitude, real_merchants.longitude),
                phone=COALESCE(excluded.phone, real_merchants.phone),
                price_per_person=COALESCE(excluded.price_per_person, real_merchants.price_per_person),
                price_range_min=excluded.price_range_min,
                price_range_max=excluded.price_range_max,
                price_range_basis=excluded.price_range_basis,
                opening_hours=COALESCE(excluded.opening_hours, real_merchants.opening_hours),
                source_name=excluded.source_name,
                source_url=excluded.source_url, verified_at=excluded.verified_at,
                source_checked_at=excluded.source_checked_at,
                source_published_at=excluded.source_published_at,
                signature_dishes=excluded.signature_dishes,
                location_note=CASE WHEN excluded.location_note = ''
                    THEN real_merchants.location_note ELSE excluded.location_note END,
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
    """Expose only recent verified records or dated, attributed public listings."""
    return (
        "(source_checked_at >= ? AND ("
        "(status='verified' AND verified_at >= ?) OR "
        "(status='pending' AND source_name='OpenStreetMap' "
        "AND external_id LIKE 'osm:%') OR "
        "(status='pending' AND external_id LIKE 'web:%' "
        "AND source_name IN ('携程美食林','高德地图','武汉市商务局','武汉市文旅局',"
        "'武汉生活之窗','蔡林记官网','万豪官网','红厨帽') "
        "AND (source_published_at='' OR source_published_at >= ?))))"
    )


def public_real_merchants(connection, district="", keyword="", limit=100, offset=0):
    """Expose recent, attributed merchant listings; distinguish verification status."""
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    conditions = [_public_filter()]
    parameters = [_fresh_cutoff(), _fresh_cutoff(), _fresh_cutoff()]
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
        "WITH recent_images AS (SELECT * FROM real_merchant_images WHERE taken_at >= ?) "
        "SELECT id,name,district,address,cuisine,latitude,longitude,"
        "phone,price_per_person,price_range_min,price_range_max,price_range_basis,opening_hours,source_name,source_url,"
        "verified_at,source_checked_at,source_published_at,signature_dishes,location_note,"
        "verification_method,"
        "CASE WHEN status='verified' THEN 'verified' "
        "WHEN source_name='OpenStreetMap' THEN 'community' ELSE 'web_listing' END AS data_quality, "
        "(SELECT p.id FROM real_merchant_photos AS p "
        " WHERE p.merchant_id=real_merchants.id AND p.status='verified' "
        " AND p.permission_confirmed=1 AND p.taken_at >= ? "
        " AND substr(p.verified_at,1,10) >= ? ORDER BY p.id LIMIT 1) AS photo_id, "
        "(SELECT p.taken_at FROM real_merchant_photos AS p "
        " WHERE p.merchant_id=real_merchants.id AND p.status='verified' "
        " AND p.permission_confirmed=1 AND p.taken_at >= ? "
        " AND substr(p.verified_at,1,10) >= ? ORDER BY p.id LIMIT 1) AS photo_taken_at, "
        "(SELECT p.copyright_holder FROM real_merchant_photos AS p "
        " WHERE p.merchant_id=real_merchants.id AND p.status='verified' "
        " AND p.permission_confirmed=1 AND p.taken_at >= ? "
        " AND substr(p.verified_at,1,10) >= ? ORDER BY p.id LIMIT 1) AS photo_copyright_holder, "
        "(SELECT i.image_url FROM recent_images AS i "
        " WHERE i.merchant_id=real_merchants.id ORDER BY "
        "CASE i.image_type WHEN 'storefront' THEN 0 WHEN 'dish' THEN 1 ELSE 2 END,i.id LIMIT 1) AS cover_image_url, "
        "(SELECT i.image_type FROM recent_images AS i "
        " WHERE i.merchant_id=real_merchants.id ORDER BY "
        "CASE i.image_type WHEN 'storefront' THEN 0 WHEN 'dish' THEN 1 ELSE 2 END,i.id LIMIT 1) AS cover_image_type, "
        "(SELECT i.caption FROM recent_images AS i "
        " WHERE i.merchant_id=real_merchants.id ORDER BY "
        "CASE i.image_type WHEN 'storefront' THEN 0 WHEN 'dish' THEN 1 ELSE 2 END,i.id LIMIT 1) AS cover_image_caption, "
        "(SELECT i.author FROM recent_images AS i "
        " WHERE i.merchant_id=real_merchants.id ORDER BY "
        "CASE i.image_type WHEN 'storefront' THEN 0 WHEN 'dish' THEN 1 ELSE 2 END,i.id LIMIT 1) AS cover_image_author, "
        "(SELECT i.license FROM recent_images AS i "
        " WHERE i.merchant_id=real_merchants.id ORDER BY "
        "CASE i.image_type WHEN 'storefront' THEN 0 WHEN 'dish' THEN 1 ELSE 2 END,i.id LIMIT 1) AS cover_image_license, "
        "(SELECT i.license_url FROM recent_images AS i "
        " WHERE i.merchant_id=real_merchants.id ORDER BY "
        "CASE i.image_type WHEN 'storefront' THEN 0 WHEN 'dish' THEN 1 ELSE 2 END,i.id LIMIT 1) AS cover_image_license_url, "
        "(SELECT i.source_url FROM recent_images AS i "
        " WHERE i.merchant_id=real_merchants.id ORDER BY "
        "CASE i.image_type WHEN 'storefront' THEN 0 WHEN 'dish' THEN 1 ELSE 2 END,i.id LIMIT 1) AS cover_image_source_url, "
        "(SELECT i.taken_at FROM recent_images AS i "
        " WHERE i.merchant_id=real_merchants.id ORDER BY "
        "CASE i.image_type WHEN 'storefront' THEN 0 WHEN 'dish' THEN 1 ELSE 2 END,i.id LIMIT 1) AS cover_image_taken_at "
        "FROM real_merchants WHERE " + where + " ORDER BY updated_at DESC,id DESC "
        "LIMIT ? OFFSET ?", (
            [_fresh_cutoff()] + [_fresh_cutoff(), _fresh_cutoff()] * 3
            + parameters + [limit, offset]
        ),
    ).fetchall()
    items = []
    for row in results:
        item = dict(row)
        photo_id = item.pop("photo_id")
        item["photo_url"] = "/real-photo/{}".format(photo_id) if photo_id else None
        items.append(item)
    return {
        "items": items,
        "total": total,
        "notice": "公开网页收录不代表营业状态已人工核实；人均参考价与菜单价格可能变化，出行前请向商家确认。",
        "license": "© OpenStreetMap contributors · ODbL (www.openstreetmap.org/copyright)",
    }


def get_public_real_merchant(connection, merchant_id):
    """Return recent community/verified details without exposing rejected candidates."""
    boundary = _fresh_cutoff()
    row = connection.execute(
        "SELECT id,name,district,address,cuisine,latitude,longitude,phone,"
        "price_per_person,price_range_min,price_range_max,price_range_basis,opening_hours,source_name,source_url,verified_at,"
        "source_checked_at,source_published_at,signature_dishes,location_note,"
        "CASE WHEN status='verified' THEN 'verified' "
        "WHEN source_name='OpenStreetMap' THEN 'community' ELSE 'web_listing' END AS data_quality "
        "FROM real_merchants WHERE id=? AND " + _public_filter(),
        (merchant_id, boundary, boundary, boundary),
    ).fetchone()
    if row is None:
        return None
    data = dict(row)
    photos = connection.execute(
        """
        SELECT id,taken_at,copyright_holder,license_note,source_url
        FROM real_merchant_photos
        WHERE merchant_id=? AND status='verified' AND permission_confirmed=1
          AND taken_at >= ? AND substr(verified_at,1,10) >= ?
        ORDER BY id LIMIT 8
        """,
        (merchant_id, boundary, boundary),
    ).fetchall()
    data["photos"] = [
        {**dict(photo), "photo_url": "/real-photo/{}".format(photo["id"])}
        for photo in photos
    ]
    data["images"] = [
        dict(image) for image in connection.execute(
            "SELECT image_url,image_type,caption,taken_at,author,license,license_url,source_url "
            "FROM real_merchant_images WHERE merchant_id=? AND taken_at >= ? ORDER BY id",
            (merchant_id, boundary),
        )
    ]
    data["menu_items"] = [
        dict(item) for item in connection.execute(
            "SELECT dish_name,price,price_unit,price_source_url,price_checked_at,price_note "
            "FROM real_merchant_menu_items WHERE merchant_id=? AND price_checked_at >= ? ORDER BY id",
            (merchant_id, boundary),
        )
    ]
    return data


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
    web_total = connection.execute(
        "SELECT COUNT(*) FROM real_merchants WHERE " + _public_filter() +
        " AND status='pending' AND external_id LIKE 'web:%'",
        (_fresh_cutoff(), _fresh_cutoff(), _fresh_cutoff()),
    ).fetchone()[0]
    return {
        "city": "武汉市",
        "verified_total": sum(counts.values()),
        "community_total": community,
        "web_listing_total": web_total,
        "candidate_total": candidate_total,
        "freshness_cutoff": boundary,
        "districts": [{"name": key, "verified_count": value} for key, value in counts.items()],
        "notice": "公开网页目录按本次采集/核对日期筛选，不等于营业状态已人工确认；人均价仅供参考，单品价以门店菜单为准。未记录 OSM 逐店调查日期的候选不会公开。",
    }


def seed_bundled_catalog(connection, data_dir=None):
    """Load the checked-in Wuhan CSV files once, then only when a file changes."""
    data_dir = Path(data_dir) if data_dir else Path(__file__).resolve().parent / "data"
    files = {
        "wuhan_restaurants.csv": "merchants",
        "wuhan_menu_items.csv": "menu",
        "wuhan_restaurant_images.csv": "images",
    }
    totals = {"merchants": 0, "menu_items": 0, "images": 0}
    for file_name, kind in files.items():
        path = data_dir / file_name
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        saved = connection.execute(
            "SELECT sha256 FROM real_catalog_seed_state WHERE file_name=?",
            (file_name,),
        ).fetchone()
        if saved and saved["sha256"] == digest:
            continue

        records = read_import_file(path)
        if kind == "merchants":
            totals["merchants"] = import_real_merchants(connection, records)["written"]
        elif kind == "menu":
            for item in records:
                merchant = connection.execute(
                    "SELECT id FROM real_merchants WHERE external_id=?",
                    (_clean(item.get("external_id")),),
                ).fetchone()
                if merchant is None:
                    continue
                raw_price = _clean(item.get("price"), 30)
                try:
                    price = float(raw_price) if raw_price else None
                except ValueError as error:
                    raise ValueError("菜品价格必须为数字") from error
                if price is not None and not 0 < price <= 10000:
                    raise ValueError("菜品价格超出允许范围")
                checked_at = _clean(item.get("price_checked_at"), 10)
                if checked_at:
                    try:
                        checked = dt.date.fromisoformat(checked_at)
                    except ValueError as error:
                        raise ValueError("菜品价格核查日期必须为 YYYY-MM-DD") from error
                    if checked > dt.date.today() or checked.isoformat() < _fresh_cutoff():
                        raise ValueError("菜品价格资料必须在最近两年内")
                source_url = _clean(item.get("price_source_url"), 1000)
                if not re.match(r"^https://[^\s/]+\.[^\s/]+", source_url):
                    raise ValueError("菜品价格必须附带 HTTPS 来源")
                connection.execute(
                    """
                    INSERT INTO real_merchant_menu_items(
                        merchant_id,dish_name,price,price_unit,price_source_url,
                        price_checked_at,price_note
                    ) VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(merchant_id,dish_name) DO UPDATE SET
                        price=excluded.price,price_unit=excluded.price_unit,
                        price_source_url=excluded.price_source_url,
                        price_checked_at=excluded.price_checked_at,
                        price_note=excluded.price_note
                    """,
                    (
                        merchant["id"], _clean(item.get("dish_name"), 100),
                        price, _clean(item.get("price_unit"), 30) or "元/份",
                        source_url, checked_at, _clean(item.get("price_note"), 300),
                    ),
                )
                totals["menu_items"] += 1
        else:
            allowed_hosts = {"thumb.wikimedia.org", "upload.wikimedia.org", "commons.wikimedia.org"}
            allowed_licenses = {"CC BY 4.0", "CC BY-SA 4.0", "CC0 1.0"}
            for item in records:
                merchant = connection.execute(
                    "SELECT id FROM real_merchants WHERE external_id=?",
                    (_clean(item.get("external_id")),),
                ).fetchone()
                if merchant is None:
                    continue
                image_url = _clean(item.get("image_url"), 1500)
                source_url = _clean(item.get("source_url"), 1500)
                license_url = _clean(item.get("license_url"), 500)
                image_host = urlsplit(image_url).hostname
                if urlsplit(image_url).scheme != "https" or image_host not in allowed_hosts:
                    raise ValueError("图片必须来自已审核的 Wikimedia 图片域名")
                if not source_url.startswith("https://commons.wikimedia.org/wiki/File:"):
                    raise ValueError("图片必须附带 Wikimedia 原始文件页")
                license_name = _clean(item.get("license"), 40)
                if license_name not in allowed_licenses or not license_url.startswith("https://creativecommons.org/"):
                    raise ValueError("图片授权信息不完整或不受支持")
                taken_at = _clean(item.get("taken_at"), 10)
                try:
                    taken = dt.date.fromisoformat(taken_at)
                except ValueError as error:
                    raise ValueError("图片拍摄日期必须为 YYYY-MM-DD") from error
                if taken > dt.date.today() or taken.isoformat() < _fresh_cutoff():
                    raise ValueError("图片拍摄日期必须在最近两年内")
                image_type = _clean(item.get("image_type"), 30)
                if image_type not in ("storefront", "dish", "dish_reference"):
                    raise ValueError("图片类型不合法")
                if not _clean(item.get("author"), 100):
                    raise ValueError("图片必须注明作者")
                connection.execute(
                    """
                    INSERT INTO real_merchant_images(
                        merchant_id,image_url,image_type,caption,taken_at,
                        author,license,license_url,source_url
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(merchant_id,image_url) DO UPDATE SET
                        image_type=excluded.image_type,caption=excluded.caption,
                        taken_at=excluded.taken_at,author=excluded.author,
                        license=excluded.license,license_url=excluded.license_url,
                        source_url=excluded.source_url
                    """,
                    (
                        merchant["id"], image_url, image_type,
                        _clean(item.get("caption"), 240), taken_at,
                        _clean(item.get("author"), 100), license_name,
                        license_url, source_url,
                    ),
                )
                totals["images"] += 1

        connection.execute(
            """
            INSERT INTO real_catalog_seed_state(file_name,sha256)
            VALUES (?,?)
            ON CONFLICT(file_name) DO UPDATE SET
                sha256=excluded.sha256, imported_at=CURRENT_TIMESTAMP
            """,
            (file_name, digest),
        )
    return totals
