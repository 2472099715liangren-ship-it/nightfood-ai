# 夜寻 · 武汉夜间餐饮决策实验室

依据《夜间经济背景下城市餐饮消费决策机制与可解释AI推荐优化研究》构建的可运行研究原型。所有商户、菜品、评分、营业时间均为演示数据，不提供真实餐饮交易。

## 启动

需要 Python 3.10+，无第三方依赖。

```bash
git clone https://github.com/2472099715liangren-ship-it/nightfood-ai.git
cd nightfood-ai
sh start.sh
```

macOS / Linux 使用 `sh start.sh` 即可同时启动网页和后端接口。脚本会检查 Python 版本、SQLite 支持及端口参数，并自动切换到项目目录，也可以从其他目录通过完整路径运行。无需安装第三方依赖。

自定义端口或数据库文件：

```bash
PORT=8080 sh start.sh
APP_DB=/absolute/path/night.db sh start.sh
```

脚本以当前用户权限运行，在前台保持服务，退出终端会停止服务。也可直接运行 `python3 app.py`。

Windows 用户也可以下载 GitHub 仓库 ZIP、完整解压后双击 `启动网页.bat`；需要先安装 Python，并勾选 Add Python to PATH。

启动后，在运行服务的同一台电脑上打开浏览器，地址栏输入 `http://localhost:8000`。保留终端窗口，按 Ctrl+C 停止服务。不要直接双击 `static/index.html`，否则后端接口无法使用。

默认监听 8000 端口；可通过 `PORT` 更改。数据库默认保存在 `data/night.db`，可通过 `APP_DB` 指定其他 SQLite 文件。首次启动自动建表并生成 4 个商圈、24 家商户、72 道菜品，再次启动保留数据。

## 功能

- 根据商圈、预算、等待时间、到店时间、口味和场景筛选推荐，包含跨午夜营业判断。
- 公开评分组成、推荐依据和取舍；采用确定性规则评分，不冒称大模型推荐。
- 商圈浏览、访客收藏、最多三家餐厅比较、推荐反馈、问卷及真实数据库聚合统计。
- 响应式中文界面，SVG 美食与城市插画无需外部图片或字体请求。

## 数据库

11 张表：`districts`、`restaurants`、`hours`、`dishes`、`sessions`、`recommendation_runs`、`recommendation_items`、`favorites`、`surveys`、`feedback`、`events`。通过外键连接、参数化 SQL 写入。浏览器随机访客会话用于收藏隔离，不是登录认证。

接口：`GET /api/health`、`GET /api/catalog`、`GET /api/stats`、`GET /api/favorites`；`POST /api/recommend`、`POST /api/favorites`、`POST /api/surveys`、`POST /api/feedback`。POST 和收藏读取使用 `X-Session` 请求头。

## 验证

```bash
python3 -m unittest discover -s tests -v
```

## 使用范围

这是研究演示和开发原型，尚未进行真实用户实验。问卷统计不构成研究结论。预算等约束采用模拟数据，空间距离为直线估算。正式上线前需接入合法授权且及时更新的商户数据，并加入用户认证、访问控制、限流、隐私管理、数据导出与删除机制及生产 WSGI/ASGI 部署方案。当前标准库 HTTP 服务用于开发运行。
