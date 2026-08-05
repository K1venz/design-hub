# Nano Banana 2 Integration Design

Date: 2026-08-05

## Goal

Add one production-facing image model, **Nano Banana 2**, backed by the stable upstream model `gemini-3.1-flash-image`. The model must be selectable in Chat, support text-to-image and reference-image editing, expose every documented aspect ratio, support 1K/2K/4K output, and use the two supplied channel credentials without storing secrets in source control.

## Model choice

Only `gemini-3.1-flash-image` will be integrated.

- Both supplied channels return `gemini-3.1-flash-image`, `gemini-3.1-flash-image-preview`, and `gemini-3-pro-image-preview` from `GET /v1/models`.
- The stable Flash model completed the same 4:5 commercial-poster probe at 1K in 36.83 seconds and at 2K in 37.67 seconds.
- Flash Preview completed the probes but is a transitional model name.
- Pro Image Preview failed both its 1K and 2K probes with gateway HTTP 524 after about 127 seconds.
- Google documents `gemini-3.1-flash-image` as the default all-around choice for quality, cost, and latency.

Internal model ID: `nano-banana-2`

Display name: `Nano Banana 2`

Upstream model: `gemini-3.1-flash-image`

## Architecture

### Model capability contracts

Introduce a model-neutral image capability registry instead of extending GPT-specific sizing conditionals.

Each built-in image model contract owns:

- platform model ID;
- supported render tiers;
- supported aspect ratios per tier;
- provider request dimensions per tier and ratio;
- platform and provider count limits;
- reference-image support.

The existing GPT Image 2 contract will implement this shared contract. Nano Banana 2 will add its own contract. Application services will resolve capabilities by selected model ID before planning work. Unsupported model/tier/ratio combinations fail before a task is persisted.

The image model catalog API will expose the selected model's capability profile. Chat will build resolution and ratio dropdowns from catalog data instead of maintaining a separate hard-coded frontend dictionary.

### Output specification

Add `RenderTier.TWO_K`. Existing `RenderTier.STANDARD` remains the default tier and is presented as 1K for Nano Banana 2. `RenderTier.FOUR_K` remains 4K.

Provider execution requests will carry an explicit image output specification containing:

- semantic aspect ratio;
- render tier;
- planned pixel dimensions.

GPT Image 2 and Wan continue to use planned pixel dimensions. The Gemini provider uses aspect ratio and render tier directly. This avoids deriving Gemini API parameters by reverse-mapping GPT dimensions.

### Gemini native provider

Add a dedicated `gemini_native_image` provider type. It will not reuse the OpenAI-compatible image adapter.

The provider calls:

`POST {base_url}/v1beta/models/{model}:generateContent`

Text-to-image request parts contain the final prompt. Reference editing puts the final prompt and all reference images in the same user `parts` array. Reference bytes are encoded as Gemini `inlineData` objects with their real MIME type.

`generationConfig` contains:

- `responseModalities: ["IMAGE"]`;
- `imageConfig.aspectRatio` using the model-aware ratio resolved before task creation;
- `imageConfig.imageSize` as `1K`, `2K`, or `4K`.

The provider extracts the first final image from `candidates[0].content.parts[].inlineData`, validates Base64 and MIME type, and immediately writes decoded bytes through `ImageStore`. Full Base64 response bodies must never be logged or persisted.

### Credentials and channel use

The provider requires a non-empty `api_keys` tuple. The two supplied keys form one `ApiKeyPool` for `https://api.yhlxj.ai`.

Credentials are accepted only through the existing encrypted model configuration flow. No API key is added to source, fixtures, generated files, logs, or design documentation.

Admin model configuration will support the new provider type and a multiline API-key field. Connection verification will perform both a 1K text-to-image probe and a 1K reference-edit probe before issuing a verification proof.

## Supported options

### Resolution

- Automatic: resolves to 1K unless a later model-aware intent rule selects another tier.
- 1K (`standard` internally)
- 2K
- 4K

### Aspect ratio

- Automatic: resolve to 1:1 for text-only input or to the closest supported reference-image ratio before task creation.
- `1:1`
- `1:4`
- `1:8`
- `2:3`
- `3:2`
- `3:4`
- `4:1`
- `4:3`
- `4:5`
- `5:4`
- `8:1`
- `9:16`
- `16:9`
- `21:9`

All 14 explicit ratios are available at 1K, 2K, and 4K for `gemini-3.1-flash-image`.

### Pixel dimensions

The capability contract records the documented output dimensions so task history and validation remain accurate. Examples include 1K 4:5 as 928x1152, 2K 4:5 as 1856x2304, and 4K 4:5 as 3712x4608. The complete matrix is a single immutable backend dictionary covered by exact-value tests.

### Count and reference images

The current platform count selector remains 1-7. Each generation item makes one Gemini request and returns one final image, so multi-image generation continues to fan out through the existing task planner.

Nano Banana 2 accepts the platform's existing multi-reference upload flow. The provider preserves upload order in Gemini request parts.

## Chat behavior

Selecting Nano Banana 2 updates the composer controls from the model catalog capability profile:

- resolution dropdown: Automatic, 1K, 2K, 4K;
- ratio dropdown: Automatic plus the 14 ratios above;
- count dropdown: existing 1-7 behavior;
- reference upload: enabled;
- helper text: identifies Nano Banana 2 and its native aspect-ratio support.

Switching between GPT Image 2 and Nano Banana 2 normalizes any unsupported current selection to Automatic. The submitted JSON uses the same generic Chat image-options schema, with `2k` added as a render-tier value.

## Error handling

- Invalid model, tier, ratio, count, response shape, MIME type, or Base64 fails immediately.
- HTTP 4xx responses are treated as provider rejection and are not retried, except 429.
- HTTP 429, 5xx, connect failures, and transport timeouts may rotate to the next key within the configured network retry budget.
- Exhausted synchronous requests surface through the existing submission-uncertain path so the task is not falsely marked as a safe deterministic failure.
- Error details must not include authorization headers or full upstream response bodies.

## Verification and testing

Implementation follows red-green-refactor.

Backend tests will cover:

- exact Nano Banana tier/ratio/dimension matrices;
- invalid capability combinations;
- provider type and encrypted credential validation;
- text-to-image and ordered multi-reference Gemini request JSON;
- model-aware automatic aspect-ratio resolution;
- Base64 image parsing and storage;
- usage metadata and request-ID recording;
- malformed responses and HTTP error classification;
- factory/resolver selection and cache behavior;
- catalog capability serialization;
- Chat validation, planning, and worker propagation of semantic output options;
- capability probes for generation and editing.

Frontend tests will cover:

- provider administration form fields;
- Nano Banana brand and model card;
- model-driven resolution and ratio dropdowns;
- normalization when switching models;
- exact Chat request JSON for 1K, 2K, and 4K.

Final verification will run the full backend suite, Ruff, mypy, the full frontend suite, ESLint, and the production build. A live smoke test will then configure the two supplied keys through encrypted local configuration and verify one text-to-image request and one reference edit through the application's task path.

## Out of scope

- `gemini-3.1-flash-image-preview` and `gemini-3-pro-image-preview` are not exposed.
- Google Search grounding is not exposed.
- Thinking controls are not exposed.
- Text responses from mixed TEXT/IMAGE generation are not retained because this product flow requests images only.
- No compatibility provider or protocol shim will translate Gemini requests into OpenAI image endpoints.
