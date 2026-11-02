# 夜寻 NightFind

一个以武汉夜间餐饮为场景的轻量研究原型。产品首页以对话式餐饮建议为主，另设商家小册和用户建议入口。

> 重要说明：当前内置的商户、菜品、价格、评分、等位和营业时间都是演示数据，不代表真实店铺或实时状态。接入真实商户前，请先取得数据授权并建立更新机制。

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
├── restaurant_catalog.py  # 真实餐厅来源、导入校验和人工审核
├── import_restaurants.py  # CSV 预览与导入命令
├── review_restaurants.py  # 待核验资料的审核命令
├── manage_restaurant_sources.py # 来源许可暂停/恢复
├── start.sh               # 本地启动脚本
├── .env.example           # 本地环境配置模板
├── static/
│   ├── index.html         # 页面骨架
│   ├── style.css          # 淡绿主题、布局与响应式
│   ├── experience.css     # 追问、对比、收藏清单的样式
│   └── app.js             # 页面交互及状态管理
├── docs/WUHAN_REAL_DATA.md # 武汉真实餐厅数据来源与运营规范
├── data/                  # CSV 模板；不要提交未经授权的商家数据
└── tests/
    ├── test_app.py        # 数据库和服务层测试
    ├── test_experience.py # 多轮对话、对比、收藏逻辑
    └── test_http.py       # API 集成测试
~~~

后端按职责拆分：app.py 不直接编写业务 SQL；database.py 不负责 HTTP；services.py 不处理浏览器 DOM。需要调整追问策略时修改 conversation.py，调整对比维度时修改 comparison.py，调整评分规则时修改 services.py。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/health | 服务健康检查 |
| GET | /api/bootstrap | 商圈信息和 AI 配置状态 |
| GET | /api/merchants | 搜索和筛选商家 |
| GET | /api/real-areas | 武汉 13 个行政区和功能区列表 |
| GET | /api/real-catalog/summary | 全市各区已核验真实餐厅数量 |
| GET | /api/real-restaurants | 只返回已核验且来源许可有效的真实餐厅 |
| GET | /api/real-restaurants/{id} | 真实餐厅详情、已核验营业时间和菜品 |
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

数据库默认保存在 data/night.db，可以通过 APP_DB 指定其他位置。首次启动会创建表并生成 4 个演示商圈、24 家演示商户和 72 道演示菜品；真实餐厅数据使用独立表，不会混入演示商户。另建立武汉 13 个行政区及 4 个功能区的覆盖目录。当前真实餐厅表为空，只有来源许可有效且人工核验通过的记录才会进入真实餐厅公开目录。

从旧版本升级时，程序只对商家表增加简介、地址标签和数据来源说明字段，并新建建议表，不会主动删除旧的收藏、评价、问卷或推荐记录。升级前仍建议自行备份 data/night.db。


## 武汉真实餐厅数据库

真实餐厅与演示商户分表保存。系统包含来源登记、CSV 导入批次、字段变更日志、重复记录复核、营业时间/菜品扩展表和人工审核状态。公开 API 只返回 record_status=verified 且来源 permission_status=approved 的记录。

**重要：** 代码已准备好导入和审核流程，但目前没有导入任何真实餐厅名录。武汉公共数据需要按授权目录和协议获取；地图/点评平台资料也需确认存储和展示许可。公开网页可见不代表可以批量复制。

完整数据来源和操作要求见 docs/WUHAN_REAL_DATA.md。

### 导入真实餐厅 CSV

先复制 data/wuhan_restaurants_template.csv，填写有权使用的真实门店资料。默认命令只预览，不会修改数据库：

~~~bash
python import_restaurants.py data/my_wuhan_restaurants.csv --source-code merchant_claimed
~~~

首次登记数据来源时，必须提供许可说明并显式确认权利；实际写入还必须追加 --apply：

~~~bash
python import_restaurants.py data/my_wuhan_restaurants.csv \
  --source-code merchant_claimed \
  --source-name "商家授权提交" \
  --source-type merchant_submission \
  --license-note "已取得商家对本批门店资料的存储和展示授权" \
  --approved-by "operator" \
  --rights-confirmed \
  --apply
~~~

导入记录默认进入待审核队列，不会直接公开。先查看：

~~~bash
python review_restaurants.py
~~~

查看或暂停数据来源；来源许可变化时应及时暂停公开：

~~~bash
python manage_restaurant_sources.py
python manage_restaurant_sources.py --suspend merchant_claimed
~~~

恢复前必须重新核验权利并明确确认：

~~~bash
python manage_restaurant_sources.py --reinstate merchant_claimed \
  --rights-confirmed --approved-by "operator"
~~~

人工核对地址和来源后再批准：

~~~bash
python review_restaurants.py --approve 12,13 --reviewed-by "reviewer" \
  --note "已核对门店地址和授权凭证"
~~~

### 真实数据字段原则

- 未知价格保留为空，不补造人均消费。
- 未知营业状态为 unknown，不显示“正在营业”。
- 不复制未经许可的第三方评分、评论或图片。
- 来源许可暂停后，该来源下的真实记录会从公开 API 隐藏。
- AI 推荐暂时继续使用独立演示数据，不把不完整真实数据混入排序。

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
git clone --branch feature/wuhan-real-restaurant-catalog --single-branch \
  https://github.com/2472099715liangren-ship-it/nightfood-ai.git \
  ~/nightfood-ai-wuhan-data

cd ~/nightfood-ai-wuhan-data
PORT=8002 sh start.sh
~~~

本地浏览器打开 http://localhost:8002。首次运行会使用独立数据库，不覆盖旧项目的数据。若之前预览的 8000 端口服务仍在运行，两个本地预览可以共存。

## 体验注意事项

- 多轮状态只在当前页面会话中保留；不是永久 AI 记忆。
- 换一批只在符合现有约束的商户中轮换，若没有新的会明确提示，不会虚构商户。
- 对比排序是使用演示价格、等待和评分的可解释规则，并非实时 AI 评测；到店前仍需核实。
- 收藏仅按浏览器本地访客 ID 区分，不是账号认证，清理浏览器存储会丢失访客 ID。
