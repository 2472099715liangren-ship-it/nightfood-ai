"""Import a permission-cleared Wuhan restaurant CSV into the review queue.

Preview is the default. Use --apply only after checking the preview. The tool
never scrapes a map/review site and never publishes imported rows automatically.
"""
import argparse
import sys
from pathlib import Path

from database import connect, initialize_database
from restaurant_catalog import (
    CatalogValidationError,
    file_sha256,
    import_rows,
    read_csv,
    register_source,
)


def build_parser():
    parser = argparse.ArgumentParser(description="导入武汉真实餐厅资料（默认仅预览）")
    parser.add_argument("csv_file", type=Path, help="UTF-8 CSV 文件")
    parser.add_argument("--source-code", required=True, help="已登记的数据来源编号")
    parser.add_argument("--created-by", default="operator", help="导入操作人")
    parser.add_argument("--apply", action="store_true", help="确认预览后实际写入待审核队列")
    parser.add_argument("--rights-confirmed", action="store_true",
                        help="确认已取得存储、展示和加工所需授权/许可")
    parser.add_argument("--source-name", default="")
    parser.add_argument("--source-type", default="merchant_submission",
                        choices=["merchant_submission", "authorized_public_data",
                                 "licensed_provider", "manual_research"])
    parser.add_argument("--source-homepage", default="")
    parser.add_argument("--terms-url", default="")
    parser.add_argument("--license-note", default="")
    parser.add_argument("--approved-by", default="")
    return parser


def main():
    args = build_parser().parse_args()
    if not args.csv_file.is_file():
        print("找不到 CSV 文件：{}".format(args.csv_file), file=sys.stderr)
        return 2

    initialize_database()
    checksum = file_sha256(args.csv_file)
    with connect() as connection:
        allowed = {
            row["name"] for row in connection.execute(
                "SELECT name FROM wuhan_areas WHERE area_type = 'administrative_district'"
            )
        }
        rows, errors = read_csv(args.csv_file, allowed)
        print("文件：{}".format(args.csv_file.name))
        print("SHA-256：{}".format(checksum))
        print("可导入：{} 条；需要修正：{} 条".format(len(rows), len(errors)))
        for error in errors[:20]:
            print("第 {} 行：{}".format(error["row_number"], error["detail"]))

        source = connection.execute(
            "SELECT * FROM restaurant_sources WHERE source_code = ?",
            (args.source_code,),
        ).fetchone()
        if source is None:
            if not args.apply:
                print("来源尚未登记。默认预览不会写入数据库；实际导入时需提供来源许可信息。")
                return 0 if not errors else 1
            if not args.rights_confirmed:
                print("拒绝写入：新来源必须使用 --rights-confirmed 明确确认数据权利。", file=sys.stderr)
                return 2
            if not args.source_name or not args.license_note:
                print("新来源还需要 --source-name 和 --license-note。", file=sys.stderr)
                return 2
            register_source(
                connection,
                args.source_code,
                args.source_name,
                args.source_type,
                args.source_homepage,
                args.terms_url,
                args.license_note,
                args.approved_by or args.created_by,
                rights_confirmed=True,
            )
            connection.commit()
            source = connection.execute(
                "SELECT * FROM restaurant_sources WHERE source_code = ?",
                (args.source_code,),
            ).fetchone()
        if source["permission_status"] != "approved":
            print("拒绝写入：该来源尚未获准或已暂停。", file=sys.stderr)
            return 2

        if not args.apply:
            print("预览完成，数据库未修改。检查无误后追加 --apply 写入待审核队列。")
            return 0 if not errors else 1

        result = import_rows(
            connection, args.source_code, rows, errors,
            args.csv_file.name, checksum, args.created_by,
        )
        connection.commit()
        print("导入批次 #{}".format(result["batch_id"]))
        print("新增：{}；更新：{}；重复待复核：{}；错误：{}".format(
            result["inserted_rows"], result["updated_rows"],
            result["review_rows"], result["error_rows"],
        ))
        print("所有新记录仍为待审核状态，不会自动出现在公开餐厅目录。")
        return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
