---
id: ISSUE-0037
title: gpt-image-2 中转 key 失效（401 Invalid token）致真实出图全失败（qa+prod 同一把死 key）
status: 已确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # 阻断 listing 上线验收的真实出图链路；prod 同 key 潜伏
reporter: QA
owner: 运维            # 环境/密钥归 ops；换 key 后交回 QA 续跑验收
created: 2026-06-08
updated: 2026-06-08
related:
  - issue: 0035(listing 上线验收，A3/A4/F 被此阻塞) / 0025(gpt-image 上游对齐) / 0033(TOS prod)
  - code: image-code 的 GPT_IMAGE_* provider 装配（build_gpt_image_provider）
  - env: server design-hub-qa-api + design-hub-api 容器 GPT_IMAGE_API_KEY
---

## 现象
listing 真实出图 100% 失败：`POST /listing/generate` 返 200 入队，但 SSE **1-2s 内即 `task_failed`**（非超时）。
`listing_job.error`（design_hub_qa 只读 DB）三连一致：

```
gpt-image-2 401 (不切备): {"error":{"code":"","message":"Invalid token (request id: ...)","type":"new_api_error"}}
```

即中转站（apinebula / new-api 网关）以 **401 Invalid token** 拒绝当前 API key。

## 复现步骤
1. server qa 实例（design-hub-qa-api，main HEAD 612d474，env GPT_IMAGE_*=服务器现成 key）。
2. 自注册 designer → `POST /uploads` → `POST /listing/generate {n=1}` → 订阅 SSE。
3. 1-2s 内收 `task_started → task_failed`；查 `listing_job.error` = `gpt-image-2 401 Invalid token`。
4. （脚本 `image-qa/listing_history_e2e.py`，QA_BASE=http://localhost:8444）

## 期望 vs 实际
- 期望：真实出图成功（`image_generated → task_completed`），出真图、落库、计费 ~¥1.19/张。
- 实际：中转 401，`task_failed`，0 成本（额度回滚正确）。

## 根因（已 fingerprint 比对，非 qa 配错）
qa 容器与 **prod 容器 gpt key 完全相同**：`md5_8=4f3abbc6`、`len=51`、单 key、同 `GPT_IMAGE_BASE_URL=https://apinebula.com/v1` + `GPT_IMAGE_MODEL=gpt-image-2-vip`。
→ **这把 server key 本身被中转站拒**，与 qa 隔离无关。

⚠️ **连带 prod**：prod `design-hub-api` 用的是同一把死 key → prod listing 真实出图现在也会 401（prod `listing_job=0` 暂无用户触发，是潜伏隐患，非仅 qa 问题）。

🔎 线索：本机 `image-code/.env` 的 `GPT_IMAGE_API_KEY` 是 **103 字符**（dev #61，疑多 key 逗号分隔），而服务器容器是 **51 字符单 key**——两者不同。**服务器这把(51)失效、本机那把(103)疑有效**。

## 建议修复（owner=ops）
1. 用本机 `image-code/.env` 的 103 字符 key 重配 server 容器（qa 优先；prod 同步换，否则 prod 出图潜伏 401）。
2. 或向中转站（apinebula）核对/更换有效 key（确认余额 + token 未过期）。
3. 换 key 后 QA 即续跑 0035 的 A3/A4/F（真实出图），无需重跑已绿项。

## 已验绿（不依赖出图，本 issue 不影响这些）
boundary 20/22（4xx fail-fast）、B 失败落库、B2/B3 分页详情、**C1 输入图回显 200（TOS qa-upload 桶现签）**、D1 越权 404、D2 401、E 失败成本回滚 0。

## 环境 / 上下文
server 203.0.113.10，design-hub-qa-api 容器（172.18.0.4:8000，main HEAD 612d474）；中转 apinebula.com/v1 gpt-image-2-vip；2026-06-08。
06-04 实测同链路曾真实出图成功（¥2.38），故 key 系**近期失效**（过期 / 被换 / 余额）。

## 处理记录
- 2026-06-08 [QA] 创建，状态=已确认。跑 0035 ③ history n=1 出图 3/3 401，fingerprint 比对确认 qa+prod 同一把 key 失效。owner=ops，换 key 后交回 QA 续跑 A3/A4/F。
