---
id: ISSUE-0070
title: 管理后台独立验收
status: 待复现
severity: P1
reporter: 开发
owner: QA
created: 2026-07-30
updated: 2026-07-30
related:
  - PRD: image-code/docs/superpowers/specs/2026-07-30-admin-console-design.md
  - code: image-code/src/design_hub/interface/api/routes/admin.py
  - code: image-web/src/components/admin/AdminLayout.tsx
  - test: image-code/tests/test_admin_api.py
  - test: image-code/tests/test_image_moderation.py
  - test: image-web/src/pages/AdminGenerationsPage.test.ts
---

## 现象

管理后台、模型调用计量、用户状态控制和图片审核能力已完成开发自测，需要 QA 独立验证权限、计量、审核与审计闭环。

## 复现步骤

1. 使用管理者和普通用户各一个账号，在已执行最新 Alembic 迁移的 QA 环境登录。
2. 依次验证 `/admin`、用户管理、出图审核、API 用量、模型配置和操作记录页面。
3. 准备一条包含输入图、结果图和生成明细的任务；由管理者屏蔽其中一张结果图。
4. 使用图片所属普通用户检查历史、Chat、下载、反推提示词、二次编辑和换背景入口。
5. 恢复图片并复查普通用户入口和管理员操作记录。
6. 按下列验收矩阵执行接口、数据库和前端检查。

## 验收矩阵

| # | 验收项 | 期望 |
|---|---|---|
| 1 | 管理者专属路由与 API | 管理者可访问；普通用户访问管理前端进入 403，管理 API 返回 403。 |
| 2 | 当前账号与最后管理者保护 | 管理员不能停用或降级自己；最后一名启用中的管理者不能被停用或降级；前端禁用入口，后端仍独立返回冲突。 |
| 3 | 停用账号的现有凭证 | 停用后，原 Bearer JWT 和 SSE token 在下一次受保护请求均返回 401；恢复后允许重新登录。 |
| 4 | GPT Image 调用次数 | generation/edit 每次真实上游 POST 均计一次，真实重试逐次计数；异步 poll、CDN 下载不计数。 |
| 5 | 豆包多轮 Token | Chat 请求携带 usage 选项；末尾 usage chunk 能记录输入、输出和总 Token；同一消息的多轮调用逐轮落库。 |
| 6 | 跨用户任务预览 | 管理者可查看全部用户任务、用户提示词、输入图、结果图和生成明细；普通用户仍只能查看自己的任务。 |
| 7 | 图片屏蔽与恢复 | 屏蔽后，普通用户在历史、Chat、下载、反推提示词、二次编辑和换背景入口均不能取得图片，只显示“该图片暂不可用”；管理员仍可预览；恢复后入口重新可用。 |
| 8 | 已签 URL 时限 | 平台不再为屏蔽图签发普通用户 URL；屏蔽前已复制的签名 URL 最长可能继续有效约一小时，过期后不可再取。 |
| 9 | 审计安全与事务原子性 | 角色、状态、审核和模型配置动作均有审计；不包含 API Key、密码或完整提示词；业务修改与审计写入同时成功或同时回滚。 |
| 10 | 筛选、分页与历史口径 | 时间、用户、模型、状态、功能筛选准确；翻页无重复漏项；旧数据不反推调用或 Token，页面明确标注统计从本版本开始。 |

## 期望 vs 实际

- 期望：以上十项全部通过，且六个管理页面具备加载态、空态、错误态和权限态。
- 实际：开发侧自动化与本地烟测通过，等待 QA 在独立环境复验。

## 环境 / 上下文

- 分支：`codex/admin-console`
- 后端自测：434 passed，13 skipped；Ruff、Mypy、Alembic upgrade/check 通过。
- 前端自测：112 passed；ESLint、TypeScript、生产构建通过。
- 本地烟测使用 `REAL_GPT_IMAGE=false`，未发送 GPT Image 或豆包真实上游流量。
- 开发烟测已验证管理者跨用户预览、屏蔽、普通用户中性不可用占位、恢复和审计记录；临时账号与审核数据已清理。

## 处理记录

- 2026-07-30 [开发] 创建独立验收单，状态=待复现，owner=QA
