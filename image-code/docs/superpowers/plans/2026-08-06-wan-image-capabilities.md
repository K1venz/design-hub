# Wan 2.7 Image Pro Capability Update Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for progress tracking.

**Goal:** Expose Wan 2.7 Image Pro's official 1K, 2K, and 4K capability and the platform's complete 16-ratio vocabulary, enforce the 4K text-to-image-only rule end to end, and verify the four extreme ratios with real 1K generations.

**Architecture:** Keep resolution and ratio truth in the backend domain contract. Publish per-tier reference support through the model catalog so the chat selector can derive valid choices from server data, while submission validation remains the authoritative guard. The DashScope adapter receives an already-validated explicit output size and validates returned images against that contract. A dedicated smoke command uses the configured live Wan provider, persists four outputs, and writes a redacted machine-readable report.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, pytest, httpx, Pillow, React 19, TypeScript 6, Vitest, OpenAPI code generation.

## Global Constraints

- Use `uv run` for every Python command and existing `npm` scripts for the frontend.
- Do not add a compatibility mapping from Wan to GPT Image dimensions; Wan owns an explicit contract.
- Do not retry a rejected size under a different size or silently downgrade tiers.
- Network retry behavior already owned by the DashScope provider remains unchanged.
- Never print or persist API keys. Smoke artifacts live under the ignored export directory; commit only the redacted report.
- Complete and commit each task before starting the next task.

---

## Task 1: Define the Wan-native size matrix and operation contract

**Files:**

- Create: `image-code/src/design_hub/domain/wan_image.py`
- Modify: `image-code/src/design_hub/domain/image_capabilities.py`
- Modify: `image-code/tests/test_image_capabilities.py`

- [ ] Add failing parameterized tests asserting that Wan exposes `standard`, `2k`, and `4k`, with these ordered ratios at every tier: `1:1`, `1:4`, `1:8`, `2:3`, `3:2`, `3:4`, `4:3`, `4:1`, `4:5`, `5:4`, `8:1`, `9:16`, `16:9`, `1:2`, `2:1`, `21:9`.
- [ ] Add failing tests for all Wan output entries: positive integer dimensions, ratio error at most 3%, and pixel area within the official tier ceiling (`1280*1280`, `2048*2048`, `4096*4096`).
- [ ] Add failing tests asserting reference images are supported at 1K/2K and rejected at 4K, while reference-free 4K is valid.
- [ ] Run `uv run pytest tests/test_image_capabilities.py -q` from `image-code` and confirm the new tests fail for the missing contract.
- [ ] Create a Wan-owned immutable size matrix. Preserve Alibaba's documented recommended dimensions for the documented ratios and explicitly list deterministic dimensions for the remaining platform ratios; include `1:4`, `4:1`, `1:8`, and `8:1` at 1K for the later smoke run.
- [ ] Refactor `ImageModelCapabilities` to hold `reference_supported_tiers` and expose `supports_references_for(render_tier)` plus `validate_operation(render_tier, ratio, *, has_references)`. Remove the model-wide `supports_references` boolean.
- [ ] Replace `_WAN_TIER_RATIO_SIZES` with the Wan-native matrix and set reference support to 1K/2K only. Update GPT and Nano declarations to the new per-tier contract.
- [ ] Run `uv run pytest tests/test_image_capabilities.py -q` and confirm green.
- [ ] Commit with `feat: define Wan image capability contract` and a body explaining the official tier, ratio, and reference limits.

## Task 2: Publish per-tier reference support in the model catalog

**Files:**

- Modify: `image-code/src/design_hub/interface/model_schemas.py`
- Modify: `image-code/src/design_hub/application/admin/model_config_service.py`
- Modify: `image-code/tests/test_model_catalog.py`

- [ ] Update catalog tests first: Wan must publish three tiers, all 16 ratios per tier, and `supports_references: false` only on 4K. GPT/Nano expectations must assert their per-tier values too.
- [ ] Remove the model-level `supports_references` field from `ImageModelCapabilitiesOut`; add `supports_references: bool` to `ImageRenderTierOut` so each selectable tier is self-describing.
- [ ] Populate the new field from `capabilities.supports_references_for(tier)` in `ModelConfigService.catalog`.
- [ ] Run `uv run pytest tests/test_model_catalog.py -q` and confirm green.
- [ ] Commit with `feat: expose tier operation limits` and a body explaining why capability filtering is catalog-driven.

## Task 3: Enforce 4K text-to-image-only on submission

**Files:**

- Modify: `image-code/src/design_hub/application/listing/submission_service.py`
- Modify: `image-code/tests/test_chat_image_options.py`
- Modify: `image-code/tests/test_submission_service.py`

- [ ] Add failing submission tests showing Wan 4K succeeds only when the operation has no source/reference image and fails fast for generate-with-upload, clone, edit, and background replacement.
- [ ] Add a focused helper that derives `has_references` from each request type. Call `capabilities.validate_operation(...)` before queue admission and before planning work; do not infer this limit inside the provider.
- [ ] Ensure ratio validation and reference validation share the same domain operation contract for listing routes and chat-generated requests.
- [ ] Run `uv run pytest tests/test_submission_service.py tests/test_chat_image_options.py -q` and confirm green.
- [ ] Commit with `feat: enforce Wan 4K operation limits` and a body describing the fail-fast boundary.

## Task 4: Allow the DashScope provider to execute validated 4K requests

**Files:**

- Modify: `image-code/src/design_hub/infrastructure/providers/factory.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/dashscope_wan.py`
- Modify: `image-code/tests/test_provider_factory.py`
- Modify: `image-code/tests/test_dashscope_wan.py`

- [ ] Add failing factory tests asserting the configured Wan provider can be built for 1K, 2K, and 4K.
- [ ] Add provider tests asserting extreme explicit dimensions are sent verbatim as `width*height`, including dimensions whose long side exceeds 8000 when the domain contract allows them.
- [ ] Remove the obsolete factory rejection for Wan 4K.
- [ ] Separate input-reference validation from output-spec validation: reference files retain provider input constraints, while generated output dimensions are accepted only when they match the validated `ImageOutputSpec`; do not apply the input-side 8000-pixel limit to outputs.
- [ ] Run `uv run pytest tests/test_provider_factory.py tests/test_dashscope_wan.py -q` and confirm green.
- [ ] Commit with `feat: execute Wan high-resolution outputs` and a body explaining the contract/provider responsibility split.

## Task 5: Make the chat selector context-aware

**Files:**

- Modify: `image-web/openapi.json` (generated from backend)
- Modify: `image-web/src/api/schema.d.ts` (generated by `npm run gen:api`)
- Modify: `image-web/src/lib/chat-image-options.ts`
- Modify: `image-web/src/lib/chat-image-options.test.ts`
- Modify: `image-web/src/components/chat/ChatComposer.tsx`
- Modify: `image-web/src/components/chat/ChatComposer.test.tsx`

- [ ] Export fresh OpenAPI JSON from `image-code` with the README command, then run `npm run gen:api` in `image-web`; never hand-edit either generated contract file.
- [ ] Add failing helper tests for a `hasReferences` parameter: Wan 4K is present with no references and removed once an upload or edit source exists; an invalid selected 4K tier normalizes to `auto`.
- [ ] Refactor `chatRenderTiersFor`, ratio derivation, and normalization to accept operation context and filter tiers by `supports_references`.
- [ ] Derive `hasReferences` in `ChatComposer` from `attached.length > 0 || selectedEditSource !== null`; use it consistently for tier options, ratio options, normalization, and capability summary text.
- [ ] Add component tests covering upload and edit-source transitions, including removal of a now-invalid 4K selection.
- [ ] Run `npm test -- --run src/lib/chat-image-options.test.ts src/components/chat/ChatComposer.test.tsx`, `npm run typecheck`, and `npm run build`.
- [ ] Commit with `feat: show valid Wan selector options` and a body describing server-driven context filtering.

## Task 6: Add and run the four-ratio live Wan smoke test

**Files:**

- Create: `image-code/scripts/smoke_wan_capabilities.py`
- Create: `image-code/tests/test_smoke_wan_capabilities.py`
- Create: `image-code/docs/superpowers/evidence/2026-08-06-wan-extreme-ratios.json`
- Runtime only: `image-code/exports/wan-capability-smoke/`

- [ ] Add unit tests around a pure result validator: exactly one result per requested ratio, actual dimensions read with Pillow, and actual/requested ratio error at most 3%. Test redaction and failure reporting without network calls.
- [ ] Implement an async command that resolves the enabled, verified `wan2.7-image-pro` configuration through the existing repository/cipher/resolver stack, submits one 1K text-to-image request for each of `1:4`, `4:1`, `1:8`, and `8:1`, resumes each task to completion, and copies/downloads each result into `exports/wan-capability-smoke/`.
- [ ] Use one stable neutral prompt whose composition works in all orientations. Record ratio, requested size, provider task ID, status, actual dimensions, ratio error, latency, and local artifact path. Never record credentials or signed provider URLs.
- [ ] Run `uv run pytest tests/test_smoke_wan_capabilities.py -q`.
- [ ] Run `uv run python scripts/smoke_wan_capabilities.py`. Do not retry a failed ratio under another size and do not proceed to release claims if any ratio fails.
- [ ] Inspect all four exported files with Pillow and visually review them. Write the redacted JSON evidence file with `passed: true` only if all four meet the contract.
- [ ] Commit with `test: verify Wan extreme aspect ratios` and a body listing the four task IDs and observed dimensions, without secrets or signed URLs.

## Task 7: Full verification and final handoff

**Files:**

- Verify all modified files from Tasks 1-6.

- [ ] Run backend quality gates from `image-code`: `uv run ruff check src tests scripts`, `uv run mypy`, and `uv run pytest -q`.
- [ ] Run frontend quality gates from `image-web`: `npm run lint`, `npm run typecheck`, `npm test`, and `npm run build`.
- [ ] Run `git diff --check`, `git status --short`, and review the full diff for generated-file drift, accidental credentials, legacy Wan/GPT coupling, and unrelated changes.
- [ ] If verification requires a code correction, make the smallest coherent refactor, rerun the affected focused tests and both final gate sets, then commit the correction before reporting.
- [ ] Report the three supported tiers, the 16 selector ratios, the 4K reference limitation, four task IDs/dimensions, local image links, commands run, and commits created. Do not claim deployment because no deployment or remote push is in scope.

## Coverage Self-Review

- Official capability coverage: 1K/2K/4K, continuous official range represented by all 16 platform ratios, 4K text-to-image only, and 2K reference/edit ceiling.
- Selector coverage: server contract, generated TypeScript types, context filtering, and normalization when references change.
- Runtime coverage: domain validation, submission validation, provider factory, explicit provider size payload, and returned-image validation.
- Evidence coverage: four user-requested ratios, one paid call each, recorded task IDs, actual dimensions, ratio tolerance, and visual inspection.
- No unresolved implementation placeholders remain; exact file paths, APIs, tests, commands, commits, and acceptance conditions are specified.
