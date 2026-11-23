# Day 2：项目管理

日期：2026-11-23（Asia/Shanghai）。在 Day 1 基础上完成项目管理闭环，不接入 OpenAPI 或 AI。

## 修改范围

- 后端：新增 `models.py`、`schemas.py`、`routers/projects.py`，实现项目创建、分页列表、详情、完整更新和删除。
- 数据库：共享请求级 Session 依赖；应用启动时创建缺失表。项目使用 UUID 与 UTC 时间，保存在已有 SQLite 数据库中。
- 前端：独立 `ProjectManager.tsx` 与 `api.ts`，集成到现有 Dashboard，提供分页、详情、表单、超时、异常与删除确认反馈。
- 文档：更新 README，保留 Day 1 历史记录。

## 已执行验证

1. 在 `backend/` 执行 `..\.venv\Scripts\python.exe -m pytest -q`：**20 passed, 1 warning**。原有 5 项健康检查测试全部通过；新增测试覆盖 CRUD、无效输入不写库、规范化后过长 URL、UUID/404、分页参数、应用重启后持久化及无效更新不破坏原数据。
2. 在根目录执行 `scripts/frontend.ps1 build`：TypeScript 与 Vite 生产构建通过。
3. 浏览器经 Vite 代理创建临时项目，列表显示成功；整页刷新后仍存在。
4. 浏览器读取项目详情，确认数据库 UUID、UTC 创建时间及配置字段；编辑名称并保存，列表与详情均显示新值。
5. 浏览器打开删除提示，再点击“保留项目”，确认取消路径正常。随后通过 API 按精确 ID、名称与描述校验后清理本轮自动创建的临时项目，DELETE 返回 **204**；刷新页面恢复空列表。未删除用户已有项目。
6. 浏览器页面同时显示 API、SQLite `Connected`。验收截图保存在被 Git 忽略的 `.verification/day2-project.jpg`，截图中的临时项目已清理。

## 设计与限制

- 路由按照 FastAPI 的 [APIRouter 组织方式](https://fastapi.tiangolo.com/tutorial/bigger-applications/)拆分，数据库沿用 SQLAlchemy 2.0 的 [Session 与 select](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)。
- 无新增第三方依赖。按 React best practices 检查：组件独立、列表使用稳定 ID、请求在卸载/切换时取消、表单带标签、写入期间防止重复提交。
- UI 的删除确认与取消已实测；确认删除的点击路径未做浏览器自动化验证，DELETE 行为由后端测试及实际 API 验证覆盖。
- 仍有 Day 1 的 Starlette/HTTPX 弃用警告，未屏蔽。
- `create_all` 仅负责创建缺失表；已有表的结构变更需要后续迁移方案。当前无认证、多用户权限和并发编辑冲突检测。
- Docker 未安装，容器构建与启动仍未验证。
