"""Recommendation and conversational assistant services.

This module owns product rules. HTTP handlers should only validate and call services.
"""
import json
import math
import os
import re
import urllib.error
import urllib.request

from database import list_merchants, save_recommendation_run


SCENES = ("朋友聚会", "独自用餐", "出游夜宵")
CUISINES = ("不限", "烧烤", "小龙虾", "湖北菜", "家常菜", "粥粉面")


def _valid_context(context):
    context = context if isinstance(context, dict) else {}
    return {
        "district": str(context.get("district", "")),
        "budget": _bounded_int(context.get("budget"), 100, 10, 500),
        "wait": _bounded_int(context.get("wait"), 40, 0, 120),
        "hour": _bounded_hour(context.get("hour", 21)),
        "scene": context.get("scene") if context.get("scene") in SCENES else "朋友聚会",
        "cuisine": context.get("cuisine") if context.get("cuisine") in CUISINES else "不限",
    }


def _bounded_int(value, default, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if minimum <= number <= maximum else default


def _bounded_hour(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 21.0
    return number if 0 <= number < 24 else 21.0


def _chinese_digits_to_arabic(message):
    """Handle common short forms such as 九点半 and 十点."""
    digits = {
        "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3,
        "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    }

    def replace(match):
        text = match.group(0)
        if text == "十":
            return "10"
        if text.startswith("十"):
            return str(10 + digits.get(text[1], 0))
        if text.endswith("十"):
            return str(digits.get(text[0], 0) * 10)
        if "十" in text:
            left, right = text.split("十", 1)
            return str(digits.get(left, 1) * 10 + digits.get(right, 0))
        return str(digits[text])

    return re.sub(r"[零〇一二两三四五六七八九十]{1,3}(?=点)", replace, message)


def parse_preferences(message, context, districts):
    """Merge new natural-language details into the current conversation context."""
    preferences = _valid_context(context)
    message = _chinese_digits_to_arabic(message)

    for district in districts:
        if district["name"] in message:
            preferences["district"] = district["name"]
            break

    budget_match = re.search(
        r"(?:人均|预算|每人|每位|控制在|不超过|最多)(?:在|为|约)?\s*[¥￥]?\s*(\d{1,3})",
        message,
    )
    if not budget_match:
        budget_match = re.search(r"[¥￥]\s*(\d{1,3})", message)
    if not budget_match:
        budget_match = re.search(r"(\d{1,3})\s*(?:元|块)(?:以内|左右)?", message)
    if budget_match:
        value = int(budget_match.group(1))
        if 10 <= value <= 500:
            preferences["budget"] = value

    wait_patterns = (
        r"(?:等位|等待|等)\s*(?:不超过|最多|控制在)?\s*(\d{1,3})\s*分钟",
        r"(?:最多|不超过)\s*等\s*(\d{1,3})\s*分钟",
    )
    for pattern in wait_patterns:
        match = re.search(pattern, message)
        if match:
            value = int(match.group(1))
            if 0 <= value <= 120:
                preferences["wait"] = value
            break
    if any(word in message for word in ("不想排队", "不想等", "不排队")):
        preferences["wait"] = min(preferences["wait"], 10)

    time_match = re.search(
        r"(凌晨|早上|上午|中午|下午|傍晚|晚上|今晚)?\s*"
        r"(\d{1,2})(?::|：)(\d{2})|"
        r"(凌晨|早上|上午|中午|下午|傍晚|晚上|今晚)?\s*"
        r"(\d{1,2})点(半|(\d{1,2})分?)?",
        message,
    )
    if time_match:
        groups = time_match.groups()
        if groups[1] is not None:
            period, hour, minute = groups[0], int(groups[1]), int(groups[2])
        else:
            period, hour = groups[3], int(groups[4])
            minute = 30 if groups[5] == "半" else int(groups[6] or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            parsed_hour = hour + minute / 60
            if period in ("晚上", "傍晚", "下午", "今晚") and hour < 12:
                parsed_hour += 12
            if period in ("凌晨", "早上", "上午") and hour == 12:
                parsed_hour = minute / 60
            if period == "中午" and hour < 11:
                parsed_hour += 12
            preferences["hour"] = parsed_hour % 24

    if any(word in message for word in ("一个人", "独自", "单人", "自己吃")):
        preferences["scene"] = "独自用餐"
    elif any(word in message for word in ("朋友", "聚会", "同事", "多人")):
        preferences["scene"] = "朋友聚会"
    elif any(word in message for word in ("夜宵", "出游", "逛街", "散步")):
        preferences["scene"] = "出游夜宵"

    if any(word in message for word in ("小龙虾", "虾")):
        preferences["cuisine"] = "小龙虾"
    elif any(word in message for word in ("烧烤", "烤肉", "烤串")):
        preferences["cuisine"] = "烧烤"
    elif any(word in message for word in ("清淡", "粥", "面条", "粉面")):
        preferences["cuisine"] = "粥粉面"
    elif any(word in message for word in ("家常菜", "家常口味")):
        preferences["cuisine"] = "家常菜"
    elif any(word in message for word in ("湖北菜", "武汉特色", "本地菜")):
        preferences["cuisine"] = "湖北菜"

    return preferences


def recommend(connection, preferences, session_id):
    """Filter impossible options first, then rank feasible merchants transparently."""
    districts = {
        row["name"]: (row["lat"], row["lng"])
        for row in connection.execute("SELECT name, lat, lng FROM districts")
    }
    selected_district = preferences["district"]
    if selected_district not in districts:
        selected_district = next(iter(districts), "")
        preferences["district"] = selected_district

    origin = districts.get(selected_district, (None, None))
    merchants = list_merchants(
        connection,
        district=selected_district,
        cuisine=preferences["cuisine"],
        max_price=preferences["budget"],
        limit=200,
    )
    feasible = []
    requested_hour = preferences["hour"]
    business_hour = requested_hour + 24 if requested_hour < 12 else requested_hour

    for merchant in merchants:
        if merchant["wait"] > preferences["wait"]:
            continue
        if merchant["opens"] is None or not (
            merchant["opens"] <= business_hour < merchant["closes"]
        ):
            continue

        distance = 0.0
        if origin[0] is not None and merchant["lat"] is not None:
            distance = round(
                math.hypot(
                    (merchant["lat"] - origin[0]) * 111,
                    (merchant["lng"] - origin[1]) * 96,
                ),
                1,
            )

        budget_score = 25 * (1 - merchant["price"] / preferences["budget"] * 0.5)
        distance_score = 25 / (1 + distance / 2)
        wait_score = 20 * (
            1 - merchant["wait"] / max(preferences["wait"], 1) * 0.6
        )
        scene_score = 20 if preferences["scene"] in merchant["tags"] else 8
        rating_score = merchant["rating"] / 5 * 10
        parts = {
            "预算": round(budget_score, 1),
            "距离": round(distance_score, 1),
            "等待": round(wait_score, 1),
            "场景": round(scene_score, 1),
            "评分": round(rating_score, 1),
        }
        merchant["distance"] = distance
        merchant["score"] = round(sum(parts.values()), 1)
        merchant["parts"] = parts
        merchant["reasons"] = [
            "人均约 ¥{}，在当前预算内".format(merchant["price"]),
            "预计等位 {} 分钟".format(merchant["wait"]),
            "距所选商圈中心约 {} 公里（直线估算）".format(distance),
        ]
        merchant["explanation"] = json.dumps(parts, ensure_ascii=False)
        feasible.append(merchant)

    feasible.sort(key=lambda item: item["score"], reverse=True)
    save_recommendation_run(connection, session_id, preferences, feasible)
    return feasible


def _local_reply(preferences, items):
    district = preferences["district"] or "你选择的商圈"
    if not items:
        return (
            "我按你的条件看了一遍，目前没有合适的演示商户。"
            "可以试着放宽一点预算或等待时间，也可以换个商圈再看看。"
        )

    first = items[0]
    return (
        "我先帮你从{}附近挑了一轮。按人均{}元、等位{}分钟以内的条件，"
        "目前有{}家可以考虑。{}人均约{}元，预计等位{}分钟，"
        "和你刚才说的需求比较接近。".format(
            district,
            preferences["budget"],
            preferences["wait"],
            len(items),
            first["name"],
            first["price"],
            first["wait"],
        )
    )


def _build_tips(preferences, items):
    tips = []
    if preferences["budget"] <= 50:
        tips.append("预算比较精简，可以先看人均价格，再给饮料或加菜留一点余量。")
    if preferences["wait"] <= 20:
        tips.append("如果不想久等，出发前最好再问一下现场排队情况。")
    if preferences["scene"] == "朋友聚会":
        tips.append("多人一起吃的话，可以提前确认座位和是否方便拼桌。")
    elif preferences["scene"] == "独自用餐":
        tips.append("一个人吃饭，可以优先考虑上菜节奏和单人份菜品。")
    if preferences["hour"] >= 23 or preferences["hour"] < 5:
        tips.append("现在选择的是较晚时段，营业时间是演示数据，出发前请核实。")
    if not tips:
        tips.append("可以先看两三家商户的介绍和菜单，再按当晚心情决定。")
    if not items:
        tips.append("可以先把预算提高 10–20 元，或把等待时间放宽到 40 分钟。")
    return tips[:3]


def _response_text(response_data):
    direct_text = response_data.get("output_text")
    if direct_text:
        return direct_text.strip()

    parts = []
    for output_item in response_data.get("output", []):
        if output_item.get("type") != "message":
            continue
        for content in output_item.get("content", []):
            if content.get("type") == "output_text":
                parts.append(content.get("text", ""))
    return "\n".join(parts).strip()


def _ask_openai(message, history, preferences, items):
    """Call the OpenAI Responses API only from the server, never expose the key."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    model = os.environ.get("OPENAI_MODEL", "gpt-5.5").strip()
    base_url = os.environ.get(
        "OPENAI_BASE_URL", "https://api.openai.com/v1/responses"
    ).strip()
    if not base_url.startswith("https://"):
        raise ValueError("AI 服务地址必须使用 HTTPS")

    safe_history = []
    for entry in history[-8:]:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        content = str(entry.get("content", "")).strip()[:500]
        if role in ("user", "assistant") and content:
            safe_history.append({"role": role, "content": content})

    candidates = [
        {
            "name": item["name"],
            "district": item["district"],
            "cuisine": item["cuisine"],
            "price_per_person": item["price"],
            "wait_minutes": item["wait"],
            "match_score": item["score"],
            "description": item["description"],
        }
        for item in items[:8]
    ]
    context_text = (
        "用户最新需求：{}\n"
        "已解析条件：{}\n"
        "数据库中符合条件的商户：{}\n"
        "请结合这些候选商户回答。若列表为空，诚实说明没有符合项并建议放宽条件。"
        "不要虚构商家、地址、营业状态、电话、评价或实时排队信息。"
    ).format(
        message,
        json.dumps(preferences, ensure_ascii=False),
        json.dumps(candidates, ensure_ascii=False),
    )
    input_messages = safe_history + [
        {"role": "user", "content": context_text}
    ]
    request_body = {
        "model": model,
        "instructions": (
            "你是夜寻的餐饮规划助手。用自然、轻松、真诚的中文交流，"
            "像熟悉本地生活的朋友一样给建议，不要使用夸张营销话术。"
            "优先回应用户真正关心的事，简短说明推荐理由，并给出一到两条实用建议。"
            "只能推荐数据库候选列表中的商家；所有价格、评分和等待信息都要以候选数据为准。"
            "本项目的商户数据是演示数据，不能暗示它们是真实商家。"
        ),
        "input": input_messages,
        "max_output_tokens": 420,
        "store": False,
    }
    request = urllib.request.Request(
        base_url,
        data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        data = json.loads(response.read().decode("utf-8"))
    text = _response_text(data)
    return text or None


def chat(connection, payload, session_id, districts):
    """Build a grounded recommendation, then add natural-language AI guidance."""
    message = str(payload.get("message", "")).strip()
    if not message or len(message) > 2000:
        raise ValueError("请写下你的需求（最多 2000 个字符）")

    preferences = parse_preferences(
        message, payload.get("context"), districts
    )
    items = recommend(connection, preferences, session_id)
    # Finish the short database write before waiting for an external AI response.
    connection.commit()
    tips = _build_tips(preferences, items)
    history = payload.get("history", [])
    if not isinstance(history, list):
        history = []

    mode = "local"
    is_help_request = any(
        word in message for word in ("怎么用", "帮助", "你能做什么", "功能介绍")
    )
    reply = _local_reply(preferences, items)
    if is_help_request:
        reply = (
            "你可以像和朋友商量晚饭一样告诉我：想去哪一片、人均大概多少、"
            "几点到、能等多久，以及喜欢什么口味。我会先按这些条件筛选，"
            "再把合适的商家和推荐理由列给你。"
        )

    if os.environ.get("OPENAI_API_KEY", "").strip():
        try:
            ai_reply = _ask_openai(message, history, preferences, items)
            if ai_reply:
                reply = ai_reply
                mode = "openai"
            else:
                mode = "fallback"
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            mode = "fallback"

    return {
        "reply": reply,
        "items": items[:8],
        "total": len(items),
        "constraints": preferences,
        "tips": tips,
        "mode": mode,
    }
