# Task 12 report: secure one-time model bootstrap

## Status

COMPLETE — ready for the stable Task 12 commit.

## Baseline and scope

- Required base: `19be6fd13a112d733394b45369f19dc510adf4ce`
- Implementation scope:
  - `image-code/src/design_hub/cli/__init__.py`
  - `image-code/src/design_hub/cli/bootstrap_models.py`
  - `image-code/tests/test_bootstrap_models.py`
  - `image-code/README.md`
- No private or user-provided CSV was read, copied, printed, or committed.
- Unrelated concurrent worktree changes were preserved and excluded from this task.

## TDD evidence

1. The focused suite first failed at collection because `design_hub.cli` did not
   exist.
2. Minimal importable command interfaces were added, after which the suite
   produced eight expected behavioral failures from unimplemented bootstrap
   operations.
3. The secure bootstrap implementation made the same eight tests pass.

## Implemented behavior

- Requires the existing persistent `AUTH_RSA_PRIVATE_KEY_PEM`; it never
  generates an ephemeral bootstrap key.
- Reads legacy `GPT_IMAGE_*` and `TEXT_LLM_*` values only inside the explicit
  command process.
- Requires an absolute Wan CSV path outside the repository and accepts only the
  three vertical fields `apiKey`, `apiHost`, and `dashScope`.
- Restricts Wan to the native DashScope endpoint
  `https://dashscope.aliyuncs.com/api/v1`; compatible-mode and arbitrary hosts
  fail fast.
- Encrypts GPT standard keys independently, encrypts the GPT 4K key
  independently, and separately encrypts the Wan and Chat keys.
- Uses the existing `ModelCapabilityService` for real image generation/edit and
  Chat text/tool checks, then uses `ModelConfigService` to persist the verified
  configuration.
- Enables a model only after its exact real capability check passes, stops at
  the first failure, and keeps the failing migration skeleton disabled.
- Sets GPT as the image default and Doubao as the Chat default after their
  successful checks.
- Emits only fixed model IDs with `success` or `failure`; unexpected failures
  are reduced to a generic status without exception details.

## Secret-safety coverage

- Tests use only generated RSA keys, temporary environment values, a temporary
  SQLite database, and a temporary synthetic CSV.
- Tests verify plaintext credentials never enter model configuration storage.
- Tests decrypt each stored field with the persistent test key to prove
  field-by-field encryption.
- Tests verify stdout and stderr exclude plaintext credentials, ciphertext,
  CSV content, and the full input path on success and failure.
- Input and model failure exceptions suppress their original causes and contain
  no input details.

## Verification

- `uv run pytest tests/test_bootstrap_models.py -q`
  - `8 passed in 1.80s`
- `uv run ruff check src/design_hub/cli tests/test_bootstrap_models.py`
  - `All checks passed!`
- `uv run mypy`
  - `Success: no issues found in 149 source files`

The user-authorized streamlined CI scope was used: focused bootstrap tests,
Task 12-related Ruff checks, and the complete configured MyPy source check.

## Blockers

None.
