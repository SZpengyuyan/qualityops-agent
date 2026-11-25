# QualityOps Agent

基于 LLM 与 Agent 技术的智能质量保障平台。当前已完成 **工程基础设施、项目管理、OpenAPI 导入、HTTP 执行、保存用例、用例集回归及跨用例变量传递**，并提供本地订单 Demo API。

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

如需自定义数据库，将 `backend/.env.example` 复制为 `backend/.env`。默认数据库为 `backend/data/qualityops.db`，相对路径始终以 `backend/` 为基准。启动时通过 SQLAlchemy `create_all` 创建缺失的项目、文档、执行及测试资产表，不删除已有数据。当前尚无版本化数据库迁移；后续修改已有表结构前需引入迁移方案。

## 项目管理

在 Dashboard 点击“新建项目”，填写名称、HTTP/HTTPS API 基础地址和可选描述。保存后可查看详情、编辑或删除；刷新页面后项目仍从 SQLite 加载。项目 URL 只用于保存配置，此阶段不会请求待测服务。

- `GET /api/projects?limit=20&offset=0`：分页列表，返回 `items`、`total`、`limit`、`offset`；每页 1–100 条。
- `POST /api/projects`：创建，返回 201。
- `GET /api/projects/{id}`：详情，不存在返回 404。
- `PUT /api/projects/{id}`：替换名称、描述、基础地址，返回更新后的项目。
- `DELETE /api/projects/{id}`：删除，返回 204。

名称去除首尾空白后需为 1–100 字，描述最多 2000 字。基础地址不接受凭据、查询参数和片段；无效输入返回 422。ID 使用 UUID，时间为 UTC。项目名称允许重复。前端每页显示 6 条，并提供加载、失败、保存和删除确认反馈。

当前是本地单用户 MVP，未实现登录、权限或多用户隔离。验收记录：[Day 1](docs/day-1.md)、[Day 2](docs/day-2.md)、[Day 3](docs/day-3.md)、[Day 4](docs/day-4.md)、[Day 5](docs/day-5.md)、[Day 6](docs/day-6.md)。

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
- 编辑项目和重新导入文档保留执行历史；删除项目会清理关联记录。已支持保存用例、顺序回归及流程变量，暂未实现自动 Schema 断言或 Agent 编排。

新增接口（前缀 `/api/projects/{project_id}`）：

- `POST /operations/{operation_id}/execute`：接受 path_params、query_params、body、expected_status、checks、timeout_seconds，完成后返回执行记录，HTTP 201。
- `GET /executions?limit=20&offset=0`：分页历史。
- `GET /executions/{execution_id}`：项目内执行详情。

执行模块文件、命令与验证证据见 [Day 4 记录](docs/day-4.md)。当前开发分支为 `codex/day-6-flow-variables`。Docker 流程尚未验证，现有 Compose 不包含 Demo API。

## 保存测试用例与用例集回归

1. 打开已导入接口，在执行表单中配置参数、请求体、预期状态和 JSON 断言，填写“用例名称”，点击“保存为测试用例”。保存本身不发送请求，目标允许地址在实际运行时检查。
2. 在项目详情下方“测试资产与回归”查看、编辑、单独运行或删除用例。编辑使用请求与断言 JSON 配置；编辑表单保留所属接口，接口已删除时可从新接口重新建立用例。
3. 点击“新建用例集”，勾选用例，通过上移/下移调整顺序，保存后点击“运行用例集”。首次运行与后续回归均复用保存的配置。
4. 在回归运行记录中查看整体统计、每条用例的断言、响应和输入快照。修改用例、项目地址或用例集顺序，不会改写既有快照。

当前每项目最多 100 条用例、50 个用例集，每集最多 10 条且不能重复。空用例集可以保存，但不能运行。被用例集引用的用例需先从集合移除才能删除；删除用例或用例集保留旧运行记录，删除项目会清理全部关联资产和历史。

用例集运行前会校验所有用例，冻结配置、目标地址、顺序与名称；任何前置校验失败都不会发送请求。文档内容有变化（包括组件 Schema）时，用例需重新编辑并保存；内容相同、仅 JSON 字段顺序或格式变化的重新导入不影响用例。

执行采用同步顺序模式：每条失败后继续后续用例；总时限 30 秒，到期后剩余项标为跳过，当前项可能结果未知。每个项目仅允许一个运行中的用例集，重复启动返回 409。刷新页面可重新读取记录，平台不自动重试请求。

当前服务须以**单进程、单 worker**运行。启动时把遗留运行标为 interrupted，不自动重放请求；多 worker、后台任务队列及 Agent 自动编排尚未实现。

用例配置保留原始输入以支持再次执行，请勿保存真实密钥。运行历史会遮盖已知敏感字段以及相应 JSON 指针的期望值；遮盖不是加密或完整秘密识别。当前输入快照用于审阅，不提供历史快照直接重放。

新增接口（前缀 `/api/projects/{project_id}`）：

- `GET/POST /test-cases`，`GET/PUT/DELETE /test-cases/{case_id}`：用例管理，创建/修改接受 name、description、operation_id、input（沿用执行配置）。
- `POST /test-cases/{case_id}/execute`：使用保存配置执行，返回执行记录。
- `GET/POST /test-suites`，`GET/PUT/DELETE /test-suites/{suite_id}`：用例集管理，接受 name、description、按顺序排列的 case_ids。
- `POST /test-suites/{suite_id}/run`：顺序运行并返回汇总、快照和逐项结果。
- `GET /suite-runs?limit=10&offset=0`，`GET /suite-runs/{run_id}`：回归记录与详情。

详细修改和验收证据见 [Day 5 记录](docs/day-5.md)。

## 跨用例流程变量

例如先创建订单，再自动查询本次创建的订单：

1. 在 POST /orders 的“响应变量提取 JSON”填写 `{"order_id":"/id"}`，保存为创建用例。
2. GET /orders/{order_id} 的路径参数填写 `{"order_id":"{{order_id}}"}`；JSON 断言可填写 `[{"pointer":"/id","expected":"{{order_id}}"}]`，保存为查询用例。
3. 用例集按创建、查询排序后运行。每次运行使用本次返回的新 ID，详情可查看模板快照、实际输入和导出变量。

仅全部断言通过的步骤才导出变量；任意提取失败则该步为 error，整组变量都不导出。上游失败后，依赖其变量的步骤跳过且不发送 HTTP 请求，不依赖这些变量的后续步骤仍继续。保存和运行用例集时均拒绝前向引用、未声明变量和重复导出名。

引用必须占满字段值，如 `{{order_id}}`；支持路径/查询参数值、JSON 请求体值和 JSON 断言期望值。路径和查询参数转为字符串，请求体和断言保留数值、布尔等标量类型。不支持字符串拼接、动态键名、脚本、URL/方法/Header 模板。服务端返回的字符串只替换一次，不作为模板再次解释。

变量名以英文字母开头，仅含字母、数字、下划线，最长 64 字符。每条用例最多提取 10 个变量，使用固定 JSON Pointer；值须为非 null 的字符串、有限数值或布尔值，每值最多 4 KiB。对象、数组、已遮盖字段及已知 token/password 等敏感名称不能提取。

变量仅在一次用例集运行中有效，没有全局或初始变量，也不跨运行复用。含引用的用例需在用例集中执行；无引用的生产用例可以单独执行并查看导出值。原有用例和报告仍兼容，无数据库表结构变更。详细验收见 [Day 6 记录](docs/day-6.md)。

## GitHub 与密钥

Public 仓库：[SZpengyuyan/qualityops-agent](https://github.com/SZpengyuyan/qualityops-agent)。阶段分支为 `codex/day-1-infrastructure`、`codex/day-2-project-management`、`codex/day-3-openapi-import`。已完成设备认证并配置 `origin`；后续推送前可检查：

```powershell
gh auth status
git remote -v
gh repo view SZpengyuyan/qualityops-agent
```

若未认证，需要用户完成 `gh auth login --web`。请勿把 API Key 写入代码或 Git；当前阶段无需任何 AI API Key。`.venv/`、`.tools/`、`.env`、数据库与构建产物均已忽略。
