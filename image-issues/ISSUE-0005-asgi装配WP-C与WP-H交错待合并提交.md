---
id: ISSUE-0005
title: asgi.py 同时含 WP-C(selection) 与 WP-H(admin/model_config) 装配，需由 WP-H 合并提交
status: 已修复        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: 开发        # WP-C
owner: QA             # WP-H 已合并提交并复验，转 QA 终验/关闭
created: 2026-06-01
updated: 2026-06-01
related:
  - code: image-code/src/design_hub/interface/api/asgi.py
  - WP: WP-C（选稿+评分，本单元）/ WP-H（模型配置后台，并行）
---

## 现象 / 背景
多 agent 共写同一工作树。WP-C 完成时按任务要求在 `asgi.py` 加了自己的两处装配：
1. `app.state.selection_service = SelectionService(images=SqlAlchemyGeneratedImageRepository(...))`
2. `app.include_router(selection.router)`（+ 对应 import）

与此同时 WP-H 也在 `asgi.py` 加了 admin/model_config 的装配与
`app.include_router(admin.router)`（+ import `application.admin.*`、`infrastructure.db.model_config_repo`、
`routes/admin`）。当前 `asgi.py` 工作区**已同时含两套装配行**，`ruff`/`mypy`/本地 import 均绿。

## 为什么 WP-C 不单独提交 asgi.py
- `asgi.py` 现**硬依赖 WP-H 尚未提交（git 未跟踪）的 admin 模块**（`application/admin/`、
  `interface/api/routes/admin.py`、`infrastructure/db/model_config_repo.py`、
  `ports/model_config_repository.py` 等）。若 WP-C 单独 `git add asgi.py` 提交，HEAD 的
  `asgi.py` 会 import 不存在于 git 的模块 → 干净检出下 `from design_hub.interface.api.asgi import app`
  **import 失败**，破坏构建。
- 若把 WP-H 的未提交文件一起 `git add` → 把他人未验证代码扫进 WP-C 提交（即 ISSUE-0004 的教训），
  违反「只提交自己显式路径」铁律。
- 不能对 WP-H 正在编辑的 `asgi.py` 做 `git checkout`/覆盖手术（会毁其未提交工作）。

## 期望处理（owner=WP-H）
WP-H 提交 admin 模块时，用显式路径连同 `asgi.py` 一并提交，**保留 WP-C 已在 asgi.py 的两处
selection 装配行**（合并双方的行，勿回退）。提交后 HEAD 的 asgi 即自洽可 import。

## 验证（提交后任一 agent/QA 可复验）
1. `cd image-code`
2. `uv run python -c "from design_hub.interface.api.asgi import app; print(sorted(r.path for r in app.routes if getattr(r,'path','').startswith('/jobs')))"`
3. 期望含 `/jobs/{job_id}/images`、`.../score`、`.../keep`、`/jobs/{job_id}/usable-rate` 四条（WP-C），
   且 `/admin/*`（WP-H）同时在册；`uv run ruff check src` + `uv run mypy` 全绿。

## 处理记录
- 2026-06-01 [开发] WP-C 完成选稿+评分(端口/仓储/用例/schema/deps/路由均已独立提交并 smoke 绿)，
  asgi.py 两处 selection 装配行已就位但因上述跨依赖**不单独提交**；开单交 WP-H 合并提交。
  状态=待验证，owner=WP-H。
- 2026-06-01 [开发] WP-H 已按要求合并提交：commit **621ce68** 用显式路径提交 admin 模块 + `asgi.py`，
  **保留 WP-C 两处 selection 装配行未回退**（其源码已在 HEAD，提交后 asgi 自洽）。复验通过：
  `from design_hub.interface.api.asgi import app` 正常，路由含 WP-C 四条 `/jobs/*`
  (images/score/keep/usable-rate) + WP-H `/admin/models`·`/admin/models/{name}`；ruff+mypy(133) 全绿。
  状态→已修复，owner→QA。
