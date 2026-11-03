# 夜寻 NightFind

一个以武汉夜间餐饮为场景的轻量研究原型。产品首页以对话式餐饮建议为主，另设商家小册和用户建议入口。

> 真实资料说明：商家小册已附带 55 条武汉门店公开网页目录、55 条有授权信息的图片记录、73 条招牌菜记录（其中 16 条有可引用的明确单价）。公开网页收录不等于营业状态已人工核验；未找到可靠单价的菜品会显示“价格待核”，不会用人均价冒充单品价。原有推荐、评分、等位和营业时间演示数据仍明确与真实目录分开。

## 功能结构

1. **聊聊今晚**：多轮对话保留已明确提供的商圈、预算和口味，显示偏好小标签；按缺失信息追问，也可点击“便宜一点”“少等一会”“换一批”。支持从推荐卡片直接收藏和选择对比。
2. **商家小册**：搜索商家、按商圈/菜系/人均预算筛选，查看商家介绍、菜单和已提交的体验反馈；商家卡片可直接加入清单或对比。
3. **今晚清单**：使用原有 SQLite 收藏表，在同一个浏览器的访客会话里保存餐厅；可随时取消收藏并从清单开始比较，不需要注册。
4. **餐厅对比**：选择 2–3 家商户，查看人均价格、预计等位、菜系、演示评分，以及依据透明规则计算的对比建议。
5. **留言建议**：提交功能建议、商家信息纠错和使用体验，后台只统计数量与分类，不公开其他用户的原文。

界面采用淡绿色和暖白色，适配手机和桌面，并提供轻量过渡动画。

## 启动

需要 Python 3.10 或以上版本。项目后端仅使用 Python 标准库，不需要安装第三方包。

~~~bash
git clone https://github.com/2472099715liangren-ship-it/nightfood-ai.git
cd nightfood-ai
sh start.sh
~~~

浏览器打开 http://localhost:8000。终端保持运行，按 Ctrl+C 停止服务。

第一次启动时，程序会从仓库内的 CSV 自动导入真实商家目录，不需要先手动执行数据库导入，也不会在启动时爬取网站。

需要把具体门店地址补到地图上时，额外运行一次：

~~~bash
python3 import_wuhan_catalog.py --geocode
~~~

该命令使用 OpenStreetMap Nominatim，按每秒不超过一条的节奏查询具体地址并缓存 WGS84 坐标。模糊商圈、没有门牌的记录不会被猜坐标，仍会保留在列表中。

可选配置：

~~~bash
cp .env.example .env
~~~

然后编辑 .env：

~~~dotenv
OPENAI_API_KEY=在这里填写你自己的服务端密钥
OPENAI_MODEL=gpt-5.5
PORT=8000
~~~

再次运行 sh start.sh。配置密钥后，对话会调用 OpenAI Responses API；没有配置密钥时，仍可使用本地规则推荐模式。密钥只从服务器环境读取，不会发送到浏览器，也不应提交到 GitHub。不要把 API 密钥发到聊天窗口或写进前端文件。启用 AI 后，用户提交的对话内容及最近几轮对话会发送给所配置的模型服务；请勿在聊天中输入敏感个人信息。

如果使用其他兼容 Responses API 的服务，可设置 OPENAI_BASE_URL，必须使用 HTTPS。

## 项目结构

~~~text
nightfood-ai/
├── app.py                 # HTTP 路由、请求校验和静态资源
├── database.py            # SQLite 建表、迁移和数据访问
├── services.py            # 偏好解析、推荐评分和 AI 助手
├── conversation.py        # 多轮偏好整理与追问建议
├── comparison.py          # 2–3 家商户的结构化对比
├── real_catalog.py         # 真实商户、图片、菜品和两年时效规则
├── import_wuhan_catalog.py # 55家武汉门店导入及可选地址地理编码
├── data/
│   ├── wuhan_restaurants.csv       # 门店地址、来源、菜系和人均参考价
│   ├── wuhan_restaurant_images.csv # 图片链接、作者、拍摄日期和授权
│   └── wuhan_menu_items.csv        # 招牌菜和有来源的单品价格
├── start.sh               # 本地启动脚本
├── .env.example           # 本地环境配置模板
├── static/
│   ├── index.html         # 页面骨架
│   ├── style.css          # 淡绿主题、布局与响应式
│   ├── experience.css     # 追问、对比、收藏清单的样式
│   └── app.js             # 页面交互及状态管理
└── tests/
    ├── test_app.py        # 数据库和服务层测试
    ├── test_experience.py # 多轮对话、对比、收藏逻辑
    └── test_http.py       # API 集成测试
~~~

后端按职责拆分：app.py 不直接编写业务 SQL；database.py 不负责 HTTP；services.py 不处理浏览器 DOM。需要调整追问策略时修改 conversation.py，调整对比维度时修改 comparison.py，调整评分规则时修改 services.py。


## 武汉真实商家资料

- **门店：55 条分店级记录**，包含武汉 13 个行政区中的公开商家资料。搜索、区县筛选、列表、详情和地图共用独立的 `real_merchants` 表，不会混入演示商家。
- **图片：55 条**，均记录来源、作者、拍摄日期和 Creative Commons 授权。只有少数是特定门店照片；其余明确标注为菜品参考图，不能误认为该分店实拍。
- **菜品：73 条**，其中 16 条有来源明确的单品价格；其余只列出招牌菜名并标注未找到可靠公开单价。人均参考价和单品价格分开存储。
- **地图：**使用 Leaflet + OpenStreetMap，只有有坐标的门店才会放置标记。运行 `python3 import_wuhan_catalog.py --geocode` 可按具体地址补充 WGS84 坐标；没有门牌或地理编码结果不匹配街道的记录不会被放到地图上。
- **时效：**`source_checked_at` 表示目录采集/核对日期；`source_published_at` 表示来源网页发布日期（来源有明确日期时才填写）。公开 API 只显示最近两年内核对的记录。门店营业状态仍需电话或现场核验。

主要公开来源包括：

- [武汉市商务局：高端酒店外摆菜品与价格（2026-07-10）](https://sw.wuhan.gov.cn/xwdt/mtbd/202607/t20260710_2819054.shtml)
- [武汉市商务局：湖锦酒楼北湖店、汉口喜来登等门店资料（2026-07-20）](https://sw.wuhan.gov.cn/xwdt/mtbd/202607/t20260720_2822721.shtml)
- [武汉市商务局：武汉过早门店报道（2026-08-10）](https://sw.wuhan.gov.cn/xwdt/gzdt/202608/t20260810_2831553.shtml)
- [武汉市商务局：海底捞大排档火锅滨江天街店及按盘价格（2026-01-02）](https://sw.wuhan.gov.cn/xwdt/mtbd/202601/t20260102_2705727.shtml)
- [蔡林记官网门店列表](https://www.whclj.com/)
- [Wikimedia Commons 蔡林记门店及菜品图片](https://commons.wikimedia.org/wiki/Category:Cai_Lin_Ji)

更新 CSV 后，应用会根据文件 SHA 自动重新导入。若只想查看导入统计，可运行 `python3 import_wuhan_catalog.py`。后端仍只使用 Python 标准库；地理编码仅在显式运行 `--geocode` 时联网。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/health | 服务健康检查 |
| GET | /api/bootstrap | 商圈信息和 AI 配置状态 |
| GET | /api/merchants | 搜索和筛选演示商家 |
| GET | /api/real-merchants | 搜索和筛选近两年公开来源的真实门店 |
| GET | /api/real-merchants/coverage | 真实门店资料覆盖统计 |
| GET | /api/real-merchants/{id} | 真实门店详情、图片授权和菜品价格 |
| GET | /api/merchants/{id} | 商家详情、菜单和评价 |
| GET | /api/reviews | 体验评价列表及统计 |
| GET | /api/favorites | 当前访客收藏 ID 列表（兼容旧接口） |
| GET | /api/saved | 当前访客收藏的商家详情 |
| GET | /api/compare?ids=1,2[,3] | 2–3 家商户的透明规则对比，可附带 scene 参数 |
| GET | /api/suggestions/summary | 建议数量与分类汇总 |
| POST | /api/chat | 对话式餐饮建议；支持 context.known、seen_ids，返回 follow_up.actions |
| POST | /api/suggestions | 提交用户建议 |
| POST | /api/feedback | 提交商家体验评分 |
| POST | /api/favorites | 保存或取消访客收藏 |

写入接口以及 /api/saved 使用 X-Session 请求头。当前访客会话用于原型数据隔离，不等同于账号认证。聊天上下文和对比选择保存在当前页面内存中，刷新后不恢复；收藏写入 SQLite，可在同一个浏览器的访客会话中持续使用。

## 数据库与旧数据

数据库默认保存在 data/night.db，可以通过 APP_DB 指定其他位置。首次启动会创建表并生成 4 个商圈、24 家演示商户和 72 道演示菜品，同时按 CSV 校验值导入 55 条真实门店公开资料、图片和菜品记录。重复启动不会重复生成演示商户或重复导入相同版本的 CSV。

从旧版本升级时，程序只对商家表增加简介、地址标签和数据来源说明字段，并新建建议表，不会主动删除旧的收藏、评价、问卷或推荐记录。升级前仍建议自行备份 data/night.db。

## 测试

~~~bash
python3 -m unittest discover -s tests -v
~~~

## 正式上线前需要完成

- 替换演示商户为获得授权的真实商户资料，并定期核实价格、营业时间和联系方式。
- 配置正式的用户身份、访问控制、限流、HTTPS、日志和备份。
- 制定建议与评价的审核、举报、删除和隐私保留规则。
- 为 AI 服务配置密钥、预算上限和错误监控；AI 只负责组织建议，商户事实仍以数据库为准。
- 将开发用标准库 HTTP 服务替换为生产级 WSGI/ASGI 部署。

## 预览这一阶段（不影响旧版）

当前功能分支从尚未合并的淡绿色改版分支创建，新 PR 的目标分支也是淡绿色改版分支，避免把旧深色版误带进新开发。

~~~bash
git clone --branch feature/conversation-compare-tonight-list --single-branch \
  https://github.com/2472099715liangren-ship-it/nightfood-ai.git \
  ~/nightfood-ai-next

cd ~/nightfood-ai-next
PORT=8001 sh start.sh
~~~

本地浏览器打开 http://localhost:8001。首次运行会使用独立数据库，不覆盖旧项目的数据。若之前预览的 8000 端口服务仍在运行，两个本地预览可以共存。

## 体验注意事项

- 多轮状态只在当前页面会话中保留；不是永久 AI 记忆。
- 换一批只在符合现有约束的商户中轮换，若没有新的会明确提示，不会虚构商户。
- 对比排序是使用演示价格、等待和评分的可解释规则，并非实时 AI 评测；到店前仍需核实。
- 收藏仅按浏览器本地访客 ID 区分，不是账号认证，清理浏览器存储会丢失访客 ID。

## 武汉真实商户数据库（开发中）

本模块面向武汉全市 13 个行政区建立独立真实商户表 real_merchants。它与现有
restaurants 演示商家表分开存储、分开查询。**本次只搭建可核验的导入与查询机制，
尚未导入任何获得授权的真实商家记录，不会虚构商家或对外宣称已覆盖武汉全市。**

### 数据字段与审核流程

核心字段包括：来源系统中的 external_id（唯一键）、店名、行政区、地址、菜系、
经纬度、电话、人均价格、营业时间、来源名称和来源 HTTPS 链接、最后核验日期、
核验方式和审核状态。全部价格/营业信息都是可为空字段，避免制造错误的“实时”印象。

- draft：草稿；pending：待核验；rejected：未通过核验。
- verified：核验通过，满足来源、日期和核验方式要求后，才会出现在公开接口。
- 同一 external_id 导入时安全更新，不会删除或覆盖原来的演示数据。
- 导入来源必须经过许可或商家授权，不应爬取违反网站条款或涉及个人隐私的内容。
- 未来生产运营建议增加管理员审核权限、定期复核与失效下线机制。

### CSV 批量导入（在服务器/电脑终端执行，不开放前台导入接口）

先准备一个 UTF-8 CSV 文件。例如以下字段为模板，**示例为占位资料，不是真实商家**：

~~~csv
external_id,name,district,address,cuisine,source_name,source_url,verified_at,verification_method,status,phone,price_per_person,opening_hours,latitude,longitude
partner-id-001,示例占位商家,江汉区,请替换为核验地址,湖北菜,已授权资料提供方,https://example.org/record/1,2026-10-01,商家书面确认,pending,,,
~~~

请在获得可使用的数据及核验凭证后再填充；仅将真实核验通过的数据设为 verified。

~~~bash
python3 import_merchants.py /path/to/authorized-wuhan-merchants.csv --dry-run
python3 import_merchants.py /path/to/authorized-wuhan-merchants.csv
~~~

也支持 JSON 数组。文件超过 5MB 会被拒绝；单批次先整体校验再写入。
数据默认进入 data/night.db，因此原来的收藏及意见数据仍然保留。正式迁移前建议备份数据库。

### 公开读取接口

- GET /api/real-merchants?district=江汉区&keyword=餐厅&limit=30&offset=0
- GET /api/real-merchants/coverage

只返回核验通过的记录。覆盖统计包含全部 13 个行政区，
数字代表已经收录并核验的记录数，**不代表武汉全市的实际餐厅数量**。
前端商家页面新增独立的真实资料区域，演示店铺依然明确标注，不混用推荐分数或评价。
当前对话推荐仍使用演示数据，正式上线前必须完成真实商户推荐数据源切换与核验。

### 运行测试

~~~bash
python3 -m unittest discover -s tests -v
~~~

### 审核与合并

此阶段独立分支 feature/wuhan-real-merchant-database 从
feature/conversation-compare-tonight-list 创建；
应待前置改版与功能分支审核合并后，调整本 PR 的目标分支到 main，再考虑合并。

## OpenStreetMap 开放地图商家接入（新增）

本分支接入 **© OpenStreetMap contributors · ODbL** 公开地图资料，查看来源及许可：
https://www.openstreetmap.org/copyright 。
来源数据允许按 ODbL 再利用，传播和派生数据库需要保留署名并遵守该许可。
详见 data_sources/README.md。

- 通过 geofabrik_sync.py 从 Geofabrik 湖北 OpenStreetMap 提取文件裁剪出武汉市范围餐饮场所；
  如下载服务不可用，可使用 osm_sync.py 进行小范围 Overpass 查询。
- 只收录有名称且带有 OSM node/way 源 ID 的场所，并保存原始来源链接和地图坐标。
- 无法确认的行政区明确标记“待确认区县”；地址缺失写“详细地址待核实”，绝不补写猜测地址。
- OSM 社区地图数据只表示被社区收录，不能代表仍在营业，也不能把地图更新时间当作商家人工核验。
- 价格、评分、评论和等位时间不会从模拟店铺复制到真实店铺。
- 网站“商家小册”现在可分别查看社区收录、人工核验和演示商家；AI 对话可列出单独标记的 OSM 候选，但演示推荐评分仍不代表真实商家质量。
- 若仓库含 data_sources/osm_wuhan_snapshot.json，启动网站时会自动导入 SQLite；每次文件哈希变化才会重新导入一次。既有模拟数据、收藏、评价、用户建议不会被删除。
- 公共查询端点：GET /api/real-merchants 与 GET /api/real-merchants/coverage；支持分页。

**公开数据采集情况应以仓库中实际存在的快照文件和 GitHub Actions 结果为准。**
如果快照尚未成功获取，请不要声称已经导入任何真实商家。

在 Mac 预览本分支（新目录，不覆盖旧版）：

~~~bash
cd ~
git clone --branch feature/osm-wuhan-public-data --single-branch \
  https://github.com/2472099715liangren-ship-it/nightfood-ai.git nightfood-ai-osm
cd ~/nightfood-ai-osm
PORT=8003 sh start.sh
~~~

浏览器打开 http://localhost:8003。正式上线前请补上商家真实性抽查、
更新机制、联系方式核验、合规审核，以及针对真实商家的收藏/对比支持。


## 最新要求：两年内资料、授权店面照片与精进地图

**本节为真实商家数据的当前公开规则，优先于上方早期 OSM 试接入说明。**

- 来源实际核查日期必须在最近两个自然年内；人工核验商家还要求人工核验日期也在最近两年内。OSM 下载时间或元素最后编辑时间不能冒充逐店核查日期。
- 缺少 \`survey:date\` / \`check_date\` 的 OSM 候选保留在待核验库，不会出现在真实商家列表、地图和详情页。
- 地图区分绿色人工核验点位和蓝灰色 OSM 社区核查点位，支持列表/地图切换、当前搜索/分页同步、自动缩放和门店资料弹窗。
- 店面照片必须有权利人展示授权、近两年实际拍摄日期和人工审核。图片导入后才可公开，并显示拍摄日期与权利人；未授权时使用明确占位，不抓取搜索结果或点评照片。
- 目前没有商家授权照片随代码自动导入。请按 [照片导入与地图说明](docs/OSM_FRESHNESS_PHOTOS_MAP.md) 收集授权图片，再运行本地照片审核流程。
