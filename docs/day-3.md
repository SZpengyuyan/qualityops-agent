# Day 3：OpenAPI 文档导入与接口目录

日期：2026-11-23（Asia/Shanghai）。范围：项目内导入 OpenAPI JSON、离线校验、持久化与接口目录展示。

## 修改文件与设计

- `backend/app/services/openapi.py`：独立解析服务，格式、容量、复杂度与引用校验；使用 `openapi-spec-validator` 检查规范；合并参数并保留请求/响应定义。
- `backend/app/models.py`：新增 `openapi_documents` 表，每项目一份原始文档和解析快照。仅新增表，不改动既有项目表。
- `backend/app/routers/openapi.py`：文档导入/摘要、接口列表/筛选/详情；`main.py` 注册路由。
- `backend/app/routers/projects.py`：删除项目时先清理关联文档。
- `frontend/src/OpenAPIManager.tsx`：本地文件、粘贴、替换确认、目录、筛选和详情。`ProjectManager.tsx` 挂载组件，`api.ts` 展示后端可读校验错误。
- `backend/requirements.txt`、`requirements.lock.txt`：新增并锁定规范校验依赖。`docs/examples/orders.openapi.json` 提供可直接导入的三接口示例。

接口模型和参数覆盖遵循 [OpenAPI 3.1 规范](https://spec.openapis.org/oas/v3.1.0.html)，规范校验采用 [openapi-spec-validator Python API](https://python-openapi.org/openapi-spec-validator/docs/latest/python.html)。本阶段支持规范的明确子集，详见 README。

## 命令与结果

- `backend/` 下运行 `..\.venv\Scripts\python.exe -m pytest -q`：**42 passed, 1 warning**。覆盖已有模块与新增导入、筛选、引用、替换、异常数值/Unicode 和持久化测试。
- 根目录运行 `scripts/frontend.ps1 build`：TypeScript 检查和 Vite 生产构建通过。
- `python -m pip check`：`No broken requirements found.`；依赖已写入锁文件。
- `git diff --check`：提交前执行，检查空白错误。

## 浏览器与实际服务验收

1. 创建明确标识的临时项目，在项目详情打开导入表单。
2. 粘贴缺失 `info/paths` 的无效 JSON，显示可读错误，无目录写入。
3. 使用文件选择器选取订单示例 JSON，成功导入 3 个接口，显示文档版本和导入时间。
4. 按 POST 方法筛选，仅显示创建订单；打开请求体和响应定义，显示必填字段、数量约束、201/409 响应。
5. 重新导入前显示替换确认。确认导入无效文档后显示错误，原目录仍保留。
6. 整页刷新后目录仍包含原来 3 个接口。按 Orders 标签与 getOrder 搜索，显示订单详情接口；路径参数 `order_id` 的内部引用已解析，`required: true` 保留。
7. 截图存于被忽略的 `.verification/day3-openapi.jpg`。按精确 ID、名称、描述校验后通过 API 删除本轮临时项目，返回 204；刷新页面确认恢复空列表，连接状态为 Connected。

## 限制与后续

- 本阶段不调用待测接口，不生成测试用例，不包含 RAG 或 LLM；下一阶段可接入确定性的 HTTP 执行与断言。
- YAML、外部文档引用、自定义 Schema 资源/方言、OpenAPI 3.2、callbacks/webhooks 目录和文档版本历史暂不支持。Schema `$ref` 保留为符号引用，详情不自动展开关联 Schema。
- 浏览器覆盖 JSON 文件读取和错误粘贴；完整有效 JSON 的粘贴导入与成功替换由后端接口测试覆盖，未另外重复浏览器流程。
- `create_all` 仍不负责已有表结构迁移；多用户权限、并发导入冲突检测和 Docker 验证尚未完成。
- 保留一条已知 Starlette/HTTPX 第三方弃用警告，未屏蔽。
