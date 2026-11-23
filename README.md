# QualityOps Agent

基于 LLM 与 Agent 技术的智能质量保障平台。当前已完成 **工程基础设施、项目管理、OpenAPI 导入、HTTP 执行与基础断言**，并提供本地订单 Demo API。

RAG、AI 测试生成、Agent 工具编排、Agent Trace 与 Benchmark 尚未实现；当前执行器是确定性的 HTTP 执行模块，页面不展示模拟的业务统计。

## 技术栈与目录

- 前端：React、TypeScript、Vite、Tailwind CSS 4。
- 后端：Python 3.11、FastAPI、SQLAlchemy 2.0、SQLite、HTTPX、pytest、python-dotenv。
- `frontend/`：Dashboard、Vite `/api` 代理、生产 Nginx 代理。
- `backend/app/`：应用工厂、数据库配置、项目模型与 Schema、独立项目路由；`backend/tests/`：隔离数据库测试。
- `backend/app/services/openapi.py`：离线解析与规范校验；`backend/app/routers/openapi.py`：文档和接口目录 API。
- `demo-api/`：本地订单演示服务；`benchmark/`：后续阶段占位。
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

如需自定义数据库，将 `backend/.env.example` 复制为 `backend/.env`。默认数据库为 `backend/data/qualityops.db`，相对路径始终以 `backend/` 为基准。启动时通过 SQLAlchemy `create_all` 创建缺失的 `projects` 和 `openapi_documents` 表，不删除已有数据。当前尚无版本化数据库迁移；后续修改已有表结构前需引入迁移方案。

## 项目管理

在 Dashboard 点击“新建项目”，填写名称、HTTP/HTTPS API 基础地址和可选描述。保存后可查看详情、编辑或删除；刷新页面后项目仍从 SQLite 加载。项目 URL 只用于保存配置，此阶段不会请求待测服务。

- `GET /api/projects?limit=20&offset=0`：分页列表，返回 `items`、`total`、`limit`、`offset`；每页 1–100 条。
- `POST /api/projects`：创建，返回 201。
- `GET /api/projects/{id}`：详情，不存在返回 404。
- `PUT /api/projects/{id}`：替换名称、描述、基础地址，返回更新后的项目。
- `DELETE /api/projects/{id}`：删除，返回 204。

名称去除首尾空白后需为 1–100 字，描述最多 2000 字。基础地址不接受凭据、查询参数和片段；无效输入返回 422。ID 使用 UUID，时间为 UTC。项目名称允许重复。前端每页显示 6 条，并提供加载、失败、保存和删除确认反馈。

当前是本地单用户 MVP，未实现登录、权限或多用户隔离。验收记录：[Day 1](docs/day-1.md)、[Day 2](docs/day-2.md)、[Day 3](docs/day-3.md)。

## OpenAPI 文档导入与接口目录

在项目详情中点击“导入 OpenAPI”，选择本地 JSON 文件或粘贴内容，再点击“校验并导入”。可使用仓库自带的 [订单示例文档](docs/examples/orders.openapi.json)，它包含 3 个接口，仅作为解析示例，不代表待测服务已经启动。

导入后可按 HTTP 方法、标签筛选，按路径/摘要/operationId 搜索，分页查看接口；点击接口查看合并后的参数、请求体、响应、认证和服务地址定义。Schema 内的 `$ref` 保留为符号引用，不展开递归 Schema。

- 支持 OpenAPI **3.0.x / 3.1.x JSON**；不支持 YAML、Swagger 2、OpenAPI 3.2、URL 抓取或外部引用。
- 每份文档最多 **1 MiB、500 个接口**，嵌套不超过 48 层，结构节点不超过 50000；解析快照最多 4 MiB。
- 仅支持文档内 `#/` JSON Pointer 引用；拒绝自定义 `$id`、`$schema`、动态引用和 `jsonSchemaDialect`。这些限制也适用于扩展及示例对象中的同名键。
- 规范校验由 `openapi-spec-validator` 完成；操作级参数按 `(name, in)` 覆盖路径级同名参数，认证和服务器配置按层级继承。
- 每个项目保存一份最新文档及目录。重新导入需勾选替换确认；先完整解析，再事务提交，解析失败保留原目录。当前没有文档版本历史或多标签页的并发编辑冲突检测。
- 删除项目会清理对应文档。文档导入不会执行任何待测 API。

接口（均位于 `/api/projects/{project_id}`）：

- `PUT /openapi`：请求体 `{"content":"JSON 文档文本"}`，校验并整体替换，返回文档摘要。
- `GET /openapi`：文档摘要；尚未导入返回 `null`。
- `GET /operations?method=GET&tag=Orders&q=order&limit=20&offset=0`：接口分页列表。
- `GET /operations/{operation_id}`：接口详情。目录 ID 根据方法与路径生成，文档中的原始 operationId 单独保留。

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

## HTTP 执行与基础断言

在项目根目录另开终端运行 `./scripts/demo-api.ps1`，启动 [本地订单 Demo](http://127.0.0.1:9000/docs)。创建基础地址为 `http://127.0.0.1:9000` 的项目，导入订单示例文档，打开 POST /orders。

JSON 请求体填写：

~~~json
{"product_id":"demo","quantity":1}
~~~

期望状态码设为 201，JSON 相等断言填写：

~~~json
[{"pointer":"/status","expected":"created"}]
~~~

点击“发送请求并执行断言”，平台会实际请求目标服务并保存响应和断言结果。数量改为 4 时 Demo 返回 409：若预期 201 则失败；预期 409 且检查 /detail 等于 Insufficient stock 则通过。刷新页面后执行记录保留。Demo 订单仅存于内存，重启服务会清空。

- 路径和查询参数使用 JSON 对象，值均为字符串，例如 `{"order_id":"实际订单ID"}`；路径参数须与占位符完全匹配。
- 支持无认证 GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS，以及明确允许匿名的可选认证接口。暂不支持必填 Header/Cookie、Token 注入、文件上传或表单请求体。
- 实际目标使用项目基础地址，忽略 OpenAPI servers。默认仅允许本地 9000 服务。其他服务需在 backend/.env 中配置 QUALITYOPS_ALLOWED_ORIGINS，以英文逗号分隔完整 origin（协议、主机、端口），随后重启后端。
- 请求输入最多 64 KiB、JSON 断言最多 20 项；默认总超时 5 秒，API 可设置为 0.1–10 秒。响应最多 256 KiB，仅支持未压缩响应。
- 不跟随重定向、不自动重试、不使用系统代理或隐式凭据。超时不保证远端操作未执行，重试前应确认目标服务状态。
- passed 表示断言全部通过；failed 表示已收到响应但断言失败；error 表示超时、连接失败或响应超限等执行错误。前置校验失败返回 422，不发送请求、不生成记录。
- 保存方法、路径、参数、响应和断言；JSON 中匹配 password/secret/token/cookie/api_key 等已知名称的字段会被遮盖，相应断言值也会遮盖。这不是任意文本秘密检测，此 MVP 应使用测试数据。
- 编辑项目和重新导入文档保留执行历史；删除项目会清理关联记录。暂未实现可保存的测试用例集、批量回归、流程变量、自动 Schema 断言或 Agent 编排。

新增接口（前缀 `/api/projects/{project_id}`）：

- `POST /operations/{operation_id}/execute`：接受 path_params、query_params、body、expected_status、checks、timeout_seconds，完成后返回执行记录，HTTP 201。
- `GET /executions?limit=20&offset=0`：分页历史。
- `GET /executions/{execution_id}`：项目内执行详情。

执行模块文件、命令与验证证据见 [Day 4 记录](docs/day-4.md)。当前开发分支为 `codex/day-4-api-execution`。Docker 流程尚未验证，现有 Compose 不包含 Demo API。

## GitHub 与密钥

Public 仓库：[SZpengyuyan/qualityops-agent](https://github.com/SZpengyuyan/qualityops-agent)。阶段分支为 `codex/day-1-infrastructure`、`codex/day-2-project-management`、`codex/day-3-openapi-import`。已完成设备认证并配置 `origin`；后续推送前可检查：

```powershell
gh auth status
git remote -v
gh repo view SZpengyuyan/qualityops-agent
```

若未认证，需要用户完成 `gh auth login --web`。请勿把 API Key 写入代码或 Git；当前阶段无需任何 AI API Key。`.venv/`、`.tools/`、`.env`、数据库与构建产物均已忽略。
