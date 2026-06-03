---
id: ISSUE-0016
title: 去 Redis 后，跨角色文档/脚本/PRD 仍引用 Redis/arq/worker，需各角色清理
status: 待确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: 开发
owner: PM             # 球在 PM 排期/更新 PRD；FE/QA 各自清理（见下）
created: 2026-06-03
updated: 2026-06-03
related:
  - code: image-code/src/design_hub/interface/api/asgi.py（去 Redis，commit fc41318）
  - PRD: §6.2 / §6.4（仍写 Redis+arq）
---

## 背景
用户拍板**本项目不再用 Redis**（覆盖 PRD §6.2/§6.4）。开发已把异步出图+SSE 改为
**单进程内存实现**（`InProcessTaskQueue` + `InMemoryEventBus`），删除 arq worker /
RedisEventBus / ArqTaskQueue / payload / `Settings.redis_url`，`uv remove arq`（commit fc41318）。
后端已无任何 Redis 依赖；但**其它角色文件夹仍有 Redis/arq/worker 引用**，开发只写
image-code/image-issues，无法代改，列此条指给各角色。

## 待清理清单（各角色自行更新）
- **PM（image-prd/）**：`2026-05-27-design-platform-prd.md` §6.2/§6.4 的「Redis + arq 任务队列」
  改为「单进程内存队列/事件总线（单实例部署）」；多副本扩展再回退分布式队列。
- **前端（image-web/）**：`README.md` 若提到后端需 Redis/worker 启动，删去；异步出图只需起 asgi。
- **QA（image-qa/）**：`verify_fixes.py`、`e2e_driver.py`、`2026-06-02-e2e-集成验证.md` 里
  起 Redis / `uv run arq ... worker` / `REDIS_URL` 的步骤删除——现在**只起 `uvicorn asgi:app`** 即可
  跑异步+SSE（无需 Redis）。`.env` 也不再需要 `REDIS_URL`。

## 期望 vs 实际
- 期望：全仓文档/脚本与「去 Redis、单进程异步」一致。
- 实际：后端已去 Redis，但跨角色文档/脚本/PRD 仍按 Redis 架构描述，会误导新窗口与 QA。

## 影响
- 不阻断后端（后端已自洽无 Redis）；属文档/脚本一致性。QA 若照旧脚本起 Redis/worker 会扑空。

## 处理记录
- 2026-06-03 [开发] 去 Redis 重构落地（fc41318）；扫到跨角色仍有 Redis 引用，开条目指给 PM/FE/QA。
  开发侧（image-code + docs/项目状态与接口清单、工期与进度跟踪）已同步更新。状态=待确认，owner→PM。
