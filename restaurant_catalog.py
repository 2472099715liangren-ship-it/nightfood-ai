"""Verified real-restaurant catalog and controlled CSV ingestion.

No third-party scraper is included. A source must be registered with documented
storage/display rights before its records can enter the catalog. New rows remain
pending until a human reviewer approves them.
"""
import csv
import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


ADMINISTRATIVE_DISTRICTS = {
    "江岸区", "江汉区", "硚口区", "汉阳区", "武昌区", "青山区",
    "洪山区", "蔡甸区", "江夏区", "黄陂区", "新洲区", "东西湖区", "汉南区",
}
ALLOWED_BUSINESS_STATUS = {"unknown", "open", "closed", "temporarily_closed"}
RESTAURANT_FIELDS = (
    "name", "branch_name", "district", "business_area", "address",
    "latitude", "longitude", "phone", "website", "cuisine",
    "price_per_person", "business_status", "description", "source_url",
    "source_updated_at",
)
URL_SCHEMES = {"http", "https"}


class CatalogValidationError(ValueError):
    """A row is incomplete, inconsistent, or outside the supported schema."""


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalise(value):
    value = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", "", value).casefold()


def _valid_url(value, allow_submission_reference=False):
    value = str(value or "").strip()
    if allow_submission_reference and value.startswith("merchant-submission:"):
        return True
    parsed = urlparse(value)
    return parsed.scheme in URL_SCHEMES and bool(parsed.netloc)


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def register_source(
    connection,
    source_code,
    source_name,
    source_type,
    source_homepage,
    terms_url,
    license_note,
    approved_by,
    rights_confirmed=False,
):
    """Register a data source only after the operator explicitly confirms rights."""
    code = str(source_code or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_-]{2,47}", code):
        raise CatalogValidationError("来源编号需为 3–48 位小写字母、数字或连字符")
    if not str(source_name or "").strip() or not str(license_note or "").strip():
        raise CatalogValidationError("来源名称和授权/许可说明不能为空")
    if not rights_confirmed:
        raise CatalogValidationError(
            "尚未确认数据存储与展示权利；请完成授权核验后再使用 --rights-confirmed"
        )
    if source_homepage and not _valid_url(source_homepage):
        raise CatalogValidationError("来源主页必须是有效的 http/https 地址")
    if terms_url and not _valid_url(terms_url):
        raise CatalogValidationError("许可条款地址必须是有效的 http/https 地址")
    if source_type not in {
        "merchant_submission", "authorized_public_data",
        "licensed_provider", "manual_research",
    }:
        raise CatalogValidationError("不支持的来源类型")

    connection.execute(
        """
        INSERT INTO restaurant_sources (
            source_code, source_name, source_type, source_homepage,
            terms_url, license_note, permission_status, approved_by, approved_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'approved', ?, ?)
        """,
        (
            code, str(source_name).strip(), source_type,
            str(source_homepage or "").strip(), str(terms_url or "").strip(),
            str(license_note).strip(), str(approved_by or "operator").strip(),
            _now(),
        ),
    )
    return connection.execute(
        "SELECT id, source_code, source_name, permission_status "
        "FROM restaurant_sources WHERE source_code = ?",
        (code,),
    ).fetchone()


def _optional_float(value, label, minimum, maximum):
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise CatalogValidationError("{}必须是数字".format(label)) from error
    if not minimum <= number <= maximum:
        raise CatalogValidationError("{}超出武汉市合理坐标范围".format(label))
    return number


def _optional_int(value, label, minimum, maximum):
    if value is None or str(value).strip() == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise CatalogValidationError("{}必须是整数".format(label)) from error
    if not minimum <= number <= maximum:
        raise CatalogValidationError("{}范围为 {}–{}".format(label, minimum, maximum))
    return number


def validate_restaurant_row(row, allowed_districts):
    """Return a clean row or raise a field-specific validation error."""
    clean = {
        field: str(row.get(field, "") or "").strip()
        for field in RESTAURANT_FIELDS
        if field not in {"latitude", "longitude", "price_per_person"}
    }
    clean["business_status"] = clean["business_status"] or "unknown"
    clean["external_id"] = str(row.get("external_id", "") or "").strip()
    if not clean["name"] or len(clean["name"]) > 120:
        raise CatalogValidationError("餐厅名称不能为空且最多 120 个字符")
    if clean["district"] not in allowed_districts:
        raise CatalogValidationError("行政区不在武汉 13 个区的范围内")
    if not clean["address"] or len(clean["address"]) > 300:
        raise CatalogValidationError("真实门店地址不能为空且最多 300 个字符")
    if not _valid_url(clean["source_url"], allow_submission_reference=True):
        raise CatalogValidationError(
            "每条记录都需要可追溯的来源网址或 merchant-submission: 提交编号"
        )
    if clean["website"] and not _valid_url(clean["website"]):
        raise CatalogValidationError("商家网站必须是有效的 http/https 地址")
    if clean["business_status"] not in ALLOWED_BUSINESS_STATUS:
        raise CatalogValidationError(
            "营业状态只能是 unknown/open/closed/temporarily_closed"
        )
    if clean["source_updated_at"]:
        try:
            datetime.fromisoformat(clean["source_updated_at"].replace("Z", "+00:00"))
        except ValueError as error:
            raise CatalogValidationError("source_updated_at 必须使用 ISO 日期时间") from error

    clean["latitude"] = _optional_float(row.get("latitude"), "纬度", 29.8, 31.5)
    clean["longitude"] = _optional_float(row.get("longitude"), "经度", 113.5, 115.2)
    clean["price_per_person"] = _optional_int(
        row.get("price_per_person"), "人均价格", 1, 5000
    )
    if bool(clean["latitude"] is None) != bool(clean["longitude"] is None):
        raise CatalogValidationError("经纬度需要同时填写，或同时留空")
    if clean["external_id"] and len(clean["external_id"]) > 160:
        raise CatalogValidationError("external_id 最多 160 个字符")
    if not clean["external_id"]:
        fingerprint = _normalise(clean["name"]) + "|" + _normalise(clean["address"])
        clean["external_id"] = hashlib.sha256(
            fingerprint.encode("utf-8")
        ).hexdigest()[:32]
    return clean


def read_csv(path, allowed_districts):
    """Read UTF-8 CSV and return validated rows plus row-specific errors."""
    rows = []
    errors = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"name", "district", "address", "source_url"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise CatalogValidationError(
                "CSV 缺少必需列：" + "、".join(sorted(missing))
            )
        for row_number, raw in enumerate(reader, start=2):
            if not any(str(value or "").strip() for value in raw.values()):
                continue
            try:
                rows.append((row_number, validate_restaurant_row(raw, allowed_districts)))
            except CatalogValidationError as error:
                errors.append({
                    "row_number": row_number,
                    "external_id": str(raw.get("external_id", "") or "")[:160],
                    "error_code": "invalid_row",
                    "detail": str(error),
                })
    return rows, errors


def _possible_duplicates(connection, clean, exclude_id=None):
    candidates = connection.execute(
        """
        SELECT id, name, address FROM real_restaurants
        WHERE district = ? AND record_status != 'rejected'
        """,
        (clean["district"],),
    ).fetchall()
    name_key = _normalise(clean["name"])
    address_key = _normalise(clean["address"])
    return [
        row["id"] for row in candidates
        if row["id"] != exclude_id
        and _normalise(row["name"]) == name_key
        and _normalise(row["address"]) == address_key
    ]


def import_rows(
    connection, source_code, rows, errors, file_name, checksum, imported_by=""
):
    """Store valid rows as pending; exact cross-source duplicates need review."""
    source = connection.execute(
        """
        SELECT id, permission_status FROM restaurant_sources
        WHERE source_code = ?
        """,
        (source_code,),
    ).fetchone()
    if source is None:
        raise CatalogValidationError("数据来源尚未登记")
    if source["permission_status"] != "approved":
        raise CatalogValidationError("该来源未获准存储/展示，不能导入")

    connection.execute(
        """
        INSERT INTO restaurant_import_batches (
            source_id, file_name, file_sha256, imported_by, total_rows
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            source["id"], Path(file_name).name, checksum, imported_by,
            len(rows) + len(errors),
        ),
    )
    batch_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    inserted = updated = review = 0

    for error in errors:
        connection.execute(
            """
            INSERT INTO restaurant_import_errors (
                batch_id, row_number, external_id, error_code, detail
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                batch_id, error["row_number"], error["external_id"],
                error["error_code"], error["detail"],
            ),
        )

    fields = list(RESTAURANT_FIELDS)
    columns = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    update_fields = ", ".join(
        field + " = excluded." + field for field in fields if field != "external_id"
    )
    for row_number, clean in rows:
        existing = connection.execute(
            """
            SELECT id, record_status, name, branch_name, district, business_area,
                   address, latitude, longitude, phone, website, cuisine,
                   price_per_person, business_status, description, source_url,
                   source_updated_at
            FROM real_restaurants WHERE source_id = ? AND external_id = ?
            """,
            (source["id"], clean["external_id"]),
        ).fetchone()
        duplicates = _possible_duplicates(
            connection, clean, existing["id"] if existing else None
        )
        changed = existing is None or any(
            str(existing[field] if existing[field] is not None else "") !=
            str(clean[field] if clean[field] is not None else "")
            for field in fields
        )
        status = (
            "needs_review" if duplicates
            else "pending" if changed or existing is None
            else existing["record_status"]
        )
        values = [clean[field] for field in fields]
        if existing is None:
            connection.execute(
                """
                INSERT INTO real_restaurants (
                    source_id, external_id, """ + columns + """,
                    record_status, last_seen_at
                ) VALUES (?, ?, """ + placeholders + """, ?, CURRENT_TIMESTAMP)
                """,
                [source["id"], clean["external_id"]] + values + [status],
            )
            inserted += 1
            restaurant_id = connection.execute(
                "SELECT last_insert_rowid()"
            ).fetchone()[0]
        else:
            restaurant_id = existing["id"]
            for field in fields:
                old_value = str(existing[field] if existing[field] is not None else "")
                new_value = str(clean[field] if clean[field] is not None else "")
                if old_value != new_value:
                    connection.execute(
                        """
                        INSERT INTO restaurant_change_log (
                            restaurant_id, source_id, field_name, old_value, new_value
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (restaurant_id, source["id"], field, old_value, new_value),
                    )
            connection.execute(
                """
                UPDATE real_restaurants SET """ + update_fields + """,
                    record_status = ?, last_seen_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                values + [status, restaurant_id],
            )
            updated += 1
        if duplicates:
            review += 1
            connection.execute(
                """
                UPDATE real_restaurants
                SET verification_note = ?
                WHERE id = ?
                """,
                ("可能与门店记录 {} 重复，需人工确认".format(
                    ",".join(str(value) for value in duplicates)
                ), restaurant_id),
            )

    connection.execute(
        """
        UPDATE restaurant_import_batches
        SET inserted_rows = ?, updated_rows = ?, review_rows = ?, error_rows = ?
        WHERE id = ?
        """,
        (inserted, updated, review, len(errors), batch_id),
    )
    return {
        "batch_id": batch_id,
        "total_rows": len(rows) + len(errors),
        "inserted_rows": inserted,
        "updated_rows": updated,
        "review_rows": review,
        "error_rows": len(errors),
    }


def review_queue(connection, limit=100):
    return [
        dict(row) for row in connection.execute(
            """
            SELECT r.id, r.name, r.district, r.address, r.business_area,
                   r.source_url, r.record_status, r.verification_note,
                   s.source_name, s.permission_status
            FROM real_restaurants AS r
            JOIN restaurant_sources AS s ON s.id = r.source_id
            WHERE r.record_status IN ('pending', 'needs_review')
            ORDER BY CASE r.record_status WHEN 'needs_review' THEN 0 ELSE 1 END,
                     r.created_at, r.id
            LIMIT ?
            """,
            (max(1, min(int(limit), 500)),),
        )
    ]


def set_review_status(connection, restaurant_ids, status, reviewed_by, note=""):
    """Human approval is the only path from pending to public verified data."""
    if status not in {"verified", "rejected"}:
        raise CatalogValidationError("审核状态只能是 verified 或 rejected")
    if not str(reviewed_by or "").strip():
        raise CatalogValidationError("审核人不能为空")
    changed = 0
    for restaurant_id in restaurant_ids:
        row = connection.execute(
            """
            SELECT r.*, s.permission_status FROM real_restaurants AS r
            JOIN restaurant_sources AS s ON s.id = r.source_id
            WHERE r.id = ?
            """,
            (restaurant_id,),
        ).fetchone()
        if row is None:
            raise CatalogValidationError("找不到真实餐厅记录：{}".format(restaurant_id))
        if status == "verified":
            if row["permission_status"] != "approved":
                raise CatalogValidationError("数据来源许可已暂停，不能公开")
            if not row["name"] or not row["district"] or not row["address"] or not row["source_url"]:
                raise CatalogValidationError("名称、行政区、门店地址和来源凭证均为必需")
        connection.execute(
            """
            UPDATE real_restaurants
            SET record_status = ?, verification_method = 'manual',
                verification_note = ?, verified_by = ?, verified_at = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                status, str(note or "").strip(), str(reviewed_by).strip(),
                _now() if status == "verified" else None, restaurant_id,
            ),
        )
        changed += 1
    return changed


def list_real_restaurants(
    connection, keyword="", district="", cuisine="", max_price=None, limit=100
):
    """Public listing: verified records from currently approved sources only."""
    conditions = [
        "r.record_status = 'verified'",
        "s.permission_status = 'approved'",
    ]
    parameters = []
    if keyword:
        pattern = "%" + str(keyword).strip()[:80] + "%"
        conditions.append("(r.name LIKE ? OR r.cuisine LIKE ? OR r.address LIKE ?)")
        parameters.extend([pattern, pattern, pattern])
    if district:
        conditions.append("r.district = ?")
        parameters.append(district)
    if cuisine:
        conditions.append("r.cuisine = ?")
        parameters.append(cuisine)
    if max_price not in (None, ""):
        conditions.append("(r.price_per_person IS NOT NULL AND r.price_per_person <= ?)")
        parameters.append(max_price)
    parameters.append(max(1, min(int(limit), 200)))
    rows = connection.execute(
        """
        SELECT r.id, r.name, r.branch_name, r.district, r.business_area,
               r.address, r.latitude, r.longitude, r.phone, r.website,
               r.cuisine, r.price_per_person, r.business_status,
               r.description, r.source_url, r.source_updated_at, r.verified_at,
               s.source_name
        FROM real_restaurants AS r
        JOIN restaurant_sources AS s ON s.id = r.source_id
        WHERE """ + " AND ".join(conditions) + """
        ORDER BY r.district, r.name LIMIT ?
        """,
        parameters,
    ).fetchall()
    return [dict(row) for row in rows]


def get_real_restaurant(connection, restaurant_id):
    row = connection.execute(
        """
        SELECT r.*, s.source_name, s.source_homepage, s.terms_url
        FROM real_restaurants AS r
        JOIN restaurant_sources AS s ON s.id = r.source_id
        WHERE r.id = ? AND r.record_status = 'verified'
          AND s.permission_status = 'approved'
        """,
        (restaurant_id,),
    ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["hours"] = [
        dict(item) for item in connection.execute(
            """
            SELECT weekday, opens_at, closes_at, is_closed, note
            FROM real_restaurant_hours
            WHERE restaurant_id = ? ORDER BY weekday
            """,
            (restaurant_id,),
        )
    ]
    result["dishes"] = [
        dict(item) for item in connection.execute(
            """
            SELECT name, price FROM real_restaurant_dishes
            WHERE restaurant_id = ? AND record_status = 'verified'
            ORDER BY name
            """,
            (restaurant_id,),
        )
    ]
    return result


def public_catalog_summary(connection):
    rows = connection.execute(
        """
        SELECT a.name AS district, COUNT(r.id) AS verified_count
        FROM wuhan_areas AS a
        LEFT JOIN real_restaurants AS r
          ON r.district = a.name AND r.record_status = 'verified'
          AND EXISTS (
              SELECT 1 FROM restaurant_sources AS s
              WHERE s.id = r.source_id AND s.permission_status = 'approved'
          )
        WHERE a.area_type = 'administrative_district'
        GROUP BY a.id, a.name, a.sort_order
        ORDER BY a.sort_order
        """
    ).fetchall()
    total = sum(row["verified_count"] for row in rows)
    return {
        "total_verified": total,
        "districts": [dict(row) for row in rows],
        "notice": "仅统计来源许可有效且经人工核验的真实门店；未核验资料不会出现在公开目录。",
    }


def list_wuhan_areas(connection):
    return [
        dict(row) for row in connection.execute(
            """
            SELECT name, area_type FROM wuhan_areas
            WHERE active = 1 ORDER BY sort_order
            """
        )
    ]
