---
id: ISSUE-0012
title: 缺「项目级 jobs/images 列表」端点，FE-3 选稿持久化 + FE-5 导出无法独立枚举
status: 待验证
severity: P1
reporter: 前端
owner: QA
created: 2026-06-02
updated: 2026-06-02
related:
  - code: image-code/src/design_hub/interface/api/routes/selection.py
  - code: image-code/src/design_hub/interface/api/routes/export.py
  - 接口: GET /jobs/{job_id}/images (需先有 job_id) · POST /projects/{id}/export (需 image_ids[])
  - 前端卡: docs/前端工作包拆分.md FE-3 / FE-5
---

## 现象
前端要做 选稿(FE-3) 与 导出(FE-5)，但当前 26 端点**无法从项目枚举其出图任务/候选图**：

- 选稿：`GET /jobs/{job_id}/images` 必须**先有 job_id**，而 job_id 只来自 `POST /projects/{id}/generate` 的同步响应（在内存里）。**页面刷新后丢失**，无法重新打开某历史任务的候选图。
- 导出：`POST /projects/{id}/export` 直接收 `image_ids[]`，但前端**没有端点列出项目下有哪些 image 可选**（GET 仅按 job_id 列图）。
- 没有 `GET /projects/{id}/jobs`，也没有 `GET /projects/{id}/images`。

结论：选稿/导出只能在「同一次出图会话内（拿着 job_id）」happy-path 跑通；**刷新/跨会话/独立进入导出**都无路可走。

## 期望 vs 实际
- 期望：前端能据 project_id 列出该项目（可选按 round_no/subscene 过滤）的出图任务与候选图，供选稿展示与导出勾选。
- 实际：只能按已知 job_id 查，job_id 无持久化获取途径。

## 建议方案（需后端实现，前端不碰 image-code）
二选一或都加：
1. **`GET /projects/{id}/jobs`** → 列项目下生成任务（job_id/round_no/subscene/used_model/total_cost/status/created_at/candidate_count）。前端据此再逐 job 拉 `GET /jobs/{job_id}/images`。
2. **`GET /projects/{id}/images[?round_no=&kept=]`** → 直接列项目所有候选图（含 id/job_id/score/kept/round_no），供导出勾选与「保留图」总览。

> 倾向**两者都加**：方案 1 支撑选稿按任务分组，方案 2 支撑导出/交付按项目选图。
> 数据已具备：`generation_job.project_id` + `generated_image.job_id` 关联即可聚合（参考 WP-E 的 `export_query.py` 已有 ⋈ 逻辑）。

## 影响
- **FE-3 选稿**：happy-path（出图后立即选稿）可做；持久化/重进选稿 受阻。
- **FE-5 导出**：独立进入「交付导出」tab 无法列图选 image_ids → **基本受阻**，需本端点。
- **FE-4 改稿**：关联候选图也依赖能列出图。

## 环境 / 上下文
- 前端 FE-0/1/2/6/7 已交付；本缺口与 ISSUE-0011(SSE+JWT) 共同挡住 FE-3/4/5 主链路。

## QA 验证步骤（开发建议）
- `GET /projects/{id}/jobs[?round_no=]` → 列本项目出图任务(job_id/round_no/subscene/family/tier/
  category/used_model/candidate_count/total_cost/status/created_at)，按 created_at 倒序；不跨项目。
- `GET /projects/{id}/images[?round_no=&kept=]` → 列本项目候选图(image_id/job_id/url/seed/score/
  kept/round_no/subscene)，round_no/kept 可过滤；不跨项目。
- 端点挂 login_required(需 Bearer)。

## 处理记录
- 2026-06-02 [前端] 创建，状态=待复现；FE-5 开工前核实后端无项目级图/任务列举能力，开条目指给开发。
- 2026-06-02 [开发] **已实现**(两端点都加)：CQRS 读侧——`ports/project_catalog.py`
  (ProjectCatalogQuery + ProjectJob/ProjectImage 读模型) + `infrastructure/db/project_catalog.py`
  (generation_job WHERE project_id；generated_image⋈job WHERE job.project_id；round_no/kept 过滤) +
  `application/project/catalog_service.py` + 独立薄路由 `routes/project_catalog.py`(不动 WP-A 的
  projects.py，同 /projects 前缀 FastAPI 合并) + asgi 装配/注册(login_required)。未动 schema。
  验证 ruff+mypy(176)+sqlite smoke(本项目任务/候选图列举 + round_no/kept 过滤 + 不跨项目)。
  状态→待验证，owner→QA。前端 FE-3 选稿持久化 / FE-5 导出枚举可解锁。
