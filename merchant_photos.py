"""Operator-only storefront photo pipeline for the OSM Wuhan catalog.

Do not treat an OSM place tag or an image search result as a photo license.
Only a recently photographed, explicitly licensed, human-reviewed image can
appear on public merchant cards.
"""
import os
import re
import secrets
from pathlib import Path

from database import ROOT
from real_catalog import _fresh_cutoff

PHOTO_DIR = Path(os.environ.get("MERCHANT_PHOTO_DIR", ROOT / "data" / "merchant_photos"))
MAX_BYTES = 5 * 1024 * 1024


def recent_date(raw, label):
    from datetime import date
    try:
        value = date.fromisoformat(str(raw))
    except (TypeError, ValueError) as error:
        raise ValueError("{}必须是 YYYY-MM-DD 格式".format(label)) from error
    if value > date.today() or value.isoformat() < _fresh_cutoff():
        raise ValueError("{}必须在最近两个自然年内，且不能为未来日期".format(label))
    return value.isoformat()


def inspect_image(path):
    file_path = Path(path)
    if not file_path.is_file() or file_path.stat().st_size > MAX_BYTES:
        raise ValueError("店面照片不存在或超过 5 MB")
    data = file_path.read_bytes()
    if len(data) < 128:
        raise ValueError("店面照片文件不完整")
    if data.startswith(b"\xff\xd8\xff"):
        ext = ".jpg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        ext = ".png"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        ext = ".webp"
    else:
        raise ValueError("店面图片只能使用 JPEG、PNG 或 WebP")
    if any(token in data for token in (
        b"Exif\x00\x00", b"eXIf", b"iTXt", b"tEXt", b"zTXt",
        b"http://ns.adobe.com/xap/1.0/", b"XMP ",
    )):
        raise ValueError("图片含常见 EXIF/XMP 元数据，请先移除后再提交")
    return data, ext


def add_photo(
    connection, merchant_id, image_path, taken_at, source_url,
    copyright_holder, license_note, operator, rights_confirmed=False,
):
    if not rights_confirmed:
        raise ValueError("尚未明确确认图片复制、存储和展示的授权")
    taken_at = recent_date(taken_at, "拍摄日期")
    if not operator or not operator.strip():
        raise ValueError("操作员不能为空")
    if not copyright_holder or not copyright_holder.strip() or not license_note:
        raise ValueError("必须提供照片权利人和展示授权说明")
    if not re.match(r"^(https://\S+|merchant-submission:[A-Za-z0-9_-]+)$", source_url or ""):
        raise ValueError("需要可追溯的照片来源网址或商家提交凭证")
    merchant = connection.execute(
        "SELECT id,source_checked_at FROM real_merchants WHERE id=?",
        (merchant_id,),
    ).fetchone()
    if merchant is None:
        raise ValueError("未找到真实门店")
    # A photo can be prepared for a pending candidate; public serving remains gated.
    data, ext = inspect_image(image_path)
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    filename = secrets.token_hex(20) + ext
    target = PHOTO_DIR / filename
    with target.open("xb") as out:
        out.write(data)
    try:
        connection.execute(
            """
            INSERT INTO real_merchant_photos(
                merchant_id,image_filename,taken_at,source_url,
                copyright_holder,license_note,permission_confirmed
            ) VALUES (?,?,?,?,?,?,1)
            """,
            (
                merchant_id, filename, taken_at, source_url,
                copyright_holder.strip(), license_note.strip(),
            ),
        )
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return connection.execute("SELECT last_insert_rowid()").fetchone()[0]


def approve_photo(connection, photo_id, reviewer, status="verified"):
    if status not in ("verified", "rejected"):
        raise ValueError("不支持的照片审核状态")
    if not reviewer or not reviewer.strip():
        raise ValueError("审核人不能为空")
    row = connection.execute(
        "SELECT taken_at,permission_confirmed FROM real_merchant_photos WHERE id=?",
        (photo_id,),
    ).fetchone()
    if row is None:
        raise ValueError("照片不存在")
    if status == "verified":
        recent_date(row["taken_at"], "照片拍摄日期")
        if row["permission_confirmed"] != 1:
            raise ValueError("缺少图片授权")
    connection.execute(
        """
        UPDATE real_merchant_photos SET status=?,verified_at=CURRENT_TIMESTAMP,
            reviewed_by=? WHERE id=?
        """,
        (status, reviewer.strip(), photo_id),
    )


def public_photo_file(connection, photo_id):
    """No image bytes may escape when merchant/photo evidence is stale."""
    boundary = _fresh_cutoff()
    row = connection.execute(
        """
        SELECT p.image_filename FROM real_merchant_photos AS p
        JOIN real_merchants AS r ON r.id=p.merchant_id
        WHERE p.id=? AND p.permission_confirmed=1 AND p.status='verified'
          AND p.taken_at >= ? AND substr(p.verified_at,1,10) >= ?
          AND r.source_checked_at >= ?
          AND ((r.status='verified' AND r.verified_at >= ?) OR
               (r.status='pending' AND r.source_name='OpenStreetMap'
                AND r.external_id LIKE 'osm:%'))
        """,
        (photo_id, boundary, boundary, boundary, boundary),
    ).fetchone()
    return row


def safe_image_path(filename):
    if not re.fullmatch(r"[a-f0-9]{40}\.(jpg|png|webp)", filename):
        raise ValueError("无效照片文件")
    path = PHOTO_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(filename)
    return path
