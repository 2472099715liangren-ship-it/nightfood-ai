"""Manage authorized storefront photographs from a local operator terminal.

Example:
  python manage_photos.py add --restaurant-id 12 --file ./storefront.jpg \
    --taken-at 2026-10-20 --source-url merchant-submission:abc \
    --copyright-holder "门店经营者" --license-note "书面授权夜寻展示" \
    --operator editor --rights-confirmed

New photos always remain pending until manually approved with:
  python manage_photos.py approve --photo-id 1 --reviewed-by editor
"""
import argparse

from database import connect, initialize_database
from restaurant_photos import add_storefront_photo, review_photo


def main():
    parser = argparse.ArgumentParser(description="管理授权、近两年拍摄的真实门店照片")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="导入一张照片到待审核区")
    add.add_argument("--restaurant-id", type=int, required=True)
    add.add_argument("--file", required=True)
    add.add_argument("--taken-at", required=True, help="拍摄日期 YYYY-MM-DD")
    add.add_argument("--source-url", required=True, help="照片来源网址或商家提交凭证")
    add.add_argument("--copyright-holder", required=True)
    add.add_argument("--license-note", required=True)
    add.add_argument("--operator", required=True)
    add.add_argument("--rights-confirmed", action="store_true")

    for action in ("approve", "reject"):
        cmd = commands.add_parser(action, help="人工审核照片")
        cmd.add_argument("--photo-id", type=int, required=True)
        cmd.add_argument("--reviewed-by", required=True)
    commands.add_parser("list", help="显示待审核照片")

    options = parser.parse_args()
    initialize_database()
    with connect() as connection:
        if options.command == "add":
            photo_id = add_storefront_photo(
                connection,
                options.restaurant_id, options.file, options.taken_at,
                options.source_url, options.copyright_holder,
                options.license_note, options.operator, options.rights_confirmed,
            )
            connection.commit()
            print("照片 #{} 已导入，状态为待审核；不会立即公开。".format(photo_id))
        elif options.command in ("approve", "reject"):
            review_photo(
                connection, options.photo_id,
                "verified" if options.command == "approve" else "rejected",
                options.reviewed_by,
            )
            connection.commit()
            print("照片 #{} 审核记录已更新。".format(options.photo_id))
        elif options.command == "list":
            rows = connection.execute(
                """
                SELECT p.id, r.name, p.captured_at, p.source_url, p.copyright_holder
                FROM real_restaurant_photos AS p
                JOIN real_restaurants AS r ON r.id = p.restaurant_id
                WHERE p.record_status = 'pending'
                ORDER BY p.id
                """
            ).fetchall()
            for row in rows:
                print("#{} {} | 拍摄日期 {} | 权利人 {} | {}".format(
                    row["id"], row["name"], row["captured_at"],
                    row["copyright_holder"], row["source_url"],
                ))
            if not rows:
                print("暂无待审核照片。")


if __name__ == "__main__":
    main()
