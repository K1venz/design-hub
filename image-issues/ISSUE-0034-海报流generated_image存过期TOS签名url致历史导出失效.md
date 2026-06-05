---
id: ISSUE-0034
title: 海报流 generated_image.url 落库的是会过期的 TOS 预签名 url，历史回看/导出会失效
status: 已确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # 海报流历史/导出随 TTL 过期成死链；listing 不受影响。若海报流产线活跃使用请 PM/开发升 P1
reporter: 运维
owner: 开发
created: 2026-06-05
updated: 2026-06-05
related:
  - code: image-code/src/design_hub/infrastructure/storage/tos.py:59-62（TosImageStore.save 返回预签名 url）
  - code: image-code/src/design_hub/infrastructure/db/job_repository.py:49,75（海报流把 url 直接落 generated_image.url）
  - code: image-code/src/design_hub/infrastructure/db/export_query.py:50,66（导出从 generated_image.url 读字节）
  - code: image-code/src/design_hub/infrastructure/db/listing_history_repo.py / listing_query_repo.py（listing 存 key、读时现签的正确范式，可对齐）
  - issue: ISSUE-0033（运维已激活 prod TOS，本条是其副作用，已在 0033 知会）
  - issue: ISSUE-0030（listing 存 key 不存 url 的做法）
---

## 现象
ISSUE-0033 激活生产 TOS（私有桶 + 预签名 url）后，**海报流**出图的结果 url 落库的是
**会过期的 TOS 预签名 url**（默认 `TOS_SIGNED_URL_TTL=3600s`）。超过 TTL 后：
- 海报流/项目候选图**历史回看裂图**（签名失效，TOS 返回 403）；
- **导出**（从 `generated_image.url` 读字节）也会取不到。

TOS 未激活（本地 `/img`，ISSUE-0029）时无此问题——这是**激活 TOS 的副作用**，根因在落库方式。

## 根因（读码定位）
- `TosImageStore.save()` 返回的是 `signer.generated_url(key)` = **预签名 url**（`storage/tos.py:59-62`），短期有效。
- **海报流** `JobRepository` 把 `image_store.save()` 的返回值（这个签名 url）**直接持久化**到
  `generated_image.url`（`job_repository.py:49,75`）→ 落库瞬间就埋下了「到点失效的死链」。
- 导出 `export_query.py` 又从 `generated_image.url` 读 → 同样受影响。

## 对照：listing 做对了（可直接对齐）
- listing（ISSUE-0030）`listing_image` 存的是 **`image_key`（文件名 `<sha>.png`），不存 url**；
  列表/详情**读时**用 `TosMediaUrlSigner.generated_url(key)` 现签（或本地拼 `/img/<key>`）→ **永不过期**。
- 海报流应对齐这个范式。

## 建议修复方向（开发定方案）
把海报流从「**存可访问 url**」改成「**存 key + 读时现签**」：
1. `generated_image` 存 **key**（文件名），不存签名 url——需评估是否给表加 `image_key` 列 + **additive 迁移**
   （涉及建表/改表，按规矩**先与用户确认 schema**，运维可在确认后部署时跑迁移）。
2. 海报流读路径（历史回看 / 项目候选 / **导出 export_query**）在**读时**经 `MediaUrlSigner` 现签
   （TOS→预签名；本地→`/img/<key>`），对齐 listing。
3. 兼容历史：库里已存的旧 url（本地 `/img` 形态）回退处理，避免误判。

## 影响范围
- 受影响：海报流历史回看、项目候选图回看、导出。
- 不受影响：listing（已存 key 现签）。

## 期望 vs 实际
- 期望：海报流历史/导出长期可回看（不随签名过期失效）。
- 实际：激活 TOS 后落库签名 url，过 TTL 即死链。

## 处理记录
- 2026-06-05 [运维] ISSUE-0033 激活生产 TOS 后暴露本问题；按代码定位根因（海报流落库签名 url，
  非 key），对照 listing 正确范式，开本条派开发。owner=开发，severity P2（若海报流产线活跃使用请升 P1）。
  运维侧：方案定后若涉及迁移，部署时由运维跑 `alembic upgrade head`（同 ISSUE-0030/0033 流程）。
