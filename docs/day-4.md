# Day 4：复查修复与 HTTP 执行

日期：2026-11-24（Asia/Shanghai）。先复查 Day 3，修复后再实现确定性的 HTTP 执行和断言，未接入 LLM。

## 复查结果

- 已复现并修复 OpenAPI 3.0 引用同级字段覆盖问题：路径参数的 required:true 曾可被引用旁的 required:false 错误替换。3.0 现在忽略同级字段，3.1 仅允许 summary/description 的引用覆盖；Schema 引用仍保持符号形式。
- 解析快照大小检查改为增量编码，超限时停止，避免先创建完整的大字符串。
- 刷新接口目录会关闭旧详情，避免同一接口 ID 显示旧文档的数据。
- 修复单独提交为 85f8825；修复后的后端回归为 45 passed，前端生产构建通过。未发现其他阻塞下一阶段的问题；这不是全面安全审计。

## 新增模块与文件

- backend/app/services/execution.py：地址校验、参数组装、HTTPX 流式请求、总超时、响应上限、状态码与 JSON Pointer 相等断言。
- backend/app/routers/executions.py：执行接口、项目内分页记录和详情；main.py 注册路由。
- backend/app/models.py：新增 executions 表；projects.py 删除项目时清理记录，项目编辑不影响历史。
- frontend/src/ExecutionPanel.tsx：执行配置、逐项断言、响应内容和分页历史；OpenAPIManager.tsx 挂载组件并同步忙碌状态。
- demo-api/main.py、scripts/demo-api.ps1：本地订单服务，支持创建、查询和库存不足场景，使用现有 Python 依赖。
- backend/tests/test_execution.py：执行器、路由持久化和 Demo API 测试；backend/.env.example 说明允许执行的 origin 配置。

超时与请求 API 依据 [HTTPX 官方文档](https://www.python-httpx.org/advanced/timeouts/)。没有增加第三方依赖。

## 命令与结果

- 在 backend/ 使用虚拟环境执行 python -m pytest -q：**58 passed, 1 warning**。覆盖原有模块、请求序列化、路径编码、允许目标、参数校验、可选认证、JSON Pointer、布尔值/数字区别、超时与网络错误、响应上限、禁止重定向、字段遮盖、历史持久化与跨项目隔离。
- 根目录执行 scripts/frontend.ps1 build：TypeScript 与 Vite 生产构建成功。
- git diff --check：提交前检查空白错误。
- Docker 未安装，容器流程未验证；现有 Compose 不包含 Demo API，容器内 loopback 与宿主机不同，本地演示步骤不代表 Docker 验收。

## 浏览器与真实网络验证

1. 启动本地 8000 后端、9000 Demo API，沿用 5173 Vite 服务。
2. 浏览器创建临时项目并粘贴导入订单创建接口定义。
3. quantity=1、期望 HTTP 201、JSON /status 等于 created：实际返回 201，状态码及 JSON 断言通过。
4. quantity=4、仍预期 201：实际返回 409，断言失败，响应说明 Insufficient stock。
5. quantity=4、期望 409、JSON /detail 等于 Insufficient stock：负向用例通过。
6. 整页刷新后保留三条执行记录；打开历史详情可查看实际响应和逐项结果。截图为 .verification/day4-execution.jpg（已被 Git 忽略）。
7. 核对 ID、名称、描述后清理临时项目及文档/执行记录，DELETE 返回 204；浏览器刷新恢复空列表与 Connected。Demo 内存保留一条 qa-demo 验收订单，重启 Demo 服务即可清空。

## 当前边界

仅面向本地单用户测试环境，无登录权限、后台任务、批量用例、跨步骤变量传递或自动 Schema 断言。JSON 字段遮盖只匹配已知名称，无法识别任意文本中的秘密。

超时不保证远端写操作未执行，平台不自动重试。总超时与响应上限已实现，尚无跨用户并发配额。其他客户端在执行期间删除项目或并发修改文档的冲突处理仍待完善。

保留第三方 Starlette/HTTPX 弃用警告，未屏蔽。下一阶段可建立可保存的测试用例与用例集，再接 Agent 工具注册和任务规划。
