# M1 架构脊柱（引擎核心）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 MockModelProvider 端到端跑通「需求 → 路由 → Prompt 编排 → 成本守门 → 多候选出图」引擎脊柱，CI 零真实 API 费用，完整体现 SOLID。

**Architecture:** 分层包 `design_hub`：domain（枚举/DTO 契约）← providers（抽象+Mock+注册表）/ routing（数据驱动路由）/ prompt（4 族骨架+5 词库+编排器）/ cost（估算+预算+守门）→ pipeline（依赖注入组装，编排但不实现细节）。所有跨层依赖指向抽象，新增模型/模板族/合成方式为新增文件而非改写。

**Tech Stack:** Python 3.12 · uv · pydantic-settings · structlog · pytest + pytest-asyncio（asyncio 自动模式）· ruff · mypy。FastAPI / SQLAlchemy / arq / Redis 属 M2，本里程碑不引入。

**代码根目录：** `image-code/`（项目现有空目录；非 `image-core`）。

**约束（CLAUDE.md）：** 仅用 `uv`（`uv run` / `uv add`，禁用 `uv pip`，禁手改依赖清单）；非 I/O 逻辑 fail-fast，不加重试/兜底/默认值掩盖错误（fallback 仅出现在 Provider 网络调用）；代码注释英文且最少；提交信息中文、`type: description`、含正文、无 Co-authored-by。

---

## 文件结构（职责锁定）

```
image-code/
  pyproject.toml                      # uv 管理；含 ruff/mypy/pytest 配置
  .python-version                     # 3.12
  src/design_hub/
    __init__.py
    config/settings.py                # Pydantic Settings（SecretStr + from_kms 入口占位）
    logging.py                        # structlog JSON 日志初始化
    errors.py                         # 领域异常基类（fail-fast）
    domain/
      enums.py                        # SubScene/Tier/TemplateFamily/Style/Category/MaterialType/ModelName
      dto.py                          # GeneratedImage/PromptPair/RoutingDecision/ProductVisualInfo/Brief/GenerationResult
    providers/
      base.py                         # AbstractModelProvider（ISP：唯一 generate）
      errors.py                       # ProviderError / ProviderTimeout
      mock.py                         # MockModelProvider（可控延迟/失败，LSP）
      registry.py                     # ProviderRegistry（DIP 组装根）
    routing/
      table.py                        # 路由数据表（OCP：族→模型、档位规则、fallback 链）
      router.py                       # ModelRouter（族+场景+档位→RoutingDecision）
    prompt/
      libraries/color.py             # 词库 A 风格→色卡
      libraries/negative.py          # 词库 B 中文负面句
      libraries/guard.py             # 词库 C 歧义防御
      libraries/quality.py           # 词库 D 质量增强词
      libraries/lens.py              # 词库 E 镜头（含 LensPurpose 枚举）
      families/base.py               # TemplateFamilySkeleton 基类（OCP/LSP）
      families/family3.py            # 极简电商主图
      families/family4.py            # 高端商业摄影
      families/family5.py            # 氛围沉浸场景
      families/family7.py            # 中式节庆促销
      families/registry.py           # FamilyRegistry
      vision.py                      # VisionAssist 接口 + MockVisionAssist（ISP/DIP）
      brand.py                       # BrandNameGenerator
      rules.py                       # 10 法则可执行片段（format_ratio / typography_block）
      orchestrator.py                # PromptOrchestrator（DIP：组合注入）
    cost/
      estimator.py                   # CostEstimator
      budget.py                      # BudgetSnapshot / BudgetPolicy / BudgetExceeded
      ledger.py                      # LedgerRepository 接口 + InMemoryLedgerRepository
      guard.py                       # CostGuard + @cost_guard 装饰器 + GuardContext
    pipeline/pipeline.py             # GenerationPipeline（依赖注入组装）
  tests/
    conftest.py
    domain/test_enums.py · test_dto.py
    providers/test_mock.py · test_registry.py
    routing/test_router.py
    prompt/test_libraries.py · test_families.py · test_orchestrator.py
    cost/test_estimator.py · test_budget.py · test_ledger.py · test_guard.py
    pipeline/test_pipeline.py
```

---

## Task 1: 项目脚手架

**Files:**
- Create: `image-code/pyproject.toml`（由 `uv init` 生成）、`image-code/.python-version`
- Create: `image-code/src/design_hub/__init__.py`
- Create: `image-code/tests/conftest.py`

- [ ] **Step 1: 初始化项目并固定 Python 版本**

```bash
cd image-code
uv init --package --name design-hub
uv python pin 3.12
```

Expected: 生成 `pyproject.toml`、`src/design_hub/__init__.py`、`.python-version`（内容 `3.12`）。

- [ ] **Step 2: 添加运行期与开发期依赖（仅用 uv，勿手改清单）**

```bash
uv add pydantic pydantic-settings structlog
uv add --dev pytest pytest-asyncio ruff mypy
```

Expected: `uv.lock` 生成，`uv run python -c "import pydantic, structlog"` 无报错。

- [ ] **Step 3: 追加工具配置到 pyproject.toml**

在 `image-code/pyproject.toml` 末尾追加（工具配置非依赖，可编辑）：

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.mypy]
python_version = "3.12"
strict = true
```

- [ ] **Step 4: 写最小冒烟测试**

`image-code/tests/conftest.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
```

`image-code/tests/test_smoke.py`:

```python
def test_package_importable():
    import design_hub  # noqa: F401
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd image-code && uv run pytest tests/test_smoke.py -v`
Expected: PASS（1 passed）。

- [ ] **Step 6: 提交**

```bash
git add image-code/pyproject.toml image-code/.python-version image-code/uv.lock image-code/src image-code/tests
git commit -m "chore: 初始化 design_hub 引擎脚手架(uv + pytest)

用 uv 建立 image-code/design_hub 包，固定 Python 3.12，接入
pytest-asyncio/ruff/mypy，提供导入冒烟测试作为脊柱起点。"
```

---

## Task 2: 配置与日志与异常基类

**Files:**
- Create: `image-code/src/design_hub/config/settings.py`、`image-code/src/design_hub/logging.py`、`image-code/src/design_hub/errors.py`
- Test: `image-code/tests/test_config.py`

- [ ] **Step 1: 写失败测试**

`image-code/tests/test_config.py`:

```python
from design_hub.config.settings import Settings
from design_hub.errors import DomainError


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_KEY", "k-123")
    s = Settings()
    assert s.dashscope_key.get_secret_value() == "k-123"


def test_domain_error_is_exception():
    assert issubclass(DomainError, Exception)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/test_config.py -v`
Expected: FAIL（ModuleNotFoundError: design_hub.config）。

- [ ] **Step 3: 实现配置**

`image-code/src/design_hub/config/settings.py`:

```python
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.development", extra="ignore")

    dashscope_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")

    @classmethod
    def from_kms(cls) -> "Settings":
        # Production secrets pulled from Aliyun KMS at startup; not on disk.
        raise NotImplementedError("KMS loader wired in deployment milestone")
```

`image-code/src/design_hub/errors.py`:

```python
class DomainError(Exception):
    """Base for non-IO domain errors. Propagated, never swallowed."""
```

`image-code/src/design_hub/logging.py`:

```python
import structlog


def configure_logging() -> None:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )
```

Create empty `image-code/src/design_hub/config/__init__.py`.

- [ ] **Step 4: 运行确认通过**

Run: `cd image-code && uv run pytest tests/test_config.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/config image-code/src/design_hub/errors.py image-code/src/design_hub/logging.py image-code/tests/test_config.py
git commit -m "feat: 配置/日志/领域异常基座

Pydantic Settings 用 SecretStr 管密钥并预留 from_kms 入口；
structlog JSON 日志；DomainError 作为 fail-fast 异常根。"
```

---

## Task 3: 领域枚举

**Files:**
- Create: `image-code/src/design_hub/domain/__init__.py`、`image-code/src/design_hub/domain/enums.py`
- Test: `image-code/tests/domain/test_enums.py`

- [ ] **Step 1: 写失败测试**

`image-code/tests/domain/test_enums.py`:

```python
from design_hub.domain.enums import (
    Category, MaterialType, ModelName, Style, SubScene, TemplateFamily, Tier,
)


def test_subscene_values():
    assert {s.value for s in SubScene} == {"S1", "S3", "S4"}


def test_all_nine_families_defined_even_if_v1_does_four():
    assert len(list(TemplateFamily)) == 9


def test_seven_styles_match_color_lib_keys():
    assert Style.GUOCHAO.value == "国潮中式"


def test_models_enumerated():
    assert ModelName.SEEDREAM_5.value == "seedream-5"
    assert {ModelName.GPT_IMAGE_2, ModelName.QWEN_IMAGE_PRO,
            ModelName.WANXIANG_27, ModelName.LINGDONG_2} <= set(ModelName)


def test_tier_and_material_and_category_present():
    assert Tier.STANDARD.value == "standard"
    assert MaterialType.MAIN.value == "主图"
    assert Category.MIRROR.value == "镜面玻璃"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/domain/test_enums.py -v`
Expected: FAIL（ModuleNotFoundError）。需先建 `image-code/tests/domain/__init__.py`（空）。

- [ ] **Step 3: 实现枚举**

`image-code/src/design_hub/domain/enums.py`:

```python
from enum import StrEnum


class SubScene(StrEnum):
    S1 = "S1"  # 商品主图换背景
    S3 = "S3"  # 商品场景图
    S4 = "S4"  # 多角度/姿势裂变


class Tier(StrEnum):
    DRAFT = "draft"
    STANDARD = "standard"
    REFINE = "refine"


class TemplateFamily(StrEnum):
    F1 = "family_1"  # 大透视广告海报
    F2 = "family_2"  # 结构光效/X射线
    F3 = "family_3"  # 极简电商主图
    F4 = "family_4"  # 高端商业摄影
    F5 = "family_5"  # 氛围沉浸场景
    F6 = "family_6"  # 双语规范+排版
    F7 = "family_7"  # 中式节庆促销
    F8 = "family_8"  # 字效/标题字
    F9 = "family_9"  # 创意超现实


class Style(StrEnum):
    LUXURY = "高端轻奢"
    NORDIC = "极简北欧"
    GUOCHAO = "国潮中式"
    TECH = "科技未来"
    FRESH = "清新自然"
    SPORT = "运动机能"
    FESTIVE = "喜庆节日"


class Category(StrEnum):
    DIGITAL_3C = "3C数码"
    APPAREL = "服饰配件"
    BEAUTY = "美妆护肤"
    FOOD = "食品"
    WITH_PERSON = "含人物"
    MIRROR = "镜面玻璃"


class MaterialType(StrEnum):
    MAIN = "主图"
    DETAIL = "详情"
    POSTER = "海报"
    LEAFLET = "折页"
    OFFLINE = "线下"


class ModelName(StrEnum):
    GPT_IMAGE_2 = "gpt-image-2"
    QWEN_IMAGE_PRO = "qwen-image-pro"
    SEEDREAM_5 = "seedream-5"
    WANXIANG_27 = "wanxiang-2.7-pro"
    LINGDONG_2 = "lingdong-2"
```

Create empty `image-code/src/design_hub/domain/__init__.py`.

- [ ] **Step 4: 运行确认通过**

Run: `cd image-code && uv run pytest tests/domain/test_enums.py -v`
Expected: PASS（5 passed）。

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/domain image-code/tests/domain
git commit -m "feat: 领域枚举(场景/档位/模板族/风格/品类/物料/模型)

9 个模板族全部入枚举(V1 仅实现 4 族)，新增族无需改枚举(OCP)。"
```

---

## Task 4: 领域 DTO

**Files:**
- Create: `image-code/src/design_hub/domain/dto.py`
- Test: `image-code/tests/domain/test_dto.py`

- [ ] **Step 1: 写失败测试**

`image-code/tests/domain/test_dto.py`:

```python
from decimal import Decimal

import pytest

from design_hub.domain.dto import (
    Brief, GeneratedImage, GenerationResult, PromptPair, RoutingDecision,
)
from design_hub.domain.enums import (
    Category, ModelName, Style, SubScene, TemplateFamily, Tier,
)


def test_generated_image_is_frozen():
    img = GeneratedImage(url="mock://1", seed=1, latency_ms=5, cost=Decimal("0.20"))
    with pytest.raises(Exception):
        img.url = "x"  # type: ignore[misc]


def test_brief_defaults_to_six_candidates():
    brief = Brief(
        customer="客户A", subscene=SubScene.S1, family=TemplateFamily.F3,
        tier=Tier.STANDARD, style=Style.NORDIC, category=Category.BEAUTY,
        size=(1500, 2000),
    )
    assert brief.n == 6
    assert brief.reference_images == ()


def test_routing_decision_carries_fallbacks():
    d = RoutingDecision(primary=ModelName.SEEDREAM_5,
                        fallbacks=(ModelName.QWEN_IMAGE_PRO,), candidate_count=6)
    assert d.primary is ModelName.SEEDREAM_5
    assert d.candidate_count == 6


def test_generation_result_shape():
    pair = PromptPair(positive="p", negative="n")
    d = RoutingDecision(ModelName.SEEDREAM_5, (), 6)
    r = GenerationResult(job_prompt=pair, decision=d, used_model=ModelName.SEEDREAM_5,
                         images=(), total_cost=Decimal("0"))
    assert r.used_model is ModelName.SEEDREAM_5
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/domain/test_dto.py -v`
Expected: FAIL（cannot import dto）。

- [ ] **Step 3: 实现 DTO**

`image-code/src/design_hub/domain/dto.py`:

```python
from dataclasses import dataclass
from decimal import Decimal

from .enums import Category, ModelName, Style, SubScene, TemplateFamily, Tier


@dataclass(frozen=True)
class GeneratedImage:
    url: str
    seed: int
    latency_ms: int
    cost: Decimal


@dataclass(frozen=True)
class PromptPair:
    positive: str
    negative: str


@dataclass(frozen=True)
class RoutingDecision:
    primary: ModelName
    fallbacks: tuple[ModelName, ...]
    candidate_count: int


@dataclass(frozen=True)
class ProductVisualInfo:
    product_type: str
    main_color_hex: str
    material: str
    shape_ratio: str
    logo_position: str


@dataclass(frozen=True)
class Brief:
    customer: str
    subscene: SubScene
    family: TemplateFamily
    tier: Tier
    style: Style
    category: Category
    size: tuple[int, int]
    n: int = 6
    copy_text: str | None = None
    taboo: str | None = None
    product_desc: str | None = None
    brand_name: str | None = None
    reference_images: tuple[bytes, ...] = ()


@dataclass(frozen=True)
class GenerationResult:
    job_prompt: PromptPair
    decision: RoutingDecision
    used_model: ModelName
    images: tuple[GeneratedImage, ...]
    total_cost: Decimal
```

- [ ] **Step 4: 运行确认通过**

Run: `cd image-code && uv run pytest tests/domain/test_dto.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/domain/dto.py image-code/tests/domain/test_dto.py
git commit -m "feat: 领域 DTO 契约(不可变 dataclass)

GeneratedImage/Brief/PromptPair/RoutingDecision/GenerationResult
作为各层稳定契约，frozen 防误改。"
```

---

## Task 5: Provider 抽象接口与异常

**Files:**
- Create: `image-code/src/design_hub/providers/__init__.py`、`base.py`、`errors.py`
- Test: `image-code/tests/providers/test_base.py`

- [ ] **Step 1: 写失败测试**

建空 `image-code/tests/providers/__init__.py`。`image-code/tests/providers/test_base.py`:

```python
import pytest

from design_hub.providers.base import AbstractModelProvider
from design_hub.providers.errors import ProviderError, ProviderTimeout


def test_abstract_cannot_instantiate():
    with pytest.raises(TypeError):
        AbstractModelProvider()  # type: ignore[abstract]


def test_timeout_is_provider_error():
    assert issubclass(ProviderTimeout, ProviderError)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/providers/test_base.py -v`
Expected: FAIL（import error）。

- [ ] **Step 3: 实现接口与异常**

`image-code/src/design_hub/providers/errors.py`:

```python
class ProviderError(Exception):
    """Model provider failure (network/IO domain — fallback is allowed here)."""


class ProviderTimeout(ProviderError):
    """Provider exceeded its latency budget."""
```

`image-code/src/design_hub/providers/base.py`:

```python
from abc import ABC, abstractmethod
from decimal import Decimal

from ..domain.dto import GeneratedImage
from ..domain.enums import ModelName


class AbstractModelProvider(ABC):
    name: ModelName
    unit_cost: Decimal  # CNY per image

    @abstractmethod
    async def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        reference_images: list[bytes],
        size: tuple[int, int],
        n: int,
        seed: int | None = None,
    ) -> list[GeneratedImage]:
        ...
```

Create empty `image-code/src/design_hub/providers/__init__.py`.

- [ ] **Step 4: 运行确认通过**

Run: `cd image-code && uv run pytest tests/providers/test_base.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/providers/__init__.py image-code/src/design_hub/providers/base.py image-code/src/design_hub/providers/errors.py image-code/tests/providers
git commit -m "feat: AbstractModelProvider 抽象接口(ISP)

唯一抽象方法 generate；ProviderTimeout 继承 ProviderError 供
路由层据此决定是否切同档位备选。"
```

---

## Task 6: MockModelProvider

**Files:**
- Create: `image-code/src/design_hub/providers/mock.py`
- Test: `image-code/tests/providers/test_mock.py`

- [ ] **Step 1: 写失败测试**

`image-code/tests/providers/test_mock.py`:

```python
from decimal import Decimal

import pytest

from design_hub.domain.enums import ModelName
from design_hub.providers.errors import ProviderTimeout
from design_hub.providers.mock import MockModelProvider


async def test_mock_returns_n_deterministic_images():
    p = MockModelProvider(name=ModelName.SEEDREAM_5, unit_cost=Decimal("0.20"))
    images = await p.generate(prompt="p", negative_prompt="n", reference_images=[],
                              size=(1500, 2000), n=6, seed=100)
    assert len(images) == 6
    assert images[0].seed == 100
    assert images[0].cost == Decimal("0.20")
    assert images[0].url == "mock://seedream-5/100.png"


async def test_mock_can_fail_for_fallback_tests():
    p = MockModelProvider(name=ModelName.GPT_IMAGE_2, unit_cost=Decimal("1.19"), fail=True)
    with pytest.raises(ProviderTimeout):
        await p.generate(prompt="p", negative_prompt="n", reference_images=[],
                         size=(1, 1), n=1)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/providers/test_mock.py -v`
Expected: FAIL（cannot import mock）。

- [ ] **Step 3: 实现 Mock**

`image-code/src/design_hub/providers/mock.py`:

```python
import asyncio
from decimal import Decimal

from ..domain.dto import GeneratedImage
from ..domain.enums import ModelName
from .base import AbstractModelProvider
from .errors import ProviderTimeout


class MockModelProvider(AbstractModelProvider):
    def __init__(
        self,
        *,
        name: ModelName = ModelName.SEEDREAM_5,
        unit_cost: Decimal = Decimal("0.20"),
        latency_ms: int = 5,
        fail: bool = False,
    ) -> None:
        self.name = name
        self.unit_cost = unit_cost
        self._latency_ms = latency_ms
        self._fail = fail

    async def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        reference_images: list[bytes],
        size: tuple[int, int],
        n: int,
        seed: int | None = None,
    ) -> list[GeneratedImage]:
        await asyncio.sleep(self._latency_ms / 1000)
        if self._fail:
            raise ProviderTimeout(f"{self.name} mock failure")
        base = seed if seed is not None else 0
        return [
            GeneratedImage(
                url=f"mock://{self.name}/{base + i}.png",
                seed=base + i,
                latency_ms=self._latency_ms,
                cost=self.unit_cost,
            )
            for i in range(n)
        ]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd image-code && uv run pytest tests/providers/test_mock.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/providers/mock.py image-code/tests/providers/test_mock.py
git commit -m "feat: MockModelProvider(LSP, CI 零费用)

可注入名称/单价/延迟/失败，行为契约与真实 Provider 一致，
支持 fallback 场景测试。"
```

---

## Task 7: ProviderRegistry

**Files:**
- Create: `image-code/src/design_hub/providers/registry.py`
- Test: `image-code/tests/providers/test_registry.py`

- [ ] **Step 1: 写失败测试**

`image-code/tests/providers/test_registry.py`:

```python
import pytest

from design_hub.domain.enums import ModelName
from design_hub.providers.mock import MockModelProvider
from design_hub.providers.registry import ProviderRegistry


def test_register_and_get():
    reg = ProviderRegistry()
    p = MockModelProvider(name=ModelName.SEEDREAM_5)
    reg.register(p)
    assert reg.get(ModelName.SEEDREAM_5) is p
    assert ModelName.SEEDREAM_5 in reg


def test_get_unknown_raises():
    reg = ProviderRegistry()
    with pytest.raises(KeyError):
        reg.get(ModelName.GPT_IMAGE_2)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/providers/test_registry.py -v`
Expected: FAIL（cannot import registry）。

- [ ] **Step 3: 实现注册表**

`image-code/src/design_hub/providers/registry.py`:

```python
from ..domain.enums import ModelName
from .base import AbstractModelProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[ModelName, AbstractModelProvider] = {}

    def register(self, provider: AbstractModelProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: ModelName) -> AbstractModelProvider:
        if name not in self._providers:
            raise KeyError(f"No provider registered for {name}")
        return self._providers[name]

    def __contains__(self, name: ModelName) -> bool:
        return name in self._providers
```

- [ ] **Step 4: 运行确认通过**

Run: `cd image-code && uv run pytest tests/providers/test_registry.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/providers/registry.py image-code/tests/providers/test_registry.py
git commit -m "feat: ProviderRegistry(DIP 组装根)

pipeline 通过注册表按 ModelName 取 Provider，不 import 具体实现。"
```

---

## Task 8: 模型路由表与 Router

**Files:**
- Create: `image-code/src/design_hub/routing/__init__.py`、`table.py`、`router.py`
- Test: `image-code/tests/routing/test_router.py`

- [ ] **Step 1: 写失败测试**

建空 `image-code/tests/routing/__init__.py`。`image-code/tests/routing/test_router.py`:

```python
from design_hub.domain.enums import ModelName, SubScene, TemplateFamily, Tier
from design_hub.routing.router import ModelRouter


def test_family_primary_at_standard_tier():
    r = ModelRouter()
    assert r.route(TemplateFamily.F3, SubScene.S1, Tier.STANDARD).primary is ModelName.SEEDREAM_5
    assert r.route(TemplateFamily.F7, SubScene.S1, Tier.STANDARD).primary is ModelName.QWEN_IMAGE_PRO
    assert r.route(TemplateFamily.F4, SubScene.S1, Tier.STANDARD).primary is ModelName.GPT_IMAGE_2


def test_refine_tier_upgrades_to_gpt():
    r = ModelRouter()
    assert r.route(TemplateFamily.F3, SubScene.S1, Tier.REFINE).primary is ModelName.GPT_IMAGE_2


def test_draft_tier_downgrades_by_subscene():
    r = ModelRouter()
    assert r.route(TemplateFamily.F3, SubScene.S1, Tier.DRAFT).primary is ModelName.LINGDONG_2
    assert r.route(TemplateFamily.F3, SubScene.S4, Tier.DRAFT).primary is ModelName.WANXIANG_27


def test_forced_gpt_family_ignores_tier():
    r = ModelRouter()
    # 族1 含真人/复杂版式，草稿档也强制 GPT
    assert r.route(TemplateFamily.F1, SubScene.S1, Tier.DRAFT).primary is ModelName.GPT_IMAGE_2


def test_decision_has_fallbacks_and_default_candidates():
    r = ModelRouter()
    d = r.route(TemplateFamily.F3, SubScene.S1, Tier.STANDARD)
    assert d.candidate_count == 6
    assert ModelName.QWEN_IMAGE_PRO in d.fallbacks
    assert d.primary not in d.fallbacks  # 不跨档/不自指
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/routing/test_router.py -v`
Expected: FAIL（cannot import router）。

- [ ] **Step 3: 实现路由表**

`image-code/src/design_hub/routing/table.py`:

```python
from ..domain.enums import ModelName, TemplateFamily

# 含真人/复杂版式：强制 GPT-image，忽略档位
FORCED_GPT_FAMILIES: frozenset[TemplateFamily] = frozenset({
    TemplateFamily.F1, TemplateFamily.F2, TemplateFamily.F6,
    TemplateFamily.F8, TemplateFamily.F9,
})

# 标准档：模板族 → 首选模型（V1 4 族）
FAMILY_PRIMARY: dict[TemplateFamily, ModelName] = {
    TemplateFamily.F3: ModelName.SEEDREAM_5,
    TemplateFamily.F4: ModelName.GPT_IMAGE_2,
    TemplateFamily.F5: ModelName.SEEDREAM_5,
    TemplateFamily.F7: ModelName.QWEN_IMAGE_PRO,
}

REFINE_MODEL: ModelName = ModelName.GPT_IMAGE_2
DRAFT_MODEL_S4: ModelName = ModelName.WANXIANG_27
DRAFT_MODEL_DEFAULT: ModelName = ModelName.LINGDONG_2

DEFAULT_CANDIDATES = 6
MAX_CANDIDATES = 12

# 同档位备选链（绝不跨档升级）
FALLBACKS: dict[ModelName, tuple[ModelName, ...]] = {
    ModelName.SEEDREAM_5: (ModelName.QWEN_IMAGE_PRO,),
    ModelName.QWEN_IMAGE_PRO: (ModelName.SEEDREAM_5,),
    ModelName.GPT_IMAGE_2: (ModelName.SEEDREAM_5,),
    ModelName.LINGDONG_2: (ModelName.WANXIANG_27,),
    ModelName.WANXIANG_27: (ModelName.LINGDONG_2,),
}
```

- [ ] **Step 4: 实现 Router**

`image-code/src/design_hub/routing/router.py`:

```python
from ..domain.dto import RoutingDecision
from ..domain.enums import ModelName, SubScene, TemplateFamily, Tier
from . import table


class ModelRouter:
    def route(self, family: TemplateFamily, subscene: SubScene, tier: Tier) -> RoutingDecision:
        primary = self._primary(family, subscene, tier)
        fallbacks = table.FALLBACKS.get(primary, ())
        return RoutingDecision(
            primary=primary,
            fallbacks=fallbacks,
            candidate_count=table.DEFAULT_CANDIDATES,
        )

    def _primary(self, family: TemplateFamily, subscene: SubScene, tier: Tier) -> ModelName:
        if family in table.FORCED_GPT_FAMILIES:
            return ModelName.GPT_IMAGE_2
        if tier is Tier.REFINE:
            return table.REFINE_MODEL
        if tier is Tier.DRAFT:
            return table.DRAFT_MODEL_S4 if subscene is SubScene.S4 else table.DRAFT_MODEL_DEFAULT
        if family not in table.FAMILY_PRIMARY:
            raise KeyError(f"Template family {family} has no V1 primary model")
        return table.FAMILY_PRIMARY[family]
```

- [ ] **Step 5: 运行确认通过**

Run: `cd image-code && uv run pytest tests/routing/test_router.py -v`
Expected: PASS（5 passed）。

- [ ] **Step 6: 提交**

```bash
git add image-code/src/design_hub/routing image-code/tests/routing
git commit -m "feat: 模型路由器(模板族×档位 二维, OCP 数据驱动)

族→首选模型/档位升降级/含真人族强制 GPT 全部表驱动；
fallback 仅同档位备选，绝不自动跨档升级以防烧钱。"
```

---

## Task 9: 词库 A/C/D（色卡/防御/质量）

**Files:**
- Create: `image-code/src/design_hub/prompt/__init__.py`、`prompt/libraries/__init__.py`、`color.py`、`guard.py`、`quality.py`
- Test: `image-code/tests/prompt/test_libraries.py`

- [ ] **Step 1: 写失败测试**

建空 `image-code/tests/prompt/__init__.py`。`image-code/tests/prompt/test_libraries.py`:

```python
import pytest

from design_hub.domain.enums import Category, ModelName, Style
from design_hub.prompt.libraries.color import ColorLibrary
from design_hub.prompt.libraries.guard import GuardLibrary
from design_hub.prompt.libraries.quality import QualityLibrary


def test_color_lib_has_hex():
    assert "#E60012" in ColorLibrary().get(Style.GUOCHAO)


def test_color_lib_missing_raises():
    class Fake:
        pass
    with pytest.raises(KeyError):
        ColorLibrary().get(Fake())  # type: ignore[arg-type]


def test_guard_lib_by_category():
    assert "非明星脸" in GuardLibrary().get(Category.WITH_PERSON)


def test_quality_lib_by_model():
    assert "8K" in QualityLibrary().get(ModelName.SEEDREAM_5)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/prompt/test_libraries.py -v`
Expected: FAIL（import error）。

- [ ] **Step 3: 实现三个词库**

`image-code/src/design_hub/prompt/libraries/color.py`:

```python
from ...domain.enums import Style

_COLOR: dict[Style, str] = {
    Style.LUXURY: "黑金 #1a1a1a + 暖金 #c9a86a + 深红 #6b2020",
    Style.NORDIC: "鼠尾草绿 #b2c2a8 + 牛皮纸 #d4c4a0 + 奶油白 #f5f0e6",
    Style.GUOCHAO: "中国红 #E60012 + 鎏金 #d4af37 + 墨黑 #1c1c1c",
    Style.TECH: "深空蓝 #0a1428 + 电光紫 #8b5cf6 + 冷银 #c0c8d0",
    Style.FRESH: "薄荷绿 #a8d8c0 + 浅木色 #d9c9b0 + 白 #ffffff",
    Style.SPORT: "电光橙 #ff6b1a + 冷灰 #4a5057 + 黑 #1a1a1a",
    Style.FESTIVE: "正红 #c8102e + 金 #f0c419 + 暖白 #fff8e7",
}


class ColorLibrary:
    def get(self, style: Style) -> str:
        if style not in _COLOR:
            raise KeyError(f"No color card for style {style}")
        return _COLOR[style]
```

`image-code/src/design_hub/prompt/libraries/guard.py`:

```python
from ...domain.enums import Category

_GUARD: dict[Category, str] = {
    Category.DIGITAL_3C: "严格保持产品外观结构比例不变；屏幕/按键位置不变；接口结构清晰",
    Category.APPAREL: "手指不能遮挡核心结构；材质纹理清晰；五金件高光突出",
    Category.BEAUTY: "瓶身比例不变；Logo/标签文字清晰；瓶盖结构完整",
    Category.FOOD: "保留产品原色；避免过度调色；包装文字清晰",
    Category.WITH_PERSON: "原创模特，非明星脸，非真人复刻",
    Category.MIRROR: "反射干净，无杂乱人脸/背景；透明折射真实",
}


class GuardLibrary:
    def get(self, category: Category) -> str:
        if category not in _GUARD:
            raise KeyError(f"No guard words for category {category}")
        return _GUARD[category]
```

`image-code/src/design_hub/prompt/libraries/quality.py`:

```python
from ...domain.enums import ModelName

_QUALITY: dict[ModelName, str] = {
    ModelName.GPT_IMAGE_2: "8K超高清，电影级画质，商业广告质感，极致细节，锐利清晰",
    ModelName.SEEDREAM_5: "8K, 商业广告, 锐利细节, 高色彩还原",
    ModelName.QWEN_IMAGE_PRO: "超高清，商业摄影质感，精致细节",
    ModelName.WANXIANG_27: "(masterpiece:1.2), (8k:1.1), sharp focus, commercial photography",
    ModelName.LINGDONG_2: "(masterpiece:1.2), (8k:1.1), sharp focus, commercial photography",
}


class QualityLibrary:
    def get(self, model: ModelName) -> str:
        if model not in _QUALITY:
            raise KeyError(f"No quality words for model {model}")
        return _QUALITY[model]
```

Create empty `image-code/src/design_hub/prompt/__init__.py` and `image-code/src/design_hub/prompt/libraries/__init__.py`.

- [ ] **Step 4: 运行确认通过**

Run: `cd image-code && uv run pytest tests/prompt/test_libraries.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/prompt/__init__.py image-code/src/design_hub/prompt/libraries image-code/tests/prompt
git commit -m "feat: 词库 A/C/D(色卡/歧义防御/质量增强, SRP)

每库独立成文件，缺 key 直接抛错(fail-fast, 不静默给默认)。"
```

---

## Task 10: 词库 B/E（负面句/镜头）

**Files:**
- Create: `image-code/src/design_hub/prompt/libraries/negative.py`、`lens.py`
- Test: 追加到 `image-code/tests/prompt/test_libraries.py`

- [ ] **Step 1: 追加失败测试**

在 `image-code/tests/prompt/test_libraries.py` 末尾追加：

```python
from design_hub.domain.enums import TemplateFamily
from design_hub.prompt.libraries.lens import LensLibrary, LensPurpose
from design_hub.prompt.libraries.negative import NegativeLibrary


def test_negative_always_includes_common():
    items = NegativeLibrary().build(Category.BEAUTY, TemplateFamily.F3)
    assert "不要 AI 廉价感" in items


def test_negative_adds_festive_for_family7():
    items = NegativeLibrary().build(Category.FOOD, TemplateFamily.F7)
    assert "不要俗气红" in items
    assert "不要塑料感" in items  # 食品品类


def test_lens_lib():
    assert "50mm" in LensLibrary().get(LensPurpose.SINGLE_PRODUCT)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/prompt/test_libraries.py -v`
Expected: FAIL（import negative/lens 失败）。

- [ ] **Step 3: 实现两个词库**

`image-code/src/design_hub/prompt/libraries/negative.py`:

```python
from ...domain.enums import Category, TemplateFamily

_COMMON = ["不要廉价电商风", "不要过度设计", "不要杂乱", "不要 AI 廉价感"]
_BY_CATEGORY: dict[Category, list[str]] = {
    Category.WITH_PERSON: ["不要普通街拍", "不要全身穿搭展示", "不要电商白底图"],
    Category.FOOD: ["不要过度调色", "不要塑料感", "不要假食物感"],
    Category.MIRROR: ["不要镜面杂乱反射", "不要出现杂乱人脸"],
}
_FESTIVE = ["不要俗气红", "不要复古酒吧风"]


class NegativeLibrary:
    def build(self, category: Category, family: TemplateFamily) -> list[str]:
        items = list(_COMMON)
        items += _BY_CATEGORY.get(category, [])
        if family is TemplateFamily.F7:
            items += _FESTIVE
        return items
```

`image-code/src/design_hub/prompt/libraries/lens.py`:

```python
from enum import StrEnum


class LensPurpose(StrEnum):
    SINGLE_PRODUCT = "单品精修"
    BIG_PERSPECTIVE = "大透视冲击"
    STRUCTURE = "结构展示"
    AMBIANCE = "场景氛围"


_LENS: dict[LensPurpose, str] = {
    LensPurpose.SINGLE_PRODUCT: "50mm标准镜头，f/1.8大光圈，浅景深，近景特写",
    LensPurpose.BIG_PERSPECTIVE: "24mm广角，低角度仰拍，第一人称视角，近大远小",
    LensPurpose.STRUCTURE: "45°斜角特写 + 轻微低角度仰拍，产品居中占 65-70%",
    LensPurpose.AMBIANCE: "中焦，柔焦，电影级光影，eye-level 平视",
}


class LensLibrary:
    def get(self, purpose: LensPurpose) -> str:
        if purpose not in _LENS:
            raise KeyError(f"No lens for purpose {purpose}")
        return _LENS[purpose]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd image-code && uv run pytest tests/prompt/test_libraries.py -v`
Expected: PASS（7 passed）。

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/prompt/libraries/negative.py image-code/src/design_hub/prompt/libraries/lens.py image-code/tests/prompt/test_libraries.py
git commit -m "feat: 词库 B/E(中文负面句/镜头, SRP)

负面句通用+按品类+族7节庆叠加；镜头库按用途，自带 LensPurpose。"
```

---

## Task 11: 模板族基类 + 族3

**Files:**
- Create: `image-code/src/design_hub/prompt/families/__init__.py`、`base.py`、`family3.py`
- Test: `image-code/tests/prompt/test_families.py`

- [ ] **Step 1: 写失败测试**

`image-code/tests/prompt/test_families.py`:

```python
import pytest

from design_hub.domain.enums import TemplateFamily
from design_hub.prompt.families.family3 import Family3Minimal


def test_family3_renders_with_required_slots():
    fam = Family3Minimal()
    assert fam.family is TemplateFamily.F3
    slots = {k: "X" for k in fam.required_slots()}
    out = fam.render(slots)
    assert "极简主义" in out


def test_family3_missing_slot_raises():
    fam = Family3Minimal()
    with pytest.raises(KeyError):
        fam.render({})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/prompt/test_families.py -v`
Expected: FAIL（import error）。

- [ ] **Step 3: 实现基类与族3**

`image-code/src/design_hub/prompt/families/base.py`:

```python
from abc import ABC, abstractmethod
from typing import ClassVar

from ...domain.enums import TemplateFamily


class TemplateFamilySkeleton(ABC):
    family: ClassVar[TemplateFamily]

    @abstractmethod
    def required_slots(self) -> set[str]:
        ...

    @abstractmethod
    def render(self, slots: dict[str, str]) -> str:
        ...

    def _check(self, slots: dict[str, str]) -> None:
        missing = self.required_slots() - slots.keys()
        if missing:
            raise KeyError(f"{self.family} missing slots: {sorted(missing)}")
```

`image-code/src/design_hub/prompt/families/family3.py`:

```python
from typing import ClassVar

from ...domain.enums import TemplateFamily
from .base import TemplateFamilySkeleton


class Family3Minimal(TemplateFamilySkeleton):
    """族 3：极简电商主图（美妆/护肤/保健）。"""

    family: ClassVar[TemplateFamily] = TemplateFamily.F3

    def required_slots(self) -> set[str]:
        return {"风格", "品类", "产品描述", "位置", "角度", "浅色A",
                "浅色B", "装饰元素", "色卡", "标题文案", "比例"}

    def render(self, slots: dict[str, str]) -> str:
        self._check(slots)
        return (
            f"极简主义{slots['风格']}{slots['品类']}电商海报。"
            f"主体产品是{slots['产品描述']}。"
            f"产品位于画面{slots['位置']}，呈{slots['角度']}倾斜。"
            f"背景为{slots['浅色A']}至{slots['浅色B']}渐变。"
            f"产品周围{slots['装饰元素']}，营造柔和景深层次。"
            f"专业棚拍布光，排版干净，留有充足文案空间，8k，高端{slots['品类']}广告摄影风格。{slots['比例']}\n"
            f"【文字排版】主色调：{slots['色卡']}；主标题：{slots['标题文案']}"
        )
```

Create empty `image-code/src/design_hub/prompt/families/__init__.py`.

- [ ] **Step 4: 运行确认通过**

Run: `cd image-code && uv run pytest tests/prompt/test_families.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/prompt/families/__init__.py image-code/src/design_hub/prompt/families/base.py image-code/src/design_hub/prompt/families/family3.py image-code/tests/prompt/test_families.py
git commit -m "feat: 模板族基类 + 族3极简电商主图(OCP/LSP)

骨架基类声明 required_slots/render，缺槽报错；族3 按 playbook
§三骨架填槽，新增族只需新增子类。"
```

---

## Task 12: 族4/5/7 + FamilyRegistry

**Files:**
- Create: `image-code/src/design_hub/prompt/families/family4.py`、`family5.py`、`family7.py`、`registry.py`
- Test: 追加到 `image-code/tests/prompt/test_families.py`

- [ ] **Step 1: 追加失败测试**

在 `image-code/tests/prompt/test_families.py` 末尾追加：

```python
from design_hub.prompt.families.registry import FamilyRegistry


def test_registry_returns_four_v1_families():
    reg = FamilyRegistry()
    for fam in (TemplateFamily.F3, TemplateFamily.F4, TemplateFamily.F5, TemplateFamily.F7):
        skeleton = reg.get(fam)
        slots = {k: "X" for k in skeleton.required_slots()}
        assert skeleton.render(slots)


def test_registry_unimplemented_family_raises():
    with pytest.raises(KeyError):
        FamilyRegistry().get(TemplateFamily.F2)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/prompt/test_families.py -v`
Expected: FAIL（import family4/registry 失败）。

- [ ] **Step 3: 实现族4/5/7**

`image-code/src/design_hub/prompt/families/family4.py`:

```python
from typing import ClassVar

from ...domain.enums import TemplateFamily
from .base import TemplateFamilySkeleton


class Family4Premium(TemplateFamilySkeleton):
    """族 4：高端商业摄影（单品精修/首图）。"""

    family: ClassVar[TemplateFamily] = TemplateFamily.F4

    def required_slots(self) -> set[str]:
        return {"镜头", "构图", "光影", "产品描述", "色卡", "氛围词", "用途", "比例"}

    def render(self, slots: dict[str, str]) -> str:
        self._check(slots)
        return (
            "8K超高清，电影级画质，极致细节。超写实3D渲染，商业摄影质感。"
            f"{slots['镜头']}。{slots['构图']}。{slots['光影']}。"
            f"主体为{slots['产品描述']}。画面无人物。"
            f"主色调{slots['色卡']}。{slots['氛围词']}。"
            f"{slots['用途']}。{slots['比例']}"
        )
```

`image-code/src/design_hub/prompt/families/family5.py`:

```python
from typing import ClassVar

from ...domain.enums import TemplateFamily
from .base import TemplateFamilySkeleton


class Family5Ambiance(TemplateFamilySkeleton):
    """族 5：氛围沉浸场景（食品/咖啡/生活方式）。"""

    family: ClassVar[TemplateFamily] = TemplateFamily.F5

    def required_slots(self) -> set[str]:
        return {"风格", "产品名", "色卡", "装饰元素", "标题文案", "比例"}

    def render(self, slots: dict[str, str]) -> str:
        self._check(slots)
        return (
            f"一张{slots['风格']}「{slots['产品名']}」产品宣传海报，"
            "电商广告与品牌视觉结合风格。"
            f"背景使用{slots['色卡']}，营造沉浸氛围。"
            f"主体立体摆放，{slots['装饰元素']}。"
            f"主标题：{slots['标题文案']}。"
            f"要求高级质感、非AI廉价感。{slots['比例']}"
        )
```

`image-code/src/design_hub/prompt/families/family7.py`:

```python
from typing import ClassVar

from ...domain.enums import TemplateFamily
from .base import TemplateFamilySkeleton


class Family7Festive(TemplateFamilySkeleton):
    """族 7：中式节庆促销（年货节/国潮/IP 大促）。"""

    family: ClassVar[TemplateFamily] = TemplateFamily.F7

    def required_slots(self) -> set[str]:
        return {"品牌", "主题场景名", "产品描述", "装饰元素",
                "主标题", "促销标语", "搜索词", "比例"}

    def render(self, slots: dict[str, str]) -> str:
        self._check(slots)
        return (
            "3D 电影感，C4D 风格，超大广角，超大透视，仰视角度，夸张视觉表现。"
            f"这是{slots['品牌']} \"{slots['主题场景名']}\" 主题场景，国风年味氛围。"
            f"主视觉元素：{slots['产品描述']}，鎏金材质。"
            f"场景细节：周围{slots['装饰元素']}，背景中式牌楼。"
            f"文字信息：顶部大标题 \"{slots['主标题']}\"，标语 \"{slots['促销标语']}\"，"
            f"底部搜索入口 \"{slots['搜索词']}\"。"
            f"光影：暖调金色光线。整体喜庆红火。{slots['比例']}"
        )
```

- [ ] **Step 4: 实现 FamilyRegistry**

`image-code/src/design_hub/prompt/families/registry.py`:

```python
from ...domain.enums import TemplateFamily
from .base import TemplateFamilySkeleton
from .family3 import Family3Minimal
from .family4 import Family4Premium
from .family5 import Family5Ambiance
from .family7 import Family7Festive


class FamilyRegistry:
    def __init__(self) -> None:
        self._families: dict[TemplateFamily, TemplateFamilySkeleton] = {}
        for skeleton in (Family3Minimal(), Family4Premium(),
                         Family5Ambiance(), Family7Festive()):
            self._families[skeleton.family] = skeleton

    def get(self, family: TemplateFamily) -> TemplateFamilySkeleton:
        if family not in self._families:
            raise KeyError(f"Template family {family} not implemented in V1")
        return self._families[family]
```

- [ ] **Step 5: 运行确认通过**

Run: `cd image-code && uv run pytest tests/prompt/test_families.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 6: 提交**

```bash
git add image-code/src/design_hub/prompt/families image-code/tests/prompt/test_families.py
git commit -m "feat: 族4/5/7骨架 + FamilyRegistry(OCP)

补齐 V1 四族(高端摄影/氛围沉浸/中式节庆)，注册表按 family 取用，
未实现族明确报错。"
```

---

## Task 13: 视觉辅助 + 品牌名生成

**Files:**
- Create: `image-code/src/design_hub/prompt/vision.py`、`brand.py`
- Test: `image-code/tests/prompt/test_vision_brand.py`

- [ ] **Step 1: 写失败测试**

`image-code/tests/prompt/test_vision_brand.py`:

```python
from design_hub.domain.dto import ProductVisualInfo
from design_hub.domain.enums import Category
from design_hub.prompt.brand import BrandNameGenerator
from design_hub.prompt.vision import MockVisionAssist, VisionAssist


async def test_mock_vision_returns_info():
    assist: VisionAssist = MockVisionAssist()
    info = await assist.analyze([b"fakebytes"])
    assert isinstance(info, ProductVisualInfo)
    assert info.main_color_hex.startswith("#")


def test_brand_generator_by_category():
    gen = BrandNameGenerator()
    names = gen.candidates(Category.APPAREL, count=2)
    assert len(names) == 2
    assert all(isinstance(n, str) for n in names)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/prompt/test_vision_brand.py -v`
Expected: FAIL（import error）。

- [ ] **Step 3: 实现视觉接口与品牌生成**

`image-code/src/design_hub/prompt/vision.py`:

```python
from abc import ABC, abstractmethod

from ..domain.dto import ProductVisualInfo


class VisionAssist(ABC):
    @abstractmethod
    async def analyze(self, images: list[bytes]) -> ProductVisualInfo:
        ...


class MockVisionAssist(VisionAssist):
    async def analyze(self, images: list[bytes]) -> ProductVisualInfo:
        return ProductVisualInfo(
            product_type="通用产品",
            main_color_hex="#cccccc",
            material="哑光塑料",
            shape_ratio="竖向圆柱",
            logo_position="正面居中",
        )
```

`image-code/src/design_hub/prompt/brand.py`:

```python
from ..domain.enums import Category

_BRAND_POOL: dict[Category, list[str]] = {
    Category.DIGITAL_3C: ["Thermo Arc", "Volt Edge", "Nimbus Core"],
    Category.APPAREL: ["Urban Loop", "Field Mark", "Crane & Co"],
    Category.BEAUTY: ["Lumi Veil", "Petal Form", "Aura Skin"],
    Category.FOOD: ["Harvest Lane", "Grain & Ember", "Pure Crumb"],
    Category.WITH_PERSON: ["Modeluxe", "Form Atelier", "Mode Nord"],
    Category.MIRROR: ["Clearon", "Mirage Lab", "Glass Theory"],
}


class BrandNameGenerator:
    def candidates(self, category: Category, count: int = 3) -> list[str]:
        pool = _BRAND_POOL.get(category, ["Generica", "Marque One", "Brandly"])
        return pool[:count]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd image-code && uv run pytest tests/prompt/test_vision_brand.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/prompt/vision.py image-code/src/design_hub/prompt/brand.py image-code/tests/prompt/test_vision_brand.py
git commit -m "feat: 视觉辅助接口(ISP/DIP) + 虚构品牌名生成

VisionAssist 抽象 + Mock 实现，真实 qwen-vl-max 后续注入；
品牌名按品类出候选，规避真实品牌版权。"
```

---

## Task 14: 10 法则可执行片段

**Files:**
- Create: `image-code/src/design_hub/prompt/rules.py`
- Test: `image-code/tests/prompt/test_rules.py`

- [ ] **Step 1: 写失败测试**

`image-code/tests/prompt/test_rules.py`:

```python
from design_hub.domain.enums import ModelName
from design_hub.prompt.rules import format_ratio, typography_block


def test_ratio_for_gpt_is_chinese():
    assert format_ratio((1500, 2000), ModelName.GPT_IMAGE_2) == "3:4竖版"


def test_ratio_for_tag_model_uses_ar():
    assert format_ratio((1500, 2000), ModelName.WANXIANG_27) == "--ar 3:4"


def test_typography_block_empty_when_no_copy():
    assert typography_block(None) == ""


def test_typography_block_renders_segment():
    out = typography_block("年货大促")
    assert "年货大促" in out and "【文字排版】" in out
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/prompt/test_rules.py -v`
Expected: FAIL（import error）。

- [ ] **Step 3: 实现法则片段**

`image-code/src/design_hub/prompt/rules.py`:

```python
from math import gcd

from ..domain.enums import ModelName

# 法则 10：即梦/MJ 风模型用 --ar，GPT/Seedream/千问 用中文比例
_TAG_STYLE_MODELS = {ModelName.WANXIANG_27, ModelName.LINGDONG_2}


def format_ratio(size: tuple[int, int], model: ModelName) -> str:
    width, height = size
    divisor = gcd(width, height)
    ratio_w, ratio_h = width // divisor, height // divisor
    if model in _TAG_STYLE_MODELS:
        return f"--ar {ratio_w}:{ratio_h}"
    orientation = "竖版" if height >= width else "横版"
    return f"{ratio_w}:{ratio_h}{orientation}"


def typography_block(copy_text: str | None) -> str:
    # 法则 6：文字/版式信息独立成段
    if not copy_text:
        return ""
    return f"\n【文字排版】{copy_text}（内容+位置+字号+字重+字体+颜色独立成段）"
```

- [ ] **Step 4: 运行确认通过**

Run: `cd image-code && uv run pytest tests/prompt/test_rules.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/prompt/rules.py image-code/tests/prompt/test_rules.py
git commit -m "feat: 10 法则可执行片段(比例格式化/文字独立段)

按目标模型差异化输出比例(GPT 中文 vs MJ风 --ar)，文字版式
独立成段，供编排器收尾套用。"
```

---

## Task 15: PromptOrchestrator 编排器

**Files:**
- Create: `image-code/src/design_hub/prompt/orchestrator.py`
- Test: `image-code/tests/prompt/test_orchestrator.py`

- [ ] **Step 1: 写失败测试**

`image-code/tests/prompt/test_orchestrator.py`:

```python
from design_hub.domain.dto import Brief
from design_hub.domain.enums import (
    Category, ModelName, Style, SubScene, TemplateFamily, Tier,
)
from design_hub.prompt.brand import BrandNameGenerator
from design_hub.prompt.families.registry import FamilyRegistry
from design_hub.prompt.libraries.color import ColorLibrary
from design_hub.prompt.libraries.guard import GuardLibrary
from design_hub.prompt.libraries.negative import NegativeLibrary
from design_hub.prompt.libraries.quality import QualityLibrary
from design_hub.prompt.orchestrator import PromptOrchestrator
from design_hub.prompt.vision import MockVisionAssist


def _make_orchestrator() -> PromptOrchestrator:
    return PromptOrchestrator(
        families=FamilyRegistry(), colors=ColorLibrary(),
        negatives=NegativeLibrary(), guards=GuardLibrary(),
        qualities=QualityLibrary(), vision=MockVisionAssist(),
        brands=BrandNameGenerator(),
    )


def _brief(**kw) -> Brief:
    base = dict(customer="客户A", subscene=SubScene.S1, family=TemplateFamily.F3,
                tier=Tier.STANDARD, style=Style.NORDIC, category=Category.BEAUTY,
                size=(1500, 2000))
    base.update(kw)
    return Brief(**base)  # type: ignore[arg-type]


async def test_build_injects_color_guard_quality_ratio():
    orch = _make_orchestrator()
    pair = await orch.build(_brief(), ModelName.SEEDREAM_5)
    assert "极简主义" in pair.positive          # 族3 骨架
    assert "瓶身比例不变" in pair.positive       # 词库C 防御(美妆)
    assert "高色彩还原" in pair.positive         # 词库D 质量(Seedream)
    assert "3:4竖版" in pair.positive            # 法则10 比例
    assert "不要 AI 廉价感" in pair.negative     # 词库B 负面


async def test_build_uses_vision_when_no_product_desc():
    orch = _make_orchestrator()
    pair = await orch.build(_brief(product_desc=None), ModelName.SEEDREAM_5)
    assert "哑光塑料" in pair.positive            # MockVision 补全


async def test_build_festive_family_adds_festive_negative():
    orch = _make_orchestrator()
    pair = await orch.build(
        _brief(family=TemplateFamily.F7, style=Style.GUOCHAO, category=Category.FOOD),
        ModelName.QWEN_IMAGE_PRO,
    )
    assert "不要俗气红" in pair.negative
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/prompt/test_orchestrator.py -v`
Expected: FAIL（import error）。

- [ ] **Step 3: 实现编排器**

`image-code/src/design_hub/prompt/orchestrator.py`:

```python
from ..domain.dto import Brief, PromptPair
from ..domain.enums import ModelName
from .brand import BrandNameGenerator
from .families.registry import FamilyRegistry
from .libraries.color import ColorLibrary
from .libraries.guard import GuardLibrary
from .libraries.negative import NegativeLibrary
from .libraries.quality import QualityLibrary
from .rules import format_ratio, typography_block
from .vision import VisionAssist


class PromptOrchestrator:
    def __init__(
        self,
        *,
        families: FamilyRegistry,
        colors: ColorLibrary,
        negatives: NegativeLibrary,
        guards: GuardLibrary,
        qualities: QualityLibrary,
        vision: VisionAssist,
        brands: BrandNameGenerator,
    ) -> None:
        self._families = families
        self._colors = colors
        self._negatives = negatives
        self._guards = guards
        self._qualities = qualities
        self._vision = vision
        self._brands = brands

    async def build(self, brief: Brief, target_model: ModelName) -> PromptPair:
        product_desc = brief.product_desc
        if product_desc is None:
            info = await self._vision.analyze(list(brief.reference_images))
            product_desc = f"{info.material}{info.product_type}，主色{info.main_color_hex}，{info.shape_ratio}"

        color_card = self._colors.get(brief.style)
        slots = self._build_slots(brief, product_desc, color_card, target_model)
        positive = self._families.get(brief.family).render(slots)

        # 法则4 防御词 + 法则6 文字独立段 + 法则10 质量词与比例收尾
        positive += "。" + self._guards.get(brief.category)
        positive += typography_block(brief.copy_text)
        positive += "。" + self._qualities.get(target_model)
        positive += " " + format_ratio(brief.size, target_model)

        negative = "、".join(self._negatives.build(brief.category, brief.family))
        return PromptPair(positive=positive, negative=negative)

    def _build_slots(
        self, brief: Brief, product_desc: str, color_card: str, target_model: ModelName,
    ) -> dict[str, str]:
        ratio = format_ratio(brief.size, target_model)
        brand = brief.brand_name or self._brands.candidates(brief.category, 1)[0]
        title = brief.copy_text or f"{brand} 臻选"
        return {
            "风格": brief.style.value,
            "品类": brief.category.value,
            "产品描述": product_desc,
            "色卡": color_card,
            "比例": ratio,
            "品牌": brand,
            "位置": "正中",
            "角度": "15°",
            "浅色A": "奶油白",
            "浅色B": "浅咖",
            "装饰元素": "柔光与几何点缀",
            "标题文案": title,
            "产品名": product_desc,
            "主标题": title,
            "促销标语": brief.copy_text or "限时优惠",
            "主题场景名": "新春",
            "搜索词": brand,
            "镜头": "50mm标准镜头，f/1.8大光圈，浅景深，近景特写",
            "构图": "居中留白，重心沉稳",
            "光影": "侧上方柔和暖光，明暗对比强烈",
            "氛围词": "高级沉浸氛围",
            "用途": f"电商{brief.category.value}广告主图",
        }
```

- [ ] **Step 4: 运行确认通过**

Run: `cd image-code && uv run pytest tests/prompt/test_orchestrator.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/prompt/orchestrator.py image-code/tests/prompt/test_orchestrator.py
git commit -m "feat: PromptOrchestrator 编排器(DIP 组合注入)

按 playbook §五流程：视觉补全→选族填槽→注入防御/负面→质量词
与比例收尾，按目标模型差异化。依赖词库/族/视觉抽象而非具体。"
```

---

## Task 16: 成本估算器 + 预算策略

**Files:**
- Create: `image-code/src/design_hub/cost/__init__.py`、`estimator.py`、`budget.py`
- Test: `image-code/tests/cost/test_estimator.py`、`test_budget.py`

- [ ] **Step 1: 写失败测试**

建空 `image-code/tests/cost/__init__.py`。`image-code/tests/cost/test_estimator.py`:

```python
from decimal import Decimal

from design_hub.cost.estimator import CostEstimator
from design_hub.domain.dto import RoutingDecision
from design_hub.domain.enums import ModelName
from design_hub.providers.mock import MockModelProvider


def test_estimate_is_count_times_unit_cost():
    provider = MockModelProvider(name=ModelName.SEEDREAM_5, unit_cost=Decimal("0.20"))
    decision = RoutingDecision(ModelName.SEEDREAM_5, (), 6)
    assert CostEstimator().estimate(decision, provider) == Decimal("1.20")
```

`image-code/tests/cost/test_budget.py`:

```python
from decimal import Decimal

import pytest

from design_hub.cost.budget import BudgetExceeded, BudgetPolicy, BudgetSnapshot


def _snap(**kw) -> BudgetSnapshot:
    base = dict(user_month_used=Decimal("10"), user_monthly_quota=Decimal("200"),
                company_month_used=Decimal("100"), company_monthly_budget=Decimal("800"))
    base.update(kw)
    return BudgetSnapshot(**base)  # type: ignore[arg-type]


def test_passes_within_budget():
    BudgetPolicy().check(Decimal("1.20"), _snap())  # no raise


def test_company_budget_exhausted():
    with pytest.raises(BudgetExceeded, match="公司本月预算"):
        BudgetPolicy().check(Decimal("1"), _snap(company_month_used=Decimal("800")))


def test_user_quota_exhausted():
    with pytest.raises(BudgetExceeded, match="用户本月配额"):
        BudgetPolicy().check(Decimal("1"), _snap(user_month_used=Decimal("200")))


def test_single_task_over_half_remaining():
    # 剩余 100，单次 60 > 50
    with pytest.raises(BudgetExceeded, match="50%"):
        BudgetPolicy().check(Decimal("60"), _snap(company_month_used=Decimal("700")))
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/cost/test_estimator.py tests/cost/test_budget.py -v`
Expected: FAIL（import error）。

- [ ] **Step 3: 实现估算器与预算策略**

`image-code/src/design_hub/cost/estimator.py`:

```python
from decimal import Decimal

from ..domain.dto import RoutingDecision
from ..providers.base import AbstractModelProvider


class CostEstimator:
    def estimate(self, decision: RoutingDecision, provider: AbstractModelProvider) -> Decimal:
        return provider.unit_cost * decision.candidate_count
```

`image-code/src/design_hub/cost/budget.py`:

```python
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class BudgetSnapshot:
    user_month_used: Decimal
    user_monthly_quota: Decimal
    company_month_used: Decimal
    company_monthly_budget: Decimal


class BudgetExceeded(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class BudgetPolicy:
    """PRD §3.9 三条红线（顺序：公司总预算 → 用户配额 → 单次占比）。"""

    def check(self, estimate: Decimal, snapshot: BudgetSnapshot) -> None:
        company_remaining = snapshot.company_monthly_budget - snapshot.company_month_used
        if company_remaining <= 0:
            raise BudgetExceeded("公司本月预算已用尽，需管理者手动解锁")
        if snapshot.user_month_used >= snapshot.user_monthly_quota:
            raise BudgetExceeded("用户本月配额已用尽")
        if estimate > company_remaining * Decimal("0.5"):
            raise BudgetExceeded("单次任务超过公司剩余预算的 50%")
```

Create empty `image-code/src/design_hub/cost/__init__.py`.

- [ ] **Step 4: 运行确认通过**

Run: `cd image-code && uv run pytest tests/cost/test_estimator.py tests/cost/test_budget.py -v`
Expected: PASS（5 passed）。

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/cost/__init__.py image-code/src/design_hub/cost/estimator.py image-code/src/design_hub/cost/budget.py image-code/tests/cost/__init__.py image-code/tests/cost/test_estimator.py image-code/tests/cost/test_budget.py
git commit -m "feat: 成本估算器 + 预算 3 红线策略(SRP)

estimate=候选数×单价；BudgetPolicy 纯函数式校验三红线，
与存储解耦。"
```

---

## Task 17: Ledger 仓储（接口 + 内存实现）

**Files:**
- Create: `image-code/src/design_hub/cost/ledger.py`
- Test: `image-code/tests/cost/test_ledger.py`

- [ ] **Step 1: 写失败测试**

`image-code/tests/cost/test_ledger.py`:

```python
from decimal import Decimal

from design_hub.cost.ledger import InMemoryLedgerRepository


async def test_reserve_then_snapshot_reflects_usage():
    repo = InMemoryLedgerRepository(user_quota=Decimal("200"), company_budget=Decimal("800"))
    await repo.reserve("u1", Decimal("1.20"))
    snap = await repo.snapshot("u1")
    assert snap.user_month_used == Decimal("1.20")
    assert snap.company_month_used == Decimal("1.20")


async def test_rollback_restores():
    repo = InMemoryLedgerRepository()
    await repo.reserve("u1", Decimal("5"))
    await repo.rollback("u1", Decimal("5"))
    snap = await repo.snapshot("u1")
    assert snap.user_month_used == Decimal("0")
    assert snap.company_month_used == Decimal("0")
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/cost/test_ledger.py -v`
Expected: FAIL（import error）。

- [ ] **Step 3: 实现仓储**

`image-code/src/design_hub/cost/ledger.py`:

```python
from abc import ABC, abstractmethod
from decimal import Decimal

from .budget import BudgetSnapshot


class LedgerRepository(ABC):
    @abstractmethod
    async def snapshot(self, user_id: str) -> BudgetSnapshot:
        ...

    @abstractmethod
    async def reserve(self, user_id: str, amount: Decimal) -> None:
        ...

    @abstractmethod
    async def rollback(self, user_id: str, amount: Decimal) -> None:
        ...


class InMemoryLedgerRepository(LedgerRepository):
    def __init__(
        self, *, user_quota: Decimal = Decimal("200"), company_budget: Decimal = Decimal("800"),
    ) -> None:
        self._user_quota = user_quota
        self._company_budget = company_budget
        self._user_used: dict[str, Decimal] = {}
        self._company_used = Decimal("0")

    async def snapshot(self, user_id: str) -> BudgetSnapshot:
        return BudgetSnapshot(
            user_month_used=self._user_used.get(user_id, Decimal("0")),
            user_monthly_quota=self._user_quota,
            company_month_used=self._company_used,
            company_monthly_budget=self._company_budget,
        )

    async def reserve(self, user_id: str, amount: Decimal) -> None:
        self._user_used[user_id] = self._user_used.get(user_id, Decimal("0")) + amount
        self._company_used += amount

    async def rollback(self, user_id: str, amount: Decimal) -> None:
        self._user_used[user_id] = self._user_used.get(user_id, Decimal("0")) - amount
        self._company_used -= amount
```

- [ ] **Step 4: 运行确认通过**

Run: `cd image-code && uv run pytest tests/cost/test_ledger.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/cost/ledger.py image-code/tests/cost/test_ledger.py
git commit -m "feat: LedgerRepository 接口 + 内存实现(DIP)

reserve/rollback/snapshot 抽象，M2 用 PG 实现按 LSP 直接替换。"
```

---

## Task 18: CostGuard + @cost_guard 装饰器

**Files:**
- Create: `image-code/src/design_hub/cost/guard.py`
- Test: `image-code/tests/cost/test_guard.py`

- [ ] **Step 1: 写失败测试**

`image-code/tests/cost/test_guard.py`:

```python
from decimal import Decimal

import pytest

from design_hub.cost.budget import BudgetExceeded, BudgetPolicy
from design_hub.cost.guard import CostGuard, GuardContext, cost_guard
from design_hub.cost.ledger import InMemoryLedgerRepository


def _guard() -> CostGuard:
    return CostGuard(ledger=InMemoryLedgerRepository(), policy=BudgetPolicy())


async def test_precheck_reserves_on_pass():
    g = _guard()
    await g.precheck_and_reserve("u1", Decimal("1.20"))
    snap = await g.ledger.snapshot("u1")
    assert snap.user_month_used == Decimal("1.20")


async def test_precheck_raises_and_does_not_reserve_when_over_budget():
    g = CostGuard(ledger=InMemoryLedgerRepository(company_budget=Decimal("0")),
                  policy=BudgetPolicy())
    with pytest.raises(BudgetExceeded):
        await g.precheck_and_reserve("u1", Decimal("1"))


async def test_decorator_rolls_back_on_failure():
    g = _guard()

    @cost_guard
    async def task(ctx: GuardContext) -> str:
        raise RuntimeError("boom")

    ctx = GuardContext(user_id="u1", estimate=Decimal("3"), guard=g)
    with pytest.raises(RuntimeError):
        await task(ctx)
    snap = await g.ledger.snapshot("u1")
    assert snap.user_month_used == Decimal("0")  # 预扣已回滚


async def test_decorator_keeps_reservation_on_success():
    g = _guard()

    @cost_guard
    async def task(ctx: GuardContext) -> str:
        return "ok"

    ctx = GuardContext(user_id="u1", estimate=Decimal("3"), guard=g)
    assert await task(ctx) == "ok"
    snap = await g.ledger.snapshot("u1")
    assert snap.user_month_used == Decimal("3")
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/cost/test_guard.py -v`
Expected: FAIL（import error）。

- [ ] **Step 3: 实现守门与装饰器**

`image-code/src/design_hub/cost/guard.py`:

```python
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from functools import wraps
from typing import TypeVar

from .budget import BudgetPolicy
from .ledger import LedgerRepository

T = TypeVar("T")


@dataclass
class CostGuard:
    ledger: LedgerRepository
    policy: BudgetPolicy

    async def precheck_and_reserve(self, user_id: str, estimate: Decimal) -> None:
        snapshot = await self.ledger.snapshot(user_id)
        self.policy.check(estimate, snapshot)  # raises BudgetExceeded
        await self.ledger.reserve(user_id, estimate)

    async def rollback(self, user_id: str, estimate: Decimal) -> None:
        await self.ledger.rollback(user_id, estimate)


@dataclass
class GuardContext:
    user_id: str
    estimate: Decimal
    guard: CostGuard


def cost_guard(func: Callable[[GuardContext], Awaitable[T]]) -> Callable[[GuardContext], Awaitable[T]]:
    """PRD §3.9：入队前预扣额度，任务失败回滚。包裹任务入口函数。"""

    @wraps(func)
    async def wrapper(ctx: GuardContext) -> T:
        await ctx.guard.precheck_and_reserve(ctx.user_id, ctx.estimate)
        try:
            return await func(ctx)
        except Exception:
            await ctx.guard.rollback(ctx.user_id, ctx.estimate)
            raise

    return wrapper
```

- [ ] **Step 4: 运行确认通过**

Run: `cd image-code && uv run pytest tests/cost/test_guard.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/cost/guard.py image-code/tests/cost/test_guard.py
git commit -m "feat: CostGuard + @cost_guard 装饰器(预扣/失败回滚)

precheck_and_reserve 校验红线后预扣；装饰器包裹任务入口，
异常时回滚并 re-raise(fail-fast)。M2 用于包裹 arq 任务。"
```

---

## Task 19: GenerationPipeline 组装

**Files:**
- Create: `image-code/src/design_hub/pipeline/__init__.py`、`pipeline.py`
- Test: `image-code/tests/pipeline/test_pipeline.py`

- [ ] **Step 1: 写失败测试**

建空 `image-code/tests/pipeline/__init__.py`。`image-code/tests/pipeline/test_pipeline.py`:

```python
from decimal import Decimal

import pytest

from design_hub.cost.budget import BudgetExceeded, BudgetPolicy
from design_hub.cost.estimator import CostEstimator
from design_hub.cost.guard import CostGuard
from design_hub.cost.ledger import InMemoryLedgerRepository
from design_hub.domain.dto import Brief
from design_hub.domain.enums import (
    Category, ModelName, Style, SubScene, TemplateFamily, Tier,
)
from design_hub.pipeline.pipeline import GenerationPipeline
from design_hub.prompt.brand import BrandNameGenerator
from design_hub.prompt.families.registry import FamilyRegistry
from design_hub.prompt.libraries.color import ColorLibrary
from design_hub.prompt.libraries.guard import GuardLibrary
from design_hub.prompt.libraries.negative import NegativeLibrary
from design_hub.prompt.libraries.quality import QualityLibrary
from design_hub.prompt.orchestrator import PromptOrchestrator
from design_hub.prompt.vision import MockVisionAssist
from design_hub.providers.mock import MockModelProvider
from design_hub.providers.registry import ProviderRegistry
from design_hub.routing.router import ModelRouter


def _orchestrator() -> PromptOrchestrator:
    return PromptOrchestrator(
        families=FamilyRegistry(), colors=ColorLibrary(), negatives=NegativeLibrary(),
        guards=GuardLibrary(), qualities=QualityLibrary(), vision=MockVisionAssist(),
        brands=BrandNameGenerator(),
    )


def _registry(*, primary_fail: bool = False) -> ProviderRegistry:
    reg = ProviderRegistry()
    # 族3标准档 primary=Seedream，fallback=千问
    reg.register(MockModelProvider(name=ModelName.SEEDREAM_5,
                                   unit_cost=Decimal("0.20"), fail=primary_fail))
    reg.register(MockModelProvider(name=ModelName.QWEN_IMAGE_PRO, unit_cost=Decimal("0.10")))
    return reg


def _pipeline(reg: ProviderRegistry) -> GenerationPipeline:
    return GenerationPipeline(
        router=ModelRouter(), orchestrator=_orchestrator(), registry=reg,
        estimator=CostEstimator(),
        guard=CostGuard(ledger=InMemoryLedgerRepository(), policy=BudgetPolicy()),
    )


def _brief(**kw) -> Brief:
    base = dict(customer="客户A", subscene=SubScene.S1, family=TemplateFamily.F3,
                tier=Tier.STANDARD, style=Style.NORDIC, category=Category.BEAUTY,
                size=(1500, 2000), n=6)
    base.update(kw)
    return Brief(**base)  # type: ignore[arg-type]


async def test_pipeline_end_to_end_six_candidates():
    pipe = _pipeline(_registry())
    result = await pipe.run(_brief(), user_id="u1")
    assert len(result.images) == 6
    assert result.used_model is ModelName.SEEDREAM_5
    assert result.total_cost == Decimal("1.20")
    assert "极简主义" in result.job_prompt.positive


async def test_pipeline_fallbacks_when_primary_fails():
    pipe = _pipeline(_registry(primary_fail=True))
    result = await pipe.run(_brief(), user_id="u1")
    assert result.used_model is ModelName.QWEN_IMAGE_PRO  # 切同档位备选


async def test_pipeline_rejects_over_candidate_cap():
    pipe = _pipeline(_registry())
    with pytest.raises(ValueError, match="硬上限"):
        await pipe.run(_brief(n=13), user_id="u1")


async def test_pipeline_rolls_back_budget_when_all_providers_fail():
    reg = ProviderRegistry()
    reg.register(MockModelProvider(name=ModelName.SEEDREAM_5, unit_cost=Decimal("0.20"), fail=True))
    reg.register(MockModelProvider(name=ModelName.QWEN_IMAGE_PRO, unit_cost=Decimal("0.10"), fail=True))
    ledger = InMemoryLedgerRepository()
    pipe = GenerationPipeline(
        router=ModelRouter(), orchestrator=_orchestrator(), registry=reg,
        estimator=CostEstimator(), guard=CostGuard(ledger=ledger, policy=BudgetPolicy()),
    )
    from design_hub.providers.errors import ProviderError
    with pytest.raises(ProviderError):
        await pipe.run(_brief(), user_id="u1")
    snap = await ledger.snapshot("u1")
    assert snap.user_month_used == Decimal("0")  # 预扣已回滚
```

- [ ] **Step 2: 运行确认失败**

Run: `cd image-code && uv run pytest tests/pipeline/test_pipeline.py -v`
Expected: FAIL（import error）。

- [ ] **Step 3: 实现 Pipeline**

`image-code/src/design_hub/pipeline/pipeline.py`:

```python
from dataclasses import dataclass
from decimal import Decimal

from ..cost.estimator import CostEstimator
from ..cost.guard import CostGuard
from ..domain.dto import Brief, GeneratedImage, GenerationResult, PromptPair, RoutingDecision
from ..domain.enums import ModelName
from ..prompt.orchestrator import PromptOrchestrator
from ..providers.errors import ProviderError
from ..providers.registry import ProviderRegistry
from ..routing.router import ModelRouter
from ..routing.table import MAX_CANDIDATES


@dataclass
class GenerationPipeline:
    router: ModelRouter
    orchestrator: PromptOrchestrator
    registry: ProviderRegistry
    estimator: CostEstimator
    guard: CostGuard

    async def run(self, brief: Brief, user_id: str) -> GenerationResult:
        if brief.n > MAX_CANDIDATES:
            raise ValueError(f"候选数 {brief.n} 超过硬上限 {MAX_CANDIDATES}")

        routed = self.router.route(brief.family, brief.subscene, brief.tier)
        decision = RoutingDecision(routed.primary, routed.fallbacks, brief.n)
        prompt = await self.orchestrator.build(brief, decision.primary)
        estimate = self.estimator.estimate(decision, self.registry.get(decision.primary))

        await self.guard.precheck_and_reserve(user_id, estimate)
        try:
            used_model, images = await self._generate_with_fallback(brief, prompt, decision)
        except Exception:
            await self.guard.rollback(user_id, estimate)
            raise

        total = sum((img.cost for img in images), Decimal("0"))
        return GenerationResult(
            job_prompt=prompt, decision=decision, used_model=used_model,
            images=tuple(images), total_cost=total,
        )

    async def _generate_with_fallback(
        self, brief: Brief, prompt: PromptPair, decision: RoutingDecision,
    ) -> tuple[ModelName, list[GeneratedImage]]:
        last_error: ProviderError | None = None
        for model in (decision.primary, *decision.fallbacks):
            provider = self.registry.get(model)
            try:
                images = await provider.generate(
                    prompt=prompt.positive,
                    negative_prompt=prompt.negative,
                    reference_images=list(brief.reference_images),
                    size=brief.size,
                    n=decision.candidate_count,
                )
                return model, images
            except ProviderError as error:  # 网络/IO 域：允许切同档位备选
                last_error = error
        raise last_error if last_error else ProviderError("no provider available")
```

Create empty `image-code/src/design_hub/pipeline/__init__.py`.

- [ ] **Step 4: 运行确认通过**

Run: `cd image-code && uv run pytest tests/pipeline/test_pipeline.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: 提交**

```bash
git add image-code/src/design_hub/pipeline image-code/tests/pipeline
git commit -m "feat: GenerationPipeline 引擎脊柱组装(DIP 集大成)

注入 router/orchestrator/registry/estimator/guard，编排
route→prompt→estimate→预扣→生成(同档位 fallback)→回滚。
候选数超 12 拒绝；全失败回滚预扣并 re-raise。"
```

---

## Task 20: 全量回归 + lint + 类型检查 + CI

**Files:**
- Create: `image-code/tests/test_integration.py`
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: 写端到端集成测试（J2）**

`image-code/tests/test_integration.py`:

```python
from decimal import Decimal

from design_hub.cost.budget import BudgetPolicy
from design_hub.cost.estimator import CostEstimator
from design_hub.cost.guard import CostGuard
from design_hub.cost.ledger import InMemoryLedgerRepository
from design_hub.domain.dto import Brief
from design_hub.domain.enums import Category, ModelName, Style, SubScene, TemplateFamily, Tier
from design_hub.pipeline.pipeline import GenerationPipeline
from design_hub.prompt.brand import BrandNameGenerator
from design_hub.prompt.families.registry import FamilyRegistry
from design_hub.prompt.libraries.color import ColorLibrary
from design_hub.prompt.libraries.guard import GuardLibrary
from design_hub.prompt.libraries.negative import NegativeLibrary
from design_hub.prompt.libraries.quality import QualityLibrary
from design_hub.prompt.orchestrator import PromptOrchestrator
from design_hub.prompt.vision import MockVisionAssist
from design_hub.providers.mock import MockModelProvider
from design_hub.providers.registry import ProviderRegistry
from design_hub.routing.router import ModelRouter


async def test_festive_project_runs_through_engine():
    reg = ProviderRegistry()
    reg.register(MockModelProvider(name=ModelName.QWEN_IMAGE_PRO, unit_cost=Decimal("0.10")))
    reg.register(MockModelProvider(name=ModelName.SEEDREAM_5, unit_cost=Decimal("0.20")))
    pipe = GenerationPipeline(
        router=ModelRouter(),
        orchestrator=PromptOrchestrator(
            families=FamilyRegistry(), colors=ColorLibrary(), negatives=NegativeLibrary(),
            guards=GuardLibrary(), qualities=QualityLibrary(), vision=MockVisionAssist(),
            brands=BrandNameGenerator(),
        ),
        registry=reg, estimator=CostEstimator(),
        guard=CostGuard(ledger=InMemoryLedgerRepository(), policy=BudgetPolicy()),
    )
    brief = Brief(
        customer="客户A", subscene=SubScene.S1, family=TemplateFamily.F7,
        tier=Tier.STANDARD, style=Style.GUOCHAO, category=Category.FOOD,
        size=(1500, 2000), n=6, copy_text="年货大促",
    )
    result = await pipe.run(brief, user_id="designer-1")
    assert result.used_model is ModelName.QWEN_IMAGE_PRO  # 族7→千问
    assert len(result.images) == 6
    assert result.total_cost == Decimal("0.60")
    assert "不要俗气红" in result.job_prompt.negative
```

- [ ] **Step 2: 运行全量测试**

Run: `cd image-code && uv run pytest -v`
Expected: 全部 PASS。

- [ ] **Step 3: lint 与类型检查**

Run: `cd image-code && uv run ruff check src tests && uv run mypy src`
Expected: ruff 无错误；mypy 无错误（如有，按提示修正后重跑）。

- [ ] **Step 4: 写 CI 工作流**

`.github/workflows/ci.yml`:

```yaml
name: ci
on:
  push:
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: image-code
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v5
      - run: uv python install 3.12
      - run: uv sync --dev
      - run: uv run ruff check src tests
      - run: uv run mypy src
      - run: uv run pytest -v
```

- [ ] **Step 5: 提交**

```bash
git add image-code/tests/test_integration.py .github/workflows/ci.yml
git commit -m "test: 端到端集成测试 + CI 流水线(零真实 API)

MockProvider 跑通节庆项目全链路验证脊柱组装；CI 跑
ruff+mypy+pytest，全程零模型调用不产生费用(PRD §6.5)。"
```

---

## Self-Review（规格覆盖核对）

| 功能点(FP) | 对应任务 | 覆盖 |
|---|---|---|
| A1 项目骨架 | Task 1 | ✅ |
| A2 配置密钥 / A3 日志异常 | Task 2 | ✅ |
| B1 枚举 / B2 DTO | Task 3 / Task 4 | ✅ |
| C1 抽象 / C4 异常 | Task 5 | ✅ |
| C2 Mock | Task 6 | ✅ |
| C3 注册表 | Task 7 | ✅ |
| D1 表 / D2 Router / D3 fallback | Task 8 | ✅ |
| E1 5 词库 | Task 9 + Task 10 | ✅ |
| E2 模板族(基类+4族+注册表) | Task 11 + Task 12 | ✅ |
| E4 视觉 / E5 品牌名 | Task 13 | ✅ |
| E3 法则 | Task 14 | ✅ |
| E6 编排器 | Task 15 | ✅ |
| F1 估算 / F2 预算 | Task 16 | ✅ |
| F3 Ledger | Task 17 | ✅ |
| F4 守门+装饰器 | Task 18 | ✅ |
| G1 pipeline / G4 多候选 | Task 19 | ✅ |
| J2 集成 / J3 CI | Task 20 | ✅ |

**类型一致性核对**：`Brief`/`RoutingDecision`/`GeneratedImage`/`PromptPair`/`GenerationResult` 字段在 Task 4 定义，Task 8/15/19 引用一致；`AbstractModelProvider.generate` 关键字参数签名（Task 5）与 Mock（Task 6）、pipeline 调用（Task 19）一致；`CostGuard.precheck_and_reserve` / `rollback`（Task 18）与 pipeline 调用（Task 19）一致；`ModelRouter.route(family, subscene, tier)`（Task 8）与 pipeline 调用（Task 19）一致。

**未覆盖（按设计推迟到后续里程碑，非遗漏）**：F5 成本预估提示 API（属 API 层，M2 随 FastAPI 接入）；A1 中的 FastAPI/SQLAlchemy 脚手架（M2）；C5 真实 Provider（M3）；I 两阶段合成（M4）。

---

## 执行交接

计划已落盘 `docs/superpowers/plans/2026-05-28-m1-engine-spine.md`。两种执行方式：

1. **Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，任务间双段评审，迭代快
2. **Inline Execution** — 本会话内按 executing-plans 批量执行，带检查点

选哪种？
