"""Operator-only photo import and approval for the Wuhan OSM catalog."""
import argparse
from database import connect, initialize_database
from merchant_photos import add_photo, approve_photo


def main():
    parser = argparse.ArgumentParser(description="导入或审核近两年授权店面照片")
    actions = parser.add_subparsers(dest="command", required=True)
    add = actions.add_parser("add")
    add.add_argument("--merchant-id", type=int, required=True)
    add.add_argument("--file", required=True)
    add.add_argument("--taken-at", required=True, help="照片真实拍摄日 YYYY-MM-DD")
    add.add_argument("--source-url", required=True)
    add.add_argument("--copyright-holder", required=True)
    add.add_argument("--license-note", required=True)
    add.add_argument("--operator", required=True)
    add.add_argument("--rights-confirmed", action="store_true")
    for command in ("approve", "reject"):
        cmd = actions.add_parser(command)
        cmd.add_argument("--photo-id", type=int, required=True)
        cmd.add_argument("--reviewed-by", required=True)
    actions.add_parser("list")
    options = parser.parse_args()
    initialize_database()
    with connect() as db:
        if options.command == "add":
            photo_id = add_photo(
                db, options.merchant_id, options.file, options.taken_at,
                options.source_url, options.copyright_holder,
                options.license_note, options.operator, options.rights_confirmed,
            )
            db.commit()
            print("图片 #{} 已保存在待审核区，尚未公开。".format(photo_id))
        elif options.command in ("approve", "reject"):
            approve_photo(
                db, options.photo_id, options.reviewed_by,
                "verified" if options.command == "approve" else "rejected",
            )
            db.commit()
            print("图片 #{} 审核状态已更新。".format(options.photo_id))
        else:
            records = db.execute(
                "SELECT p.id,r.name,p.taken_at,p.copyright_holder,p.source_url "
                "FROM real_merchant_photos AS p JOIN real_merchants AS r "
                "ON r.id=p.merchant_id WHERE p.status='pending' ORDER BY p.id"
            ).fetchall()
            if not records:
                print("目前没有待审核照片。")
            for row in records:
                print("#{} {} | 拍摄于 {} | 权利人 {} | 来源 {}".format(
                    row["id"], row["name"], row["taken_at"],
                    row["copyright_holder"], row["source_url"],
                ))


if __name__ == "__main__":
    main()
