"""Explainable decisions over the real catalog.

Hard known failures are excluded. Missing facts remain conditional candidates;
we never synthesize wait times, opening hours, menu prices or travel durations.
"""

import math
import re
from collections import Counter
from datetime import datetime, timedelta
from urllib.parse import urlencode

from decision_catalog import list_public_merchants, require_public_merchant
from decision_preferences import next_question, parse_request, per_person_budget

CUISINE_TERMS = {
    "清淡": ("粥", "面", "清淡"),
    "面食": ("面", "粉"),
    "湖北菜": ("湖北", "鄂菜", "武汉菜"),
    "素食": ("素食", "素菜"),
}
WEEKDAYS = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")


def opening_status(raw, arrival):
    """Understand simple daily or OSM weekday time ranges, including midnight.

    Unsupported holiday/seasonal/free-text schedules deliberately stay unknown.
    A returned 'open' means the published schedule covers arrival, not live status.
    """
    if not raw or not arrival:
        return "unknown"
    raw = raw.strip()
    if raw.lower() in ("closed", "off", "暂停营业", "已停业", "永久停业"):
        return "closed"
    if raw in ("24/7", "24小时", "全天营业"):
        return "open"
    raw = re.sub(r"[至~–—]", "-", raw).replace("：", ":")
    schedules = []
    for section in raw.split(";"):
        match = re.fullmatch(
            r"(?:(Mo|Tu|We|Th|Fr|Sa|Su)(?:-(Mo|Tu|We|Th|Fr|Sa|Su))?\s+)?(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})",
            section.strip(),
        )
        if not match:
            return "unknown"
        first, last, sh, sm, eh, em = match.groups()
        sh, sm, eh, em = map(int, (sh, sm, eh, em))
        if sh > 23 or eh > 24 or sm > 59 or em > 59 or (eh == 24 and em):
            return "unknown"
        days = set(range(7))
        if first:
            start = WEEKDAYS.index(first)
            end = WEEKDAYS.index(last or first)
            days = {(start + step) % 7 for step in range((end - start) % 7 + 1)}
        if sh * 60 + sm == eh * 60 + em:
            return "unknown"
        schedules.append((days, sh * 60 + sm, eh * 60 + em))
    current = datetime.fromisoformat(arrival)
    for day in (current.date(), current.date() - timedelta(days=1)):
        for weekdays, start, end in schedules:
            if day.weekday() not in weekdays:
                continue
            if end <= start:
                end += 24 * 60
            midnight = datetime.combine(day, datetime.min.time(), current.tzinfo)
            if (
                midnight + timedelta(minutes=start)
                <= current
                < midnight + timedelta(minutes=end)
            ):
                return "open"
    return "closed"


def distance_km(origin, merchant):
    values = (
        origin.get("latitude"),
        origin.get("longitude"),
        merchant.get("latitude"),
        merchant.get("longitude"),
    )
    if any(value is None for value in values):
        return None
    lat1, lng1, lat2, lng2 = map(math.radians, values)
    angle = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    )
    return 6371 * 2 * math.asin(min(1, math.sqrt(angle)))


def price_ceiling(merchant):
    if merchant.get("price_range_basis") == "per_person":
        return merchant.get("price_range_max") or merchant.get("price_per_person")
    # A dish-price band must never masquerade as a per-person meal budget.
    return merchant.get("price_per_person")


def navigation_links(merchant):
    name = merchant["name"]
    query = "武汉市 " + merchant["district"] + " " + merchant["address"] + " " + name
    has_coordinates = (
        merchant.get("latitude") is not None and merchant.get("longitude") is not None
    )
    destination = (
        "{},{}".format(merchant["latitude"], merchant["longitude"])
        if has_coordinates
        else query
    )
    return {
        "navigation_url": "https://www.google.com/maps/dir/?"
        + urlencode({"api": 1, "destination": destination, "travelmode": "walking"}),
        "map_search_url": "https://uri.amap.com/search?"
        + urlencode(
            {"keyword": query, "city": "武汉", "src": "nightfind", "callnative": 1}
        ),
        "navigation_notice": (
            "坐标为来源提供的近似点位，请核对具体分店。"
            if has_coordinates
            else "暂无坐标，将按名称和地址查找；请在地图中核对具体分店。"
        ),
    }


def describe_merchant(merchant):
    """A single presentation model shared by results, details and comparisons."""
    item = dict(merchant)
    item.update(navigation_links(item))
    phone = item.get("phone") or ""
    item["phone_url"] = (
        "tel:" + re.sub(r"[ ()-]", "", phone)
        if re.fullmatch(r"\+?[\d ()-]{5,30}", phone)
        else None
    )
    item["quality_label"] = {
        "verified": "人工核验资料",
        "community": "OSM 社区资料",
        "web_listing": "公开网页资料，营业状态未人工核验",
    }.get(item.get("data_quality"), "资料待确认")
    item["price_notice"] = "来源参考价，实际消费以门店为准"
    return item


def evaluate_merchant(merchant, preferences):
    """Return (candidate, exclusion). Keep each decision rule easy to change."""
    item = describe_merchant(merchant)
    reasons, questions = [], []
    budget = per_person_budget(preferences)
    ceiling = price_ceiling(item)
    if budget is not None and ceiling is not None and ceiling > budget:
        return None, "超过预算参考上限"
    if ceiling is None:
        questions.append("缺少可靠人均参考价，需确认是否符合预算")
    else:
        reasons.append(
            "来源参考人均上限约 ¥{:g}，在 ¥{:g}/人的预算内".format(ceiling, budget)
            if budget is not None
            else "来源参考人均上限约 ¥{:g}".format(ceiling)
        )
    location = preferences["location"] or {}
    distance = distance_km(location, item)
    if (
        distance is None
        and location.get("district")
        and item["district"] != location["district"]
    ):
        return None, "不在所选行政区且无法确认距离"
    radius = preferences["radius_km"]
    if distance is not None and radius is not None and distance > radius:
        return None, "超过指定直线距离"
    if distance is None:
        questions.append("距离待确认，缺少出发位置或门店坐标")
    else:
        reasons.append("距出发位置约 {:.1f} 公里（直线估算）".format(distance))
    item["distance_km"] = round(distance, 1) if distance is not None else None
    status = opening_status(item.get("opening_hours"), preferences["arrival"])
    if status == "closed":
        return None, "来源营业时间不覆盖到店时间"
    if status == "unknown":
        questions.append("无法确认到店时是否营业，请电话或通过来源渠道核实")
    else:
        reasons.append("来源营业时间覆盖预计到店时间，仍建议出发前确认")
    item["opening_status"] = status
    cuisine = preferences["cuisine"]
    text = item["cuisine"] + " " + item.get("signature_dishes", "")
    taste_match = bool(
        cuisine and any(word in text for word in CUISINE_TERMS.get(cuisine, (cuisine,)))
    )
    if cuisine:
        (reasons if taste_match else questions).append(
            "菜系或招牌菜符合「{}」偏好".format(cuisine)
            if taste_match
            else "菜系与「{}」偏好不同，作为备选".format(cuisine)
        )
    for avoid in preferences["avoid"]:
        if avoid in text:
            return None, "已知菜系或菜品与忌口冲突"
    if preferences["avoid"]:
        questions.append("忌口/过敏需向门店逐项确认，现有菜单不能证明不含相关食材")
    if (preferences["party_size"] or 1) > 1:
        questions.append(
            "{} 人座位及是否需要预约需联系门店确认".format(preferences["party_size"])
        )
    if preferences["wait_minutes"] is not None:
        questions.append(
            "没有实时排队资料，无法保证等待不超过 {} 分钟".format(
                preferences["wait_minutes"]
            )
        )
    item.update(
        reasons=reasons,
        questions=questions,
        needs_confirmation=bool(questions),
        taste_match=taste_match,
        estimated_total=(
            round(ceiling * preferences["party_size"], 2)
            if ceiling and preferences["party_size"]
            else None
        ),
    )
    # No opaque quality score: rank by facts and the visitor's current priority.
    distance_order = distance if distance is not None else math.inf
    price_order = ceiling if ceiling is not None else math.inf
    priority = preferences["priority"]
    order = (
        (distance_order, price_order)
        if priority == "distance"
        else (price_order, distance_order)
    )
    if priority == "balanced":
        order = (not taste_match if cuisine else False, distance_order, price_order)
    item["_order"] = (len(questions), *order, item["id"])
    return item, None


def prepare_decision(payload):
    message = str(payload.get("message", "")).strip()
    if not message or len(message) > 2000:
        raise ValueError("请写下 1–2000 个字符的需求")
    return parse_request(message, payload.get("context"), payload.get("location"))


def _ids(values):
    if not isinstance(values, list) or len(values) > 100:
        raise ValueError("候选门店编号列表无效")
    try:
        return {int(value) for value in values}
    except (TypeError, ValueError) as error:
        raise ValueError("候选门店编号无效") from error


def make_decision(connection, preferences, payload, mode="local"):
    question = next_question(preferences)
    result = dict(
        stage="clarify" if question else "candidates",
        constraints=preferences,
        budget_per_person=per_person_budget(preferences),
        mode=mode,
        items=[],
        eligible_total=0,
        excluded={},
        follow_up=question,
        exhausted=False,
    )
    if question:
        result["reply"] = question["question"]
        return result
    message = str(payload.get("message", ""))
    seen = (
        _ids(payload.get("seen_ids", []))
        if any(word in message for word in ("换一批", "换一家", "换掉", "看看别的"))
        else set()
    )
    keep = _ids(payload.get("keep_ids", []))
    previous = payload.get("previous_ids", [])
    if not isinstance(previous, list) or len(previous) > 3:
        raise ValueError("上一轮候选编号无效")
    reference = re.search(r"第([一二三123])家", message)
    if reference:
        position = (
            "一二三".find(reference[1])
            if reference[1] in "一二三"
            else int(reference[1]) - 1
        )
        if position < len(previous):
            merchant_id = int(previous[position])
            if "保留" in message:
                keep.add(merchant_id)
            elif "换" in message or "贵" in message:
                seen.add(merchant_id)
    candidates, excluded = [], Counter()
    for merchant in list_public_merchants(connection):
        item, reason = evaluate_merchant(merchant, preferences)
        if reason:
            excluded[reason] += 1
        else:
            candidates.append(item)
    candidates.sort(key=lambda item: item["_order"])
    pinned = [item for item in candidates if item["id"] in keep][:3]
    available = [item for item in candidates if item["id"] not in seen | keep]
    selected = (pinned + available)[:3]
    result["exhausted"] = bool(seen) and not available and len(selected) < 3
    for item in selected:
        item.pop("_order")
        item["kept"] = item["id"] in keep
        # Enrich just the selected rows with dated menu/image evidence.
        detail = require_public_merchant(connection, item["id"])
        item.update(
            menu_items=detail["menu_items"],
            images=detail["images"],
            photos=detail["photos"],
        )
    result.update(
        items=selected, eligible_total=len(candidates), excluded=dict(excluded)
    )
    if not selected:
        result["reply"] = (
            "当前条件下没有新的可用候选。不会自动放宽预算、距离或忌口；可以明确修改条件后再找。"
        )
    else:
        result["reply"] = "找到 {} 家真实门店候选。".format(len(selected))
        if any(item["needs_confirmation"] for item in selected):
            result[
                "reply"
            ] += "标出的未知信息需要出发前向门店确认，这些候选不代表已满足全部条件。"
        if result["exhausted"]:
            result["reply"] += "当前没有更多未展示的候选。"
    result["follow_up"] = {
        "question": "还想调整什么？",
        "actions": ["便宜一点", "找近一点", "换一批", "不限口味"],
    }
    return result


def compare_real_merchants(connection, raw_ids):
    from comparison import parse_merchant_ids

    ids = parse_merchant_ids(raw_ids)
    items = [
        describe_merchant(require_public_merchant(connection, value)) for value in ids
    ]
    return {
        "items": items,
        "notice": "按来源事实并列比较；不使用演示评分。未知价格、营业和距离不作保证。",
    }
