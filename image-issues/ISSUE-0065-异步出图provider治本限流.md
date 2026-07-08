---
id: ISSUE-0065
title: 转异步出图（apinebula image-tasks 队列）治本同步端点限流——prod 真实用户成功率 ~33%
status: 已关闭        # 异步治本坐实:prod成功率33%→87%(13/15)+FOOD3/3零回归+两provider切换实操+保真绿;QA证据落image-qa
severity: P1          # 真实用户当前受影响：prod 出图成功率 ~33%（同步端点过载即拒、串行 mitigation 不够）；非资损但核心功能可用性硬伤
reporter: coordinator  # 品类批终态全 1/3 暴露、coordinator 异步接口实证（#1101）
owner: —              # 已关闭：异步 provider 治本、成功率 33%→87%、余2张fail-closed正确(0064 backlog再抬)
created: 2026-07-08
updated: 2026-07-08
related:
  - issue: ISSUE-0063（新 key 分组限流紧=本条根因，串行/image2-vip 是 stopgap，本条=治本）、ISSUE-0056（key 恢复=同步链）、ISSUE-0057（配置页注册表=异步 provider 挂载点，两 provider 并存/切换）、ISSUE-0055（墙钟/人话失败兜底沿用）
  - code: image-code infrastructure/providers/openai_compat（同步 provider 保留=备用渠道）、application/registry（ProviderRegistry 注册异步 provider_type）、MediaUrlSigner（现签 reference URL）、ImageStore（download_url→bytes→落存，后段复用）
  - 群聊: image-gen#1 #1101（品类批 1/3 暴露 + 异步接口实证）
---

## 现状 & 治本（coordinator #1101）
- **现状**：新 key 分组（gpt-image-2-1k）同步端点 `/images/edits` **限流紧**——并发失败、串行也挨限流（品类批终态**全 1/3**）；**prod 真实用户出图成功率 ~33%**=核心功能可用性硬伤。
- **实证治本**：同一把 KeyA，**异步任务接口** `POST /v1/image-tasks/edits`（JSON、images 传 **URL**）→ queued → **30 秒 completed 拿 download_url、零失败**。结论=同步端点过载即拒、**异步排队消化**；还带**失败自动退款**。→ **转异步是治本**（非 image2-vip 升级/串行 stopgap）。

## ⚠️ 前置实证（dev 先做、别盲建，≈¥0.8，**四问**）
异步 edits 是否**尊重/可行**（文档未列全，不支持则方案要重估）——**必须用一张真实 product upload 的现签 URL 验**（非随手公网图，否则「假通过」）：
1. **`size`（如 `1536x1024`）**——⚠️ 若不支持=**非 1:1 比例全废**（**size 结果 dev 第一时间 @PM，PM 预载产品取舍：异步只保 1:1 / 非 1:1 留同步 provider**）。
2. **⚠️ 参考图 URL 可达性（dev #1104，同等致命）**——异步端点是 apinebula 服务端**回拉 images URL**，该 URL 须**公网可达+无需我方鉴权**；但我们产品图现走 `GET /uploads/{id}` **带 Bearer 鉴权代理**、**apinebula worker 拉不到**。⚠️ **我们出图全链走 /images/edits 带产品图**（保真靠 edits 端点）→ **URL 可达性影响所有出图、非仅复刻/编辑**。三结局：① prod 走 TOS 预签名（公网可达+签名有效期）→ `MediaUrlSigner.upload_url` 直用、方案成立；② nginx /img 对象公开可读→需实测；③ 鉴权代理后不公开→需给参考图开**临时公网只读通道**（presigned/临时 token URL）或改 submit 传 **base64**（**显著改端口设计**、scope 上升）。
3. **`input_fidelity`**（产品/文字保真核心价值，734f24b 同款）。
4. **`n`**（我们全链恒 1，确认异步同语义）。
> 四问任一不过（尤其 size / URL 可达性）→ 停下重估、报 PM/coordinator，别硬建。端口演进提案按实证结论分支写。

## 实现（实证过后，dev）
- 新 `provider_type = apinebula_async_image` → **0057 注册表映射**（配置页切换即用、**与同步 provider 两存**、同步保留=备用渠道）。
- **submit**（JSON、images=**现签 URL**——⚠️ 端口今传 bytes，需把 reference 的**签名 URL** 带进 provider 调用，`MediaUrlSigner` 现成、**端口演进 dev 设计**）→ **轮询**（queued/in_progress→completed/failed，沿 `retry_max_elapsed` 墙钟语义）→ **download_url 拉 bytes → ImageStore 落存**（后段全复用、0055 失败人话/墙钟沿用）。
- 失败自动退款语义对齐现有 fail-closed 计费。

## 验收标准（QA）
1. **前置实证（四问）**：size / **参考图 URL 可达性** / input_fidelity / n 结论明确入档（用真实 product upload 现签 URL 验；尤其 size 尊重非 1:1 + apinebula worker 能拉到我方鉴权代理后的产品图）。
2. **异步出图成功率**：真实/mock 队列场景成功率显著回升（对比同步 ~33%）、30s 级完成、无僵尸。
3. **两 provider 并存**：0057 配置页切默认在同步/异步间切换即生效（异步治本、同步备用）。
4. **保真不回退**：input_fidelity 生效（产品/文字保真）、size/比例正确。
5. **零回归**：ImageStore 落存/历史/计费/0055 失败兜底不变；失败自动退款正确。

## 范围外（YAGNI）
webhook 回调（先轮询）/ 异步批量并发编排 / 多中转站负载均衡。

## 处理记录
- 2026-07-08 [coordinator+PM] 品类批终态全 1/3 暴露 prod 真实用户 ~33% 成功率（同步端点限流、串行不够）→ coordinator 实证异步接口 image-tasks（30s completed 零失败+自动退款）=治本 → PM 开条挂账 **P1**（真实用户核心功能可用性）。
  **dev 接**：① 先 ≈¥0.8 前置实证（size/input_fidelity/n 是否支持、尤其 **size 非 1:1 是死穴**）；② 过则建 `apinebula_async_image` provider（0057 注册表挂载、submit 现签 URL/端口演进、轮询、download_url→ImageStore、同步保留备用）。**品类真图批（ISSUE-0060 ①⑤）等异步 provider 上线后重跑**（现 4 张 1/3 残图不作数、评图要全套）。
  **部署拆两波**：Hero 波（2d8f26f+734f24b 就绪）coordinator 先上；异步 provider 波 dev 完工后走。**知识库「明确不支持」暂不动**（异步=内部实现、非用户可见功能变更，coordinator #1101）。owner=开发（前置实证→实现）。
- 2026-07-08 [PM] **前置实证升为四问 + size 握手锁定（dev #1104/#1106）**：dev 补第 4 实证项 **参考图 URL 可达性**（同等致命）——apinebula 异步 worker 回拉 images URL 须公网可达无鉴权，但我方产品图现走 `/uploads/{id}` 带 Bearer 代理；⚠️ **我们出图全链走 /images/edits 带产品图→ URL 可达性影响所有出图**；结局③（改 base64）=显著改端口、scope 上升。四问=size / URL 可达性 / input_fidelity / n，**用真实 product upload 现签 URL 验**（防假通过）。
  **握手锁定**：**size 实证结果 dev 第一时间 @PM** → 若异步不尊重 size，PM 拍产品取舍（异步只保 1:1 / 非 1:1 留同步 provider），dev 按 PM 口径落 provider 选择逻辑；URL 可达性结局③若中→端口 scope 变更也回报 PM/coordinator。**分工边界**：端口演进提案=dev 技术设计、coordinator/dev 技术过（非 PM 产品口径）；PM 只盯产品验收（size/成功率/切换/保真/零回归+退款）。
  **卡在 coordinator 输入**：①异步接口契约 shape + ②KeyA 带外通路（密钥绝不进群聊）——dev 到位即当天出四问结论。PM 候场等 size/URL 结局回报拍取舍。
- 2026-07-08 [coordinator] **✅ 四问实证全过、build gate 开（#1107，prod 容器内真实产品图 ¥0.8）**：
  ① **size 尊重**（请求 1536x1024→返回实测 1536x1024，PNG IHDR 解析）=**非 1:1 死穴解除、PM 无需产品取舍**；② **n=2→只返 1 张**（同步一致、全链 n=1 免疫）；③ **input_fidelity=high 接受**；④ **真实产品图 TOS 预签 URL worker 拉取成功**（upload 存储=TOS 非本地代理、#1104 分支①成立、`MediaUrlSigner.upload_url` 直用）。任务 70s 完成、全程零「临时繁忙」。
  **接口契约 shape 定稿**：`POST /v1/image-tasks/edits`（JSON `{model,prompt,quality:high,size:WxH,input_fidelity:high,images:[{image_url}]}`、Bearer、服务端自动 async=true）→ 提交返 `{task_id,status:queued}` → 轮询 `GET /v1/image-tasks/{task_id}?detail=true`（枚举 queued/in_progress/completed/failed、10s 节奏、建议 5-10s 沿 retry_max_elapsed 墙钟、超时穷尽 fail-closed）→ 完成体 `detail.data[].download_url`（cdnimage.apinebula.com 公网直拉 bytes→ImageStore）、失败体 `error.message`、**失败/取消按预扣退款**。
  **端口演进提案 coordinator 预 GO**（reference bytes→现签 URL、provider_type 走 0057 注册表两存）→ dev 出一页 coordinator 快速过即动码。**PM 侧无产品取舍待拍**（size 已解）——候场等 dev 建完 → QA 验收 5 条 → 异步波部署 → 品类真图批重跑。owner=开发（实现）。
- 2026-07-08 [开发] **✅ AsyncImageTasksProvider 建完（335c0db，150 绿 + 1 已知完全复刻 HOLD red，ruff 净，openapi 无变）**。端口演进提案先入档 `docs/0065-async-image-provider-port-design.md`（866b4ed），coordinator #1112 过 3 点（launcher 分支/MVP 不重投/并发解耦）后落码：
  ① 端口 `reference_images: list[bytes]→list[ReferenceImage]`（domain VO data|url）+ `AbstractModelProvider.reference_mode` 声明模态；解析留 launcher（注入 MediaUrlSigner）按模态只物化——**url 模态签公网 URL 不白载字节**、bytes 模态载字节；同步 provider 读 .data、异步读 .url，各 fail-fast 装配错；三路（generate/clone/edit）+ service/commands 透传，edit 源图走 generated_url。
  ② `AsyncImageTasksProvider`（`infrastructure/providers/apinebula_async.py`）：submit→轮询（沿 `gpt_image_async_poll_max_elapsed` 墙钟穷尽 fail-closed）→download_url 拉字节（**不带 Bearer 不泄 key 给 CDN**）→ImageStore；over-deliver 截断同 0045；failed=fail-closed 不重投（上游自动退款）。HTTP 状态分流/退避/compose 抽 `_openai_common` 单一事实源。
  ③ 0057 接入：`composition` 按 `default_config.provider_type=apinebula_async_image` 分派、连接解析复用、与同步并存=备用渠道。settings 加 `gpt_image_async_poll_interval/max_elapsed`。
  ④ 测：6 条 async 契约（submit shape/轮询状态机/download 落存不泄 key/failed fail-closed/墙钟穷尽/模态装配错）。
  **⚠️ 部署激活步骤（coordinator/QA 注意）**：本条**无 DB 迁移**，代码上线后 prod **仍走同步**（seed 默认 provider_type=`openai_compat_image`）；**激活异步=管理员在 0057 配置页新增/设默认一行 provider_type=`apinebula_async_image`（base_url=apinebula /v1、model=gpt-image-2、api_key_env 指 KeyA）+ 重启**；**回退=切默认回同步行+重启**（备用渠道）。状态→待验证，owner=QA。
- 2026-07-08 [coordinator] **✅ 异步波部署+激活（#1117）**：335c0db 上线 → coordinator 经 0057 配置页 API 加 `gpt-image-2-async` 行+设默认+重启（**恰一默认核过=验收⑤两 provider 切换流程本身已实操**）。**QA 实弹正跑品类批全套 5 品类×3（含 FOOD 零回归）走异步管线**——一批同时回答本条**验收②成功率/④保真** + **ISSUE-0060 品类卡三问（真图①⑤）**。结果出来 coordinator 评图+通报 → PM 关账 0065 + 收尾 0060。owner=QA（实弹验收中）。
- 2026-07-08 [coordinator+PM] **✅ 异步治本坐实、PM 关账（#1119 品类批评图）**：**验收②成功率 33%→87%（13/15）**——异步治本坐实（余 2 张「临时繁忙」由 fail-closed 正确落败=0055 兜底在、可再抬走 ISSUE-0064 backlog）；**④保真绿**（品牌大字保真、密集小字限界另记 0060）；**⑤两 provider 切换**=coordinator 0057 配置页实操过；**FOOD 3/3 零回归**。QA 证据落 image-qa 报告。**status→已关闭**。治本方案（同步端点过载即拒→异步队列消化+失败退款）线上验证完整。
