# 装配草案：composition.py 接入 apinebula（gpt-image-2 单跑）

- 日期：2026-05-29
- 面向：image-code 开发窗口（本稿是草案/参考，开发负责落地到 image-code/）
- 依据：ISSUE-0003（apinebula 单跑、备用挂起）、failover spec、ISSUE-0002（adapter 修复）
- 范围：只动 `composition.py` 装配 + `config/settings.py` 配置字段；不改 pipeline/router/registry

## 0. 前置依赖（必须先做，否则本装配跑不通）

本草案假设 **ISSUE-0002 的 adapter 修复已完成**：
- `OpenAICompatImageProvider` 已支持 b64_json 解码（apinebula 实测返回 b64，非 url）
- 已支持图生图 `/images/edits`（reference_images 非空走 edits multipart）
- 错误映射按 status_code 分流（400/422/401/403→上抛，429/5xx→ProviderTimeout 切备）
- 默认 timeout≥180s（实测延迟 ~90s）

若 ISSUE-0002 未完成，本装配能 import、能注册，但实际出图会失败（取不到 url / 不支持 edits）。

## 1. config/settings.py 新增字段

```python
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.development", extra="ignore")

    db_url: str = "sqlite+aiosqlite:///./design_hub.db"
    redis_url: str = "redis://127.0.0.1:6379/0"
    dashscope_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")

    # --- gpt-image-2 中转：apinebula（ISSUE-0003 单跑）---
    apinebula_base_url: str = "https://apinebula.com/v1"
    apinebula_api_key: SecretStr = SecretStr("")
    # 实测：测试 key 落在 vip_image2 组，可用模型名为 gpt-image-2-vip；
    # 裸 "gpt-image-2" 在该组报 503。生产 key 分组不同则按实际改此值。
    apinebula_model: str = "gpt-image-2-vip"
    apinebula_unit_cost: str = "0.10"   # CNY/张，实测控制台扣费；用 str 避免 float 入账误差
    relay_timeout_s: float = 180.0

    @classmethod
    def from_kms(cls) -> "Settings":
        raise NotImplementedError("KMS loader wired in deployment milestone")
```

`.env`（真密钥，已 gitignore，不要写进 .env.development）：
```
APINEBULA_API_KEY=sk-xxxxxxxx
```

## 2. composition.py：新增 build_real_registry()

```python
from decimal import Decimal

import httpx

from design_hub.application.registry import ProviderRegistry
from design_hub.config.settings import Settings
from design_hub.domain.enums import ModelName
from design_hub.infrastructure.providers.failover import FailoverModelProvider
from design_hub.infrastructure.providers.openai_compat import OpenAICompatImageProvider


def build_real_registry(settings: Settings, client: httpx.AsyncClient) -> ProviderRegistry:
    """真实装配：gpt-image-2 走 apinebula（用 Failover 包单 relay，便于未来补备用）。

    其余 ModelName 暂仍需注册（见 §4 诚实说明），否则 router 命中时 registry.get 抛 KeyError。
    """
    registry = ProviderRegistry()

    apinebula = OpenAICompatImageProvider(
        name=ModelName.GPT_IMAGE_2,
        unit_cost=Decimal(settings.apinebula_unit_cost),
        base_url=settings.apinebula_base_url,
        api_key=settings.apinebula_api_key.get_secret_value(),
        model=settings.apinebula_model,
        client=client,                       # 共享连接池，勿每次新建
        timeout=settings.relay_timeout_s,
    )

    # 关键：即使只有一家也用 Failover 包一层。
    # 未来补备用 = 往 providers 列表 append 第二家，零改其它代码（OCP）。
    registry.register(
        FailoverModelProvider(providers=[apinebula])
    )

    # TODO(另开 issue)：注册国内模型真实 adapter（SEEDREAM_5/QWEN_IMAGE_PRO/
    # WANXIANG_27/LINGDONG_2）。在此之前见 §4。
    return registry
```

## 3. build_engine 改造 + httpx.AsyncClient 生命周期

`httpx.AsyncClient` 必须 **app 生命周期单例**（连接池复用），不能在 build_engine 里临时建、也不能每次调用新建。

```python
def build_engine(
    *,
    settings: Settings,
    client: httpx.AsyncClient,
    registry: ProviderRegistry | None = None,
    ledger: LedgerRepository | None = None,
) -> Engine:
    registry = registry if registry is not None else build_real_registry(settings, client)
    ledger = ledger if ledger is not None else InMemoryLedgerRepository()
    router = ModelRouter()
    estimator = CostEstimator()
    guard = CostGuard(ledger=ledger, policy=BudgetPolicy())
    pipeline = GenerationPipeline(
        router=router, orchestrator=build_orchestrator(),
        registry=registry, estimator=estimator, guard=guard,
    )
    preview = CostPreviewService(
        router=router, registry=registry, estimator=estimator, ledger=ledger,
    )
    return Engine(pipeline=pipeline, preview=preview)
```

ASGI 侧（`interface/api/app.py` 的 lifespan，开发按现有结构落）：
```python
@asynccontextmanager
async def lifespan(app):
    settings = Settings()
    async with httpx.AsyncClient() as client:   # 单例，随 app 关闭
        app.state.engine = build_engine(settings=settings, client=client)
        yield
```

> 注：`build_mock_registry` / 现有 `build_engine` 全 mock 入口保留给 CI/本地（零基础设施、零成本），真实装配是新增路径，不破坏 LSP。

## 4. 诚实说明：外层兜底当前是“假兜底”

failover spec 讲过两层：内层换中转（本稿）、外层换模型（pipeline 已有 `GPT_IMAGE_2 → SEEDREAM_5`）。

**但 SEEDREAM_5 等国内模型目前只有 MockModelProvider，没有真实 adapter。** 所以：
- apinebula 单跑期间，若 apinebula 全挂，pipeline 外层会切到 SEEDREAM_5 —— 但那是个 **mock**，生产环境等于没有真兜底。
- 两个选择（需 PM/开发定，建议另开 issue）：
  - **(a)** 尽快补国内模型真实 adapter（通义万相/海螺），让外层兜底真实生效；
  - **(b)** 在补齐前，明确接受 apinebula 单点故障（与 ISSUE-0003 “单跑过渡态”一致）。
- 在 §2 把其余 ModelName 注册成 mock 只是为了让 router 不 KeyError；**这不是真兜底，别误判**。

## 5. SOLID 自检
- **OCP**：补备用中转 = `providers=[apinebula, 第二家]`，补国内模型 = 多 register 几个，均不改 pipeline/router/registry。
- **DIP**：composition 是唯一认识具体 adapter 的地方；上层只见端口。
- **LSP**：mock 装配与真实装配可互换，CI 仍走 mock。
- **SRP**：build_real_registry 只管“绑定具体 relay”，连接池生命周期交给 ASGI lifespan。

## 6. 落地清单（给开发）
1. 先做 ISSUE-0002（adapter 三项修复），否则本装配出图会失败。
2. settings.py 加 §1 字段；.env 放真 key（勿入库）。
3. composition.py 加 build_real_registry + 改 build_engine（§2/§3）。
4. app.py lifespan 建 AsyncClient 单例并注入。
5. 决定 §4 的 (a)/(b)，建议另开 issue 跟踪国内模型真实 adapter。
