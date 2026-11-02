"""Offline authorized merchant-data import tool.

Examples:
    python3 import_merchants.py data/authorized_merchants.csv --dry-run
    python3 import_merchants.py data/authorized_merchants.csv

Only import information you are licensed or otherwise permitted to use.
"""
import argparse
import json
import sys

from database import connect, initialize_database
from real_catalog import import_real_merchants, read_import_file


def main():
    parser = argparse.ArgumentParser(description="导入武汉真实餐厅资料（CSV/JSON）")
    parser.add_argument("path", help="已获得使用权的 CSV/JSON 数据文件")
    parser.add_argument("--dry-run", action="store_true", help="只校验，不写入")
    args = parser.parse_args()
    try:
        records = read_import_file(args.path)
        initialize_database()
        with connect() as connection:
            result = import_real_merchants(connection, records, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("提示：只有 status=verified 且具有核验日期/方式的记录会公开。")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print("导入失败：" + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
