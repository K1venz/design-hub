# 电商 Listing 一键出图（轻量链路）后端实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: 用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐条实现。步骤用 `- [ ]` 复选框追踪。

**Goal:** 后端新增一条 `POST /listing/generate` 轻量图生图链路——multipart 直传 ≤3 图 + 用户自由 prompt + 下拉(modifiers) + 比例 + 张数 → gpt-image-2 直接 edit 出 N 张候选，异步 + SSE 进度。

**Architecture:** 复用现有基础设施（Provider / CostGuard / ImageStore / 单进程异步队列 / InMemoryEventBus），**不复用**重编排（PromptOrchestrator / ModelRouter / project / asset 库）。先把异步层泛化为「命令模式」（海报流适配为 `PosterGenerationCommand`），再在其上加 listing 命令。prompt 服务端组装（自由文本 + 下拉话术片段），ratio→size，出图历史经端口留口子（MVP NoOp）。

**Tech Stack:** Python 3.12 / uv / FastAPI / SQLAlchemy async / httpx / 六边形架构。

**质量门（本项目现状）:** 无 pytest / 无测试套件；门为 `uv run ruff check src` + `uv run mypy`（strict, 173 文件）+ 每任务一个可运行的 in-process 冒烟脚本（`uv run python -c ...`）。**正式测试用例归 QA**（Dev 角色不写测试），见 Phase 5 派单。

**设计依据:** `docs/superpowers/specs/2026-06-04-listing-image-generation-design.md`

**提交纪律:** 每任务完成即提交；**显式 `git add <具体路径>`，禁止 `git add -A`**（并行 agent 共写同一工作树，参 ISSUE-0004）；commit 格式 `type: 中文描述` + 详述 body，无 co-author。

---

## 文件结构（决策锁定）

**新增：**
- `src/design_hub/application/commands.py` — `PosterGenerationCommand`（原 task_runner 逻辑搬入，brief/user_id 入构造）
- `src/design_hub/application/listing/__init__.py`
- `src/design_hub/application/listing/prompt_composer.py` — `PromptModifierRegistry` + `compose_prompt`
- `src/design_hub/application/listing/sizing.py` — `ratio_to_size`
- `src/design_hub/application/listing/listing_service.py` — `ListingGenerationService`
- `src/design_hub/application/listing/commands.py` — `ListingGenerationCommand`
- `src/design_hub/ports/listing_history.py` — `ListingHistory` 端口
- `src/design_hub/infrastructure/listing/__init__.py`
- `src/design_hub/infrastructure/listing/noop_history.py` — `NoOpListingHistory`
- `src/design_hub/interface/api/routes/listing.py` — 路由

**改动：**
- `src/design_hub/ports/task_queue.py` — 加 `GenerationCommand` ABC，`enqueue` 改收命令
- `src/design_hub/infrastructure/queue/in_process.py` — 队列只调度命令
- `src/design_hub/application/task_runner.py` — **删除**（逻辑迁入 commands.py）
- `src/design_hub/domain/models.py` — 加 `ListingResult`
- `src/design_hub/infrastructure/providers/openai_compat.py` — `_edit` 支持多图
- `src/design_hub/interface/api/routes/async_generation.py` — 入队改建命令
- `src/design_hub/interface/api/asgi.py` — 队列改造 + 装配 listing + 挂路由

---

## Phase 0 — 异步层泛化为命令模式（先稳住海报流）

### Task 0.1：定义 `GenerationCommand` 端口 + 改 `TaskQueue.enqueue`

**Files:**
- Modify: `src/design_hub/ports/task_queue.py`（整文件替换）

- [ ] **Step 1: 替换文件内容**

```python
from abc import ABC, abstractmethod


class GenerationCommand(ABC):
    """一次异步出图任务的自包含执行单元（命令模式）。

    每个命令自己负责：发布进度事件、生成、持久化。队列只调度，不认识具体流程。
    """

    @abstractmethod
    async def run(self, job_id: str) -> None:
        ...


class TaskQueue(ABC):
    """出图任务入队端口（DIP）；单进程实现 InProcessTaskQueue，多副本可换分布式适配器。"""

    @abstractmethod
    async def enqueue(self, *, job_id: str, command: GenerationCommand) -> None:
        ...
```

- [ ] **Step 2: 校验（此步会暂时打断引用方，预期 mypy 报 in_process/async_generation 不匹配，下一任务修复）**

Run: `uv run ruff check src/design_hub/ports/task_queue.py`
Expected: PASS（本文件本身干净）

- [ ] **Step 3: 提交**

```bash
git add src/design_hub/ports/task_queue.py
git commit -m "refactor(queue): TaskQueue 端口泛化为命令模式

新增 GenerationCommand 抽象（自包含 run(job_id)，自管事件/生成/持久化），
enqueue 改收命令而非 brief。为 listing 与海报流共用同一异步队列铺路。
引用方在后续任务同步适配。"
```

### Task 0.2：`InProcessTaskQueue` 改为只调度命令

**Files:**
- Modify: `src/design_hub/infrastructure/queue/in_process.py`（整文件替换）

- [ ] **Step 1: 替换文件内容**

```python
"""TaskQueue 的单进程内存实现（去 Redis/arq）。

enqueue 即在 API 进程内用 asyncio.create_task 后台运行命令；命令自己经
InMemoryEventBus 发布进度，/events 订阅同一实例。单实例部署；多副本换分布式适配器。
"""

import asyncio

from design_hub.ports.task_queue import GenerationCommand, TaskQueue


class InProcessTaskQueue(TaskQueue):
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()  # 持有引用防后台任务被 GC

    async def enqueue(self, *, job_id: str, command: GenerationCommand) -> None:
        task = asyncio.create_task(command.run(job_id))
        self._tasks.add(task)
        task.add_done_callback(self._on_done)

    def _on_done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        # 取出异常防 asyncio "Task exception never retrieved"（命令已发布 task_failed）
        if not task.cancelled():
            task.exception()
```

- [ ] **Step 2: 校验**

Run: `uv run ruff check src/design_hub/infrastructure/queue/in_process.py`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add src/design_hub/infrastructure/queue/in_process.py
git commit -m "refactor(queue): InProcessTaskQueue 改为调度 GenerationCommand

队列不再持有 runner、不再认识 Brief；enqueue 后台跑 command.run(job_id)。"
```

### Task 0.3：海报流迁移为 `PosterGenerationCommand`，删除 task_runner

**Files:**
- Create: `src/design_hub/application/commands.py`
- Delete: `src/design_hub/application/task_runner.py`

- [ ] **Step 1: 新建 commands.py**

```python
from dataclasses import dataclass

from design_hub.application.pipeline import GenerationPipeline
from design_hub.domain.enums import TaskEventType
from design_hub.domain.models import Brief, TaskEvent
from design_hub.ports.events import EventPublisher
from design_hub.ports.job_repository import JobRepository
from design_hub.ports.task_queue import GenerationCommand


@dataclass
class PosterGenerationCommand(GenerationCommand):
    """海报流异步命令：跑 pipeline → 落库 → 沿途发进度事件（原 GenerationTaskRunner 逻辑）。

    brief/user_id 在构造时绑定，满足 GenerationCommand.run(job_id) 统一签名。
    """

    pipeline: GenerationPipeline
    jobs: JobRepository
    events: EventPublisher
    brief: Brief
    user_id: str

    async def run(self, job_id: str) -> None:
        await self.events.publish(TaskEvent(job_id, TaskEventType.TASK_STARTED, {}))
        try:
            result = await self.pipeline.run(self.brief, self.user_id)
            await self.events.publish(
                TaskEvent(job_id, TaskEventType.MODEL_CALLED, {"model": result.used_model.value})
            )
            for image in result.images:
                await self.events.publish(
                    TaskEvent(
                        job_id,
                        TaskEventType.IMAGE_GENERATED,
                        {"url": image.url, "seed": image.seed},
                    )
                )
            await self.jobs.save_completed(
                job_id=job_id, user_id=self.user_id, brief=self.brief, result=result
            )
            await self.events.publish(
                TaskEvent(
                    job_id, TaskEventType.TASK_COMPLETED, {"total_cost": str(result.total_cost)}
                )
            )
        except Exception as exc:
            await self.events.publish(
                TaskEvent(job_id, TaskEventType.TASK_FAILED, {"error": str(exc)})
            )
            raise
```

- [ ] **Step 2: 删除旧文件**

Run: `git rm src/design_hub/application/task_runner.py`
（asgi.py 对它的 import 在 Task 0.4 修复）

- [ ] **Step 3: 校验本文件**

Run: `uv run ruff check src/design_hub/application/commands.py`
Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add src/design_hub/application/commands.py src/design_hub/application/task_runner.py
git commit -m "refactor(async): GenerationTaskRunner 迁为 PosterGenerationCommand

海报异步逻辑（事件→pipeline→落库→事件）原样搬入命令，brief/user_id 入构造，
适配命令模式队列。删除 task_runner.py。"
```

### Task 0.4：`async_generation` 路由建命令入队 + asgi 装配适配

**Files:**
- Modify: `src/design_hub/interface/api/routes/async_generation.py:39-49`（`enqueue` 函数）
- Modify: `src/design_hub/interface/api/asgi.py`（队列/runner 装配段 + import）

- [ ] **Step 1: 改 async_generation 的 enqueue 函数**

把现有 `enqueue` 函数体替换为（新增 import：顶部加 `from design_hub.application.commands import PosterGenerationCommand`）：

```python
@router.post("/async")
async def enqueue(
    req: GenerateRequest,
    request: Request,
    queue: QueueDep,
    _user: CurrentUserDep,  # 需 Bearer（鉴权改逐路由挂，见 asgi）
    user_id: UserIdDep = "designer-anon",
) -> dict[str, str]:
    """入队即返回 job_id；进度经 SSE 查询。"""
    job_id = uuid.uuid4().hex
    command = PosterGenerationCommand(
        pipeline=request.app.state.engine.pipeline,
        jobs=request.app.state.job_repository,
        events=request.app.state.event_stream,
        brief=req.to_brief(),
        user_id=user_id,
    )
    await queue.enqueue(job_id=job_id, command=command)
    return {"job_id": job_id}
```

（`Request` 已在该文件 import；确认顶部 `from fastapi import APIRouter, Depends, Header, Request` 含 Request——已含。）

- [ ] **Step 2: 改 asgi.py 装配**

(a) import 段：删除 `from design_hub.application.task_runner import GenerationTaskRunner`。

(b) 把 lifespan 内这段（约 111-121 行）：

```python
    event_bus = InMemoryEventBus()
    runner = GenerationTaskRunner(
        pipeline=pipeline,
        jobs=SqlAlchemyJobRepository(session_factory),
        events=event_bus,
    )

    app.state.engine = Engine(pipeline=pipeline, preview=preview)
    app.state.task_queue = InProcessTaskQueue(runner)
    app.state.event_stream = event_bus
```

替换为：

```python
    event_bus = InMemoryEventBus()
    app.state.engine = Engine(pipeline=pipeline, preview=preview)
    app.state.job_repository = SqlAlchemyJobRepository(session_factory)
    app.state.task_queue = InProcessTaskQueue()
    app.state.event_stream = event_bus
```

（`SqlAlchemyJobRepository` 已 import；`project_generation_service` 段里另建的 `SqlAlchemyJobRepository(session_factory)` 保持不动，互不影响。）

- [ ] **Step 3: 校验全量（Phase 0 收口，应全绿）**

Run: `uv run ruff check src && uv run mypy`
Expected: ruff All checks passed；mypy Success（文件数随新增略增）

- [ ] **Step 4: 冒烟——海报异步命令端到端（Mock 引擎，无需 DB）**

新建临时脚本运行后删除（不提交）：
Run:
```bash
uv run python -c "
import asyncio
from design_hub.composition import build_engine
from design_hub.infrastructure.events.memory import InMemoryEventBus
from design_hub.infrastructure.queue.in_process import InProcessTaskQueue
from design_hub.application.commands import PosterGenerationCommand
from design_hub.domain.enums import TaskEventType
from design_hub.domain.models import Brief
from design_hub.domain.enums import SubScene, TemplateFamily, Tier, Style, Category

class FakeJobs:
    saved = []
    async def save_completed(self, **kw): FakeJobs.saved.append(kw)

async def main():
    eng = build_engine()  # 全 Mock
    bus = InMemoryEventBus()
    q = InProcessTaskQueue()
    brief = Brief(customer='c', subscene=SubScene.S1, family=TemplateFamily.FAMILY_4,
                  tier=Tier.STANDARD, style=Style.FRESH, category=Category.FOOD, size=(1024,1024), n=2)
    cmd = PosterGenerationCommand(pipeline=eng.pipeline, jobs=FakeJobs(), events=bus, brief=brief, user_id='u1')
    await q.enqueue(job_id='job1', command=cmd)
    seen=[]
    async for e in bus.subscribe('job1'):
        seen.append(e.type)
        if e.type in (TaskEventType.TASK_COMPLETED, TaskEventType.TASK_FAILED): break
    assert TaskEventType.TASK_STARTED in seen, seen
    assert TaskEventType.TASK_COMPLETED in seen, seen
    assert FakeJobs.saved, 'save_completed 未被调用'
    print('POSTER ASYNC SMOKE OK', [t.value for t in seen])

asyncio.run(main())
"
```
Expected: 打印 `POSTER ASYNC SMOKE OK [...task_started...task_completed]`
> 注：`SubScene/TemplateFamily/Tier/Style/Category` 的真实枚举成员名以 `src/design_hub/domain/enums.py` 为准，冒烟脚本里取任一合法成员即可（若成员名不同，按文件改）。

- [ ] **Step 5: 提交**

```bash
git add src/design_hub/interface/api/routes/async_generation.py src/design_hub/interface/api/asgi.py
git commit -m "refactor(async): 海报异步入队改建 PosterGenerationCommand

async_generation 路由按命令入队；asgi 队列改 InProcessTaskQueue() 无 runner、
设 app.state.job_repository 供路由建命令。Mock 引擎冒烟海报异步全序列通过。"
```

---

## Phase 1 — Provider 支持多图 edit

### Task 1.1：`openai_compat._edit` 发送 ≤3 张图

**Files:**
- Modify: `src/design_hub/infrastructure/providers/openai_compat.py`（`generate` 内 edit 调用、`_edit`、`_request_multipart` 三处）

- [ ] **Step 1: 改 generate 内的 edit 分支**

把（约 77-78 行）：
```python
                if reference_images:
                    response = await self._edit(composed, reference_images[0], size_str, n)
```
改为：
```python
                if reference_images:
                    response = await self._edit(composed, reference_images, size_str, n)
```

- [ ] **Step 2: 改 `_edit` 签名与实现**

把：
```python
    async def _edit(
        self, prompt: str, image: bytes, size: str, n: int
    ) -> httpx.Response:
        data = {"model": self._model, "prompt": prompt, "n": str(n), "size": size}
        files = {"image": ("product.png", image, "image/png")}
        return await self._request_multipart(f"{self._base_url}/images/edits", data, files)
```
改为：
```python
    async def _edit(
        self, prompt: str, images: list[bytes], size: str, n: int
    ) -> httpx.Response:
        # gpt-image edits 多图：同名重复字段 image[]（OpenAI gpt-image-1 协议）。
        # 中转站若不支持多图，ListingGenerationService 会在上层退化为逐图调用（见 spec §6.1 风险）。
        data = {"model": self._model, "prompt": prompt, "n": str(n), "size": size}
        files = [
            ("image[]", (f"product_{i}.png", img, "image/png")) for i, img in enumerate(images)
        ]
        return await self._request_multipart(f"{self._base_url}/images/edits", data, files)
```

- [ ] **Step 3: 改 `_request_multipart` 的 files 类型为 list**

把签名：
```python
    async def _request_multipart(
        self,
        url: str,
        data: dict[str, str],
        files: dict[str, tuple[str, bytes, str]],
    ) -> httpx.Response:
```
改为：
```python
    async def _request_multipart(
        self,
        url: str,
        data: dict[str, str],
        files: list[tuple[str, tuple[str, bytes, str]]],
    ) -> httpx.Response:
```
（函数体不变；httpx `post(files=...)` 同时接受 list-of-2tuple 形式。）

- [ ] **Step 4: 校验**

Run: `uv run ruff check src/design_hub/infrastructure/providers/openai_compat.py && uv run mypy`
Expected: 全绿

- [ ] **Step 5: 冒烟——多图 edit 真发出 image[] 多字段（注入假 httpx client，不打真网络）**

Run:
```bash
uv run python -c "
import asyncio
from decimal import Decimal
from design_hub.infrastructure.providers.openai_compat import OpenAICompatImageProvider
from design_hub.domain.enums import ModelName

class FakeResp:
    status_code=200
    def json(self): return {'data':[{'url':'http://x/a.png'}]}
    text=''
class FakeClient:
    def __init__(self): self.calls=[]
    async def post(self, url, **kw):
        self.calls.append((url, kw)); return FakeResp()

async def main():
    fc=FakeClient()
    p=OpenAICompatImageProvider(name=ModelName.GPT_IMAGE_2, unit_cost=Decimal('1'),
        base_url='http://api', api_key='k', model='gpt-image-2', client=fc)
    imgs=[b'a',b'b',b'c']
    out=await p.generate(prompt='hi', negative_prompt='', reference_images=imgs, size=(1024,1024), n=1)
    url, kw = fc.calls[0]
    assert url.endswith('/images/edits'), url
    files=kw['files']
    names=[f[0] for f in files]
    assert names==['image[]','image[]','image[]'], names
    assert len(out)==1
    print('MULTI-IMAGE EDIT SMOKE OK', names)

asyncio.run(main())
"
```
Expected: `MULTI-IMAGE EDIT SMOKE OK ['image[]', 'image[]', 'image[]']`

- [ ] **Step 6: 提交**

```bash
git add src/design_hub/infrastructure/providers/openai_compat.py
git commit -m "feat(provider): gpt-image edit 支持多张参考图

_edit 由写死 reference_images[0] 改为发送全部 ≤3 张为 image[] 多字段；
_request_multipart files 改 list 以支持同名重复字段。注入假 client 冒烟通过。"
```

---

## Phase 2 — 轻量组件（组装/尺寸/历史口子/结果类型）

### Task 2.1：`ListingResult` 领域类型

**Files:**
- Modify: `src/design_hub/domain/models.py`（在 `GenerationResult` 之后追加）

- [ ] **Step 1: 追加类型**

在 `GenerationResult` 定义块之后插入：
```python
@dataclass(frozen=True)
class ListingResult:
    """listing 轻量出图结果（不含路由/编排，区别于 GenerationResult）。"""

    prompt: str
    used_model: ModelName
    images: tuple[GeneratedImage, ...]
    total_cost: Decimal
```
（确认文件顶部已 import `Decimal`、`ModelName`、`GeneratedImage`——`GenerationResult` 已用到它们，故已 import。）

- [ ] **Step 2: 校验 + 提交**

Run: `uv run ruff check src/design_hub/domain/models.py && uv run mypy`
Expected: 全绿
```bash
git add src/design_hub/domain/models.py
git commit -m "feat(domain): 新增 ListingResult 轻量出图结果类型"
```

### Task 2.2：`PromptModifierRegistry` + `compose_prompt`

**Files:**
- Create: `src/design_hub/application/listing/__init__.py`（空文件）
- Create: `src/design_hub/application/listing/prompt_composer.py`

- [ ] **Step 1: 建空 __init__.py**

Run: `: > src/design_hub/application/listing/__init__.py`

- [ ] **Step 2: 写 prompt_composer.py**

```python
from dataclasses import dataclass, field

from design_hub.domain.errors import DomainError

# 种子片段表：(field, value) -> 注入 prompt 的中文话术。正式文案由 image-prompt 出（ISSUE-0022）。
_SEED_FRAGMENTS: dict[tuple[str, str], str] = {
    ("platform", "亚马逊"): "用于亚马逊电商平台的商品展示图",
    ("platform", "淘宝"): "用于淘宝电商平台的商品展示图",
    ("platform", "TikTok"): "用于 TikTok 电商的商品展示图",
    ("platform", "独立站"): "用于品牌独立站的商品展示图",
    ("region", "美国"): "商品面向美国市场",
    ("region", "中国"): "商品面向中国市场",
    ("language", "英文"): "广告文字使用英文",
    ("language", "中文"): "广告文字使用中文",
}


@dataclass
class PromptModifierRegistry:
    """下拉值 → prompt 话术片段（可版本化、可测）。未知值 fail-fast。"""

    fragments: dict[tuple[str, str], str] = field(
        default_factory=lambda: dict(_SEED_FRAGMENTS)
    )

    def fragment(self, field_name: str, value: str) -> str:
        try:
            return self.fragments[(field_name, value)]
        except KeyError:
            raise DomainError(
                f"未知下拉值：{field_name}={value}（未在话术表登记）"
            ) from None


def compose_prompt(
    prompt: str, modifiers: dict[str, str], registry: PromptModifierRegistry
) -> str:
    """最终 prompt = 用户自由文本 + 各 modifier 片段拼接（用户文本为主体）。"""
    base = prompt.strip()
    if not base:
        raise DomainError("prompt 不能为空")
    fragments = [registry.fragment(k, v) for k, v in modifiers.items()]
    if not fragments:
        return base
    return base + "。" + "；".join(fragments)
```
（确认 `design_hub.domain.errors.DomainError` 存在——app.py 已 import 它，存在。）

- [ ] **Step 3: 校验**

Run: `uv run ruff check src/design_hub/application/listing/ && uv run mypy`
Expected: 全绿

- [ ] **Step 4: 冒烟——已知值拼接 / 未知值报错 / 空 prompt 报错**

Run:
```bash
uv run python -c "
from design_hub.application.listing.prompt_composer import PromptModifierRegistry, compose_prompt
from design_hub.domain.errors import DomainError
r=PromptModifierRegistry()
out=compose_prompt('花生礼盒，突出酥脆', {'platform':'亚马逊','language':'英文'}, r)
assert '花生礼盒' in out and '亚马逊' in out and '英文' in out, out
try:
    compose_prompt('x', {'platform':'未知平台'}, r); raise SystemExit('未报错!')
except DomainError: pass
try:
    compose_prompt('   ', {}, r); raise SystemExit('空 prompt 未报错!')
except DomainError: pass
print('COMPOSER SMOKE OK ::', out)
"
```
Expected: `COMPOSER SMOKE OK :: 花生礼盒，突出酥脆。用于亚马逊电商平台的商品展示图；广告文字使用英文`

- [ ] **Step 5: 提交**

```bash
git add src/design_hub/application/listing/__init__.py src/design_hub/application/listing/prompt_composer.py
git commit -m "feat(listing): prompt 组装器（下拉话术片段表 + compose，未知值 fail-fast）

服务端组装最终 prompt=用户自由文本+片段拼接；种子片段表待 image-prompt 出正式文案
（ISSUE-0022）。空 prompt/未知下拉值均 fail-fast。冒烟通过。"
```

### Task 2.3：`ratio_to_size`

**Files:**
- Create: `src/design_hub/application/listing/sizing.py`

- [ ] **Step 1: 写 sizing.py**

```python
from design_hub.domain.errors import DomainError

# gpt-image-2 仅支持三种尺寸；非方形比例归并到最接近的竖/横版。最终支持范围由 PM 定（ISSUE-0021）。
_RATIO_TO_SIZE: dict[str, tuple[int, int]] = {
    "1:1": (1024, 1024),
    "3:4": (1024, 1536),
    "9:16": (1024, 1536),
    "4:3": (1536, 1024),
    "16:9": (1536, 1024),
}


def ratio_to_size(ratio: str) -> tuple[int, int]:
    try:
        return _RATIO_TO_SIZE[ratio]
    except KeyError:
        raise DomainError(f"不支持的比例：{ratio}") from None
```

- [ ] **Step 2: 校验 + 冒烟**

Run:
```bash
uv run ruff check src/design_hub/application/listing/sizing.py && uv run mypy && \
uv run python -c "
from design_hub.application.listing.sizing import ratio_to_size
from design_hub.domain.errors import DomainError
assert ratio_to_size('1:1')==(1024,1024)
assert ratio_to_size('16:9')==(1536,1024)
try: ratio_to_size('5:7'); raise SystemExit('未报错')
except DomainError: pass
print('SIZING SMOKE OK')
"
```
Expected: 全绿 + `SIZING SMOKE OK`

- [ ] **Step 3: 提交**

```bash
git add src/design_hub/application/listing/sizing.py
git commit -m "feat(listing): ratio→size 映射（gpt-image-2 三尺寸，未知比例 fail-fast）"
```

### Task 2.4：`ListingHistory` 端口 + `NoOpListingHistory`

**Files:**
- Create: `src/design_hub/ports/listing_history.py`
- Create: `src/design_hub/infrastructure/listing/__init__.py`（空）
- Create: `src/design_hub/infrastructure/listing/noop_history.py`

- [ ] **Step 1: 写端口**

`src/design_hub/ports/listing_history.py`：
```python
from abc import ABC, abstractmethod

from design_hub.domain.models import ListingResult


class ListingHistory(ABC):
    """listing 出图历史持久化端口（架构口子）。MVP 绑 NoOp 不存；将来换 DB 实现，业务零改动。"""

    @abstractmethod
    async def record(self, *, user_id: str, result: ListingResult) -> None:
        ...
```

- [ ] **Step 2: 写 NoOp 实现**

Run: `: > src/design_hub/infrastructure/listing/__init__.py`

`src/design_hub/infrastructure/listing/noop_history.py`：
```python
from design_hub.domain.models import ListingResult
from design_hub.ports.listing_history import ListingHistory


class NoOpListingHistory(ListingHistory):
    """MVP：不持久化 listing 历史（服务器空间充足后换 DB 实现，业务零改动）。"""

    async def record(self, *, user_id: str, result: ListingResult) -> None:
        return None
```

- [ ] **Step 3: 校验 + 提交**

Run: `uv run ruff check src/design_hub/ports/listing_history.py src/design_hub/infrastructure/listing/ && uv run mypy`
Expected: 全绿
```bash
git add src/design_hub/ports/listing_history.py src/design_hub/infrastructure/listing/__init__.py src/design_hub/infrastructure/listing/noop_history.py
git commit -m "feat(listing): 出图历史端口 + NoOp 实现（MVP 不存，留 DB 口子）"
```

---

## Phase 3 — ListingGenerationService + 命令

### Task 3.1：`ListingGenerationService`

**Files:**
- Create: `src/design_hub/application/listing/listing_service.py`

- [ ] **Step 1: 写 service**

```python
from dataclasses import dataclass
from decimal import Decimal

from design_hub.application.cost.guard import CostGuard
from design_hub.application.listing.prompt_composer import (
    PromptModifierRegistry,
    compose_prompt,
)
from design_hub.application.listing.sizing import ratio_to_size
from design_hub.application.registry import ProviderRegistry
from design_hub.domain.enums import ModelName
from design_hub.domain.errors import DomainError
from design_hub.domain.models import ListingResult

_MAX_IMAGES = 3
_MAX_N = 7


@dataclass
class ListingGenerationService:
    """listing 轻量出图用例：组装 prompt → 守门预扣 → gpt-image-2 直 edit → 回正。

    不走 PromptOrchestrator/ModelRouter（纯 prompt 直出，live edit 仅 gpt-image-2）。
    """

    registry: ProviderRegistry
    guard: CostGuard
    modifiers: PromptModifierRegistry

    async def generate(
        self,
        *,
        prompt: str,
        modifiers: dict[str, str],
        images: tuple[bytes, ...],
        ratio: str,
        n: int,
        user_id: str,
    ) -> ListingResult:
        if not 1 <= len(images) <= _MAX_IMAGES:
            raise DomainError(f"参考图数量需为 1..{_MAX_IMAGES}，实际 {len(images)}")
        if not 1 <= n <= _MAX_N:
            raise DomainError(f"张数需为 1..{_MAX_N}，实际 {n}")
        final_prompt = compose_prompt(prompt, modifiers, self.modifiers)
        size = ratio_to_size(ratio)
        provider = self.registry.get(ModelName.GPT_IMAGE_2)
        estimate = provider.unit_cost * n
        await self.guard.precheck_and_reserve(user_id, estimate)
        try:
            generated = await provider.generate(
                prompt=final_prompt,
                negative_prompt="",
                reference_images=list(images),
                size=size,
                n=n,
            )
        except Exception:
            await self.guard.rollback(user_id, estimate)
            raise
        total = sum((img.cost for img in generated), Decimal("0"))
        await self.guard.reconcile(user_id, reserved=estimate, actual=total)
        return ListingResult(
            prompt=final_prompt,
            used_model=ModelName.GPT_IMAGE_2,
            images=tuple(generated),
            total_cost=total,
        )
```
（确认 `ProviderRegistry.get(name)`、`CostGuard.precheck_and_reserve/rollback/reconcile`、`provider.unit_cost`、`provider.generate(...)` 签名——均见现有 pipeline.py / guard.py / model_provider.py，一致。）

- [ ] **Step 2: 校验**

Run: `uv run ruff check src/design_hub/application/listing/listing_service.py && uv run mypy`
Expected: 全绿

- [ ] **Step 3: 冒烟——Mock provider 全链路 + 预扣回正 + 越界报错**

Run:
```bash
uv run python -c "
import asyncio
from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.application.listing.prompt_composer import PromptModifierRegistry
from design_hub.application.cost.guard import CostGuard
from design_hub.application.cost.budget import BudgetPolicy
from design_hub.composition import build_mock_registry
from design_hub.infrastructure.ledger.memory import InMemoryLedgerRepository
from design_hub.domain.errors import DomainError

async def main():
    reg=build_mock_registry()
    svc=ListingGenerationService(registry=reg,
        guard=CostGuard(ledger=InMemoryLedgerRepository(), policy=BudgetPolicy()),
        modifiers=PromptModifierRegistry())
    res=await svc.generate(prompt='花生礼盒', modifiers={'platform':'亚马逊'},
        images=(b'a',b'b'), ratio='1:1', n=3, user_id='u1')
    assert len(res.images)==3, res
    assert res.total_cost>0
    try:
        await svc.generate(prompt='x', modifiers={}, images=(b'a',), ratio='1:1', n=99, user_id='u1')
        raise SystemExit('n 越界未报错')
    except DomainError: pass
    print('LISTING SERVICE SMOKE OK', len(res.images), str(res.total_cost))

asyncio.run(main())
"
```
Expected: `LISTING SERVICE SMOKE OK 3 ...`
> 注：MockModelProvider 须能按 n 返回 n 张。若 Mock 仅返回 1 张，按其真实行为调整断言（不改 Mock）。

- [ ] **Step 4: 提交**

```bash
git add src/design_hub/application/listing/listing_service.py
git commit -m "feat(listing): ListingGenerationService（组装→守门→gpt-image-2直edit→回正）

绕过 PromptOrchestrator/ModelRouter；图数 1..3、张数 1..7 边界 fail-fast；
预扣失败回滚。Mock 全链路冒烟通过。"
```

### Task 3.2：`ListingGenerationCommand`

**Files:**
- Create: `src/design_hub/application/listing/commands.py`

- [ ] **Step 1: 写命令**

```python
from dataclasses import dataclass

from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.domain.enums import TaskEventType
from design_hub.domain.models import TaskEvent
from design_hub.ports.events import EventPublisher
from design_hub.ports.listing_history import ListingHistory
from design_hub.ports.task_queue import GenerationCommand


@dataclass
class ListingGenerationCommand(GenerationCommand):
    """listing 异步命令：service 出图 → 沿途发事件 → 历史口子（MVP NoOp）。"""

    service: ListingGenerationService
    events: EventPublisher
    history: ListingHistory
    user_id: str
    prompt: str
    modifiers: dict[str, str]
    images: tuple[bytes, ...]
    ratio: str
    n: int

    async def run(self, job_id: str) -> None:
        await self.events.publish(TaskEvent(job_id, TaskEventType.TASK_STARTED, {}))
        try:
            result = await self.service.generate(
                prompt=self.prompt,
                modifiers=self.modifiers,
                images=self.images,
                ratio=self.ratio,
                n=self.n,
                user_id=self.user_id,
            )
            await self.events.publish(
                TaskEvent(job_id, TaskEventType.MODEL_CALLED, {"model": result.used_model.value})
            )
            for image in result.images:
                await self.events.publish(
                    TaskEvent(
                        job_id,
                        TaskEventType.IMAGE_GENERATED,
                        {"url": image.url, "seed": image.seed},
                    )
                )
            await self.history.record(user_id=self.user_id, result=result)
            await self.events.publish(
                TaskEvent(
                    job_id, TaskEventType.TASK_COMPLETED, {"total_cost": str(result.total_cost)}
                )
            )
        except Exception as exc:
            await self.events.publish(
                TaskEvent(job_id, TaskEventType.TASK_FAILED, {"error": str(exc)})
            )
            raise
```

- [ ] **Step 2: 校验 + 冒烟（队列调度 listing 命令，复用 Phase 3.1 的 service）**

Run:
```bash
uv run ruff check src/design_hub/application/listing/commands.py && uv run mypy && \
uv run python -c "
import asyncio
from design_hub.application.listing.commands import ListingGenerationCommand
from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.application.listing.prompt_composer import PromptModifierRegistry
from design_hub.application.cost.guard import CostGuard
from design_hub.application.cost.budget import BudgetPolicy
from design_hub.composition import build_mock_registry
from design_hub.infrastructure.ledger.memory import InMemoryLedgerRepository
from design_hub.infrastructure.events.memory import InMemoryEventBus
from design_hub.infrastructure.queue.in_process import InProcessTaskQueue
from design_hub.infrastructure.listing.noop_history import NoOpListingHistory
from design_hub.domain.enums import TaskEventType

async def main():
    svc=ListingGenerationService(registry=build_mock_registry(),
        guard=CostGuard(ledger=InMemoryLedgerRepository(), policy=BudgetPolicy()),
        modifiers=PromptModifierRegistry())
    bus=InMemoryEventBus(); q=InProcessTaskQueue()
    cmd=ListingGenerationCommand(service=svc, events=bus, history=NoOpListingHistory(),
        user_id='u1', prompt='花生礼盒', modifiers={'platform':'亚马逊'},
        images=(b'a',), ratio='1:1', n=2)
    await q.enqueue(job_id='L1', command=cmd)
    seen=[]
    async for e in bus.subscribe('L1'):
        seen.append(e.type)
        if e.type in (TaskEventType.TASK_COMPLETED, TaskEventType.TASK_FAILED): break
    assert TaskEventType.TASK_COMPLETED in seen, seen
    print('LISTING COMMAND SMOKE OK', [t.value for t in seen])

asyncio.run(main())
"
```
Expected: `LISTING COMMAND SMOKE OK [...task_started...task_completed]`

- [ ] **Step 3: 提交**

```bash
git add src/design_hub/application/listing/commands.py
git commit -m "feat(listing): ListingGenerationCommand（异步命令：出图→事件→历史口子）

队列调度 listing 命令冒烟通过（task_started→...→task_completed）。"
```

---

## Phase 4 — 路由 + 装配 + 挂载

### Task 4.1：listing 路由

**Files:**
- Create: `src/design_hub/interface/api/routes/listing.py`

- [ ] **Step 1: 写路由**

```python
import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Form, Header, Request, UploadFile
from fastapi.responses import StreamingResponse

from design_hub.application.listing.commands import ListingGenerationCommand
from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.domain.errors import DomainError
from design_hub.domain.models import TaskEvent
from design_hub.interface.api.deps import CurrentUserDep, CurrentUserSseDep
from design_hub.ports.events import EventPublisher, EventStream
from design_hub.ports.listing_history import ListingHistory
from design_hub.ports.task_queue import TaskQueue

router = APIRouter(prefix="/listing", tags=["listing"])


def _sse(event: TaskEvent) -> str:
    return f"event: {event.type.value}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


@router.post("/generate")
async def generate_listing(
    request: Request,
    _user: CurrentUserDep,  # 需 Bearer
    images: list[UploadFile],
    prompt: Annotated[str, Form()],
    ratio: Annotated[str, Form()],
    n: Annotated[int, Form()],
    modifiers: Annotated[str, Form()] = "{}",
    user_id: Annotated[str, Header(alias="X-User-Id")] = "designer-anon",
) -> dict[str, str]:
    """listing 一键出图：multipart 直传 ≤3 图 + prompt + modifiers，异步返回 job_id。"""
    if not 1 <= len(images) <= 3:
        raise DomainError(f"图片数量需为 1..3，实际 {len(images)}")
    parsed = json.loads(modifiers)  # 非法 JSON → ValueError → 400
    if not isinstance(parsed, dict):
        raise DomainError("modifiers 必须是 JSON 对象")
    image_bytes = tuple([await f.read() for f in images])
    queue: TaskQueue = request.app.state.task_queue
    service: ListingGenerationService = request.app.state.listing_service
    history: ListingHistory = request.app.state.listing_history
    events: EventPublisher = request.app.state.event_stream
    job_id = uuid.uuid4().hex
    command = ListingGenerationCommand(
        service=service,
        events=events,
        history=history,
        user_id=user_id,
        prompt=prompt,
        modifiers={str(k): str(v) for k, v in parsed.items()},
        images=image_bytes,
        ratio=ratio,
        n=n,
    )
    await queue.enqueue(job_id=job_id, command=command)
    return {"job_id": job_id}


@router.get("/{job_id}/events")
async def listing_events(
    job_id: str, request: Request, _user: CurrentUserSseDep
) -> StreamingResponse:
    # SSE 鉴权经 ?access_token=（原生 EventSource 不能带头，ISSUE-0011）
    stream: EventStream = request.app.state.event_stream

    async def generator() -> AsyncIterator[str]:
        async for event in stream.subscribe(job_id):
            yield _sse(event)

    return StreamingResponse(generator(), media_type="text/event-stream")
```
（确认 `CurrentUserDep` / `CurrentUserSseDep` 在 `interface/api/deps.py` 导出——async_generation.py 已从该处 import 同名依赖，存在。）

- [ ] **Step 2: 校验**

Run: `uv run ruff check src/design_hub/interface/api/routes/listing.py && uv run mypy`
Expected: 全绿

- [ ] **Step 3: 提交**

```bash
git add src/design_hub/interface/api/routes/listing.py
git commit -m "feat(listing): /listing/generate(multipart) + /listing/{job_id}/events(SSE)

薄控制器：校验图数/解析 modifiers→建 ListingGenerationCommand 入队；
SSE 复用 InMemoryEventBus，鉴权沿用 Bearer + ?access_token(ISSUE-0011)。"
```

### Task 4.2：asgi 装配 listing + 挂路由

**Files:**
- Modify: `src/design_hub/interface/api/asgi.py`（import 段 / lifespan 装配 / include_router）

- [ ] **Step 1: import 段新增**

加：
```python
from design_hub.application.listing.listing_service import ListingGenerationService
from design_hub.application.listing.prompt_composer import PromptModifierRegistry
from design_hub.infrastructure.listing.noop_history import NoOpListingHistory
```
并把路由 import（`from design_hub.interface.api.routes import (...)`）加入 `listing,`。

- [ ] **Step 2: lifespan 内装配（在 `app.state.event_stream = event_bus` 之后插入）**

复用已有的 `guard`：当前 pipeline 内联建了 `CostGuard(ledger=ledger, policy=BudgetPolicy())`。改为先建一次再复用——

把（约 99-107 行 pipeline 构造里的）：
```python
        guard=CostGuard(ledger=ledger, policy=BudgetPolicy()),
```
改为：
```python
        guard=guard,
```
并在 pipeline 构造**之前**加一行：
```python
    guard = CostGuard(ledger=ledger, policy=BudgetPolicy())
```
然后在 `app.state.event_stream = event_bus` 之后加：
```python
    app.state.listing_service = ListingGenerationService(
        registry=registry, guard=guard, modifiers=PromptModifierRegistry()
    )
    app.state.listing_history = NoOpListingHistory()
```

- [ ] **Step 3: 挂路由（在 `app.include_router(async_generation.router)` 之后）**

```python
    # listing 一键出图：/listing/generate 走 Bearer，SSE /events 走 ?access_token=（同 async_generation）
    app.include_router(listing.router)
```

- [ ] **Step 4: 校验全量**

Run: `uv run ruff check src && uv run mypy`
Expected: ruff All checks passed；mypy Success

- [ ] **Step 5: 冒烟——生产 app 能构建且挂上 /listing 路由（sqlite，不连 MySQL/不打真网络）**

Run:
```bash
DB_URL="sqlite+aiosqlite:///./_smoke_listing.db" \
GPT_IMAGE_BASE_URL="http://localhost" GPT_IMAGE_MODEL="gpt-image-2" GPT_IMAGE_API_KEY="x" \
JWT_SECRET="smoke-secret" \
uv run python -c "
from fastapi.testclient import TestClient
from design_hub.interface.api.asgi import create_production_app
app=create_production_app()
with TestClient(app) as c:
    paths={r.path for r in app.routes}
    assert '/listing/generate' in paths, sorted(paths)
    assert '/listing/{job_id}/events' in paths, sorted(paths)
    # 未带 Bearer 应 401（鉴权生效）
    r=c.post('/listing/generate', files={'images':('a.png',b'x','image/png')},
             data={'prompt':'p','ratio':'1:1','n':'1','modifiers':'{}'})
    assert r.status_code==401, r.status_code
print('ASGI LISTING WIRING SMOKE OK')
" ; rm -f ./_smoke_listing.db
```
Expected: `ASGI LISTING WIRING SMOKE OK`
> 注：上面环境变量名以 `config/settings.py` 实际字段为准（如 `DB_URL`/`GPT_IMAGE_*`/`JWT_SECRET`）；若 settings 必填项更多，按其报错补齐再跑。lifespan 需要可连接的 DB——sqlite 文件即可建表（若启动有 alembic/建表依赖，改用 e2e 文档既定的起法）。

- [ ] **Step 6: 提交**

```bash
git add src/design_hub/interface/api/asgi.py
git commit -m "feat(listing): asgi 装配 listing_service/NoOp 历史并挂 /listing 路由

复用单一 CostGuard 实例注入 pipeline 与 listing；生产 app 构建冒烟通过、
/listing 路由就位、未鉴权 401。"
```

---

## Phase 5 — 收口与派单

### Task 5.1：全量门 + 进度文档

**Files:**
- Modify: `docs/工期与进度跟踪.md`（若存在；记录里程碑——遵循项目活文档约定）

- [ ] **Step 1: 全量质量门**

Run: `uv run ruff check src && uv run mypy`
Expected: 全绿

- [ ] **Step 2: 更新进度活文档**（追加一条：listing 一键出图后端 MVP 完成 + 日期 + 关键决策链接到 spec；若该文档不存在则跳过）

- [ ] **Step 3: 提交**

```bash
git add docs/工期与进度跟踪.md
git commit -m "docs: 进度更新——listing 一键出图后端 MVP 完成"
```

### Task 5.2：给 QA 开测试用例 issue

**Files:**
- Create: `../image-issues/ISSUE-00XX-QA-listing出图测试用例.md`（编号取黑板当前最大+1，避开撞号）

- [ ] **Step 1: 写 issue**（owner=QA，reporter=开发，status=已确认），覆盖点：
  - `/listing/generate` 多图(1/2/3 张)+ modifiers 入队返回 job_id；图数 0 或 >3 → 400；非法 modifiers JSON → 400；未知下拉值 → 4xx；未带 Bearer → 401。
  - SSE 全序列 task_started→model_called→image_generated×n→task_completed；失败发 task_failed。
  - prompt 组装正确（含用户文本 + 片段）；ratio→size 正确；n 越界 4xx。
  - 成本预扣/回正（CostGuard）；真实 gpt-image-2 多图 edit 联调（带真 key 环境）。
  - 验收口径待 PM（ISSUE-0021）给出后细化。

- [ ] **Step 2: 提交**

```bash
git add "../image-issues/ISSUE-00XX-QA-listing出图测试用例.md"
git commit -m "chore(issue): 给 QA 开 listing 出图测试用例（owner=QA）"
```

### Task 5.3：真实联调（带 key 环境，人工触发）

- [ ] **Step 1:** 在配好 `.env`(GPT_IMAGE_*) + 真实/测试 MySQL 的环境，按 e2e 文档起 asgi，用 1 张真实产品图打 `POST /listing/generate`(n=1 控成本)，订阅 SSE，确认真出图。
- [ ] **Step 2:** 若中转站 `/images/edits` 不支持 `image[]` 多字段（多图报错），按 spec §6.1 风险：在 `ListingGenerationService` 退化为并发逐图单 edit（封装在 service/provider 内，API 契约不变），补一条 issue 记录处理。
> 真实联调可能产生费用，须人工在受控环境执行；不纳入自动冒烟。

---

## Self-Review（已对 spec 核对）

- **Spec 覆盖**：§4 契约→Task 4.1；§5 组装→2.2；§4.3 尺寸→2.3；§6.1 service→3.1/3.2；§6.2 真改1多图→Phase 1，真改2命令模式→Phase 0；§6.3 历史口子→2.4；§7 成本/鉴权→3.1+4.1；§8 派单→Phase 5 + 已开 ISSUE-0020/0021/0022。✓
- **占位扫描**：无 TBD；种子片段表/ratio 表为「待 PM/image-prompt 替换」的真实可跑值，非占位。✓
- **类型一致**：`GenerationCommand.run(job_id)`、`ListingResult` 字段、`ListingGenerationService.generate(...)` 关键字参数、`ListingHistory.record(user_id, result)` 在各任务间一致。✓
- **风险**：(1) 多图 `image[]` 是否被中转站支持→Task 5.3 验证 + 退化方案；(2) MockModelProvider 是否按 n 返回 n 张→冒烟注明按真实行为调断言；(3) settings 必填环境变量名→冒烟注明以 settings.py 为准；(4) 无测试网=重构靠 mypy strict + 冒烟兜底，正式用例归 QA。
