"""Review pending real-restaurant records from a local operator terminal."""
import argparse

from database import connect, initialize_database
from restaurant_catalog import review_queue, set_review_status


def parse_ids(value):
    try:
        identifiers = [int(item.strip()) for item in value.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError("编号必须是逗号分隔的整数") from error
    if not identifiers or any(item <= 0 for item in identifiers):
        raise argparse.ArgumentTypeError("编号必须是正整数")
    if len(set(identifiers)) != len(identifiers):
        raise argparse.ArgumentTypeError("不能重复填写编号")
    return identifiers


def main():
    parser = argparse.ArgumentParser(description="审核武汉真实餐厅资料")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--approve", type=parse_ids, help="核验通过的餐厅编号，例如 1,2")
    group.add_argument("--reject", type=parse_ids, help="拒绝公开的餐厅编号，例如 3,4")
    parser.add_argument("--reviewed-by", default="", help="审核人")
    parser.add_argument("--note", default="", help="核验依据或拒绝原因")
    args = parser.parse_args()

    initialize_database()
    with connect() as connection:
        if args.approve or args.reject:
            if not args.reviewed_by.strip():
                parser.error("执行审核操作时必须填写 --reviewed-by")
            status = "verified" if args.approve else "rejected"
            count = set_review_status(
                connection, args.approve or args.reject, status,
                args.reviewed_by, args.note,
            )
            connection.commit()
            print("已更新 {} 条记录：{}".format(count, status))
            return

        queue = review_queue(connection)
        if not queue:
            print("当前没有待审核的真实餐厅资料。")
            return
        for item in queue:
            print(
                "#{id} [{record_status}] {name}｜{district}｜{address}\\n"
                "  来源：{source_name}｜{source_url}\\n"
                "  备注：{verification_note}".format(**item)
            )


if __name__ == "__main__":
    main()
