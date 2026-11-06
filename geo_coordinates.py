"""WGS84 ↔ GCJ-02 conversion for explicitly labelled mainland map coordinates."""

import math


def wgs84_to_gcj02(latitude, longitude):
    if not (72.004 <= longitude <= 137.8347 and 0.8293 <= latitude <= 55.8271):
        return latitude, longitude
    x, y = longitude - 105, latitude - 35
    dlat = -100 + 2 * x + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    dlng = 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    wave = (20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)) * 2 / 3
    dlat += wave + (20 * math.sin(y * math.pi) + 40 * math.sin(y * math.pi / 3)) * 2 / 3
    dlat += (
        (160 * math.sin(y * math.pi / 12) + 320 * math.sin(y * math.pi / 30)) * 2 / 3
    )
    dlng += wave + (20 * math.sin(x * math.pi) + 40 * math.sin(x * math.pi / 3)) * 2 / 3
    dlng += (
        (150 * math.sin(x * math.pi / 12) + 300 * math.sin(x * math.pi / 30)) * 2 / 3
    )
    radians = latitude / 180 * math.pi
    magic = 1 - 0.00669342162296594323 * math.sin(radians) ** 2
    dlat = (
        dlat
        * 180
        / (
            (6378245 * (1 - 0.00669342162296594323))
            / (magic * math.sqrt(magic))
            * math.pi
        )
    )
    dlng = dlng * 180 / (6378245 / math.sqrt(magic) * math.cos(radians) * math.pi)
    return latitude + dlat, longitude + dlng


def gcj02_to_wgs84(latitude, longitude):
    """Invert by iteration; do not apply this to an already-WGS84 OSM point."""
    lat, lng = latitude, longitude
    for _ in range(5):
        projected_lat, projected_lng = wgs84_to_gcj02(lat, lng)
        lat -= projected_lat - latitude
        lng -= projected_lng - longitude
    return round(lat, 7), round(lng, 7)
