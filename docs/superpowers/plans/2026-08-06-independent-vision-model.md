# Independent Vision Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route reverse-prompt generation through an independently configured and verified Doubao vision model managed from the existing admin model page.

**Architecture:** Add `vision` as a first-class `ModelType`, make completion-model resolution explicitly type-scoped, and reuse the OpenAI-compatible Chat Completions transport for both Chat and vision records. A dedicated multimodal capability probe gates activation, while a migration safely clones the existing Doubao encrypted connection into a disabled `doubao-vision` record for production verification.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/Alembic, Pydantic, httpx, pytest, React 19, TypeScript 6, Vitest, OpenAPI TypeScript.

## Global Constraints

- Use `uv run` for every Python command; never use system Python or `pip`.
- Do not add dependencies.
- Never write or print plaintext API keys in source, migrations, fixtures, logs, or generated contracts.
- Do not fall back from a missing or failed vision model to a Chat model.
- Non-network failures are fail-fast; only existing network error handling is retained.
- Every implementation task follows red-green-refactor and ends in its own commit.

---

## File Structure

- `image-code/src/design_hub/domain/enums.py`: declares the new `vision` model type.
- `image-code/src/design_hub/domain/model_config.py`: declares `doubao-vision` and permits the OpenAI-compatible completion Provider for Chat and vision records.
- `image-code/src/design_hub/ports/model_resolution.py`: exposes explicit type-scoped completion resolution.
- `image-code/src/design_hub/infrastructure/providers/live_resolution.py`: resolves and caches verified completion models by model ID, revision, and expected type.
- `image-code/src/design_hub/application/chat/orchestrator.py`: requests only Chat models.
- `image-code/src/design_hub/application/image_prompts/reverse_prompt.py`: requests only the default vision model.
- `image-code/src/design_hub/application/admin/model_capability_service.py`: performs the real image-understanding and tool-call probe for vision records.
- `image-code/src/design_hub/cli/bootstrap_models.py`: includes `doubao-vision` in clean-environment bootstrap plans using the existing Doubao connection.
- `image-code/migrations/versions/b5c6d7e8f9a0_independent_vision_model.py`: clones encrypted Doubao connection data and creates the vision default.
- `image-web/src/lib/model-config.ts`: maps the shared completion Provider to both Chat and vision types.
- `image-web/src/pages/AdminModelsPage.tsx`: adds the visual model filter and label.
- `image-web/src/components/admin/ModelConfigDialog.tsx`: adds visual model selection and capability-test copy.
- `image-code/openapi.json`, `image-web/openapi.json`, `image-web/src/api/schema.d.ts`: generated API contracts.

### Task 1: Type-scoped completion model resolution

**Files:**
- Modify: `image-code/src/design_hub/domain/enums.py`
- Modify: `image-code/src/design_hub/domain/model_config.py`
- Modify: `image-code/src/design_hub/ports/model_resolution.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/live_resolution.py`
- Modify: `image-code/src/design_hub/application/chat/orchestrator.py`
- Test: `image-code/tests/test_live_model_resolution.py`
- Test: `image-code/tests/test_chat.py`
- Test: `image-code/tests/test_model_verification.py`

**Interfaces:**
- Produces: `ModelType.VISION`, `DOUBAO_VISION`, and type-scoped `TextLLMResolver.resolve(model_id, model_type)` / `resolve_default(model_type)`.
- Consumes: existing `TextLLMPort`, model repository defaults, encrypted credentials, and verified fingerprints.

- [ ] **Step 1: Write failing resolver and provider-rule tests**

Add tests asserting that `openai_compat_chat` validates both `ModelType.CHAT` and `ModelType.VISION`, that a vision default resolves only with `ModelType.VISION`, and that resolving the same record as `ModelType.CHAT` raises `ModelUnavailableError`.

```python
vision = replace(_chat_record(), name="doubao-vision", model_type=ModelType.VISION)
repo = _Repo({vision.name: vision}, defaults={ModelType.VISION: vision.name})
resolver = LiveTextLLMResolver(
    repository=repo,
    cipher=_Cipher({"enc-chat": "chat-key"}),
    recorder=RecordingModelCallRecorder(),
    settings=Settings(),
)
assert (await resolver.resolve_default(ModelType.VISION)).name == vision.name
with pytest.raises(ModelUnavailableError):
    await resolver.resolve(vision.name, ModelType.CHAT)
```

- [ ] **Step 2: Run focused tests and verify red state**

Run:

```powershell
cd image-code
uv run pytest tests/test_live_model_resolution.py tests/test_model_verification.py -q
```

Expected: failures because `ModelType.VISION` and typed resolver arguments do not exist.

- [ ] **Step 3: Implement the type model and explicit resolver API**

Use an allowed-type collection in `ProviderRule`:

```python
@dataclass(frozen=True)
class ProviderRule:
    model_types: frozenset[ModelType]
    credential_fields: tuple[str, ...]
    required_credential_fields: tuple[str, ...]
    extra_fields: tuple[str, ...]

ProviderType.OPENAI_COMPAT_CHAT: ProviderRule(
    model_types=frozenset({ModelType.CHAT, ModelType.VISION}),
    credential_fields=("api_key",),
    required_credential_fields=("api_key",),
    extra_fields=("thinking_disabled",),
)
```

Change resolution to require the expected type and include it in the cache key:

```python
async def resolve_default(self, model_type: ModelType) -> TextLLMPort:
    default_name = await self._repository.get_default(model_type)
    if default_name is None:
        raise ModelUnavailableError(_UNAVAILABLE)
    return await self.resolve(default_name, model_type)

async def resolve(self, model_id: str, model_type: ModelType) -> TextLLMPort:
    record = await self._repository.get(_required_model_id(model_id))
    credentials = _require_record(record, expected_type=model_type, cipher=self._cipher)
```

Update both Chat orchestration call sites to pass `ModelType.CHAT`.

- [ ] **Step 4: Run focused tests and verify green state**

Run:

```powershell
cd image-code
uv run pytest tests/test_live_model_resolution.py tests/test_chat.py tests/test_model_verification.py -q
uv run ruff check src tests/test_live_model_resolution.py tests/test_chat.py tests/test_model_verification.py
uv run mypy
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```powershell
git add image-code/src image-code/tests/test_live_model_resolution.py image-code/tests/test_chat.py image-code/tests/test_model_verification.py
git commit -m "feat: add type-scoped vision model resolution" -m "Introduce the vision model type and require every completion model lookup to declare its expected type so reverse prompting cannot silently use Chat defaults."
```

### Task 2: Reverse-prompt routing and multimodal verification

**Files:**
- Modify: `image-code/src/design_hub/application/image_prompts/reverse_prompt.py`
- Modify: `image-code/src/design_hub/application/admin/model_capability_service.py`
- Test: `image-code/tests/test_reverse_prompt.py`
- Test: `image-code/tests/test_model_capability_service.py`

**Interfaces:**
- Consumes: `ModelType.VISION` and the type-scoped resolver from Task 1.
- Produces: reverse prompting bound to the vision default and `_probe_vision(record, credentials, manager_id) -> tuple[str, ...]`.

- [ ] **Step 1: Write failing routing and capability tests**

Record resolver calls in `test_reverse_prompt.py` and assert exactly `ModelType.VISION`. Add a capability test whose fake provider receives one red PNG image and returns a required tool call with `{"dominant_color": "red"}`.

```python
assert resolver.default_calls == [ModelType.VISION]
assert result.checks == ("image_understanding", "tool_call")
```

Also assert that a text-only response, missing image, wrong color, or missing tool call fails with `CapabilityTestFailed`.

- [ ] **Step 2: Run focused tests and verify red state**

Run:

```powershell
cd image-code
uv run pytest tests/test_reverse_prompt.py tests/test_model_capability_service.py -q
```

Expected: failures because reverse prompt still resolves the untyped default and vision records still take the Chat probe.

- [ ] **Step 3: Implement vision routing and a real multimodal probe**

Change reverse prompt resolution to:

```python
text_llm = await self.text_llm_resolver.resolve_default(ModelType.VISION)
```

Dispatch capability tests explicitly:

```python
if model_type is ModelType.IMAGE:
    checks = await self._probe_image(record, plaintext, manager_id)
elif model_type is ModelType.VISION:
    checks = await self._probe_vision(record, plaintext, manager_id)
else:
    checks = await self._probe_chat(record, plaintext, manager_id)
```

The vision probe must attach `_deterministic_red_png()` to a user message, force a tool with a `dominant_color` enum, and accept only the expected tool name and `red` argument.

- [ ] **Step 4: Run focused tests and verify green state**

Run:

```powershell
cd image-code
uv run pytest tests/test_reverse_prompt.py tests/test_model_capability_service.py -q
uv run ruff check src tests/test_reverse_prompt.py tests/test_model_capability_service.py
uv run mypy
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```powershell
git add image-code/src/design_hub/application/image_prompts/reverse_prompt.py image-code/src/design_hub/application/admin/model_capability_service.py image-code/tests/test_reverse_prompt.py image-code/tests/test_model_capability_service.py
git commit -m "fix: route reverse prompts through verified vision models" -m "Bind reverse prompting to the independent vision default and require a real image-understanding plus structured tool-call probe before a vision configuration can be activated."
```

### Task 3: Seed and migrate the Doubao vision configuration

**Files:**
- Modify: `image-code/src/design_hub/cli/bootstrap_models.py`
- Create: `image-code/migrations/versions/b5c6d7e8f9a0_independent_vision_model.py`
- Modify: `image-code/tests/test_bootstrap_models.py`
- Create: `image-code/tests/test_independent_vision_model_migration.py`
- Modify: `image-code/tests/test_live_model_config_migration.py`

**Interfaces:**
- Consumes: `DOUBAO_VISION`, `ModelType.VISION`, existing `doubao-chat` encrypted connection fields.
- Produces: disabled `doubao-vision` configuration with model `doubao-seed-2-0-lite-260428` and a `vision` default row.

- [ ] **Step 1: Write failing bootstrap and migration tests**

Assert that clean bootstrap includes `doubao-vision` with the same encrypted API key and Base URL as `doubao-chat`, but a distinct model ID and type. For migration, build the prior schema with one `doubao-chat` row and assert upgrade creates:

```python
{
    "name": "doubao-vision",
    "display_name": "豆包 Seed 2.0 Lite 视觉",
    "model_type": "vision",
    "provider_type": "openai_compat_chat",
    "model": "doubao-seed-2-0-lite-260428",
    "enabled": False,
    "verified_at": None,
    "verified_fingerprint": None,
}
```

Assert the ciphertext and Base URL exactly equal the source row and that `model_default` contains `("vision", "doubao-vision")`.

- [ ] **Step 2: Run migration tests and verify red state**

Run:

```powershell
cd image-code
uv run pytest tests/test_bootstrap_models.py tests/test_independent_vision_model_migration.py tests/test_live_model_config_migration.py -q
```

Expected: failures because the model constant, bootstrap row, and migration do not exist.

- [ ] **Step 3: Implement secure clone migration and bootstrap entry**

The Alembic upgrade must select the existing `doubao-chat` row and insert the new row without decrypting credentials. If no source row exists, create no vision row or default. Downgrade deletes only the `vision` default and `doubao-vision` row.

Bootstrap reuses the same in-memory `chat_credentials` mapping and sets `make_default=True` for the vision type; no new environment secret is introduced.

- [ ] **Step 4: Run migration tests and verify green state**

Run:

```powershell
cd image-code
uv run pytest tests/test_bootstrap_models.py tests/test_independent_vision_model_migration.py tests/test_live_model_config_migration.py -q
uv run alembic heads
uv run ruff check src tests/test_bootstrap_models.py tests/test_independent_vision_model_migration.py tests/test_live_model_config_migration.py
```

Expected: one Alembic head, all tests and lint pass.

- [ ] **Step 5: Commit**

```powershell
git add image-code/src/design_hub/cli/bootstrap_models.py image-code/migrations/versions/b5c6d7e8f9a0_independent_vision_model.py image-code/tests/test_bootstrap_models.py image-code/tests/test_independent_vision_model_migration.py image-code/tests/test_live_model_config_migration.py
git commit -m "feat: seed the Doubao vision model configuration" -m "Clone the existing encrypted Doubao connection into a disabled Seed 2.0 Lite vision record and establish an independent vision default without exposing credentials."
```

### Task 4: Expose visual models in the admin UI

**Files:**
- Modify: `image-web/src/lib/model-config.ts`
- Modify: `image-web/src/pages/AdminModelsPage.tsx`
- Modify: `image-web/src/components/admin/ModelConfigDialog.tsx`
- Modify: `image-web/src/components/admin/ModelConfigDialog.test.tsx`
- Create: `image-web/src/pages/AdminModelsPage.test.tsx`
- Regenerate: `image-code/openapi.json`
- Regenerate: `image-web/openapi.json`
- Regenerate: `image-web/src/api/schema.d.ts`

**Interfaces:**
- Consumes: backend `ModelType` enum containing `vision`.
- Produces: type-safe model filters, labels, form selection, shared completion Provider mapping, and vision-specific verification guidance.

- [ ] **Step 1: Write failing UI tests**

Assert that the page renders “视觉模型”, filters to `model_type === "vision"`, and labels a visual row “视觉”. Assert the dialog offers `vision` and keeps `openai_compat_chat` when that type is selected.

- [ ] **Step 2: Run UI tests and verify red state**

Run:

```powershell
cd image-web
npm test -- src/components/admin/ModelConfigDialog.test.tsx src/pages/AdminModelsPage.test.tsx
```

Expected: failures because the visual model option and filter do not exist.

- [ ] **Step 3: Regenerate contracts and implement the UI mapping**

Export the backend schema without manually editing generated files:

```powershell
cd image-code
uv run python -c "import json; from design_hub.interface.api.asgi import create_production_app; print(json.dumps(create_production_app().openapi(), ensure_ascii=False, indent=2))" | Set-Content -Encoding UTF8 openapi.json
Copy-Item openapi.json ../image-web/openapi.json
cd ../image-web
npm run gen:api
```

Change Provider metadata from one `modelType` to `modelTypes`, with `openai_compat_chat` accepting `['chat', 'vision']`. Add `vision` to filters and form options, and centralize type display labels so the table has no binary image/Chat assumption.

- [ ] **Step 4: Run UI validation and verify green state**

Run:

```powershell
cd image-web
npm test -- src/components/admin/ModelConfigDialog.test.tsx src/pages/AdminModelsPage.test.tsx
npm run typecheck
npm run lint
npm run build
```

Expected: all commands pass.

- [ ] **Step 5: Commit**

```powershell
git add image-code/openapi.json image-web/openapi.json image-web/src/api/schema.d.ts image-web/src/lib/model-config.ts image-web/src/pages/AdminModelsPage.tsx image-web/src/pages/AdminModelsPage.test.tsx image-web/src/components/admin/ModelConfigDialog.tsx image-web/src/components/admin/ModelConfigDialog.test.tsx
git commit -m "feat: manage visual models in the admin console" -m "Add visual model filtering, labels, configuration, and capability guidance while preserving the existing admin UI design and generated API contract."
```

### Task 5: Full verification and production activation

**Files:**
- Verify only; no source files expected.

**Interfaces:**
- Consumes: all Tasks 1-4 and the existing production Doubao encrypted credentials.
- Produces: a verified, enabled `doubao-vision` default and a successful real reverse-prompt result.

- [ ] **Step 1: Run the complete local quality gate**

Run:

```powershell
cd image-code
uv run pytest -q
uv run ruff check src tests
uv run mypy
cd ../image-web
npm test
npm run typecheck
npm run lint
npm run build
git diff --check
git status --short
```

Expected: all commands pass and the worktree is clean after task commits.

- [ ] **Step 2: Merge and deploy through the existing production workflow**

Merge the feature branch into `main`, push only because the user explicitly requested production configuration, run the existing deployment script, and confirm Alembic reaches `b5c6d7e8f9a0`.

- [ ] **Step 3: Execute production capability verification**

Use the existing admin model capability endpoint or the same application service inside the deployed container to test `doubao-vision`. Do not print credentials. The expected checks are:

```text
image_understanding
tool_call
```

If the upstream rejects the model or credential, leave the model disabled and report the exact sanitized provider status. Do not switch to another model without a new documented decision.

- [ ] **Step 4: Enable, set default, and run a real reverse prompt**

After verification succeeds, save the proof, enable `doubao-vision`, set it as the `vision` default, upload a real PNG/JPEG/WebP through the existing product flow, and assert the response contains `summary`, `prompt_zh`, and `prompt_en`.

- [ ] **Step 5: Record final evidence**

Capture the deployed revision, migration head, model enabled/default state, successful model-call operation `reverse_prompt`, and sanitized request/chain IDs. Do not include secrets or full user prompts.
