# 设计稿：gpt-image-2 主备双中转 Failover Adapter

- 日期：2026-05-28
- 范围：image-code（design_hub），仅 `gpt-image-2` 这一条线
- 决策前置：用户已选「gpt-image-2 + 合规」——保留 gpt-image-2、必须走能开增值税票的合规中转、单张成本不再卡 1–3 毛

## 1. 背景与目标

`gpt-image-2` 在国内只能通过第三方中转站调用。第三方中转会抽风，需要主备冗余保证稳定性。
目标：在不改动 `pipeline / router / registry` 的前提下，为 `ModelName.GPT_IMAGE_2` 引入「同模型、跨中转站」的故障切换。

非目标（明确不做）：
- 不为国内官方模型（通义万相 / 即梦 Seedream / 灵动 / 万象）做中转 failover——它们走官方直连，无中转站。
- 不引入熔断 / 健康度统计 / 自动权重（YAGNI，后续可加）。
- 不改造成本预算的整体框架，只复用现有 `CostEstimator / CostGuard / Ledger`。

## 2. 关键架构发现：两层 failover 必须分层、不可混淆

现有 `pipeline._generate_with_fallback` 已实现一层 failover：`GPT_IMAGE_2` 失败 → 切到 `SEEDREAM_5`（`routing/table.py::FALLBACKS`），仅捕获 `ProviderError`（IO/网络域）。

本设计新增的是**另一条轴**——同一个 gpt-image-2、换中转站。两者**嵌套**：

```
pipeline._generate_with_fallback        外层(已存在)：换模型 GPT_IMAGE_2 → SEEDREAM_5
  └─ registry.get(GPT_IMAGE_2)
       └─ FailoverModelProvider         内层(新增)：同模型换中转站 诗云 → API易
            ├─ OpenAICompatProvider(诗云, 主)
            └─ OpenAICompatProvider(API易, 备)
```

语义：先在 gpt-image-2 的多个合规中转间穷尽切换；全挂了才把 `ProviderError` 抛回外层，由 pipeline 决定是否降级到别的模型。

## 3. 组件设计

沿用现有端口 `ports/model_provider.py::AbstractModelProvider`（`name: ModelName`、`unit_cost: Decimal`、`async generate(...)`），新增**两个 infra 适配器**，无新端口。

### 3.1 `OpenAICompatProvider`（单中转站适配器）

位置：`infrastructure/providers/openai_compat.py`

职责：把一个 OpenAI 兼容中转站封装为 `AbstractModelProvider`，调用其 `/v1/images/generations`。

```python
class OpenAICompatProvider(AbstractModelProvider):
    def __init__(
        self, *,
        name: ModelName,
        unit_cost: Decimal,          # 该中转站此质量档的 CNY/张，用于预算预估
        base_url: str,
        api_key: str,
        model_id: str,               # 中转站侧模型名，如 "gpt-image-2"
        quality: str,                # "low"|"medium"|"high"，构造期固定(见 §6 开放问题)
        timeout_s: float,
        client: httpx.AsyncClient,   # 注入，复用连接池 + 便于测试
    ) -> None: ...

    async def generate(self, *, prompt, negative_prompt, reference_images,
                       size, n, seed=None) -> list[GeneratedImage]: ...
```

错误映射（**决策①，已确认**）——这是 fail-fast 红线的落点：

| 来源 | 抛出 | 后果 |
|---|---|---|
| 连接错误 / 读超时 | `ProviderTimeout` | 可重试 → 触发 failover |
| HTTP 429 / 5xx | `ProviderTimeout` | 可重试 → 触发 failover |
| HTTP 400 / 422（提示词违规、参数非法） | `DomainError` | 立即上抛，**不切备**（同 payload 必然同样失败） |
| 2xx 但响应体不合法 | `ProviderError` | 视为该家故障 → 触发 failover |

`generate()` 返回的 `GeneratedImage.cost` 必须填**本中转站实际单价**（按 `unit_cost` 或响应中的用量换算），保证结算口径准确。

### 3.2 `FailoverModelProvider`（主备组合器）

位置：`infrastructure/providers/failover.py`

职责：按序 try 一组**同模型**中转，IO 域失败切下一家，域错误立即上抛。自身 IS-A `AbstractModelProvider`（LSP），对上层完全透明。

```python
class FailoverModelProvider(AbstractModelProvider):
    def __init__(self, *, name: ModelName,
                 relays: Sequence[AbstractModelProvider]) -> None:
        assert relays, "至少一个 relay"
        assert all(r.name == name for r in relays), "只有同模型中转才能互备"
        self.name = name
        self.unit_cost = max(r.unit_cost for r in relays)  # 决策②：按最贵预留
        self._relays = tuple(relays)

    async def generate(self, **kw) -> list[GeneratedImage]:
        last: ProviderError | None = None
        for relay in self._relays:
            try:
                return await relay.generate(**kw)   # 成功即返回(携带该家真实 cost)
            except ProviderError as e:              # 仅 IO/网络域才切备
                last = e
        assert last is not None
        raise last                                  # 全挂 → 交还外层(换模型)
```

注意：`DomainError`（含 400/422 映射出的）不被 `except ProviderError` 捕获，自然穿透——符合「不切备、立即失败」。

### 3.3 预算预留口径（决策②，已确认）

`CostEstimator` 用 provider 的 `unit_cost` 预扣额度。主备价不同，`FailoverModelProvider.unit_cost = max(relays)`：保守预留，避免切到更贵备用时额度扣不够、击穿 `CostGuard` 红线。实际结算用出图那家的真实 `cost`。

## 4. 装配（唯一改动点：composition.py）

`composition.py` 是组装根（唯一可同时认识 application 与 infrastructure 的地方）。新增真实 registry 构建函数，把 `GPT_IMAGE_2` 指向 failover 组合器；国内官方模型各自注册其官方直连 adapter（本设计不含其实现，留位）。

```python
def build_real_registry(settings: Settings, client: httpx.AsyncClient) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(FailoverModelProvider(
        name=ModelName.GPT_IMAGE_2,
        relays=[
            OpenAICompatProvider(name=ModelName.GPT_IMAGE_2, quality="medium",
                                 base_url=..., api_key=..., model_id="gpt-image-2", ...),  # 诗云(主)
            OpenAICompatProvider(name=ModelName.GPT_IMAGE_2, quality="medium",
                                 base_url=..., api_key=..., model_id="gpt-image-2", ...),  # API易(备)
        ],
    ))
    # 其余 ModelName 注册各自官方直连 adapter（通义万相/即梦等）— 本设计不展开
    return registry
```

主/备顺序由配置决定（OCP，改配置不改代码）：拿到两家 key 小额实测后，把「更稳+更便宜」设为 `relays[0]`。

## 5. SOLID 自检

- **SRP**：`OpenAICompatProvider` 只管「一个中转站的协议适配」；`FailoverModelProvider` 只管「按序切换」。
- **OCP**：增删中转站只改 `composition.py` 的 `relays` 列表，pipeline/router/registry 零改动。
- **LSP**：组合器与单中转均是 `AbstractModelProvider`，registry/pipeline 无感替换。
- **ISP**：复用既有单方法端口 `generate`，不膨胀接口。
- **DIP**：上层只依赖端口；具体中转绑定集中在组装根。

## 6. 开放问题（实现前需再拍）

**gpt-image-2 质量档与端口的矛盾**：现端口 `generate()` 无 `quality` 参数，但 gpt-image-2 成本随质量浮动近 30 倍（low ≈¥0.04 / medium ≈¥0.30 / high ≈¥1.5）。
- 本设计的最小处理：`OpenAICompatProvider` 在**构造期**固定 `quality`（默认 medium），成本可控、不动端口。
- 但 `REFINE` 精修档与 `FORCED_GPT_FAMILIES` 强制档都路由到同一个 `GPT_IMAGE_2` provider，无法按档位区分质量。
- 若需「精修走 high、强制走 medium」，需后续在端口引入 `quality`（影响所有 provider，属 LSP 级改动）——**列为独立后续项，不在本次范围**。

## 7. 成本控制约定（产品侧，非 adapter 职责）

- gpt-image-2 默认 medium（≈3毛），仅精修才 high（≈¥1.5），避免 high 成为默认。
- 1–3 毛/张的批量诉求由国内官方模型（通义万相 ¥0.10 起 / 即梦 Seedream Lite ≈¥0.25）承担，已由 `routing/table.py` 的草稿/标准档实现。
- 主备两家（诗云 / API易）均能开增值税票，failover 切换不破坏合规。

## 8. 测试要点（交由 image-qa，本稿仅列关注点）

- 主挂备活：`relays[0]` 抛 `ProviderTimeout`，`relays[1]` 成功 → 返回备用结果与备用 cost。
- 全挂上抛：两家都抛 `ProviderError` → 抛回外层（pipeline 再降级到 SEEDREAM_5）。
- 域错误不切备：`relays[0]` 抛 `DomainError`（400/422）→ 立即上抛，`relays[1]` 不应被调用。
- 预算口径：`unit_cost == max(relays)`；切到贵备用时额度不被击穿。
```
