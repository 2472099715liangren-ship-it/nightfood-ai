"""Conversation refinement and contextual follow-up suggestions.

These are lightweight, transparent conversation helpers. The restaurant facts and
ranking still come from the database/recommendation service, not an LLM.
"""
import re

FIELDS = ("district", "budget", "wait", "hour", "scene", "cuisine")


def refine_preferences(message, prior_context, preferences, districts):
    """Remember explicit choices across turns and apply short change requests.

    The returned \`known\` flags distinguish user-supplied preferences from defaults.
    Never assume that a default district/budget was explicitly chosen.
    """
    prior = prior_context if isinstance(prior_context, dict) else {}
    known = {
        field for field in prior.get("known", [])
        if isinstance(field, str) and field in FIELDS
    } if isinstance(prior.get("known"), list) else set()

    if any(item["name"] in message for item in districts):
        known.add("district")
    if re.search(r"(?:人均|预算|每人|每位|¥|￥)\s*(?:在|为|约)?\s*\d{1,3}", message) or re.search(r"\d{1,3}\s*(?:元|块)", message):
        known.add("budget")
    if re.search(r"(?:等位|排队|等待|不想等|不排队|少等|分钟)", message):
        known.add("wait")
    if re.search(r"\d{1,2}\s*(?:[:：]\d{2}|点)", message) or re.search(
        r"[零一二两三四五六七八九十]{1,3}点", message
    ):
        known.add("hour")
    if any(word in message for word in ("一个人", "独自", "单人", "自己吃", "朋友", "聚会", "同事", "多人", "夜宵", "出游", "逛街")):
        known.add("scene")
    if any(word in message for word in ("小龙虾", "烧烤", "烤肉", "烤串", "清淡", "粥", "粉面", "家常菜", "湖北菜", "武汉特色")):
        known.add("cuisine")

    if any(word in message for word in ("便宜一点", "再便宜点", "省一点", "降低预算")):
        preferences["budget"] = max(10, preferences["budget"] - 20)
        known.add("budget")
    if any(word in message for word in ("少等一会", "等位短一点", "不想久等")):
        preferences["wait"] = max(0, preferences["wait"] - 10)
        known.add("wait")
    if any(word in message for word in ("放宽预算", "预算高一点", "贵一点也行")):
        preferences["budget"] = min(500, preferences["budget"] + 20)
        known.add("budget")
    if "不限制口味" in message or "不限口味" in message:
        preferences["cuisine"] = "不限"
        known.add("cuisine")

    return preferences, sorted(known)


def follow_up_suggestions(preferences, known, districts, items):
    """Ask for a useful missing preference, then offer concrete adjustments."""
    if "district" not in known:
        return {
            "question": "你现在更方便去哪个商圈？选一个就行。",
            "actions": [
                {"label": district["name"], "message": district["name"]}
                for district in districts[:4]
            ],
        }
    if "budget" not in known:
        return {
            "question": "人均大概想花多少？我可以再帮你缩小范围。",
            "actions": [
                {"label": "50 元以内", "message": "人均 50 元以内"},
                {"label": "80 元以内", "message": "人均 80 元以内"},
                {"label": "120 元以内", "message": "人均 120 元以内"},
            ],
        }
    if "cuisine" not in known:
        return {
            "question": "口味上有没有特别想吃的？也可以先不限制。",
            "actions": [
                {"label": "想吃烧烤", "message": "想吃烧烤"},
                {"label": "清淡一点", "message": "想吃清淡一点"},
                {"label": "不限口味", "message": "不限口味"},
            ],
        }

    if not items:
        return {
            "question": "这些条件有点紧，要不要换个方向再看看？",
            "actions": [
                {"label": "预算高一点", "message": "放宽预算"},
                {"label": "多等一会儿", "message": "等位最多 40 分钟"},
                {"label": "不限口味", "message": "不限口味"},
            ],
        }
    return {
        "question": "还想怎么调整？我可以接着帮你挑。",
        "actions": [
            {"label": "便宜一点", "message": "便宜一点"},
            {"label": "少等一会", "message": "少等一会"},
            {"label": "换一批", "message": "换一批"},
        ],
    }


def choose_candidate_round(items, message, already_seen):
    """Rotate among eligible merchants only when the visitor requests another batch."""
    if not any(phrase in message for phrase in ("换一批", "再换几家", "看看别的")):
        return items, False
    previous_ids = set()
    if isinstance(already_seen, list):
        for value in already_seen[:80]:
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if number > 0:
                previous_ids.add(number)
    fresh = [merchant for merchant in items if merchant["id"] not in previous_ids]
    return (fresh if fresh else items), not bool(fresh)
