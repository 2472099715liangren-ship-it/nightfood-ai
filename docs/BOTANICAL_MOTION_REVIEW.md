# 两侧植物装饰动效 · 2026-11-20

此文档记录前版柔和动效。最新醒目配色、放大动效和手机暂停行为见 [本版视觉说明](VIVID_MOTION_REVIEW.md)。

分支：`feature/animated-botanical-margins`，基于 AI 对话首页版 `f96a431`。

## 效果与使用

- 保留淡绿色植物线稿，两侧枝叶缓慢摇曳；右侧镜像，速度与起始时间错开。
- 增加错峰飘动的小叶片、明暗变化的光点和柔和呼吸光晕。
- 页脚“暂停装饰动效”可暂停所有装饰层，再点击即可恢复；浏览器会记住选择。浏览器不允许本地存储时，本页仍可正常暂停。
- 页面进入后台时暂停，返回时恢复；系统开启“减少动态效果”时保留静态花纹。
- 宽度不超过 1100 像素时收起边饰和暂停按钮，给聊天和内容留出空间。装饰不接收点击，不遮挡输入框。

[查看 6 秒实际页面动效录屏](previews/botanical-motion.gif)（4 帧/秒，压缩预览；实际页面由浏览器连续播放）。

## 后续修改

动画样式集中在 `static/style.css` 的装饰区：`botanical-sway` 控制枝叶，`botanical-drift` 控制叶片，`botanical-twinkle` 控制光点，`botanical-breathe` 控制光晕。各叶片的角度、时长和延迟使用 CSS 变量设置。

`static/decorations.js` 单独处理暂停、保存选择和页面可见性，不进入对话或商家数据逻辑。只对位移、缩放、旋转和透明度做动画，无新增运行依赖或构建步骤。

## 验证

浏览器检查涵盖实际运动、右侧镜像、暂停与恢复、刷新保留、系统减少动态效果、后台暂停、存储不可用、1440 至 320 像素宽度及输入框无遮挡。推荐成功自动跳转等既有流程也通过浏览器回归。

92 项 Python 测试与 3 项会话存储测试全部通过，新增装饰脚本的 HTTP 静态资源访问已纳入检查。

启动应用后，已安装 Playwright 的开发环境可运行：

```sh
CHROMIUM_PATH=/usr/bin/chromium node tests/decorative_motion.cjs http://127.0.0.1:8000
CHROMIUM_PATH=/usr/bin/chromium node tests/recommendation_navigation.cjs http://127.0.0.1:8000
```

`CHROMIUM_PATH` 为浏览器路径；Playwright 已配置自带浏览器时可省略。普通运行项目无需安装 Playwright。
