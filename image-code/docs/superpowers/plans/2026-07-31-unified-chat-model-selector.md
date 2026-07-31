# Unified Chat Model Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Replace the Chat page's image-only picker with the selected C-style compact selector and make both the chosen text model and image model drive the real request path.

**Architecture:** Expose authenticated catalogs for both model types from the existing verified model registry. Keep model choice account-scoped in one generic frontend store, require both choices before sending, and pass the selected text model through the Chat request and pending-confirmation flow. Reverse-prompt remains on the administrator's default text model because it has no user-facing model selector.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, pytest, React 19, TypeScript, Zustand, TanStack Query, Radix Dropdown Menu, Vitest.

**Global constraints:** Do not expose credentials, cost, or provider connection fields. Do not silently fall back when a stored model disappears. Do not add schema migration or compatibility code; this feature changes only request/API contracts and browser selection keys. Keep the UI functional for unknown future model IDs with a neutral icon.

---

## Task 1: Add a shared public model catalog

**Files:**
- Modify: `image-code/tests/test_model_catalog.py`
- Modify: `image-code/src/design_hub/application/admin/model_config_service.py`
- Modify: `image-code/src/design_hub/interface/model_schemas.py`
- Modify: `image-code/src/design_hub/interface/api/routes/models.py`

- [ ] Add failing tests proving `/models/chat` returns only enabled, currently verified Chat models and never leaks provider, cost, URL, or credential fields.
- [ ] Refactor `image_catalog()` into `catalog(model_type)` and expose both `/models/image` and `/models/chat` using one `ModelCatalogItemOut` schema.
- [ ] Run `cd image-code && uv run pytest tests/test_model_catalog.py -q`.
- [ ] Commit as `feat: expose selectable model catalogs` with a detailed body.

## Task 2: Make Chat use the selected text model end to end

**Files:**
- Modify: `image-code/tests/test_live_model_resolution.py`
- Modify: `image-code/tests/test_chat.py`
- Modify: `image-code/tests/test_chat_sse.py`
- Modify: `image-code/src/design_hub/ports/model_resolution.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/live_resolution.py`
- Modify: `image-code/src/design_hub/interface/chat_schemas.py`
- Modify: `image-code/src/design_hub/interface/api/routes/chat.py`
- Modify: `image-code/src/design_hub/application/chat/pending_store.py`
- Modify: `image-code/src/design_hub/application/chat/orchestrator.py`

- [ ] Add failing resolver tests for explicit Chat model IDs, including disabled, stale-verification, missing, and revision-cache behavior.
- [ ] Add failing Chat tests proving `chat_model` is required, is resolved explicitly during planning, and is retained across generation confirmation.
- [ ] Add `TextLLMResolver.resolve(model_id)` while retaining `resolve_default()` solely for flows such as reverse prompt that have no selector.
- [ ] Thread the required `chat_model` through the request route, orchestrator, and pending action; use it again after confirmation.
- [ ] Run `cd image-code && uv run pytest tests/test_live_model_resolution.py tests/test_chat.py tests/test_chat_sse.py tests/test_reverse_prompt.py -q`.
- [ ] Commit as `feat: route chat through selected text model` with a detailed body.

## Task 3: Unify account-scoped model selection on the frontend

**Files:**
- Add: `image-web/src/stores/model-selection-store.ts`
- Add: `image-web/src/stores/model-selection-store.test.ts`
- Delete: `image-web/src/stores/image-model-store.ts`
- Delete: `image-web/src/stores/image-model-store.test.ts`
- Modify: `image-web/src/components/models/ImageModelGate.tsx`
- Modify: `image-web/src/api/models.ts`
- Modify: `image-web/src/api/chat.ts`
- Modify: `image-web/src/api/chat.test.ts`
- Modify generated contract: `image-web/openapi.json`
- Modify generated contract: `image-web/src/api/schema.d.ts`

- [ ] Add failing store tests for independent Chat/image defaults, account isolation, explicit re-selection after a removed model, and invalid selection rejection.
- [ ] Replace the image-only Zustand store with one generic two-kind store using `model-selection:<kind>:<user>` keys; update `ImageModelGate` to use its image slice.
- [ ] Add `useChatModels()` and include required `chat_model` in the Chat request body.
- [ ] Export the backend OpenAPI document with `uv run`, regenerate TypeScript via `npm run gen:api`, and run the focused Vitest tests.
- [ ] Commit as `feat: persist text and image model choices` with a detailed body.

## Task 4: Ship the C-style selector in the real Chat composer

**Files:**
- Add: `image-web/src/components/models/UnifiedChatModelSelector.tsx`
- Add: `image-web/src/components/models/UnifiedChatModelSelector.test.tsx`
- Modify: `image-web/src/pages/ChatPage.tsx`
- Delete if unused: `image-web/src/components/models/ImageModelSelector.tsx`
- Delete if unused: `image-web/src/components/models/ImageModelSelector.test.tsx`

- [ ] Add failing component tests for the dual-segment trigger, grouped model items, unknown-brand icon, busy state, and independent error/empty/re-selection states.
- [ ] Build the production C selector from real catalogs: text segment, divider, image segment, shared dropdown, search, checkmarks, and compact responsive labels.
- [ ] Move the selector beside the send button, remove the page-top image selector, require both models before auto-send/manual send/reverse-prompt, and refresh both catalogs after `model_unavailable`.
- [ ] Preserve the user's draft and attachments when either selected model becomes unavailable; use wording that covers both model types.
- [ ] Run focused frontend tests, typecheck, and a production build.
- [ ] Commit as `feat: add compact chat model selector` with a detailed body.

## Task 5: Remove the demo and verify the integrated feature

**Files:**
- Modify: `image-web/src/App.tsx`
- Delete: `image-web/src/pages/model-selector-demo/`
- Retain: `image-web/public/model-brands/*.svg`

- [ ] Remove the DEV demo route, lazy import, demo components, and fixtures; verify the production selector owns the retained logo assets.
- [ ] Run `cd image-code && uv run pytest tests/test_model_catalog.py tests/test_live_model_resolution.py tests/test_chat.py tests/test_chat_sse.py tests/test_reverse_prompt.py -q`.
- [ ] Run `cd image-web && npm test -- --run && npm run typecheck && npm run build`.
- [ ] Inspect the real `/chat` page at desktop and narrow viewport; verify model switching, disabled state while streaming, and no overflow.
- [ ] Confirm `git diff --check` and review the final diff for credentials or generated artifacts that do not belong.
- [ ] Commit as `chore: remove model selector demo` with a detailed body, then report the completed branch without pushing unless the user asks.
