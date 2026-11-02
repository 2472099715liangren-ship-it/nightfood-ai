# 夜寻 NightFind

一个以武汉夜间餐饮为场景的轻量研究原型。产品首页以对话式餐饮建议为主，另设商家小册和用户建议入口。

> 重要说明：当前内置的商户、菜品、价格、评分、等位和营业时间都是演示数据，不代表真实店铺或实时状态。接入真实商户前，请先取得数据授权并建立更新机制。

## 功能结构

1. **聊聊今晚**：自然语言描述位置、预算、时间、口味和就餐场景；按数据库中的候选商户筛选，再生成推荐理由和实用建议。
2. **商家小册**：搜索商家、按商圈/菜系/人均预算筛选，查看商家介绍、菜单和已提交的体验反馈。
3. **留言建议**：提交功能建议、商家信息纠错和使用体验，后台只统计数量与分类，不公开其他用户的原文。

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

再次运行 sh start.sh。配置密钥后，对话会调用 OpenAI Responses API；没有配置密钥时，仍可使用本地规则推荐模式。密钥只从服务器环境读取，不会发送到浏览器，也不应提交到 GitHub。不要把 API 密钥发到聊天窗口或写进前端文件。

如果使用其他兼容 Responses API 的服务，可设置 OPENAI_BASE_URL，必须使用 HTTPS。

## 项目结构

~~~text
nightfood-ai/
├── app.py                 # HTTP 路由、请求校验和静态资源
├── database.py            # SQLite 建表、迁移和数据访问
├── services.py            # 偏好解析、推荐评分和 AI 助手
├── start.sh               # 本地启动脚本
├── .env.example           # 本地环境配置模板
├── static/
│   ├── index.html         # 页面骨架
│   ├── style.css          # 颜色、布局、响应式和动画
│   └── app.js             # 页面交互
└── tests/
    └── test_app.py        # 数据库和服务层测试
~~~

后端按职责拆分：app.py 不直接编写业务 SQL；database.py 不负责 HTTP；services.py 不处理浏览器 DOM。需要调整推荐规则时优先修改 services.py，需要增加表或查询时修改 database.py。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/health | 服务健康检查 |
| GET | /api/bootstrap | 商圈信息和 AI 配置状态 |
| GET | /api/merchants | 搜索和筛选商家 |
| GET | /api/merchants/{id} | 商家详情、菜单和评价 |
| GET | /api/reviews | 体验评价列表及统计 |
| GET | /api/suggestions/summary | 建议数量与分类汇总 |
| POST | /api/chat | 对话式餐饮建议 |
| POST | /api/suggestions | 提交用户建议 |
| POST | /api/feedback | 提交商家体验评分 |
| POST | /api/favorites | 保存或取消访客收藏 |

写入接口使用 X-Session 请求头。当前访客会话用于原型数据隔离，不等同于账号认证。

## 数据库与旧数据

数据库默认保存在 data/night.db，可以通过 APP_DB 指定其他位置。首次启动会创建表并生成 4 个商圈、24 家演示商户和 72 道演示菜品。重复启动不会重复生成演示商户。

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
