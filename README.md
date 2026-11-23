# QualityOps Agent

基于 LLM 与 Agent 技术的智能质量保障平台。当前为 **Day 1 工程基础设施**：可运行的 React Dashboard、FastAPI 健康检查、SQLite 连接和 pytest 测试。

项目管理、OpenAPI 解析、RAG、测试生成、工具执行、Agent Trace 与 Benchmark 尚未实现；页面不展示模拟的业务统计。

## 技术栈与目录

- 前端：React、TypeScript、Vite、Tailwind CSS 4。
- 后端：Python 3.11、FastAPI、SQLAlchemy 2.0、SQLite、HTTPX、pytest、python-dotenv。
- `frontend/`：Dashboard、Vite `/api` 代理、生产 Nginx 代理。
- `backend/app/`：应用工厂和数据库配置；`backend/tests/`：隔离数据库测试。
- `demo-api/`、`benchmark/`：后续阶段占位。
- `scripts/`：Windows 启动脚本；`docs/`：阶段验证记录。

## Windows 本地启动

在项目根目录打开 PowerShell。当前实际位置为 `C:\Users\刘家宇\Documents\ChatGPT\qualityops-agent`；环境中没有可用的 D 盘，因此未使用原计划路径。

要求 Python 3.11、Node.js 22.12+（推荐 Node 22）与 npm。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
```

`requirements.txt` 声明直接依赖，`requirements.lock.txt` 固定本次验证的全部 Python 依赖。前端通过 `package-lock.json` 锁定。

如果系统 Node 版本较旧，可在项目内安装运行时（`.tools/` 已被 Git 忽略）：

```powershell
npm install --prefix .tools --no-audit --no-fund --registry=https://registry.npmjs.org/ node@22.23.5
```

安装前端依赖并启动（脚本优先使用项目内 Node，避免旧版 npm.cmd 调用系统 Node）：

```powershell
.\scripts\frontend.ps1 ci
.\scripts\frontend.ps1 dev
```

另开一个终端，在根目录启动后端：

```powershell
.\scripts\backend.ps1
```

访问 [Dashboard](http://127.0.0.1:5173) 和 [API 文档](http://127.0.0.1:8000/docs)。关闭服务使用对应终端的 Ctrl+C。

如需自定义数据库，将 `backend/.env.example` 复制为 `backend/.env`。默认数据库为 `backend/data/qualityops.db`，相对路径始终以 `backend/` 为基准。首次数据库健康检查会连接并创建 SQLite 文件；Day 1 尚无业务数据表。

## 健康检查与验收

- `GET /`：应用名称、版本和文档地址。
- `GET /api/health`：API 存活状态。
- `GET /api/health/db`：执行真实 `SELECT 1`，成功返回 200，数据库异常返回 503；不向客户端暴露异常详情。

Dashboard 在加载时并行检查 API 与数据库，两者均成功才显示 `Connected`。请求超时为 5 秒；失败显示 `Disconnected`。点击“重新检查”更新状态，不进行后台轮询。前端通过同源 `/api` 请求交由 Vite 转发至 `127.0.0.1:8000`，不需要放宽 CORS。

运行测试与构建：

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest -q
Pop-Location
.\scripts\frontend.ps1 build
```

生产构建输出 `frontend/dist/`。Vite preview 仅用于本地预览；真实部署需要反向代理 `/api`，容器配置中已提供 Nginx 示例。

## Docker

安装并启动 Docker Desktop 后：

```powershell
docker compose up --build
```

访问地址同本地模式。SQLite 数据使用命名卷保存。不要与本地开发服务同时占用 8000、5173 端口。Docker 是否经过验证请以 `docs/day-1.md` 为准。

## GitHub 与密钥

计划使用独立 Public 仓库 `qualityops-agent`。在创建和推送前检查：

```powershell
gh auth status
git remote -v
gh repo view OWNER/qualityops-agent
```

若未认证，需要用户完成 `gh auth login --web`。请勿把 API Key 写入代码或 Git；当前阶段无需任何 AI API Key。`.venv/`、`.tools/`、`.env`、数据库与构建产物均已忽略。
