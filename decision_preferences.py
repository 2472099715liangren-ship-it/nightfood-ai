"""Turn a dining request into small, editable constraints.

No restaurant facts come from the model. Local parsing works without a key;
optional Responses API extraction only adds request fields. Every turn is validated.
"""

import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from real_catalog import WUHAN_DISTRICTS

try:
    LOCAL_ZONE = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:
    # Windows may lack IANA data. Modern Shanghai uses UTC+8 without DST.
    LOCAL_ZONE = timezone(timedelta(hours=8), "Asia/Shanghai")
# Approximate district centers, not device locations or route destinations.
LANDMARKS = {
    "江汉路": (30.586, 114.291, "江汉区"),
    "楚河汉街": (30.557, 114.342, "武昌区"),
    "光谷": (30.506, 114.402, "洪山区"),
    "粮道街": (30.545, 114.307, "武昌区"),
}
CUISINES = (
    "湖北菜",
    "烧烤",
    "小龙虾",
    "火锅",
    "面食",
    "家常菜",
    "清淡",
    "素食",
    "咖啡",
    "奶茶",
    "汉堡",
    "披萨",
    "日料",
    "中餐",
    "快餐",
)
DEFAULTS = dict(
    party_size=None,
    budget=None,
    budget_kind=None,
    location=None,
    arrival=None,
    arrival_date_inferred=False,
    cuisine="",
    avoid=[],
    radius_km=None,
    wait_minutes=None,
    priority="balanced",
    provenance={},
)


def local_now():
    return datetime.now(LOCAL_ZONE)


def chinese_number(text):
    """The common integer forms used for people, hours and meal budgets."""
    digits = dict(zip("零一二三四五六七八九", range(10)))
    digits["两"] = 2
    if text.isdigit():
        return int(text)
    total = current = 0
    for char in text:
        if char in digits:
            current = digits[char]
        elif char in "十百千":
            total += (current or 1) * {"十": 10, "百": 100, "千": 1000}[char]
            current = 0
        else:
            raise ValueError("无法识别这个数字")
    return total + current


def resolve_location(value):
    """Only known local landmarks and explicit device coordinates are resolved."""
    if not isinstance(value, dict):
        return None
    name = str(value.get("name", "")).strip()[:100]
    if not name:
        return None
    for landmark, (lat, lng, district) in LANDMARKS.items():
        if landmark in name:
            return dict(
                name=landmark,
                latitude=lat,
                longitude=lng,
                district=district,
                note="商圈中心近似位置，距离为直线估算",
            )
    for district in WUHAN_DISTRICTS:
        if district in name:
            return dict(
                name=district,
                latitude=None,
                longitude=None,
                district=district,
                note="仅按行政区筛选，尚不能计算距离",
            )
    if value.get("latitude") is not None or value.get("longitude") is not None:
        lat, lng = float(value.get("latitude")), float(value.get("longitude"))
        if not (29.8 <= lat <= 31.5 and 113.5 <= lng <= 115.2):
            raise ValueError("当前版本只支持武汉范围的位置")
        return dict(
            name=name,
            latitude=lat,
            longitude=lng,
            district="",
            note="用户提供的 WGS84 坐标",
        )
    return None


def validate_preferences(raw):
    raw = raw if isinstance(raw, dict) else {}
    result = {key: raw.get(key, default) for key, default in DEFAULTS.items()}
    for key, low, high in (
        ("party_size", 1, 50),
        ("budget", 1, 100000),
        ("radius_km", 0.1, 100),
        ("wait_minutes", 0, 180),
    ):
        if result[key] is not None:
            try:
                number = float(result[key])
            except (TypeError, ValueError, OverflowError) as error:
                raise ValueError("人数、预算、距离和等待时间需要是有效数字") from error
            if not math.isfinite(number) or not low <= number <= high:
                raise ValueError("人数、预算、距离或等待时间超出支持范围")
            if key in ("party_size", "wait_minutes") and not number.is_integer():
                raise ValueError("人数和等待分钟数需要是整数")
            result[key] = (
                int(number) if key in ("party_size", "wait_minutes") else number
            )
    if result["budget_kind"] not in (None, "total", "per_person"):
        raise ValueError("预算单位需要是总预算或人均预算")
    result["location"] = resolve_location(result["location"])
    if result["arrival"]:
        arrival = datetime.fromisoformat(str(result["arrival"]))
        if arrival.tzinfo is None:
            arrival = arrival.replace(tzinfo=LOCAL_ZONE)
        result["arrival"] = arrival.astimezone(LOCAL_ZONE).isoformat(timespec="minutes")
    result["arrival_date_inferred"] = bool(result["arrival_date_inferred"])
    result["cuisine"] = str(result["cuisine"] or "")[:40]
    if not isinstance(result["avoid"], list) or len(result["avoid"]) > 10:
        raise ValueError("忌口需要是最多 10 项的列表")
    result["avoid"] = list(
        dict.fromkeys(str(item)[:40] for item in result["avoid"] if item)
    )
    result["priority"] = (
        result["priority"]
        if result["priority"] in ("balanced", "distance", "budget")
        else "balanced"
    )
    provenance = result["provenance"] if isinstance(result["provenance"], dict) else {}
    result["provenance"] = {
        k: v
        for k, v in provenance.items()
        if k in DEFAULTS and v in ("user", "inferred", "device")
    }
    return result


def _extract_with_ai(message, now):
    """Optional semantic extraction; return data only, never merchant suggestions."""
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return {}
    endpoint = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1/responses")
    if not endpoint.startswith("https://"):
        raise ValueError("AI 地址必须使用 HTTPS")
    body = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-5.5"),
        "store": False,
        "instructions": (
            "只提取用户本轮明确说出的餐饮条件，返回一个JSON对象，不要Markdown。"
            "可用字段：party_size整数；budget数字；budget_kind为total或per_person；"
            "location为{name:原文位置}；arrival为带+08:00的ISO到店时间；"
            "cuisine字符串；avoid忌口数组；radius_km数字；wait_minutes整数。"
            "没有提及的字段省略。预算单位模糊时不要猜。禁止编造坐标或餐厅信息。"
            "人数不能从聚会二字推断。当前北京时间：" + now.isoformat()
        ),
        "input": message,
        "max_output_tokens": 500,
    }
    request = Request(
        endpoint,
        data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=15) as response:
        output = json.load(response)
    text = output.get("output_text") or "".join(
        part.get("text", "")
        for item in output.get("output", [])
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    )
    fields = json.loads(text)
    if not isinstance(fields, dict):
        raise ValueError("AI 条件格式无效")
    allowed = set(DEFAULTS) - {"provenance", "priority", "arrival_date_inferred"}
    fields = {
        key: value
        for key, value in fields.items()
        if key in allowed and value is not None
    }
    if "location" in fields:
        fields["location"] = {"name": str(fields["location"].get("name", ""))}
    return fields


def parse_request(message, context=None, location=None, now=None):
    """Merge a single turn; defaults never masquerade as explicit choices."""
    now = now or local_now()
    preferences = validate_preferences(context)
    changes = {}
    mode = "local"
    if os.environ.get("OPENAI_API_KEY", "").strip():
        try:
            changes = _extract_with_ai(message, now)
            validate_preferences({**preferences, **changes})
            mode = "ai"
        except (URLError, OSError, ValueError, TypeError, AttributeError, KeyError):
            changes, mode = {}, "fallback"
    text = re.sub(
        r"[零一二两三四五六七八九十百千]+",
        lambda match: str(chinese_number(match.group())),
        message,
    )
    # A diner with a dietary restriction is not a change to the whole party.
    describes_diner = (
        preferences["party_size"]
        and any(word in text for word in ("不吃", "过敏", "忌口", "不能吃"))
        and not re.search(r"改成|改为|人数|一共|总共|现在是|我们(?:是)?\d+", text)
    )
    if describes_diner:
        changes.pop("party_size", None)
    else:
        match = re.search(r"(\d+)\s*(?:个人|人|位)", text)
        if match:
            changes["party_size"] = int(match[1])
    if re.search(r"^(?:我|就我|今晚)?自己吃", message):
        changes["party_size"] = 1
    match = re.search(
        r"(人均|每人|总共|总预算|一共|合计|预算)\s*(?:不超过|最多|约|在|为|降到|提高到|改成|改为)?\s*[¥￥]?\s*(\d+(?:\.\d+)?)",
        text,
    )
    if match:
        changes["budget"] = float(match[2])
        changes["budget_kind"] = (
            "per_person"
            if match[1] in ("人均", "每人")
            else preferences["budget_kind"] if match[1] == "预算" else "total"
        )
    else:
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块)", text)
        if match:
            changes.update(budget=float(match[1]), budget_kind=None)
    # Unit-only replies resolve the previous budget without losing its amount.
    if "budget" not in changes:
        if "人均" in text or "每人" in text:
            changes["budget_kind"] = "per_person"
        elif "总预算" in text or "总共" in text or "总价" in text:
            changes["budget_kind"] = "total"
    place = next((name for name in LANDMARKS if name in message), None)
    place = place or next((name for name in WUHAN_DISTRICTS if name in message), None)
    if place:
        changes["location"] = {"name": place}
    elif re.search(r"(?:在|去|到).+?(?:附近|吃饭|用餐)", message):
        # A newly mentioned unknown place must not silently reuse the old origin.
        changes["location"] = None
    unsupported_day = re.search(r"下周|本周|周末|周[1-7]|星期[1-7]", text)
    hour = re.search(
        r"(凌晨|上午|中午|下午|傍晚|晚上|今晚)?\s*(\d{1,2})(?:[:：](\d{2})|点(半|\d{1,2}分?)?)",
        text,
    )
    if unsupported_day and "arrival" not in changes:
        changes["arrival"] = None
    if hour and not unsupported_day:
        period, value, minutes, suffix = hour.groups()
        h = int(value)
        minute = int(
            minutes or (30 if suffix == "半" else (suffix or "0").rstrip("分"))
        )
        if not 0 <= h < 24 or not 0 <= minute < 60:
            raise ValueError("请给出有效的到店时间")
        if (period in ("下午", "傍晚", "晚上", "今晚") or "今晚" in text) and h < 12:
            h += 12
        if period in ("凌晨", "上午") and h == 12:
            h = 0
        if period == "中午" and h < 11:
            h += 12
        day_offset = 2 if "后天" in text else 1 if "明天" in text else 0
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", text)
        day = (
            datetime.fromisoformat(date_match[0]).date()
            if date_match
            else (now + timedelta(days=day_offset)).date()
        )
        changes["arrival_date_inferred"] = not (
            date_match or any(word in text for word in ("今天", "今晚", "明天", "后天"))
        )
        changes["arrival"] = (
            datetime.combine(day, datetime.min.time(), LOCAL_ZONE)
            .replace(hour=h, minute=minute)
            .isoformat(timespec="minutes")
        )
    elif ("明天" in text or "后天" in text or "今天" in text) and preferences[
        "arrival"
    ]:
        previous = datetime.fromisoformat(preferences["arrival"])
        day = (
            now + timedelta(days=2 if "后天" in text else 1 if "明天" in text else 0)
        ).date()
        changes["arrival_date_inferred"] = False
        changes["arrival"] = datetime.combine(day, previous.timetz()).isoformat(
            timespec="minutes"
        )
    if "现在" in text:
        changes["arrival_date_inferred"] = False
        changes["arrival"] = now.isoformat(timespec="minutes")
    for cuisine in CUISINES:
        if cuisine in message and not re.search(r"(?:不吃|不要)" + cuisine, message):
            changes["cuisine"] = cuisine
            break
    if "不限口味" in text or "不限制口味" in text:
        changes["cuisine"] = ""
    avoid = re.findall(
        r"(?:不吃|忌口|不能吃)\s*([\u4e00-\u9fff]{1,8}?)(?=[，。；、！\s]|$)", message
    )
    avoid += re.findall(r"([\u4e00-\u9fff]{1,5})过敏", message)
    if "没有忌口" in text or "取消忌口" in text:
        changes["avoid"] = []
    elif avoid:
        changes["avoid"] = list(dict.fromkeys(preferences["avoid"] + avoid))
    distance = re.search(r"(\d+(?:\.\d+)?)\s*(?:公里|千米|km)", text, re.I)
    if distance:
        changes["radius_km"] = float(distance[1])
    if "不限距离" in text:
        changes["radius_km"] = None
    wait = re.search(r"(?:等位|等待|排队|等)\s*(?:最多|不超过)?\s*(\d+)\s*分钟", text)
    if wait:
        changes["wait_minutes"] = int(wait[1])
    if "近一点" in text or "找近" in text:
        changes["priority"] = "distance"
    if "便宜" in text or "太贵" in text:
        changes["priority"] = "budget"
    provenance = dict(preferences["provenance"])
    provenance.update({key: "user" for key in changes})
    if location is not None:
        changes["location"] = location
        provenance["location"] = "device"
    result = validate_preferences({**preferences, **changes, "provenance": provenance})
    return result, mode


def per_person_budget(preferences):
    amount = preferences["budget"]
    if amount is None or not preferences["budget_kind"]:
        return None
    if preferences["budget_kind"] == "total":
        return amount / preferences["party_size"] if preferences["party_size"] else None
    return amount


def next_question(preferences, now=None):
    """Ask one necessary question at a time; cuisine can stay unrestricted."""
    checks = (
        (
            not preferences["location"],
            "你准备从哪里出发？目前可识别江汉路、楚河汉街、光谷、粮道街及武汉行政区，也可以使用当前位置。",
            ["江汉路附近", "楚河汉街附近", "光谷附近"],
        ),
        (
            not preferences["party_size"],
            "一共有几个人用餐？",
            ["一个人", "两个人", "四个人"],
        ),
        (
            preferences["budget"] is None,
            "这顿饭预算大概多少？请说明是人均还是总预算。",
            ["人均50元", "人均80元", "总预算300元"],
        ),
        (
            not preferences["budget_kind"],
            "刚才的预算是每个人的，还是所有人加起来的总预算？",
            ["是人均预算", "是总预算"],
        ),
        (
            not preferences["arrival"],
            "预计什么时候到店？可以说“今晚七点”或“明天中午十二点”。",
            ["现在出发", "今晚七点", "明天中午十二点"],
        ),
    )
    for missing, question, actions in checks:
        if missing:
            return {"question": question, "actions": actions}
    if datetime.fromisoformat(preferences["arrival"]) < (
        now or local_now()
    ) - timedelta(minutes=30):
        return {
            "question": "这个到店时间已经过去了，请确认是明天还是另一个时间。",
            "actions": ["明天同一时间", "现在出发"],
        }
    return None
