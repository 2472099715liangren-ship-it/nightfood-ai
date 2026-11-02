"""Download Wuhan OSM restaurants from the provincial Geofabrik PBF extract.

This is a fallback when public Overpass servers are busy. The data file is
OpenStreetMap ODbL. Use only within the Wuhan administrative polygon (OSM
relation 3076268), not a guessed rectangular bounding box.

Requires osmium and shapely only during OFFLINE collection, not for site use.
"""
import argparse
import json
import tempfile
import urllib.request
from pathlib import Path

from osm_sync import (
    MAX_RECORDS, SNAPSHOT, convert_osm_element,
)

PBF_URL = "https://download.geofabrik.de/asia/china/hubei-latest.osm.pbf"
WUHAN_BOUNDARY_URL = (
    "https://raw.githubusercontent.com/whuyao/GeoClaw_Claude/main/"
    "data/wuhan/boundary.geojson"
)


def collect_from_extract(pbf_path, boundary_json):
    """Filter mapped food venues by true Wuhan polygon, using OSM node/way IDs."""
    import osmium
    from shapely.geometry import Point, shape

    features = boundary_json.get("features", [])
    if len(features) != 1:
        raise ValueError("武汉市行政边界必须恰好包含一个要素")
    properties = features[0].get("properties") or {}
    if properties.get("osm_id") != 3076268:
        raise ValueError("武汉行政区边界来源 ID 不匹配")
    polygon = shape(features[0]["geometry"])
    if not polygon.is_valid:
        raise ValueError("武汉市行政边界无效")

    class WuhanFoodHandler(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.records = {}

        def add(self, type_name, osm_id, tags, lat, lon):
            if (
                tags.get("amenity") not in
                ("restaurant", "fast_food", "cafe", "food_court")
                or not tags.get("name")
                or not polygon.covers(Point(lon, lat))
            ):
                return
            record = convert_osm_element({
                "type": type_name,
                "id": osm_id,
                "lat": lat,
                "lon": lon,
                "tags": tags,
            })
            if record:
                self.records[record["external_id"]] = record

        def node(self, node):
            if not node.location.valid():
                return
            tags = {tag.k: tag.v for tag in node.tags}
            self.add("node", node.id, tags, node.location.lat, node.location.lon)

        def way(self, way):
            tags = {tag.k: tag.v for tag in way.tags}
            if tags.get("amenity") not in (
                "restaurant", "fast_food", "cafe", "food_court"
            ) or not tags.get("name"):
                return
            coords = []
            for nd in way.nodes:
                if nd.location.valid():
                    coords.append((nd.location.lat, nd.location.lon))
            if coords:
                # This is an average of tagged way nodes, not a precise entrance.
                lat = sum(pair[0] for pair in coords) / len(coords)
                lon = sum(pair[1] for pair in coords) / len(coords)
                self.add("way", way.id, tags, lat, lon)

    handler = WuhanFoodHandler()
    handler.apply_file(str(pbf_path), locations=True)
    records = [
        handler.records[key] for key in sorted(handler.records)
    ][:MAX_RECORDS]
    if not records:
        raise ValueError("省级数据提取后未得到武汉餐饮场所，不导入空快照")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=SNAPSHOT)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        pbf_path = Path(tmp) / "hubei.osm.pbf"
        request = urllib.request.Request(
            PBF_URL, headers={"User-Agent": "NightFindOSMImporter/1.0"}
        )
        with urllib.request.urlopen(request, timeout=150) as response:
            with pbf_path.open("wb") as destination:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    destination.write(chunk)
                    if destination.tell() > 150 * 1024 * 1024:
                        raise ValueError("Hubei extract exceeded 150 MB")
        with urllib.request.urlopen(WUHAN_BOUNDARY_URL, timeout=45) as resp:
            boundary_json = json.loads(resp.read(5_000_000).decode("utf-8"))
        records = collect_from_extract(pbf_path, boundary_json)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "已从 Geofabrik 湖北 OSM 提取中按武汉行政区边界得到 {} 条餐饮场所。".format(
            len(records)
        ), flush=True,
    )
    print(
        "© OpenStreetMap contributors · ODbL。"
        "社区数据未经人工核实，不应宣称价格、评分或实时营业。",
        flush=True,
    )


if __name__ == "__main__":
    main()
