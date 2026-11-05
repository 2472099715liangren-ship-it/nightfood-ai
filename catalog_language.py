"""Small, editable translations of OSM cuisine tags and common search aliases."""

CUISINE_TERMS = {
    "清淡": ("粥", "面", "清淡", "noodle"),
    "面食": ("面", "粉", "noodle"),
    "湖北菜": ("湖北", "鄂菜", "武汉菜", "hubei"),
    "素食": ("素食", "素菜", "vegetarian"),
    "咖啡": ("咖啡", "coffee", "cafe"),
    "奶茶": ("奶茶", "bubble_tea"),
    "汉堡": ("汉堡", "burger"),
    "披萨": ("披萨", "pizza"),
    "日料": ("日料", "日式", "japanese", "sushi"),
    "烧烤": ("烧烤", "barbecue", "bbq"),
    "中餐": ("中餐", "chinese"),
    "快餐": ("快餐", "fast_food", "burger", "chicken"),
}
BRAND_ALIASES = {
    "肯德基": ("肯德基", "KFC"),
    "麦当劳": ("麦当劳", "McDonald's", "McDonalds"),
    "星巴克": ("星巴克", "Starbucks"),
}
DISPLAY_LABELS = {
    "chinese": "中餐",
    "coffee_shop": "咖啡简餐",
    "coffee": "咖啡",
    "bubble_tea": "奶茶",
    "burger": "汉堡",
    "chicken": "鸡肉快餐",
    "pizza": "披萨",
    "japanese": "日料",
    "sushi": "寿司",
    "barbecue": "烧烤",
    "noodle": "面食",
    "noodles": "面食",
}


def search_terms(keyword):
    terms = [keyword]
    if keyword in CUISINE_TERMS:
        terms.extend(CUISINE_TERMS[keyword])
    for aliases in BRAND_ALIASES.values():
        if keyword.casefold() in {value.casefold() for value in aliases}:
            terms.extend(aliases)
    return list(dict.fromkeys(terms))[:12]


def display_cuisine(raw):
    return "、".join(
        DISPLAY_LABELS.get(part, part) for part in raw.replace(";", "、").split("、")
    )
