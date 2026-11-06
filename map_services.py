"""Optional map configuration and real walking routes. Web-service keys stay server-side."""

import json
import math
import os
import re
import time
from functools import lru_cache
from urllib.parse import urlencode
from urllib.request import urlopen

from geo_coordinates import gcj02_to_wgs84, wgs84_to_gcj02


def public_map_config():
    # TIANDITU_KEY is a browser map key: restrict its domain at the provider.
    # AMAP_WEB_KEY is private and deliberately absent from this response.
    key = os.environ.get("TIANDITU_KEY", "").strip()
    return dict(
        provider="tianditu" if key else "osm",
        tianditu_key=key,
        walking_enabled=bool(os.environ.get("AMAP_WEB_KEY", "").strip()),
    )


def coordinate(value):
    if not isinstance(value, dict):
        raise ValueError("请提供武汉范围的出发位置")
    try:
        lat, lng = float(value["latitude"]), float(value["longitude"])
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("位置需要有效的经纬度") from error
    if not (
        math.isfinite(lat)
        and math.isfinite(lng)
        and 29.8 <= lat <= 31.5
        and 113.5 <= lng <= 115.2
    ):
        raise ValueError("路线目前仅支持武汉范围")
    return lat, lng


def amap_navigation(origin, destination, name):
    start = wgs84_to_gcj02(*origin)
    end = wgs84_to_gcj02(*destination)
    return "https://uri.amap.com/navigation?" + urlencode(
        dict(
            **{"from": f"{start[1]:.6f},{start[0]:.6f},出发点"},
            to=f"{end[1]:.6f},{end[0]:.6f},{name}",
            mode="walk",
            coordinate="gaode",
            src="nightfind",
            callnative=0,
        )
    )


@lru_cache(maxsize=128)
def _fetch_route(origin, destination, key, time_bucket):
    start = wgs84_to_gcj02(*origin)
    end = wgs84_to_gcj02(*destination)
    query = urlencode(
        dict(
            key=key,
            origin=f"{start[1]:.6f},{start[0]:.6f}",
            destination=f"{end[1]:.6f},{end[0]:.6f}",
        )
    )
    # Fixed host and endpoint: neither credentials nor target URLs come from a visitor.
    with urlopen(
        "https://restapi.amap.com/v3/direction/walking?" + query, timeout=8
    ) as response:
        data = json.loads(response.read(2_000_000))
    if data.get("status") != "1":
        raise ValueError("路线服务暂不可用")
    paths = (data.get("route") or {}).get("paths") or []
    if not paths:
        raise ValueError("服务未找到步行路线")
    path = paths[0]
    distance, duration = float(path["distance"]), float(path["duration"])
    if (
        not math.isfinite(distance)
        or not math.isfinite(duration)
        or distance <= 0
        or duration <= 0
    ):
        raise ValueError("路线数据无效")
    points, steps = [], []
    for step in path.get("steps", []):
        instruction = re.sub(r"<[^>]*>", "", str(step.get("instruction", "")))[:300]
        if instruction:
            steps.append(instruction)
        for pair in str(step.get("polyline", "")).split(";"):
            if not pair:
                continue
            lng, lat = map(float, pair.split(","))
            point = gcj02_to_wgs84(lat, lng)
            coordinate(dict(latitude=point[0], longitude=point[1]))
            if not points or points[-1] != point:
                points.append(point)
    return dict(
        status="ready",
        distance_m=round(distance),
        duration_seconds=round(duration),
        points=points,
        steps=steps,
        source_name="高德步行路线",
        coordinate_system="WGS84",
    )


def walking_route(origin_value, merchant):
    origin = coordinate(origin_value)
    if merchant.get("latitude") is None or merchant.get("longitude") is None:
        return dict(
            status="missing_destination",
            notice="这家门店尚无可靠坐标，请按店名和地址在地图中查找。",
            navigation_url=merchant.get("map_search_url"),
        )
    destination = coordinate(merchant)
    base = dict(
        navigation_url=amap_navigation(origin, destination, merchant["name"]),
        origin_name=str(origin_value.get("name") or "出发点")[:100],
        origin_note=str(origin_value.get("note") or "")[:200],
    )
    key = os.environ.get("AMAP_WEB_KEY", "").strip()
    if not key:
        return dict(
            **base,
            status="unconfigured",
            notice="打开高德可查看实际步行路线与预计时间。",
        )
    try:
        result = _fetch_route(
            tuple(round(x, 6) for x in origin),
            tuple(round(x, 6) for x in destination),
            key,
            int(time.time() // 600),
        )
        return dict(**base, **result)
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        # Do not return upstream URLs, keys, or stack traces to the browser.
        return dict(
            **base,
            status="unavailable",
            notice="暂时未能读取路线，可重试或在高德继续查看。",
        )
