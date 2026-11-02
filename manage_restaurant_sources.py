"""Inspect or suspend data sources used by the real restaurant catalog."""
import argparse

from database import connect, initialize_database


def main():
    parser = argparse.ArgumentParser(description="管理真实餐厅数据来源许可状态")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--suspend", help="暂停某个来源编号")
    group.add_argument("--reinstate", help="恢复某个来源编号（需重新确认许可）")
    parser.add_argument("--rights-confirmed", action="store_true")
    parser.add_argument("--approved-by", default="")
    args = parser.parse_args()

    initialize_database()
    with connect() as connection:
        if args.suspend:
            cursor = connection.execute(
                """
                UPDATE restaurant_sources
                SET permission_status = 'suspended',
                    updated_at = CURRENT_TIMESTAMP
                WHERE source_code = ?
                """,
                (args.suspend,),
            )
            if cursor.rowcount != 1:
                parser.error("找不到该来源编号")
            connection.commit()
            print("来源已暂停；该来源的真实餐厅已从公开目录隐藏。")
            return

        if args.reinstate:
            if not args.rights_confirmed or not args.approved_by.strip():
                parser.error("恢复来源必须提供 --rights-confirmed 和 --approved-by")
            cursor = connection.execute(
                """
                UPDATE restaurant_sources
                SET permission_status = 'approved',
                    approved_by = ?, approved_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE source_code = ?
                """,
                (args.approved_by.strip(), args.reinstate),
            )
            if cursor.rowcount != 1:
                parser.error("找不到该来源编号")
            connection.commit()
            print("来源许可已重新登记；原有已核验记录重新符合公开条件。")
            return

        sources = connection.execute(
            """
            SELECT source_code, source_name, source_type, permission_status,
                   approved_by, approved_at, terms_url
            FROM restaurant_sources ORDER BY source_name
            """
        ).fetchall()
        if not sources:
            print("尚未登记数据来源。")
            return
        for source in sources:
            print(
                "{source_code} [{permission_status}] {source_name}\\n"
                "  类型：{source_type}；审核人：{approved_by}；许可日期：{approved_at}\\n"
                "  条款：{terms_url}".format(**dict(source))
            )


if __name__ == "__main__":
    main()
