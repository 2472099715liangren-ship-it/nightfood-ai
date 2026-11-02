# 武汉真实商家：两年数据门槛、店面照片与地图

本阶段基于 `feature/osm-wuhan-public-data`，在 OSM 社区餐饮候选资料之上增加严格的时效筛选、授权照片审核和地图可视化。真实商家与演示商家保持分离。

## 1. 最近两个自然年是硬性门槛

程序每天按服务器日期滚动计算边界。以 **2026-11-02** 为例，允许日期为 **2024-11-02 至 2026-11-02（含首尾）**。

- 人工核验的真实门店：`source_checked_at`（来源资料实际核查日期）和 `verified_at`（人工核验日期）都必须在有效范围内。
- OSM 社区候选：只有 OSM 标签 `survey:date` 或 `check_date` 明确提供有效日期，才可作为近两年社区资料显示；界面会明确标记“OSM 社区收录，营业状态未核实”。
- OSM 元素最后编辑时间、数据快照下载日期、导入日期都不能替代逐店核查日期。
- 缺日期、未来日期或超过两年的候选记录继续保存在数据库，但不会出现在公开真实商家列表、地图或详情中。
- 曾经通过核验的商家一旦超期，API 读取时会自动隐藏。要重新展示，必须获得更新来源并再次人工核验。
- 没有可信坐标的商家可保留在列表，但不在地图上猜测点位。

**因此，快照中有多少 OSM 候选，并不等于有多少家近两年核验的在营餐厅。** 当前快照缺少逐店调查日期的记录会被隐藏，真实目录显示为空也是正确的保护行为，不会用旧资料或演示数据填充。

## 2. 授权店面照片

OSM 的数据库许可不代表照片也可自由复制。禁止直接拿地图截图、点评网站照片、搜索引擎图片或其他商家图片冒充店面实拍。

一张照片必须同时满足：
1. 由商家/权利人提供，或具有可核验的图片使用授权，且明确允许夜寻存储和展示；
2. 真实拍摄日期在最近两个自然年内；
3. 记录来源凭证、图片权利人、展示许可说明和导入操作员；
4. JPEG、PNG 或 WebP，单张不超过 5 MB；导入前去除 EXIF/XMP 等常见元数据；
5. 导入后由人工审核通过。

照片仅在服务器本地私有目录保存，待审核期间不可公开。商家卡片及详情页展示经审核照片、拍摄日期和权利人；未获得授权照片时会显示“暂无已授权并审核的店面照片”，不会插入虚构照片。门店来源过期、照片拍摄日期过期、授权或审核失效后，照片接口也会拒绝访问。

### 照片导入与审核

先确认门店 ID：

```bash
python3 - <<'PY'
from database import connect
with connect() as db:
    for row in db.execute("SELECT id,name,district FROM real_merchants ORDER BY id"):
        print(row["id"], row["name"], row["district"])
PY
```

然后将已获得展示授权的图片导入待审核区（日期必须是实际拍摄日期）：

```bash
python3 manage_osm_photos.py add \
  --merchant-id 12 \
  --file ./authorized-storefront.jpg \
  --taken-at 2026-10-20 \
  --source-url merchant-submission:photo-2026-001 \
  --copyright-holder "门店经营者" \
  --license-note "已授权夜寻存储并展示此张店面照片" \
  --operator editor \
  --rights-confirmed
```

列出待审核图片：

```bash
python3 manage_osm_photos.py list
```

人工确认图片确为该门店、拍摄日期和权利许可后才批准：

```bash
python3 manage_osm_photos.py approve --photo-id 12 --reviewed-by editor
```

拒绝不符合条件的图片：

```bash
python3 manage_osm_photos.py reject --photo-id 12 --reviewed-by editor
```

图片原文件默认保存在 `data/merchant_photos/`（可用 `MERCHANT_PHOTO_DIR` 指定持久化目录），不应提交到 Git。当前仅提供服务器本地操作员 CLI，不开放游客上传接口。

## 3. 地图体验

商家小册中的真实资料区增加：
- “列表 / 地图”切换；
- 地图与搜索条件、当前分页结果同步；
- 仅显示有效日期和真实坐标都有记录的点位；
- 自动缩放到当前结果范围；
- 点击点位显示门店名、地址、人均价格（如有）、来源核查日期及资料状态；
- 点位按状态区分：绿色为近两年人工核验，蓝灰色为近两年 OSM 社区核查但未确认营业；
- 缺少有效坐标的商家仍可在列表中查阅，不伪造地图位置；
- 保留 OpenStreetMap 署名和 ODbL 来源链接。

地图用 Leaflet 实现。当前 OpenStreetMap 标准瓦片仅适合低流量本地开发/人工预览。正式公开部署或较高访问量时，必须选择明确允许对应商业用途和访问量的地图服务商，并遵守瓦片使用规则；不可批量下载或预缓存社区瓦片。

参考：
- OpenStreetMap 数据许可与署名：https://www.openstreetmap.org/copyright
- OSM 瓦片使用政策：https://operations.osmfoundation.org/policies/tiles/
- Leaflet 快速入门：https://leafletjs.com/examples/quick-start/

## 4. 运行与验证

启动当前分支：

```bash
PORT=8003 sh start.sh
```

访问 `http://localhost:8003`，进入“商家小册”查看“武汉真实商家资料”。

运行完整测试：

```bash
python3 -m unittest discover -s tests -v
node --check static/app.js
node --check static/wuhan_map.js
```

GitHub Actions 也会执行 Python 编译、Python 测试和前端 JavaScript 语法检查。

## 5. 当前数据边界

本分支没有自动取得任何商家照片展示许可，也没有从第三方网站批量下载图片。照片导入链路和审核界面已接入，但在实际收到商家授权照片之前，门店卡片会显示明确的照片占位提示。

同样，OSM 社区候选不代表营业状态已确认。只有独立核验通过、且来源日期与核验日期都在两年内的商家，才标记为人工核验。不得把候选数量、地图收录数量或演示商家数量宣传为武汉当前在营餐厅数量。
