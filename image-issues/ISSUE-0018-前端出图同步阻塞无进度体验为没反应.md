---
id: ISSUE-0018
title: 前端「出图」走同步阻塞 + 默认 n=6 真实 GPT + 无进度，体验为"点了没反应"
status: 已关闭        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: QA
owner: —              # QA 复验通过关闭
created: 2026-06-03
updated: 2026-06-03
related:
  - 前端: image-web/src/components/generate/GenerateConfigForm.tsx（run() 走同步 useProjectGenerate）
  - 前端: image-web/src/api/generation.ts（useProjectGenerate / 缺 async+SSE 接入）
  - code: image-code/src/design_hub/interface/api/routes/async_generation.py（/generate/async + /events 已就绪）
  - 部署: https://203.0.113.10/projects/1（线上复现）
---

## 现象
线上 `https://203.0.113.10/projects/1` 点「出图」**长时间没反应**。

## 根因（已黑盒定位，非后端问题）
QA 在线上探测确认：
1. **后端完全正常**：前端可达(200)、`/api` 反代通、`/api/auth/login` 正常、`/api/generate/cost-preview` 返回
   `model=gpt-image-2`、真实 `n=1` 出图**成功**(HTTP 200, used_model=gpt-image-2, cost=1.19, 真图落库)。
   → 线上能真连中转站出真图，链路全通。
2. **前端用同步阻塞出图**：`GenerateConfigForm.run()` = `await generate.mutateAsync(payload)`
   （同步 `POST /projects/{id}/generate`），要等**整个出图响应**回来才有 toast 反馈。
3. **默认 `n=6` + `family_4`（路由真实 gpt-image）**：单次真实出图 1-4 分钟甚至更久（n=6 更慢，中转站
   偶发 500 触发重试），期间前端**只有 loading、无进度** → 用户感知为"点了没反应"（实际后台在跑）。
4. **后端异步能力早已就绪但前端没接**：`POST /generate/async`(Bearer)→job_id；
   `GET /generate/{job_id}/events?access_token=<JWT>` 走 SSE 推 `task_started→model_called→
   image_generated→task_completed`（去 Redis 后单进程内存实现，QA 已验即时/晚订阅均收齐全序列）。
   前端 `src/api/generation.ts` 全程只用同步端点，未接 async/SSE。

## 期望 vs 实际
- 期望：点出图后立即有进度反馈（进度条/逐张到达），不阻塞，可感知。
- 实际：同步阻塞数分钟、无进度，体验为无反应。

## 建议修复（前端）
1. **改用异步 + SSE**：`/generate/async` 拿 job_id → `EventSource('/api/generate/{job_id}/events?access_token='+jwt)`
   订阅进度（注意 token 走 query，原生 EventSource 不能带头，见 ISSUE-0011）→ `task_completed` 后拉
   `/jobs/{job_id}/images` 刷候选图。
2. **降默认 n**：首试默认 `n=1~2`（现 n=6 × 真实 GPT 体验最差）；或对真实模型给"预计耗时/张数"提示。
3. **明确 loading/进度态** + 失败 toast，避免"看起来没反应"。
4. （可选）`family_3`/草稿档走 Mock 即时返回，可作"快速预览"档。

## 处理记录
- 2026-06-03 [QA] 线上黑盒定位：后端出图正常(真实 n=1 出图成功)，"没反应"=前端同步阻塞+默认n=6真实GPT+无进度。
  后端异步+SSE 能力已就绪未被前端接入。开单指给前端，owner→前端。状态=待确认。
  注：诊断在线上 project 1 留了 2 个探针 job（1 mock + 1 真实¥1.19）与探针账号 qa-probe@test.com，可忽略/清理。
- 2026-06-08 [前端] **已被 listing 流整体取代而结构性解决**（非打补丁，按 NO 兼容铁律）：
  旧同步出图（`GenerateStudio` / `useProjectGenerate` / `GenerateConfigForm` / 默认 n=6 同步阻塞）在 ISSUE-0020 工作台重做中
  **已全部删除**（grep 确认 src 无残留）。新 `/`（listing 工作台）走 **异步 + SSE**：`POST /listing/generate` 立即返回 `job_id`
  → `EventSource /listing/{id}/events` 逐张到达 + 进度条（`ResultGallery` 显「已出 N/总」）→ 不再阻塞、有进度反馈。
  「点了没反应」的两个根因（同步阻塞 + 无进度）均不复存在。状态=待验证，owner=QA（QA 的 listing e2e 已实测异步出图+逐张到达通过，请据此确认关闭本条）。
- 2026-06-08 [QA] **复验通过关闭**：① 旧同步出图组件 `GenerateConfigForm/useProjectGenerate/GenerateStudio` 全树 grep **无残留**（已删）；② 新 listing 走**异步**(`POST /listing/generate`→job_id) + **进度 UI**(`ResultGallery` 显「已出 N/总 张…」、generating 态)；③ 后端异步+SSE 逐张到达(`task_started→model_called→image_generated×n→task_completed`)经 listing e2e 多次实测通过。「同步阻塞 + 无进度」两根因均消除。状态=已关闭。
