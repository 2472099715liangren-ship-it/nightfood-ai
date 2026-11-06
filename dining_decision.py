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
from decision_preferences import (
    next_question,
    parse_request,
    per_person_budget,
    validate_preferences,
)

from catalog_language import CUISINE_TERMS, BRAND_ALIASES, display_cuisine
from catalog_policy import catalog_cutoff
from geo_coordinates import wgs84_to_gcj02

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
    sections = []
    for section in raw.split(";"):
        prefix = re.match(
            r"((?:Mo|Tu|We|Th|Fr|Sa|Su)(?:-(?:Mo|Tu|We|Th|Fr|Sa|Su))?\s+)",
            section.strip(),
        )
        for index, interval in enumerate(section.strip().split(",")):
            sections.append((prefix[1] if index and prefix else "") + interval.strip())
    for section in sections:
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
    district = merchant["district"] if "待确认" not in merchant["district"] else ""
    address = merchant["address"]
    if any(word in address for word in ("待核实", "待确认", "来源地图")):
        address = ""
    query = " ".join(part for part in ("武汉市", district, address, name) if part)
    search = "https://uri.amap.com/search?" + urlencode(
        dict(keyword=query, city="武汉", src="nightfind", callnative=0)
    )
    has_coordinates = (
        merchant.get("latitude") is not None and merchant.get("longitude") is not None
    )
    if has_coordinates:
        lat, lng = wgs84_to_gcj02(merchant["latitude"], merchant["longitude"])
        navigation = "https://uri.amap.com/navigation?" + urlencode(
            dict(
                to=f"{lng:.6f},{lat:.6f},{name}",
                mode="walk",
                coordinate="gaode",
                src="nightfind",
                callnative=0,
            )
        )
    else:
        navigation = search
    return dict(
        navigation_url=navigation,
        map_search_url=search,
        navigation_notice=(
            "按来源坐标定位，请核对分店与具体入口。"
            if has_coordinates
            else "尚无可靠坐标，按店名与地址查找，请核对具体分店。"
        ),
    )


def describe_merchant(merchant):
    """A single presentation model shared by results, details and comparisons."""
    item = dict(merchant)
    item["cuisine_display"] = display_cuisine(item["cuisine"])
    item.update(navigation_links(item))
    phone = item.get("phone") or ""
    item["phone_url"] = (
        "tel:" + re.sub(r"[ ()-]", "", phone)
        if re.fullmatch(r"\+?[\d ()-]{5,30}", phone)
        else None
    )
    item["quality_label"] = {
        "verified": "门店来源资料",
        "community": "OSM 社区资料",
        "web_listing": "公开网页资料",
    }.get(item.get("data_quality"), "资料待确认")
    item["price_notice"] = "来源参考价，实际消费以门店为准"
    if item.get("source_checked_at"):
        item["evidence_label"] = "来源日期 " + item["source_checked_at"]
    elif item.get("source_collected_at"):
        item["evidence_label"] = "在线采集 " + item["source_collected_at"]
    elif item.get("source_archived_at"):
        item["evidence_label"] = (
            "资料归档 " + item["source_archived_at"] + "，本次未重新采集"
        )
    else:
        item["evidence_label"] = "日期待确认"

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
    if "preferences" in payload:
        if not isinstance(payload["preferences"], dict):
            raise ValueError("用餐条件需要是对象")
        preferences = validate_preferences(payload["preferences"])
        if payload["preferences"].get("location") and preferences["location"] is None:
            raise ValueError(
                "暂未识别出发位置，请选择江汉路、楚河汉街、光谷、粮道街、地铁站或武汉行政区，也可使用当前位置"
            )
        return preferences, "local"
    return parse_request(message, payload.get("context"), payload.get("location"))


def _ids(values):
    if not isinstance(values, list) or len(values) > 100:
        raise ValueError("候选门店编号列表无效")
    try:
        return {int(value) for value in values}
    except (TypeError, ValueError) as error:
        raise ValueError("候选门店编号无效") from error


def make_decision(connection, preferences, payload, mode="local"):
    lookup = (
        None
        if payload.get("intent") == "plan"
        else catalog_lookup(connection, preferences, payload, mode)
    )
    if lookup is not None:
        return lookup
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


def catalog_lookup(connection, preferences, payload, mode):
    """Answer a factual lookup immediately; planning questions remain optional."""
    from real_catalog import catalog_coverage

    message = str(payload.get("message", "")).strip()
    all_merchants = list(list_public_merchants(connection))
    previous = payload.get("previous_ids", [])
    ordinal = re.search(r"第([一二三123])家", message)
    topic = (
        "menu"
        if any(word in message for word in ("菜单", "菜品", "价格", "多少钱", "单价"))
        else "overview"
    )
    targeted_id = None
    if ordinal and topic == "menu" and isinstance(previous, list):
        index = (
            "一二三".find(ordinal[1]) if ordinal[1] in "一二三" else int(ordinal[1]) - 1
        )
        if index < len(previous):
            targeted_id = int(previous[index])
    # An explicitly named branch wins over a brand-wide match.
    normalize = lambda value: re.sub(r"[^\w\u4e00-\u9fff]", "", value).casefold()
    branch_matches = [
        item
        for item in all_merchants
        if re.search(r"[（(]", item["name"])
        and normalize(item["name"]) in normalize(message)
    ]
    if branch_matches and targeted_id is None:
        targeted_id = max(branch_matches, key=lambda item: len(item["name"]))["id"]
    keyword = ""
    # Match names actually present in the database, including branch-free names.
    stems = {re.split(r"[（(·]", item["name"])[0].strip() for item in all_merchants}
    stems.update(BRAND_ALIASES)
    for name in sorted(stems, key=len, reverse=True):
        if len(name) >= 2 and name.casefold() in message.casefold():
            keyword = name
            break
    explicit = any(
        word in message
        for word in (
            "查",
            "搜索",
            "有哪些",
            "有什么",
            "菜单",
            "菜品",
            "多少钱",
            "价格",
            "地址",
            "坐标",
            "数据库",
            "真实商家",
        )
    )
    has_missing = next_question(preferences) is not None
    if not (
        explicit or targeted_id or keyword or (has_missing and preferences["cuisine"])
    ):
        return None
    if not keyword:
        keyword = preferences["cuisine"]
    if (
        not keyword
        and explicit
        and not any(
            word in message for word in ("哪些", "有什么", "数据库", "真实商家", "所有")
        )
    ):
        match = re.search(
            r"(?:查一下|查下|查询|搜索|查查|找找|找|查)\s*(.+?)(?:的(?:菜单|菜品|价格|地址|坐标)|$)",
            message,
        )
        if match:
            keyword = match[1].strip(" ，。？?!！")[:80]
            keyword = keyword.removeprefix("武汉").removesuffix("附近")
        else:
            noun = re.search(
                r"^(.{2,40}?)(?:的)?(?:菜单|菜品|价格|多少钱|地址|坐标)", message
            )
            if noun:
                keyword = noun[1].removesuffix("的").strip(" ，。？?!！")

    if targeted_id is not None:
        records = [item for item in all_merchants if item["id"] == targeted_id]
    elif keyword:
        records = list(list_public_merchants(connection, keyword=keyword))
    else:
        records = all_merchants
    candidates, excluded = [], Counter()
    for record in records:
        item, reason = evaluate_merchant(record, preferences)
        if reason:
            excluded[reason] += 1
        else:
            candidates.append(item)
    candidates.sort(key=lambda item: item["_order"])
    if (preferences["location"] or {}).get("latitude") is not None:
        candidates.sort(
            key=lambda item: (
                item["distance_km"] if item["distance_km"] is not None else math.inf
            )
        )
    if topic == "menu":
        # Prefer sourced menu evidence for a menu lookup, never synthesize a price.
        priced = {
            row[0]
            for row in connection.execute(
                "SELECT DISTINCT merchant_id FROM real_merchant_menu_items WHERE price IS NOT NULL AND price_checked_at >= ?",
                (catalog_cutoff(),),
            )
        }
        candidates.sort(key=lambda item: item["id"] not in priced)
    selected = candidates[:3]
    for item in selected:
        item.pop("_order", None)
        detail = require_public_merchant(connection, item["id"])
        item.update(
            menu_items=detail["menu_items"],
            images=detail["images"],
            photos=detail["photos"],
            kept=False,
        )
    stats = catalog_coverage(connection)
    if selected:
        reply = "在真实资料库中找到 {} 家符合本轮查询的门店，先列出 {} 家。".format(
            len(candidates), len(selected)
        )
        if topic == "menu":
            reply += "以下是来源记录的参考单价，不是实时门店报价；实际价格和适用期限请向门店确认。"
            parts = []
            for item in selected:
                prices = [
                    "{} ¥{:g}/{}".format(
                        dish["dish_name"],
                        dish["price"],
                        dish["price_unit"].removeprefix("元/"),
                    )
                    for dish in item["menu_items"]
                    if dish["price"] is not None
                ]
                parts.append(
                    item["name"]
                    + "："
                    + (
                        "；".join(prices[:3])
                        if prices
                        else "尚无带来源的菜单单价，不能据此保证预算"
                    )
                )
            reply += "\n" + "\n".join(parts)
    else:
        reply = "资料库中没有找到同时满足本轮查询的门店；不会用模拟商家或虚构价格补齐。"
    return dict(
        stage="catalog",
        constraints=preferences,
        budget_per_person=per_person_budget(preferences),
        mode=mode,
        reply=reply,
        items=selected,
        eligible_total=len(candidates),
        excluded=dict(excluded),
        exhausted=False,
        catalog_stats=stats,
        query_keyword=keyword,
        follow_up=next_question(preferences)
        or dict(
            question="还想了解哪家店？",
            actions=["查蔡林记的菜单价格", "有哪些咖啡店", "江汉路附近有哪些餐厅"],
        ),
    )
