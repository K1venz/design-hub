---
id: ISSUE-0037
title: gpt-image-2 中转 key 失效（401 Invalid token）致真实出图全失败（qa+prod 同一把死 key）
status: 已修复        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起（qa+prod 双侧 base key 已换、prod 真出图三查 PASS、档位定 base；待上线确认翻已关闭）
severity: P1          # 阻断 listing 上线真实出图链路；qa+prod 双侧已解
reporter: QA
owner: coordinator    # qa+prod 已解、档位定 base；遗留小尾=ops ¥0.40 PUT + test 残留(coordinator 决定留作凭证)；上线确认后翻已关闭
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
server 14.103.51.191，design-hub-qa-api 容器（172.18.0.4:8000，main HEAD 612d474）；中转 apinebula.com/v1 gpt-image-2-vip；2026-06-08。
06-04 实测同链路曾真实出图成功（¥2.38），故 key 系**近期失效**（过期 / 被换 / 余额）。

## 处理记录
- 2026-06-08 [QA] 创建，状态=已确认。跑 0035 ③ history n=1 出图 3/3 401，fingerprint 比对确认 qa+prod 同一把 key 失效。owner=ops，换 key 后交回 QA 续跑 A3/A4/F。
- 2026-06-08 [运维] qa 侧已修：本机 image-code/.env 的 2 把 key 实测 /models=200 有效（md5 aa9eb65f+9cfc19e2，均≠服务器死 key 4f3abbc6）。只取 GPT_IMAGE_*（TOS 仍 qa 桶不动）安全写入 server qa.env（key 走 stdin、未进群/argv），qa 容器顺带从 HEAD 797ca06(含 B4 修复)重 build 并重建（172.18.0.4:8000，localhost:8444 不变）。/models 200 仅证鉴权，余额/quota 待 QA 首张 n=1 见真章。状态=待验证，owner=QA。
- 2026-06-08 [运维] ⚠️ prod 侧 key 同样失效但**未动**（按 coordinator：救 prod 是单独生产变更，coordinator 正报用户拍）。prod listing_job=0 暂无触发、潜伏。prod 修复决策落地前此条不关闭。
- 2026-06-08 [QA] 首张 n=1 见真章**仍失败**，但根因前进一层：错误由 `401 Invalid token` → **`403 This token has no access to model gpt-image-2-vip`**。即新 key 鉴权已通过，但其中转站账号**仅有 `gpt-image-2` 权限、无 `gpt-image-2-vip`**。QA `/models` 实测（零成本、key 脱敏）：新 key 可见 gpt-image 模型 = **仅 `gpt-image-2`**。而 qa 容器 `GPT_IMAGE_MODEL=gpt-image-2-vip` → 403。
  **待决策**：A) ops 改 qa 容器 `GPT_IMAGE_MODEL=gpt-image-2`（前提 dev 确认 base 支持 /images/edits；pm 注意 F1 口径变 base 非 vip），QA 复跑 1 张验证；B) 中转站账号给 vip 权限 key（coordinator 找用户）。QA 倾向先试 A。状态=已确认（仍阻塞），owner=运维。
- 2026-06-08 [运维] 执行 A：qa 容器 `GPT_IMAGE_MODEL` 由 `gpt-image-2-vip` 改 `gpt-image-2` 并重建（172.18.0.4，localhost:8444 不变，容器内 model 确认=gpt-image-2，openapi 200）。交 QA 复跑 1 张验证。前提 dev 确认 base 支持 /images/edits、F1 口径归 pm；若 base 仍不通则上 B（vip key=用户层）。prod 仍未碰。owner=QA。
- 2026-06-08 [QA] **qa 侧已解决 ✅**：base `gpt-image-2` 复跑 n=1 **200 出图成功**（127s，task_completed，真图 TOS qa-generate 桶，¥1.19）→ 证 base 支持 /images/edits + 余额够（dev #116 判对：vip 仅计费档、base 同底模同端点）。0035 验收 A–F 全绿（F1 可用率 87.5-100%、F2 P95 193s PASS）。**qa 出图阻塞彻底解除**。
  ⚠️ 遗留两条（非 qa 验收阻塞）：① **prod 侧 key 仍是死的 4f3abbc6**——prod listing 真实出图现在仍会 401，coordinator 报用户拍（救 prod=生产变更）；② 上线档位 vip vs base 决策（PM 建议 base：成本省½ $0.05 vs $0.10 + 便利现成 key + 速度 PASS）。owner→**coordinator**（prod key + 档位决策）。qa 验收侧此条可视为已闭环。
- 2026-06-09 [QA] **prod 侧已解决 ✅（上线硬 gate 通过）**：用户授权后 ops 换 prod `.env` 有效 base key（103 字符 md5=9309c033、≠死 key 4f3abbc6）+ `GPT_IMAGE_MODEL`→`gpt-image-2`（base 定档）+ force-recreate design-hub-api（备份 .env.bak-keyfix-20260609 可回滚）。QA 经 prod api 隧道（localhost:8445）跑 prod 真出图三查**全 PASS**：① 非 401·真出图（job `de40363e…` task_completed 84s ¥1.19）② 落点=prod 桶 `bucket-design-hub-generate`（非 qa）③ SSH 核 prod 容器 `GPT_IMAGE_MODEL=gpt-image-2` + key md5 9309c033。**prod 上线就绪：用户上线不撞 401、出图落 prod 桶、跑 base 档**。档位 vip/base 已由用户拍定 **base**。→ 两条遗留全消，状态=**已修复**。遗留小尾（非阻塞）：ops 触发 ¥0.40 model_config PUT + 清 prod 测试残留（job de40363e + 用户 qa-prod-verify@example.com）。owner=coordinator（上线确认后翻已关闭）。
- 2026-06-09 [运维] 遗留小尾①已做：prod model_config `gpt-image-2` `unit_cost` 经 manager PUT `1.1900→0.4000`（改前后 GET 实证、http=200，PM 定 ¥0.40 占位价）。②prod 测试残留（job de40363e + qa-prod-verify 号）按 coordinator 指示**留着别清**（作上线前已验真凭证 + 回滚参照），coordinator 跟用户确认后再由 ops 清。ops 侧本条无遗留动作，待 coordinator 上线确认翻已关闭。
