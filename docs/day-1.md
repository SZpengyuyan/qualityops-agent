# Day 1 验证记录

日期：2026-11-23（Asia/Shanghai）。范围：工程基础设施，不包含 AI 或测试业务功能。

## 环境与位置

- Windows NT 10.0.26200.0；Git 2.51.0.windows.1。
- 原有 Python 3.13.0，现已补装 Python 3.11.9，项目 `.venv` 使用 3.11。
- 系统 Node 20.10.0 / npm 10.2.3；Vite 8 需要更新的 Node，项目 `.tools` 中安装 Node 22.23.5，启动脚本优先使用该版本。
- `D:\` 不可用，项目位于 `C:\Users\刘家宇\Documents\ChatGPT\qualityops-agent`。
- 开始时仅有已初始化但无提交、无远程的 `.git`，没有覆盖已有业务文件。

## 已执行检查

1. `python -m pytest -q`（backend 目录、项目虚拟环境）：**5 passed**。
   覆盖根路由、API 存活、数据库健康、SQLite 事务写入后从新连接读取，以及数据库异常返回 503 且不泄露内部信息。
2. `python -m pip check`：`No broken requirements found.`
3. `scripts/frontend.ps1 build`：TypeScript 检查与 Vite 8.3.8 生产构建成功，输出 `frontend/dist/`。
4. npm 安装审计：`found 0 vulnerabilities`（仅代表本次 npm 审计结果，不是全面安全审计）。
5. HTTP 实测：8000 端口的 `/`、`/api/health`、`/api/health/db` 均返回 200；5173 端口两个 `/api/health*` 代理请求均返回 200。
6. 浏览器实测：Dashboard 显示 `Connected`，API 和 SQLite 均显示连接正常；Tailwind 布局、背景、卡片和状态样式正常渲染。
7. 暂停后端并点击“重新检查”：页面显示 `Disconnected`、HTTP 502 和启动后端提示。恢复后端再检查：页面回到 `Connected`。
8. Git 忽略检查：虚拟环境、项目 Node、依赖目录、构建产物、数据库和 `.env` 均被忽略。

## 已解决的问题

- 沙箱中部分安装和运行命令无法正常联网或执行，使用经过批准的宿主执行完成验证。
- npm 首次使用旧系统 Node 安装时遗漏 Windows 原生可选包；改用项目 Node 22 并执行 `npm install --include=optional` 后构建通过。
- GitHub CLI 首次下载连接失败，重试官方安装成功。

## 限制与后续步骤

- 测试有 1 条第三方弃用警告：Starlette TestClient 提示未来将从 HTTPX 迁移至 httpx2；当前 HTTPX 测试全部通过，未屏蔽警告。
- GitHub CLI 2.105.0：用户已完成设备认证，`gh auth status` 确认账户为 `SZpengyuyan`。检查目标仓库不存在后，已创建 Public 仓库 https://github.com/SZpengyuyan/qualityops-agent 并配置 `origin`。开发分支为 `codex/day-1-infrastructure`。
- 本机未找到 Docker 命令。Dockerfile、Nginx 反向代理和 Compose 已提供，但未执行容器构建或启动，不计入已验证结果。
- 未集成 LLM、RAG、LangGraph 或任何 API Key；后续按 MVP 分阶段开发。
- 验收完成后保留本地 8000/5173 服务供演示，后台进程号与日志存放在被忽略的 `.verification/`。重启电脑后需按 README 启动服务。
