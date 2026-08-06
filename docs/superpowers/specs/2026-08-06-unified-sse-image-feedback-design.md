# 统一 SSE 图片实时回显设计

## 背景

当前图片任务的持久事件在 `image_generated` 中保存 `image_key`，但前端实时事件解析器只读取 `url`。Chat 与普通工作台收到图片完成事件后会把槽位写成空 URL，继续显示加载动画；只有任务终态后重新读取 job 详情，才获得签名 URL 并回显图片。

此外，普通 Listing SSE 响应已设置 `X-Accel-Buffering: no`，Chat 的 POST SSE 没有设置同等响应头。Chat 经 Nginx 反向代理时存在中间事件被缓冲到响应结束才集中释放的风险。这与项目已关闭的 ISSUE-0001 属于同类代理边界问题。

本设计统一治理以下入口：

- 普通单图生成；
- 套图生成；
- 爆款复刻；
- 二次编辑；
- 换背景；
- Chat 内发起的所有图片任务。

## 目标

1. `image_generated` 到达浏览器后立即显示图片，不等待 `task_completed`、Chat 收尾文字或 job 详情查询。
2. 所有 SSE 图片入口使用同一份展示契约和同一份前端槽位归并逻辑。
3. 保留 Redis Stream 的可回放能力，并使重复事件在前端幂等。
4. 兜底有明确请求上限，不以高频轮询掩盖契约错误。
5. 不持久化会过期的签名 URL，不增加数据库表、Redis Stream、Worker 或常驻任务。

## 非目标

- 不重构任务调度、Outbox 或 Worker 执行模型。
- 不引入 WebSocket。
- 不建设通用重试框架、断路器或多级事件缓存。
- 不为旧版前后端提供兼容分支；前后端契约作为同一发布单元同步升级。
- 不改变对象存储权限或签名 URL 的有效期。

## 方案比较

### 方案 A：SSE 出口统一补齐展示字段（采用）

数据库、Outbox 和 Redis Stream 继续保存稳定的 `image_key`。SSE 响应边界通过现有 `MediaUrlSigner` 生成当前可访问的 URL，再将完整图片事件发送给客户端。

优点：

- 保持持久数据稳定，不写入过期 URL；
- 图片事件到达即可展示；
- Listing 与 Chat 可复用同一转换规则；
- 无额外对象存储读取和轮询。

### 方案 B：前端由 `image_key` 拼接 URL（不采用）

生产图片位于私有 TOS，URL 需要服务端签名。把签名能力或密钥下放前端不满足安全边界。

### 方案 C：图片完成后轮询 job 详情（不采用）

轮询能够最终获得签名 URL，但会增加数据库读取、扩大高并发时的服务器负载，并继续保留实时事件契约错误。详情读取只作为终态校准和有限异常恢复，不承担实时回显。

## 架构设计

### 1. 持久任务事件

Worker 完成图片存储后，事务内继续写入包含以下字段的 `image_generated` 事件：

```json
{
  "item_id": "generation-item-id",
  "image_key": "object-key.png",
  "image_type": "场景",
  "seed": 123,
  "cost": "0.05"
}
```

这里不加入 `url`。Outbox 和 Redis Stream 继续存储同一份稳定载荷，避免回放到过期签名 URL。

`image_failed` 必须保留 `item_id`、`image_type` 和面向用户的 `error`，使成功与失败事件都能幂等归并到槽位。

### 2. 统一 SSE 事件展示器

在 API/interface 层新增一个职责单一的任务事件展示器。输入为事件类型、原始 data 和 `MediaUrlSigner`，输出为 SSE data。

规则：

- `image_generated`：要求 `item_id` 和 `image_key` 为非空字符串；调用 `generated_url(image_key)`，输出 `item_id`、`image_key`、`url` 及其余原字段。
- `image_failed`：要求 `item_id` 非空，原样输出稳定业务字段。
- 其他任务事件：原样输出。
- 不修改输入对象，返回新的 data 对象。
- 载荷违反契约时抛出数据不变量错误，不发送空字符串 URL。

Listing 路由序列化 `ReplayableEvent` 时调用该展示器。Chat 路由序列化嵌套的 `job_event` 时，对其中的任务事件调用同一个展示器。Chat Orchestrator、任务领域对象和 Redis 端口不依赖媒体签名器。

生产 TOS 的预签名和本地存储 URL 生成均复用现有 `MediaUrlSigner`。当前签名过程不读取图片，也不向对象存储发起 GET。

### 3. 统一 SSE 响应头

Listing 和 Chat 的所有 SSE StreamingResponse 统一设置：

```http
Cache-Control: no-cache
X-Accel-Buffering: no
```

可提取一个小型共享常量或响应构造函数，但不建设通用 SSE 框架。现有 Chat 20 秒心跳和 Listing 15 秒阻塞读取保持不变。

### 4. 前端事件契约

前端 `ListingEvent` 的图片成功分支调整为：

```ts
{
  kind: 'image'
  itemId: string
  imageKey: string
  url: string
  imageType?: string
  seed?: number
}
```

图片失败分支包含 `itemId`。`parseListingEvent` 对成功事件要求 `item_id`、`image_key`、`url` 均为非空字符串；缺失时抛出契约错误。Chat 的 `job_event` 继续复用同一个任务事件解析器。

真实后端契约是测试的唯一载荷口径，不再使用只有 `url`、没有 `image_key/item_id` 的伪造事件。

### 5. 共享槽位 reducer

新增纯函数统一处理所有工作台和 Chat 的实时槽位变化。现有页面必须适配该 reducer，删除各自重复的“找到首个空槽再写 URL”逻辑。

归并规则：

1. 若已有相同 `itemId` 的槽位，更新该槽，不新增完成数。
2. 否则优先选择相同 `imageType` 的首个未结算槽。
3. 无图型计划时选择首个未结算槽。
4. 成功事件写入 `itemId`、`imageKey`、`url` 和 `imageType`。
5. 失败事件写入 `itemId`、`error` 和 `imageType`。
6. 找不到可归并槽位属于状态不变量错误，不静默丢弃。

完成数从槽位派生，不再维护容易漂移的独立累加器：

```text
settled = 有 URL + 有 error + unavailable
```

Redis Stream 重放或网络边界的重复投递因此不会产生重复图片或错误计数。

### 6. Chat 状态拆分

Chat 将图片任务状态与文字流状态分开：

- `jobStatus`：`idle | generating | completed | failed | interrupted`，控制图片区域动画和任务提示。
- `streaming`：控制 Chat 文字流、“思考中”和输入区锁定。

事件处理：

- `job_started`：初始化槽位并设为 `generating`。
- `image_generated`：立即写入完整图片槽。
- `image_failed`：立即结算失败槽。
- `task_completed`：立即设为 `completed`，图片区域停止生成动画。
- `task_failed`：立即设为 `failed`，未结算槽不再继续转圈。
- `assistant_end`：仅结束文字流，不决定图片是否可见。

Chat 在任务完成后调用文本模型生成自然收尾语时，图片已经可预览、下载和继续编辑。

## 异常恢复

### 正常实时路径

SSE 图片事件是实时展示的唯一主路径。收到成功或失败图片事件时不发详情请求。

### 正常终态校准

收到 `task_completed` 或 `task_failed` 后，实时流程主动触发一次 job 详情读取，以数据库终态校准图片、失败槽和当前签名 URL。该主动校准每个 job 最多一次；用户之后打开历史页面属于独立读取，不计入实时流程预算。

### Listing SSE 断线

普通工作台继续依赖浏览器 EventSource 原生重连。服务端事件包含 Redis ID，浏览器通过 `Last-Event-ID` 续传，Redis Stream 负责回放。前端不增加自定义重试定时器或轮询。

### Chat POST SSE 断线

Chat 确认流不能安全重放一次性确认动作，因此不重发 POST：

- 若尚未收到 `job_started`，结束请求并显示对话请求失败。
- 若已经收到 `job_started`，设置 `jobStatus=interrupted`，停止无限转圈，明确提示“连接已中断，任务仍在后台执行”，并读取一次 job 详情。
- 若一次详情读取显示终态，立即渲染终态。
- 若任务仍在执行，不启动轮询；用户可从任务历史重新进入查看。

这是有限恢复，不承诺在 Chat 传输连接已断开的情况下继续实时追踪后台任务。

### 契约错误

- 后端发现图片事件缺少非空 `item_id/image_key` 时 fail-fast，并记录结构化错误。
- 前端发现 `image_generated` 缺少非空 `itemId/imageKey/url` 时关闭当前流，显示“图片事件格式异常”，不得维持加载动画。
- URL 签名失败时不发送空 URL；错误进入现有 API 错误和运行日志链路。

## 性能边界

- 正常路径不轮询。
- 每个 job 的实时终态校准最多主动发起一次详情 GET。
- 每张图片、每个实际 SSE 发送连接执行一次 URL 签名；断线回放会按新的发送连接重新签名，以避免返回过期 URL。
- 不读取图片字节，不复制图片，不新增对象存储 GET。
- 不改变 Redis Stream TTL、最大长度、Worker 并发或事件频率。
- 不缩短现有 SSE 心跳周期。
- 不给日志或指标加入签名 URL、prompt、用户文本等敏感或高体积字段。

## 观测设计

继续使用已有：

- `generation_item_completed`：图片保存和数据库完成；
- `generation_outbox_published`：Outbox 发布到 Redis Stream。

在图片事件真正写入 SSE 响应时增加 `generation_sse_image_emitted` 结构化日志，字段仅包括：

- `job_id`；
- `item_id`；
- `redis_id`；
- `endpoint_kind`：`listing | chat`；
- `event=image_generated`；
- `status=emitted`。

正常单客户端链路每张图片产生一条该日志；重连回放会产生新的发送日志，可通过相同 `redis_id` 识别。日志不记录签名 URL。

三段时间可以定位：

```text
图片保存完成 -> Outbox 发布 -> SSE 发出
```

浏览器渲染耗时由自动化测试验证，本期不引入前端遥测 SDK。

## 测试设计

### 后端单元测试

- `image_generated` 补齐签名 URL并保留 `image_key/item_id`。
- `image_failed` 保留 `item_id`。
- 非图片事件不变。
- 空或缺失 `item_id/image_key` fail-fast。
- 展示器不修改原始事件对象。

### 后端路由测试

- Listing SSE 图片事件包含非空 `item_id/image_key/url`。
- Chat 嵌套 `job_event` 使用相同载荷。
- Listing 与 Chat 均包含禁止缓存和禁止 Nginx 缓冲响应头。
- Chat 心跳与最终 `assistant_end` 顺序不回退。

### 前端单元测试

- 使用真实后端图片事件载荷解析 `itemId/imageKey/url`。
- 缺失必填字段抛出契约错误。
- 共享 reducer 覆盖成功、失败、多图、按图型归并、乱序和重复事件。
- 完成数由槽位派生且重复事件幂等。
- 所有工作台适配共享 reducer。
- Chat 收到图片事件后立即显示图片及编辑入口。
- Chat 收到 `task_completed` 后停止图片动画，但仍允许收尾文字继续流式输出。
- 流异常进入明确错误或 `interrupted` 状态，不保留无限 spinner。

### 集成与部署验收

- 从任务提交、Worker、Outbox、Redis Stream 到 SSE，断言 `image_generated` 在 `task_completed` 前到达，且 `url` 可读取、`image_key` 非空。
- 经 Nginx 分别验证 Chat 与 Listing 第一张图片实时出现，不能在终态一次性涌出。
- 覆盖普通出图、套图、复刻、编辑、换背景和 Chat。
- 验证重复回放不增加图片数或完成数。
- 验证终态校准每个实时 job 最多主动请求一次。

## 验收标准

1. `image_generated` 到达后，下一次前端渲染替换对应加载槽。
2. 图片展示不依赖 `assistant_end`，也不依赖终态详情 GET。
3. 所有 SSE 出图入口使用同一任务事件展示契约和共享槽位 reducer。
4. 经 Nginx 不发生中间事件缓冲到任务末尾。
5. 正常链路零轮询；实时流程每个 job 最多一次终态详情校准。
6. 重放或重复事件不增加图片数、不创建重复槽位。
7. 图片成功事件缺少 URL 或 key 时显示明确错误，不允许无限转圈。
8. 无数据库迁移、无新 Redis Stream、无新 Worker、无常驻恢复任务。

## 发布与回滚

前后端事件契约必须在同一发布单元上线，不提供旧载荷兼容分支。上线前完成后端、前端和经 Nginx 的集成验收。

回滚以完整应用版本为单位同时回滚前后端。数据库、Redis 和对象存储格式均未改变，因此无需数据回滚。
