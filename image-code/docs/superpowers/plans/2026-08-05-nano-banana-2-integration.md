# Nano Banana 2 Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one production-ready `Nano Banana 2` image model backed by `gemini-3.1-flash-image`, including native Gemini generation/editing, encrypted two-key pooling, 14 ratios, 1K/2K/4K, and model-driven Chat controls.

**Architecture:** A model-neutral capability registry plans semantic output options before task creation. Provider requests carry ratio, render tier, and dimensions; GPT/Wan consume dimensions while a new Gemini-native provider consumes ratio and image size. The model catalog publishes capabilities so the frontend never duplicates backend option dictionaries.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, httpx, Pillow, pytest, Ruff, mypy, React 19, TypeScript 6, Vitest, Vite.

## Global Constraints

- Integrate only `gemini-3.1-flash-image`; do not expose either preview alias.
- Internal model ID is `nano-banana-2`; display name is `Nano Banana 2`.
- Use provider type `gemini_native_image` and base URL `https://api.yhlxj.ai`.
- Accept the two supplied credentials only through encrypted configuration as one non-empty `api_keys` tuple; never write keys to source, docs, fixtures, logs, or generated schemas.
- Support text-to-image and ordered multi-reference editing.
- Support Automatic, 1K, 2K, and 4K resolution choices.
- Support Automatic plus `1:1`, `1:4`, `1:8`, `2:3`, `3:2`, `3:4`, `4:1`, `4:3`, `4:5`, `5:4`, `8:1`, `9:16`, `16:9`, and `21:9`.
- Full Base64 upstream response bodies must never be logged or persisted.
- Non-I/O validation fails immediately. Only HTTP 429, 5xx, connect failures, and transport timeouts may rotate keys within the network retry budget.
- Add no dependencies.

---

### Task 1: Model-neutral output capability registry

**Files:**
- Create: `image-code/src/design_hub/domain/image_capabilities.py`
- Create: `image-code/src/design_hub/domain/nano_banana.py`
- Modify: `image-code/src/design_hub/domain/gpt_image_2.py`
- Modify: `image-code/src/design_hub/domain/tasking.py`
- Modify: `image-code/src/design_hub/application/listing/sizing.py`
- Test: `image-code/tests/test_image_capabilities.py`
- Test: `image-code/tests/test_listing_validation.py`
- Test: `image-code/tests/test_tasking_domain.py`

**Interfaces:**
- Produces: `ImageOutputSpec(ratio: str, render_tier: RenderTier, size: tuple[int, int])`.
- Produces: `ImageModelCapabilities(model_id, tiers, platform_max_count, provider_max_count, supports_references)` with `output_for(render_tier, ratio) -> ImageOutputSpec`.
- Produces: `image_model_capabilities(model_id: str) -> ImageModelCapabilities`.
- Produces: `NANO_BANANA_2_MODEL_ID = "nano-banana-2"` and `NANO_BANANA_UPSTREAM_MODEL = "gemini-3.1-flash-image"`.

- [ ] **Step 1: Write failing contract tests**

Add literal matrix assertions that catch a missing tier, a wrong ratio, and a wrong dimension. Representative expectations:

```python
def test_nano_banana_exposes_all_ratios_at_every_tier() -> None:
    contract = image_model_capabilities("nano-banana-2")
    assert contract.ratios(RenderTier.STANDARD) == (
        "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1",
        "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9",
    )
    assert contract.output_for(RenderTier.STANDARD, "4:5").size == (928, 1152)
    assert contract.output_for(RenderTier.TWO_K, "4:5").size == (1856, 2304)
    assert contract.output_for(RenderTier.FOUR_K, "4:5").size == (3712, 4608)

def test_gpt_contract_rejects_two_k() -> None:
    with pytest.raises(ValueError, match="does not support"):
        image_model_capabilities("gpt-image-2").output_for(RenderTier.TWO_K, "1:1")
```

- [ ] **Step 2: Run RED tests**

Run: `cd image-code && uv run pytest tests/test_image_capabilities.py tests/test_listing_validation.py tests/test_tasking_domain.py -q`

Expected: FAIL because the neutral registry, Nano contract, and `RenderTier.TWO_K` do not exist.

- [ ] **Step 3: Implement the immutable capability registry**

Use `MappingProxyType` for tier/ratio matrices. Populate all Google-documented Flash dimensions for 1K/2K/4K. Adapt GPT Image 2 into the registry rather than adding Nano checks to GPT functions. Change `generation_size` to require `model_id` and delegate to `image_model_capabilities(model_id).output_for(...)`.

- [ ] **Step 4: Run GREEN tests**

Run: `cd image-code && uv run pytest tests/test_image_capabilities.py tests/test_listing_validation.py tests/test_tasking_domain.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add image-code/src/design_hub/domain image-code/src/design_hub/application/listing/sizing.py image-code/tests/test_image_capabilities.py image-code/tests/test_listing_validation.py image-code/tests/test_tasking_domain.py
git commit -m "feat: add image model capability registry" -m "Centralize model-specific resolution, ratio, dimension, and count contracts so task planning no longer assumes GPT Image 2 semantics."
```

### Task 2: Semantic provider output requests

**Files:**
- Modify: `image-code/src/design_hub/ports/provider_execution.py`
- Modify: `image-code/src/design_hub/ports/model_provider.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/execution.py`
- Modify: `image-code/src/design_hub/application/tasking/worker.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/openai_compat.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/dashscope_wan.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/apinebula_async.py`
- Test: `image-code/tests/test_provider_execution.py`
- Test: `image-code/tests/test_generation_worker.py`
- Test: `image-code/tests/test_provider_contract.py`
- Test: `image-code/tests/test_dashscope_wan.py`
- Test: `image-code/tests/test_async_provider.py`

**Interfaces:**
- Consumes: `ImageOutputSpec` from Task 1.
- Produces: `ProviderRequest.output: ImageOutputSpec`.
- Produces: `AbstractModelProvider.generate(..., output: ImageOutputSpec, ...)`.

- [ ] **Step 1: Write failing propagation tests**

Assert that the worker carries the persisted ratio, tier, and size into one `ImageOutputSpec`, and that existing providers use `output.size`:

```python
assert captured_request.output == ImageOutputSpec(
    ratio="4:5",
    render_tier=RenderTier.TWO_K,
    size=(1856, 2304),
)
```

- [ ] **Step 2: Run RED tests**

Run: `cd image-code && uv run pytest tests/test_provider_execution.py tests/test_generation_worker.py tests/test_provider_contract.py tests/test_dashscope_wan.py tests/test_async_provider.py -q`

Expected: FAIL because providers still accept a bare `size` tuple.

- [ ] **Step 3: Refactor the provider port and all implementations**

Replace the bare `size` argument with `output: ImageOutputSpec` throughout the provider boundary. Existing provider payloads must remain behaviorally identical by reading `output.size`. Do not add an overload or compatibility adapter.

- [ ] **Step 4: Run GREEN tests**

Run the RED command again. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add image-code/src/design_hub/ports image-code/src/design_hub/infrastructure/providers image-code/src/design_hub/application/tasking/worker.py image-code/tests
git commit -m "refactor: carry semantic image output specs" -m "Move provider execution from bare pixel tuples to model-aware ratio, tier, and dimension requests while preserving existing GPT and Wan payload behavior."
```

### Task 3: Gemini-native provider and encrypted configuration

**Files:**
- Create: `image-code/src/design_hub/infrastructure/providers/gemini_native.py`
- Modify: `image-code/src/design_hub/domain/enums.py`
- Modify: `image-code/src/design_hub/domain/model_config.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/factory.py`
- Modify: `image-code/src/design_hub/application/admin/model_capability_service.py`
- Modify: `image-code/src/design_hub/config/settings.py`
- Test: `image-code/tests/test_gemini_native.py`
- Test: `image-code/tests/test_model_config.py`
- Test: `image-code/tests/test_model_capability_service.py`
- Test: `image-code/tests/test_live_model_resolution.py`

**Interfaces:**
- Consumes: `ProviderType.GEMINI_NATIVE_IMAGE`, `ImageOutputSpec`, `ApiKeyPool`, `ImageStore`, and `ModelCallRecorder`.
- Produces: `GeminiNativeImageProvider.generate(...) -> list[GeneratedImage]`.

- [ ] **Step 1: Write failing request/response tests**

Use `httpx.MockTransport` only at the external HTTP boundary. Mirror a complete Gemini response fixture with `candidates`, `content.parts.inlineData`, `finishReason`, `usageMetadata`, `modelVersion`, and `responseId`. Assert observable stored output and captured HTTP JSON:

```python
assert request_json["generationConfig"] == {
    "responseModalities": ["IMAGE"],
    "imageConfig": {"aspectRatio": "4:5", "imageSize": "2K"},
}
assert request_json["contents"][0]["parts"] == [
    {"text": "final prompt"},
    {"inlineData": {"mimeType": "image/png", "data": encoded_reference}},
]
assert stored_bytes == expected_png
```

Add separate failures for malformed Base64, missing final image, unsupported MIME, 400 rejection, and 524/5xx timeout classification. Add a key-rotation behavior test where the first key receives 429 and the second succeeds.

- [ ] **Step 2: Run RED tests**

Run: `cd image-code && uv run pytest tests/test_gemini_native.py tests/test_model_config.py tests/test_model_capability_service.py tests/test_live_model_resolution.py -q`

Expected: FAIL because the provider type and implementation do not exist.

- [ ] **Step 3: Implement provider, factory, validation, and settings**

The provider must send bearer auth, detect PNG/JPEG/WebP reference MIME from bytes, Base64-encode references, decode only the first final image, save it immediately, record token usage from `usageMetadata`, and record response IDs without retaining response bodies. Credential validation requires a non-empty `api_keys` tuple and permits no extra fields.

- [ ] **Step 4: Run GREEN tests**

Run the RED command again. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add image-code/src/design_hub image-code/tests/test_gemini_native.py image-code/tests/test_model_config.py image-code/tests/test_model_capability_service.py image-code/tests/test_live_model_resolution.py
git commit -m "feat: add Gemini native image provider" -m "Implement Nano Banana generation and ordered reference editing through Gemini generateContent with encrypted key pooling, strict response validation, and bounded network retries."
```

### Task 4: Model-driven Chat planning and catalog capabilities

**Files:**
- Modify: `image-code/src/design_hub/interface/model_schemas.py`
- Modify: `image-code/src/design_hub/application/admin/model_config_service.py`
- Modify: `image-code/src/design_hub/interface/chat_schemas.py`
- Modify: `image-code/src/design_hub/application/chat/image_options.py`
- Modify: `image-code/src/design_hub/application/chat/ratio_intent.py`
- Modify: `image-code/src/design_hub/application/chat/rendering_intent.py`
- Modify: `image-code/src/design_hub/application/chat/orchestrator.py`
- Modify: `image-code/src/design_hub/application/listing/task_planner.py`
- Modify: `image-code/src/design_hub/application/listing/submission_service.py`
- Modify: `image-code/src/design_hub/application/listing/listing_service.py`
- Test: `image-code/tests/test_model_catalog.py`
- Test: `image-code/tests/test_chat_image_options.py`
- Test: `image-code/tests/test_chat_ratio_intent.py`
- Test: `image-code/tests/test_chat.py`
- Test: `image-code/tests/test_listing_submission.py`

**Interfaces:**
- Consumes: `image_model_capabilities(model_id)`.
- Produces: `ModelCatalogItemOut.image_capabilities` with tier IDs, labels, ratios, maximum count, and reference support.
- Produces: Chat `render_tier` value `2k` and model-aware validation.

- [ ] **Step 1: Write failing API and planning tests**

Assert that Nano catalog JSON exposes 1K/2K/4K and all 14 ratios, GPT exposes only its own matrix, Nano accepts 2K 4:5, GPT rejects 2K, automatic ratio resolves to 1:1 without a reference and to the closest supported ratio with a reference, and task dimensions come from the selected model contract.

- [ ] **Step 2: Run RED tests**

Run: `cd image-code && uv run pytest tests/test_model_catalog.py tests/test_chat_image_options.py tests/test_chat_ratio_intent.py tests/test_chat.py tests/test_listing_submission.py -q`

Expected: FAIL because catalog capabilities and model-aware planning are absent.

- [ ] **Step 3: Implement model-aware application flow**

Remove GPT-specific global ratio sets from Chat. Validate and normalize against the selected model's capability contract. Resolve output dimensions only after the image model is known. Preserve current fan-out count behavior and reject invalid options before persistence.

- [ ] **Step 4: Run GREEN tests**

Run the RED command again. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add image-code/src/design_hub image-code/tests
git commit -m "feat: expose model-driven image options" -m "Publish image capabilities in the model catalog and make Chat validation, intent resolution, and task planning depend on the selected model contract."
```

### Task 5: Frontend model administration and Chat controls

**Files:**
- Modify: `image-web/src/lib/model-config.ts`
- Modify: `image-web/src/components/admin/ModelConfigDialog.tsx`
- Modify: `image-web/src/components/admin/ModelConfigDialog.test.tsx`
- Modify: `image-web/src/lib/chat-image-options.ts`
- Modify: `image-web/src/lib/chat-image-options.test.ts`
- Modify: `image-web/src/components/chat/ChatComposer.tsx`
- Modify: `image-web/src/components/chat/ChatComposer.test.ts`
- Modify: `image-web/src/components/models/model-brand.ts`
- Create: `image-web/public/model-brands/gemini.svg`
- Modify: `image-web/src/api/models.ts`

**Interfaces:**
- Consumes: generated `ModelCatalogItemOut.image_capabilities`.
- Produces: model-driven composer options and encrypted multiline `api_keys` administration field.

- [ ] **Step 1: Write failing frontend tests**

Use complete catalog fixtures. Assert that selecting Nano shows Automatic/1K/2K/4K, all 14 ratios, Gemini branding, and exact payload `{render_tier: '2k', ratio: '4:5', count: 1}`. Assert switching to GPT normalizes 2K or an unsupported ratio to Automatic. Assert the admin form encrypts each non-empty API-key line into `api_keys`.

- [ ] **Step 2: Run RED tests**

Run: `cd image-web && npm test -- src/lib/chat-image-options.test.ts src/components/chat/ChatComposer.test.ts src/components/admin/ModelConfigDialog.test.tsx`

Expected: FAIL because model-driven capabilities and Gemini provider fields are absent.

- [ ] **Step 3: Implement UI behavior**

Delete GPT-specific option dictionaries from `chat-image-options.ts`. Derive selectors from the selected catalog record. Add the Gemini provider form, Gemini logo mapping, Nano helper copy, and model-switch normalization.

- [ ] **Step 4: Run GREEN tests**

Run the RED command again. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add image-web
git commit -m "feat: add Nano Banana Chat controls" -m "Render Nano Banana resolution and ratio options from backend capabilities and add secure Gemini provider administration and branding."
```

### Task 6: OpenAPI, bootstrap, full verification, and live acceptance

**Files:**
- Modify: `image-code/src/design_hub/cli/bootstrap_models.py`
- Modify: `image-code/tests/test_bootstrap_models.py`
- Regenerate: `image-code/openapi.json`
- Regenerate: `image-web/openapi.json`
- Regenerate: `image-web/src/api/schema.d.ts`

**Interfaces:**
- Consumes: Nano provider/config/catalog from Tasks 1-5.
- Produces: secure bootstrap inputs `NANO_BANANA_BASE_URL`, `NANO_BANANA_MODEL`, and `NANO_BANANA_API_KEYS`.

- [ ] **Step 1: Write failing bootstrap tests**

Assert that comma-separated Nano keys are encrypted independently, the stable upstream model is required, preview aliases are rejected, and no plaintext key appears in the resulting plan representation.

- [ ] **Step 2: Run RED tests**

Run: `cd image-code && uv run pytest tests/test_bootstrap_models.py -q`

Expected: FAIL because bootstrap has no Nano model.

- [ ] **Step 3: Implement bootstrap and regenerate schemas**

Use existing encryption and model verification flows. Regenerate backend OpenAPI through the project's existing schema command/test path, copy the schema to `image-web/openapi.json`, then run `npm run gen:api`. Do not edit generated schema files manually.

- [ ] **Step 4: Run targeted and full verification**

Run:

```powershell
cd image-code
uv run pytest -q
uv run ruff check .
uv run mypy
cd ..\image-web
npm test
npm run lint
npm run build
```

Expected: all commands exit 0.

- [ ] **Step 5: Run secret scan and live application smoke tests**

Scan tracked and untracked workspace files for the two supplied key values without printing matches. Start the backend and frontend, configure `nano-banana-2` through encrypted local model configuration, then verify:

1. authenticated `/models/image` returns Nano Banana 2 with its capabilities;
2. a 1K 4:5 text-to-image task completes and stores a real image;
3. a 1K 4:5 reference edit completes and stores a real image;
4. provider call records contain metadata but no Base64 payload or secret.

- [ ] **Step 6: Commit**

```powershell
git add image-code image-web
git commit -m "feat: enable Nano Banana 2 end to end" -m "Add secure bootstrap, generated API contracts, and final integration coverage for live Nano Banana generation and editing."
```
