"""Explainable side-by-side comparison of two or three demo merchants."""
import re

from database import get_merchant


def parse_merchant_ids(raw):
    """Accept only 2–3 unique positive decimal IDs, preserving selected order."""
    if not isinstance(raw, str) or not re.fullmatch(
        r"[1-9]\d*(?:,[1-9]\d*){1,2}", raw.strip()
    ):
        raise ValueError("请选择 2–3 家不同的商户进行对比")
    identifiers = [int(part) for part in raw.strip().split(",")]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("不能重复选择同一家商户")
    return identifiers


def compare_merchants(connection, raw_ids, scene=""):
    """Explain the trade-offs using known attributes, not imaginary reviews."""
    merchant_ids = parse_merchant_ids(raw_ids)
    items = [get_merchant(connection, merchant_id) for merchant_id in merchant_ids]
    if any(item is None for item in items):
        raise ValueError("所选商户已不存在，请重新选择")

    cheapest_price = min(item["price"] for item in items)
    shortest_wait = min(item["wait"] for item in items)
    top_rating = max(item["rating"] for item in items)

    for item in items:
        # Relative comparison only. All base scores/prices/waits are sample data.
        price_score = 40 * cheapest_price / max(item["price"], 1)
        wait_score = 35 * (shortest_wait + 10) / (item["wait"] + 10)
        rating_score = 15 * item["rating"] / 5
        scene_score = 10 if scene and scene in item["tags"] else 0
        item["comparison_score"] = round(
            price_score + wait_score + rating_score + scene_score, 1
        )
        item["highlights"] = []
        if item["price"] == cheapest_price:
            item["highlights"].append("人均较省")
        if item["wait"] == shortest_wait:
            item["highlights"].append("等位较短")
        if item["rating"] == top_rating:
            item["highlights"].append("演示评分较高")
        if scene and scene in item["tags"]:
            item["highlights"].append("符合就餐场景")

    recommended = max(items, key=lambda item: item["comparison_score"])
    price_gap = max(item["price"] for item in items) - cheapest_price
    wait_gap = max(item["wait"] for item in items) - shortest_wait
    reasons = [
        "人均价格最多相差 {} 元".format(price_gap),
        "预计等位时间最多相差 {} 分钟".format(wait_gap),
    ]
    if scene:
        reasons.append("已考虑「{}」的标签匹配".format(scene))

    return {
        "items": items,
        "summary": {
            "recommended_id": recommended["id"],
            "recommended_name": recommended["name"],
            "reason": "综合价格、等待和演示评分，{}的平衡性更好。"
            "也可以根据最看重的指标作自己的选择。".format(
                recommended["name"]
            ),
            "details": reasons,
            "cheapest_ids": [
                item["id"] for item in items if item["price"] == cheapest_price
            ],
            "fastest_ids": [
                item["id"] for item in items if item["wait"] == shortest_wait
            ],
            "sample_notice": (
                "以上价格、营业时间、等位与基础评分均为研究演示数据。"
                "排序是透明规则比较，不代表真实商户体验或实时情况。"
            ),
        },
    }
