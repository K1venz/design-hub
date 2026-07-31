# Backend live-runtime batch report (Tasks 6–11)

## Status

COMPLETE — delivered in the stable batch commit containing this report.

## Baseline and scope

- Worktree: `/Users/Zhuanz/CLAUDE/image-gen/.worktrees/live-model-config-wan`
- Required base: `84439ad3c9db7c7d06f6fb690ad9cef108cc2786`
- Initial status: clean
- Execution: Tasks 6–11 are being implemented as one final-architecture migration so
  production composition never enters an intermediate broken state.

## Architecture review

- `model_config` and `model_default` are already revisioned, encrypted, and verified.
- The remaining legacy runtime paths are startup registries, environment-backed image/chat
  construction, the synthetic `gpt-image-2-4k` provider ID, and Chat price confirmation.
- Final migration decision: stable configured model IDs remain unchanged across render tiers;
  4K is represented only by `RenderTier.FOUR_K`. No compatibility alias, shim, or fallback
  will be retained.

## TDD ledger

- Task 6: added live image/text resolver tests, observed missing-module RED, then
  implemented revision-keyed adapter caches with per-call DB availability and
  verification checks.
- Task 7: added DashScope Wan submit/poll/download contract tests, observed RED,
  then implemented the async provider and connected it through the live factory.
- Task 8: added image/chat capability probe tests, observed RED, then implemented
  the manager-scoped test service and admin endpoint.
- Task 9: added required `image_model` request tests, observed validation RED, then
  removed registry pricing from planning and froze the selected DB model/cost on
  each item.
- Task 10: migrated worker tests to the async resolver contract and verified live
  resolution immediately before execution and resume.
- Task 11: migrated Chat and reverse-prompt tests to live text resolution, stable
  image IDs, tier-only 4K intent, and price-free generation confirmation.

## Implemented architecture

- Production image and Chat connections are read from verified model configuration
  rows for every operation; only constructed adapters are cached by exact revision.
- GPT standard and 4K execution share stable ID `gpt-image-2`; 4K is represented by
  `RenderTier.FOUR_K` and requires the dedicated credential, 16:9, and one image.
- Wan 2.7 uses the documented DashScope async task API, bounded I/O retries/polling,
  strict image/reference validation, and immediate result persistence.
- Listing submissions require an explicit selected image model and snapshot its DB
  unit cost without consulting a startup registry.
- Worker, Chat, reverse prompt, admin capability testing, and ASGI composition now
  use the live resolver/factory path. Production environment settings retain only
  operational timeouts/retry/concurrency budgets.
- Chat write tools cannot choose or override the selected image model. Confirmation
  emits `generation_confirm` with model identity/display name and count, without
  user-facing price fields.

## Commits

One coherent commit is used because Tasks 6–11 replace the same composition graph;
splitting them would leave non-runnable intermediate commits.

## Verification

- Required convergence group:
  `214 passed in 2.82s`.
- Full Task 6–11 brief-focused batch:
  `276 passed, 2 skipped in 4.33s`.
- `uv run ruff check src tests`: passed.
- `uv run mypy`: passed (`147 source files`).
- Pytest emitted two pre-existing aiosqlite shutdown thread warnings from
  `tests/test_reverse_prompt.py`; all assertions passed.

## Blockers

None.

## Deferred minor brief items

- No standalone `tests/test_chat_knowledge.py` was added during the final
  budget-constrained convergence pass. The knowledge document was updated to remove
  fixed prices and fee-confirmation claims, but a follow-up should add the dedicated
  content contract test and complete the explicit model/page/unpublished-wallet copy
  requested by Task 11.
- `admin_console_repo.py` still contains the historical synthetic 4K model name in
  stale-call timeout classification. Runtime call attribution already records stable
  configured IDs, but a follow-up should make timeout classification tier-aware once
  render tier is available on model-call records.
