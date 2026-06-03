## 更新日志

### Unreleased

#### docs: 将初始化 skill 更名并重写部署模式文档

**构建/配置**
- Copilot 初始化 skill 更名为 `screenshot-export-init`，日志与 PID 文件路径同步更新
- 部署模式文档由手动步骤改写为 `deploy.zsh` 使用说明，涵盖首次部署（`--init`）、增量更新及自动回滚机制

---

### Unreleased

#### feat: 支持自定义 DOCX 每行图片列数并重命名为 Screenshot-Export

**前端**
- 新增每行图片数参数输入框（默认 2，最大 3），生成 DOCX 时将列数提交至后端

**后端**
- DOCX 生成支持自定义列数，图片宽度随列数等比自动计算
- 将 `root_path` 配置迁移至 uvicorn 启动参数，修复 nginx 子路径反向代理下的路由异常
- API 标题更新为 Screenshot-Export

**构建/配置**
- 所有环境变量前缀由 `SCREEN_EXPORT_` 统一改为 `SCREENSHOT_EXPORT_`
- 部署脚本及 systemd 路径、服务名更新为 `screenshot-export`
- 新增 screenshot-export.service systemd 服务配置文件
- 部署脚本的更新模式新增服务重启步骤

---

### Unreleased

#### refactor: 将前端单文件拆分为 Jinja2 模板分区与静态 JS

**前端**
- 将 822 行的 `index.html` 拆分为 12 个 Jinja2 分区模板（`partials/`）与独立 JS 文件
- 新增 `frontend/templates/index.html` 薄装配层，通过 `{% include %}` 组装各分区
- 将内联 `<script>` 提取为独立静态文件 `frontend/static/js/app.js`
- 分区包含：`head`、`header`、`upload`、`param-config`、`action-buttons`、`progress`、`screenshot-preview`、`history-sidebar`、`lightbox`、`docx-modal`、`toast`

**后端**
- 路由层改用 `Jinja2Templates.TemplateResponse` 替代直接读取 HTML 文件（适配 Starlette 1.x 新签名）
- 主入口新增 `/static` 静态文件挂载，通过 `StaticFiles` 服务前端 JS 资源

---

### Unreleased

#### refactor: 将后端入口拆分为多个职责单一的模块

**后端**
- 将 JobStatus 枚举提取为独立模块，便于其他模块复用
- 将 SQLite 持久化层提取为独立模块，消除主入口中的数据库逻辑
- 将运行时任务状态与存储逻辑提取为独立模块
- 将 Pydantic 请求/响应模型提取为独立模块
- 将全部 API 路由处理器提取为独立路由模块
- 将后台任务与 SSE 生成器提取为独立模块
- 主入口文件精简为应用初始化与启动配置

**构建/配置**
- 将 data 目录加入 .gitignore，避免本地数据文件被提交

---

### Unreleased

#### fix: 修复部署时数据目录权限错误

**构建/配置**
- 部署脚本在初始化阶段自动创建数据目录并授权给服务运行用户，避免服务启动时因无写入权限报错
- 启用 systemd 服务的数据目录环境变量，将数据存储迁移至项目目录外

---

### Unreleased

#### feat: 新增生产部署脚本与配置

**构建/配置**
- 新增一键部署脚本，支持全量初始化和增量更新两种模式，错误时自动回滚已部署资源
- 新增 Nginx 反向代理配置片段，支持 SSE 流式进度、大文件上传及超时调整
- 新增 systemd 服务单元，支持生产环境以后台服务方式管理进程
- 新增项目初始化 Copilot skill，支持一键搭建虚拟环境、安装依赖并启动后端服务
- 锁定全部依赖包版本号，确保跨机器部署环境完全可复现

#### chore: 清理废弃代码与临时隐藏未完成功能

**前端**
- 临时隐藏历史记录按钮（功能尚未实现）
- 删除已废弃的 NiceGUI 前端入口文件

---

### Unreleased

#### feat: 重构为纯后端架构，新增历史记录与 SQLite 持久化

**后端**
- 新增 SQLite 持久化层，服务重启后可恢复全部历史任务
- 新增历史任务列表接口，支持查询每条记录的截图数、文件状态等
- 新增任务删除接口，同步清理截图、输出及上传文件
- DOCX 下载文件名改为带时间戳格式，避免覆盖
- 服务启动时自动将中断中的任务标记为错误状态
- 后端直接 serve 前端 HTML，移除对独立前端进程的依赖

**前端**
- 用原生 HTML + Tailwind CSS 重写前端，移除 NiceGUI 依赖
- 支持历史记录面板，展示所有历史任务及其状态

**构建/配置**
- 新增 `DATABASE_PATH` 配置项，支持 SQLite 数据库路径自定义
- 数据目录支持通过环境变量独立指定，方便生产环境迁移
- 移除前端端口及前端子路径配置，合并为单服务部署
- 移除 `nicegui` 依赖

---

#### feat: 前端截图分页与代理路由

**前端**
- 截图预览支持分页，每页展示 6 张，可通过翻页按钮浏览全部截图
- 截图预览区改为可折叠面板，标题实时显示总张数
- 新增图片代理路由和 DOCX 下载代理路由，解决手机等外部设备无法访问后端 localhost 的问题
- 禁用 httpx 代理环境变量读取，避免本地请求被系统代理拦截
- 修复文件上传回调为异步，适配新版 NiceGUI API

---

#### feat: 初始化 Screen Export 应用骨架

**后端**
- 新增视频上传接口，支持 MP4、MOV、AVI、MKV、WebM 格式，并发安全
- 新增视频处理任务，通过 SSE 实时推送帧分析进度
- 新增截图查询接口，支持列表查询和单张下载
- 新增 DOCX 生成接口，将截图整理为 Word 文档（3 列 2 行布局）

**前端**
- 新增 NiceGUI 前端应用框架，通过 httpx 调用后端接口

**构建/配置**
- 新增统一配置模块，支持端口、数据目录及 nginx 子路径等环境变量覆盖
- 更新依赖列表与 .gitignore
