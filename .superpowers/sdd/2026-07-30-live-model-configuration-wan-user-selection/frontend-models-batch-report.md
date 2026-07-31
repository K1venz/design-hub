# Frontend Models Batch Report

Date: 2026-07-31  
Scope: Tasks 13–17  
Branch: `codex/live-model-config-wan`  
Commit: the commit containing this report

## Delivered

- Added one authenticated image-model catalog query and a shared route gate for
  Chat plus all four image workbenches.
- Added per-user persisted model selection. A valid saved selection wins over
  the server default; a removed or disabled selection becomes an explicit
  selection-required state and is never silently replaced.
- Added loading, retryable error, empty-catalog, selection-required, ready, and
  runtime-locked selector states.
- Sent the selected stable model ID as `image_model` through listing, set,
  clone, edit, background removal, and Chat generation requests.
- Preserved form, upload, and Chat draft state when a selected model becomes
  unavailable, then refreshed the catalog for an explicit reselection.
- Replaced Chat price confirmation with a generation confirmation snapshot
  containing only the stable model ID, display name, tool, and image count.
- Rebuilt the administrator model form around typed image/chat providers,
  exact provider-specific credential and extra fields, independently encrypted
  secrets, real capability tests, proof invalidation on runtime edits, and
  immediate runtime activation.
- Added administrator catalog filters, stable/default identity display, and
  verification metadata while retaining administrator-only internal pricing.
- Removed active user-generation price copy from home, workbenches, Chat,
  history, and style previews.
- Exposed the stored stable model ID in listing history without resolving it
  against the live catalog.
- Added the minimal backend response fields and stale-model error signaling
  required by the frontend contract, then regenerated OpenAPI artifacts.

## Verification

- `npm run gen:api` — passed; `src/api/schema.d.ts` regenerated from the final
  `openapi.json`.
- `npm run typecheck` — passed.
- `npm run lint` — passed.
- Focused Vitest command covering model persistence/selector, all request
  builders, Chat confirmation, credential encryption, administrator form,
  home, and style-preview data — 10 test files and 82 tests passed.
- Active user-generation pricing scan across `src/pages`, `src/components`,
  and `src/lib`, excluding administrator surfaces, legal pages, tests, and the
  administrator currency formatter — zero matches for `¥`, `RMB`, `元/张`,
  `套餐价`, `费用`, `价格`, `cost_confirm`, `estimateCost`, and
  `LISTING_UNIT_COST`.
- `git diff --check` — passed.

## Notes

- Administrator internal cost fields were intentionally retained.
- The legacy `cost_confirm` token remains only in a parser rejection test to
  prove that it is no longer an accepted Chat event.
- No wallet, billing, migration, compatibility adapter, or remote repository
  work was added.
