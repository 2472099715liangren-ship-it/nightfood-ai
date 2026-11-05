# 武汉地理底图

`wuhan-basemap.geojson` 是随应用分发的真实地理数据，不需要地图 API Key。坐标使用 WGS84，与商家 OSM 点位一致，由 Leaflet 投影到地图。`wuhan-basemap.meta.json` 记录原文件链接、SHA-256、各层数量和生成日期。

本 GeoJSON 作为 OpenStreetMap 派生数据库按 ODbL 1.0 提供；其中 Natural Earth 原始部分属公有领域。

## 来源与许可

- 武汉市行政边界、600 段主干道路、地铁站、公园及水域名称：来自 [GeoClaw_Claude 的武汉 GIS 数据](https://github.com/whuyao/GeoClaw_Claude/tree/2ae23e3aa6d105748d8a4715e4d39f4f8c9c548e/data/wuhan)，保留原始 OSM ID。底层 OpenStreetMap 数据采用 [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/)，署名 © OpenStreetMap contributors；可从本仓库取得派生地理数据及来源信息。上游程序的 MIT 说明不替代 OSM 数据许可。
- 长江、汉江中心线及武汉范围附近的 19 个湖泊多边形：来自 [Natural Earth 1:10m](https://github.com/nvkelso/natural-earth-vector/tree/master/geojson)，数据属[公有领域](https://www.naturalearthdata.com/about/terms-of-use/)。中文水域标签直接取来源名称，Yangtze / Han 分别译为长江 / 汉江。

## 处理方法

原始行政边界和道路几何保留；点地名去除无名记录，同层同名只保留首条；仅保留名称、OSM ID、道路分类。Natural Earth 数据筛选与武汉附近经纬范围相交的湖泊及河流；河流只保留武汉周边的原始折线段。所有坐标保留六位小数，按 `layer` 合并为 FeatureCollection。没有把公园或水域中心点推造成面积，没有根据商家名称猜测位置。

图层：`boundary`、`road`、`river`、`lake`、`park`、`station`、`water_label`。修改配色、文字密度、默认视野和商家标记时，编辑 `../wuhan_map.js` 与 `../decision.css` 即可。

## 显示与精度

先显示本地底图，再尝试加载 OpenStreetMap 在线街道瓦片。瓦片失败立即移除在线层，保留真实的本地道路、水域、地名和商家点位；不批量下载或缓存在线瓦片。在线瓦片仅用于当前低访问量的本地原型预览，遵守 [OSM 瓦片政策](https://operations.osmfoundation.org/policies/tiles/)。

本地层是地理简图：道路不是完整街道网络，Natural Earth 河流湖泊经过比例尺概化；深度放大不能提供街巷或建筑细节。它用于理解商家所在区域，不承担道路导航。精确到店路线仍交给外部地图，商家源坐标不随底图概化而改动。

更新时应从上述来源取得真实数据，保留源 ID、坐标系及许可，并同步更新元数据中的原文件校验值和数量。底图生成日期不表示商家或 OSM 源记录当天更新。
