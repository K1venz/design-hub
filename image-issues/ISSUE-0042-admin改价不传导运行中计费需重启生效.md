---
id: ISSUE-0042
title: admin 改价不传导到运行中出图计费（unit_cost 启动快照）——「热更」名不副实、重启才生效
status: 已确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # 当前无资损(prod 计费已是 0.40 且正确);toC 调价时代价=改价后忘重启 → 计费用旧价(资损面)
reporter: QA(套图回归实测 qa 计 1.19 vs admin GET 0.40)
owner: 开发
created: 2026-06-10
related:
  - code: image-code/src/design_hub/interface/api/asgi.py:71-73（lifespan 启动读 unit_cost_map 一次 → 注入 provider 构造）
  - code: image-code/src/design_hub/composition.py build_gpt_image_provider（unit_cost 构造时固化进 provider 实例）
  - code: image-code/src/design_hub/application/admin/model_config_service.py:27（PUT 只改 DB 行）
  - 群聊: #514/#515/#516（QA 与 ops"矛盾"实为快照语义）
---

## 现象
qa 套图回归：出图计费 1.19/张（cost_ledger/job total_cost），但 `GET /admin/models` 显示 0.40——
admin 改价（PUT）看似生效（DB 行已 0.40）、出图计费却用旧价。

## 根因（读码实锤）
- `asgi.py:71` lifespan **启动时读一次** `unit_cost_map()` → `build_registry(unit_costs=...)` →
  unit_cost **构造时固化进 provider 实例**（快照语义）。
- `PUT /admin/models/{name}` 只改 DB 行；**运行中 registry 里的 provider.unit_cost 不变**，
  直到下次进程重启（lifespan 重新读库）。WP-H 注释「单价热更覆盖」名不副实——是「重启时更」。

## 时序还原（QA #516 与 ops #515 都对、无矛盾）
- qa：容器重建(#500，DB 行=1.19) → provider 快照 1.19 → ops PUT(#503，DB→0.40，admin GET 读库=0.40)
  → 出图仍按快照 1.19。
- prod：ops PUT 0.40(#219) **早于**其后多次重建（067907f/e8cbe79/9c80064）→ 每次重启快照 0.40
  → 出图 0.40 正确（QA prod 实测 a664f534/7b64e81c=0.40 佐证）。
- **部署套图版（0e9ee9d 重建）后 qa/prod 都会重新读库（两边 DB 行均已 0.40）→ qa 即自愈。**

## 影响
- 当前零资损（prod 计费正确）。
- 风险在将来 toC 调价：改价后**忘重启 → 出图按旧价计**（只改了显示没改计费）= 资损面。

## 修复方向（dev，二选一，PM 排期）
1. **真热更**：PUT handler 同步刷新 app.state 里 registry 的 provider unit_cost（或 provider 每次
   generate 时从 model_config 读价）——改价即时生效。
2. **MVP 档**：不改码，把「改价后需重启/重部署生效」写进 admin 操作口径（PRD/运维 runbook），
   ops 改价 SOP 加一步重启。改价频率极低（季度复核），可能够用。

## 处理记录
- 2026-06-10 [开发] QA 套图回归发现(#516)、coordinator 派开条(#517)。读码定根因=启动快照、
  PUT 不传导运行实例；时序还原 QA/ops 无矛盾；prod 当前计费正确、部署 0e9ee9d 重建后 qa 自愈。
  owner=开发，修复方向二选一待 PM 排期（不阻断套图部署）。
