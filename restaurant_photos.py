"""Controlled ingestion and review of licensed, recent storefront photographs.

Images are imported locally by an operator. Public visitors cannot upload
files. Photo bytes are served only after explicit human approval.
"""
import os
import re
import secrets
from pathlib import Path

from database import ROOT
from freshness import parse_recent_date, cutoff_date

PHOTO_ROOT = Path(os.environ.get("RESTAURANT_PHOTO_DIR", ROOT / "data" / "restaurant_photos"))
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _classify_image(data):
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    raise ValueError("仅支持 JPEG、PNG 和 WebP 图片")


def _inspect_file(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError("照片不存在或超过 5 MB")
    data = path.read_bytes()
    if len(data) < 128:
        raise ValueError("图片文件过小，可能不是有效照片")
    ext = _classify_image(data)
    # Deny common embedded EXIF/XMP metadata to avoid publishing location,
    # camera identity or personal information accidentally.
    if any(token in data for token in (
        b"Exif\x00\x00", b"eXIf", b"iTXt", b"tEXt", b"zTXt",
        b"http://ns.adobe.com/xap/1.0/", b"XMP ",
    )):
        raise ValueError("图片包含 EXIF/XMP/文本元数据，请先导出已移除元数据的版本")
    return data, ext


def add_storefront_photo(
    connection, restaurant_id, file_path, captured_at, source_url,
    copyright_holder, license_note, operator, rights_confirmed=False,
):
    """Import a reviewed, metadata-free photo into a non-public holding state."""
    from restaurant_catalog import _valid_url

    if not rights_confirmed:
        raise ValueError("必须先明确确认门店照片的复制、存储与展示权利")
    captured_at = parse_recent_date(captured_at, "照片拍摄日期")
    if not _valid_url(source_url, allow_submission_reference=True):
        raise ValueError("照片必须有官方页面链接或商家提交凭证")
    if not str(copyright_holder).strip() or not str(license_note).strip():
        raise ValueError("必须填写图片权利人和授权说明")
    if not str(operator).strip():
        raise ValueError("操作人不能为空")

    restaurant = connection.execute(
        """
        SELECT r.id, r.source_updated_at, r.record_status, s.permission_status
        FROM real_restaurants AS r
        JOIN restaurant_sources AS s ON s.id = r.source_id
        WHERE r.id = ?
        """, (restaurant_id,),
    ).fetchone()
    if restaurant is None:
        raise ValueError("找不到这家真实餐厅")
    if restaurant["permission_status"] != "approved":
        raise ValueError("门店资料来源权限未生效，不可添加照片")
    if restaurant["source_updated_at"] < cutoff_date().isoformat():
        raise ValueError("餐厅资料已超过两年，请先更新来源信息")

    data, ext = _inspect_file(file_path)
    PHOTO_ROOT.mkdir(parents=True, exist_ok=True)
    filename = secrets.token_hex(20) + ext
    destination = PHOTO_ROOT / filename
    with destination.open("xb") as stream:
        stream.write(data)
    try:
        connection.execute(
            """
            INSERT INTO real_restaurant_photos (
                restaurant_id, image_filename, captured_at, source_url,
                copyright_holder, license_note, permission_confirmed
            ) VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                restaurant_id, filename, captured_at,
                str(source_url).strip(), str(copyright_holder).strip(),
                str(license_note).strip(),
            ),
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return connection.execute("SELECT last_insert_rowid()").fetchone()[0]


def review_photo(connection, photo_id, status, reviewer):
    """Approval alone does not bypass the public freshness/rights checks."""
    if status not in ("verified", "rejected"):
        raise ValueError("照片审核状态必须是 verified 或 rejected")
    if not reviewer or not reviewer.strip():
        raise ValueError("照片审核人不能为空")
    row = connection.execute(
        "SELECT captured_at, permission_confirmed FROM real_restaurant_photos WHERE id = ?",
        (photo_id,),
    ).fetchone()
    if row is None:
        raise ValueError("没有找到这张照片")
    if status == "verified":
        parse_recent_date(row["captured_at"], "照片拍摄日期")
        if row["permission_confirmed"] != 1:
            raise ValueError("图片授权尚未确认")
    connection.execute(
        """
        UPDATE real_restaurant_photos
        SET record_status = ?, verified_by = ?, verified_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, reviewer.strip(), photo_id),
    )


def public_photo_path(filename):
    """Resolve only the random file name from an approved database record."""
    if not re.fullmatch(r"[a-f0-9]{40}\.(jpg|png|webp)", filename):
        raise ValueError("无效照片存储路径")
    path = PHOTO_ROOT / filename
    if not path.is_file():
        raise FileNotFoundError(filename)
    return path
