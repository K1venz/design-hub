# Live Model Configuration, Wan 2.7, and User Model Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace startup-only image/chat configuration with verified database-backed live configuration, add `wan2.7-image-pro`, and let each user select one enabled image model consistently across every generation entry point without exposing prices.

**Architecture:** `model_config` becomes the sole runtime source for image and chat providers. Submission resolves and snapshots an enabled stable image-model ID plus render tier and internal cost; the worker resolves the exact model revision immediately before execution and constructs the matching protocol adapter. GPT Image remains an OpenAI-compatible synchronous adapter, Wan uses a resumable DashScope asynchronous adapter, and Chat/reverse-prompt obtain the current default chat provider through a live resolver. The React app consumes one user-safe image catalog and one per-user persisted selector shared by the four workbenches and Chat.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy async, Alembic, httpx, PyJWT, cryptography, Redis Streams, React 19, TypeScript 6, Zustand, TanStack Query 5, Tailwind 4, Vitest.

## Global Constraints

- Follow the approved design in `image-code/docs/plans/2026-07-30-live-model-configuration-wan-user-selection-design.md`.
- Supported provider protocols are exactly `openai_compat_image`, `dashscope_wan_image`, and `openai_compat_chat`.
- Do not add arbitrary JSON request templates, protocol auto-detection, provider fallbacks, automatic model switching, compatibility shims, or `.env` runtime fallback.
- A newly supported protocol requires a code adapter and tests before it can appear in the administrator form.
- `gpt-image-2-4k` is not a selectable model. It becomes `RenderTier.FOUR_K` under the stable model ID `gpt-image-2`.
- Stable image model IDs are strings in task/domain persistence. Remove the static image-model enum and adapt old code to the new type.
- The database stores only RSA-OAEP-SHA256 ciphertext for provider credentials. APIs, audit logs, exceptions, structured logs, and frontend state must never expose ciphertext or plaintext.
- Multi-key fields are arrays of independently encrypted ciphertexts. Never concatenate two
  API keys before RSA encryption because RSA-2048 OAEP-SHA256 has a bounded plaintext size.
- Production requires persistent `AUTH_RSA_PRIVATE_KEY_PEM`; a missing or invalid key must fail startup when encrypted model credentials are in use.
- A configuration can be enabled only after a real capability test of the exact connection fingerprint:
  - image provider: one generation and one edit;
  - chat provider: streamed text and a required tool call.
- The capability test returns a short-lived signed proof. Saving or enabling verifies the proof against the exact configuration fingerprint; changing a runtime field or credential invalidates it.
- `display_name` and `unit_cost` do not affect the connection fingerprint. Runtime fields and decrypted credential digests do.
- Saving a valid configuration affects the next API/Worker operation without restart. No Redis configuration event is added.
- The image catalog contains enabled and verified image models only. It never contains credentials, base URLs, upstream model IDs, internal costs, or verification fingerprints.
- User selection is persisted by `user_id`. A missing stored selection may initialize from the configured image default; a stale stored selection is cleared and requires explicit reselection. Never silently switch from one previously selected model to another.
- Every generation request carries `image_model`. The server rejects missing, disabled, unverified, or wrong-type selections.
- Chat's LLM cannot override the user's selected image model. A pending Chat generation action snapshots that model through confirmation.
- User-facing model prices remain hidden. Internal platform cost, quota protection, and administrator cost views remain.
- Initial internal skeleton costs are GPT standard `0.05`, Wan `0.50`, and Chat `0.00`.
  Keep the existing GPT 4K internal render-tier cost `0.18` until the separate wallet/pricing
  project replaces platform-protection accounting; none of these values are user-visible.
- Frontend Loading/Error/Empty/stale-selection/submission-race states are required behavior, not optional polish.
- The provided Wan CSV is one-time local input only. Never copy it into the repository, fixtures, build context, logs, command output, or commits.
- No new dependency is expected. If implementation requires one, stop and explain before using `uv add` or `npm install`.
- Run Python only through `uv run`.
- Stage only the files named by the current task because the worktree contains unrelated user changes.

---

## File Map

### Backend files to create

- `image-code/migrations/versions/d7e8f9a0b1c2_live_model_configuration.py` — rebuild the model registry schema and seed non-secret GPT/Wan/Doubao skeletons.
- `image-code/src/design_hub/domain/model_config.py` — model/provider enums, stable IDs, connection record/value objects, and fingerprint input.
- `image-code/src/design_hub/ports/secret_cipher.py` — generic RSA secret transport/at-rest cipher port.
- `image-code/src/design_hub/infrastructure/security/rsa_secret_cipher.py` — persistent RSA-OAEP-SHA256 implementation.
- `image-code/src/design_hub/ports/model_verification.py` — signed verification-proof port and capability-test result types.
- `image-code/src/design_hub/infrastructure/security/model_verification.py` — short-lived HS256 proof implementation.
- `image-code/src/design_hub/ports/model_resolution.py` — image executor and text LLM live-resolver protocols.
- `image-code/src/design_hub/infrastructure/providers/factory.py` — allowlisted provider construction from one decrypted model record.
- `image-code/src/design_hub/infrastructure/providers/live_resolution.py` — revision-keyed image and chat resolvers.
- `image-code/src/design_hub/infrastructure/providers/dashscope_wan.py` — Wan async submit/resume/poll/download adapter.
- `image-code/src/design_hub/application/admin/model_capability_service.py` — real image/chat test orchestration and proof issuance.
- `image-code/src/design_hub/interface/model_schemas.py` — user-safe model catalog response.
- `image-code/src/design_hub/interface/api/routes/models.py` — authenticated image catalog endpoint.
- `image-code/src/design_hub/cli/bootstrap_models.py` — one-time secure model bootstrap command.
- `image-code/tests/test_live_model_config_migration.py`
- `image-code/tests/test_secret_cipher.py`
- `image-code/tests/test_model_verification.py`
- `image-code/tests/test_model_catalog.py`
- `image-code/tests/test_live_model_resolution.py`
- `image-code/tests/test_dashscope_wan.py`
- `image-code/tests/test_model_capability_service.py`
- `image-code/tests/test_bootstrap_models.py`
- `image-code/tests/test_chat_knowledge.py`

### Backend files to delete

- `image-code/src/design_hub/ports/password_cipher.py`
- `image-code/src/design_hub/infrastructure/auth/rsa_cipher.py`

### Backend files to modify

- `image-code/src/design_hub/config/settings.py`
- `image-code/src/design_hub/domain/enums.py`
- `image-code/src/design_hub/domain/tasking.py`
- `image-code/src/design_hub/ports/model_provider.py`
- `image-code/src/design_hub/ports/provider_execution.py`
- `image-code/src/design_hub/ports/model_config_repository.py`
- `image-code/src/design_hub/application/registry.py`
- `image-code/src/design_hub/application/admin/model_config_service.py`
- `image-code/src/design_hub/application/listing/requests.py`
- `image-code/src/design_hub/application/listing/sizing.py`
- `image-code/src/design_hub/application/listing/task_planner.py`
- `image-code/src/design_hub/application/listing/submission_service.py`
- `image-code/src/design_hub/application/tasking/worker.py`
- `image-code/src/design_hub/application/chat/rendering_intent.py`
- `image-code/src/design_hub/application/chat/pending_store.py`
- `image-code/src/design_hub/application/chat/orchestrator.py`
- `image-code/src/design_hub/application/image_prompts/reverse_prompt.py`
- `image-code/src/design_hub/infrastructure/db/models.py`
- `image-code/src/design_hub/infrastructure/db/model_config_repo.py`
- `image-code/src/design_hub/infrastructure/db/generation_work_repo.py`
- `image-code/src/design_hub/infrastructure/db/admin_console_repo.py`
- `image-code/src/design_hub/infrastructure/providers/openai_compat.py`
- `image-code/src/design_hub/infrastructure/queue/redis_slots.py`
- `image-code/src/design_hub/interface/admin_schemas.py`
- `image-code/src/design_hub/interface/chat_schemas.py`
- `image-code/src/design_hub/interface/auth_schemas.py`
- `image-code/src/design_hub/interface/api/deps.py`
- `image-code/src/design_hub/interface/api/admin_deps.py`
- `image-code/src/design_hub/interface/api/routes/admin.py`
- `image-code/src/design_hub/interface/api/routes/auth.py`
- `image-code/src/design_hub/interface/api/routes/chat.py`
- `image-code/src/design_hub/interface/api/routes/listing.py`
- `image-code/src/design_hub/interface/api/asgi.py`
- `image-code/src/design_hub/interface/worker.py`
- `image-code/src/design_hub/composition.py`
- `image-code/src/design_hub/config/chat_knowledge.md`
- Existing backend tests that construct `ModelName`, model configs, listing requests, Chat events, or process composition.

### Frontend files to create

- `image-web/src/api/models.ts` — user image catalog query.
- `image-web/src/stores/image-model-store.ts` — per-user selection state and persistence.
- `image-web/src/components/models/ImageModelSelector.tsx` — shared robust selector.
- `image-web/src/components/models/ImageModelGate.tsx` — Loading/Error/Empty/stale-selection shell.
- `image-web/src/components/models/ImageModelSelector.test.tsx`
- `image-web/src/stores/image-model-store.test.ts`
- `image-web/src/components/admin/ModelConfigDialog.test.tsx`

### Frontend files to modify

- `image-web/src/api/crypto.ts`
- `image-web/src/api/crypto.test.ts`
- `image-web/src/api/admin.ts`
- `image-web/src/api/listing.ts`
- `image-web/src/api/listing.test.ts`
- `image-web/src/api/chat.ts`
- `image-web/src/api/chat.test.ts`
- `image-web/src/api/schema.d.ts` (generated)
- `image-web/src/lib/listing.ts`
- `image-web/src/lib/listing.test.ts`
- `image-web/src/lib/chat.ts`
- `image-web/src/lib/chat.test.ts`
- `image-web/src/lib/home.ts`
- `image-web/src/lib/home.test.ts`
- `image-web/src/stores/workbench-store.ts`
- `image-web/src/components/listing/ListingConfigPanel.tsx`
- `image-web/src/components/listing/CloneConfigPanel.tsx`
- `image-web/src/components/listing/EditConfigPanel.tsx`
- `image-web/src/components/listing/BackgroundConfigPanel.tsx`
- `image-web/src/pages/WorkbenchPage.tsx`
- `image-web/src/pages/CloneWorkbenchPage.tsx`
- `image-web/src/pages/EditWorkbenchPage.tsx`
- `image-web/src/pages/BackgroundWorkbenchPage.tsx`
- `image-web/src/pages/ChatPage.tsx`
- `image-web/src/pages/HistoryPage.tsx`
- `image-web/src/pages/HistoryDetailPage.tsx`
- `image-web/src/pages/AdminModelsPage.tsx`
- `image-web/src/components/admin/ModelConfigDialog.tsx`
- `image-web/src/components/admin/ModelRowActions.tsx`
- `image-web/openapi.json` (generated)

---

### Task 1: Model Registry Domain and Database Migration

**Files:**
- Create: `image-code/src/design_hub/domain/model_config.py`
- Create: `image-code/migrations/versions/d7e8f9a0b1c2_live_model_configuration.py`
- Create: `image-code/tests/test_live_model_config_migration.py`
- Modify: `image-code/src/design_hub/infrastructure/db/models.py`
- Modify: `image-code/src/design_hub/domain/enums.py`

**Contract:**

```python
from enum import StrEnum


class ModelType(StrEnum):
    IMAGE = "image"
    CHAT = "chat"


class ProviderType(StrEnum):
    OPENAI_COMPAT_IMAGE = "openai_compat_image"
    DASHSCOPE_WAN_IMAGE = "dashscope_wan_image"
    OPENAI_COMPAT_CHAT = "openai_compat_chat"


GPT_IMAGE_2 = "gpt-image-2"
WAN_2_7_IMAGE_PRO = "wan2.7-image-pro"
DOUBAO_CHAT = "doubao-chat"
```

- [ ] **Step 1: Write failing migration tests**

Assert after upgrade:

- `model_config` contains the approved columns and no `api_key_env` or `is_default`.
- `model_default` has one row per model type and a same-type composite foreign key.
- skeleton rows are exactly GPT Image, Wan, and Doubao; no Mock rows and no `gpt-image-2-4k`.
- all skeletons are disabled and have empty credential JSON.
- migration revision is `d7e8f9a0b1c2`, down revision is current head `b8c9d0e1f2a3`.

Run:

```bash
cd /Users/Zhuanz/CLAUDE/image-gen/image-code
uv run pytest tests/test_live_model_config_migration.py -q
```

Expected: FAIL because the migration and new domain types do not exist.

- [ ] **Step 2: Implement the domain records and ORM**

Use a string stable ID everywhere. Define `ModelConfigRecord` later against these enums; do not retain `ModelName`.

The ORM shape is:

```python
class ModelConfig(Base):
    __tablename__ = "model_config"
    __table_args__ = (
        UniqueConstraint("model_type", "name", name="uq_model_config_type_name"),
    )

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128))
    model_type: Mapped[str] = mapped_column(String(16), index=True)
    provider_type: Mapped[str] = mapped_column(String(32))
    base_url: Mapped[str] = mapped_column(String(255))
    model: Mapped[str] = mapped_column(String(128))
    credentials_ciphertext: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_fingerprint: Mapped[str | None] = mapped_column(String(64))
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ModelDefault(Base):
    __tablename__ = "model_default"

    model_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(64))
```

Add the composite foreign key in `__table_args__`. Rebuild the old table in the migration so legacy-only columns and rows are removed cleanly; do not preserve unsupported old rows.

- [ ] **Step 3: Run the focused tests and schema upgrade**

```bash
uv run pytest tests/test_live_model_config_migration.py -q
uv run alembic upgrade head
uv run alembic heads
```

Expected: tests PASS and Alembic prints only `d7e8f9a0b1c2 (head)`.

- [ ] **Step 4: Commit**

```bash
git add image-code/src/design_hub/domain/model_config.py \
  image-code/src/design_hub/domain/enums.py \
  image-code/src/design_hub/infrastructure/db/models.py \
  image-code/migrations/versions/d7e8f9a0b1c2_live_model_configuration.py \
  image-code/tests/test_live_model_config_migration.py
git commit -m "refactor: rebuild live model registry" \
  -m "Replace the legacy image-only startup configuration with typed image and chat model records, explicit defaults, verification metadata, revisions, and non-secret GPT, Wan, and Doubao skeletons."
```

---

### Task 2: Generalize RSA Secret Encryption

**Files:**
- Create: `image-code/src/design_hub/ports/secret_cipher.py`
- Create: `image-code/src/design_hub/infrastructure/security/__init__.py`
- Create: `image-code/src/design_hub/infrastructure/security/rsa_secret_cipher.py`
- Create: `image-code/tests/test_secret_cipher.py`
- Modify: `image-code/src/design_hub/config/settings.py`
- Modify: `image-code/src/design_hub/composition.py`
- Modify: `image-code/src/design_hub/interface/api/deps.py`
- Modify: `image-code/src/design_hub/interface/api/routes/auth.py`
- Modify: `image-code/tests/test_auth.py`
- Delete: `image-code/src/design_hub/ports/password_cipher.py`
- Delete: `image-code/src/design_hub/infrastructure/auth/rsa_cipher.py`

- [ ] **Step 1: Write failing generic-cipher tests**

Test:

- generated and PEM-loaded keys round-trip arbitrary UTF-8 secrets;
- malformed base64 and invalid ciphertext raise sanitized `ValueError`;
- a persistent PEM decrypts ciphertext across two instances;
- the public-key endpoint still returns SPKI PEM;
- no password-named cipher type or module remains imported.

Run:

```bash
uv run pytest tests/test_secret_cipher.py tests/test_auth.py -q
```

Expected: FAIL because `SecretCipher` and `RsaSecretCipher` do not exist.

- [ ] **Step 2: Implement the generic port and RSA class**

```python
class SecretCipher(ABC):
    @abstractmethod
    def public_key_pem(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def encrypt(self, plaintext: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def decrypt(self, ciphertext_b64: str) -> str:
        raise NotImplementedError
```

Keep RSA-OAEP with SHA-256 and a 2048-bit key. Use one sanitized message, `敏感信息解密失败，请刷新页面后重试`, for untrusted ciphertext errors. Authentication converts that to its password-specific user copy at the route boundary.

Rename `build_password_cipher` to `build_secret_cipher`, `PasswordCipherDep` to `SecretCipherDep`, and `app.state.password_cipher` to `app.state.secret_cipher`. Update old authentication code directly; do not leave aliases.

- [ ] **Step 3: Enforce production persistence**

Add `Settings.require_persistent_secret_cipher: bool = False`. API/Worker production entry points set this from deployment configuration. When true and `AUTH_RSA_PRIVATE_KEY_PEM` is empty, `build_secret_cipher` raises at startup. Local tests may continue to generate an ephemeral key.

- [ ] **Step 4: Run tests and static checks**

```bash
uv run pytest tests/test_secret_cipher.py tests/test_auth.py -q
uv run ruff check src tests/test_secret_cipher.py tests/test_auth.py
uv run mypy
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add image-code/src/design_hub/ports/secret_cipher.py \
  image-code/src/design_hub/infrastructure/security \
  image-code/src/design_hub/config/settings.py \
  image-code/src/design_hub/composition.py \
  image-code/src/design_hub/interface/api/deps.py \
  image-code/src/design_hub/interface/api/routes/auth.py \
  image-code/tests/test_secret_cipher.py image-code/tests/test_auth.py \
  image-code/src/design_hub/ports/password_cipher.py \
  image-code/src/design_hub/infrastructure/auth/rsa_cipher.py
git commit -m "refactor: generalize RSA secret encryption" \
  -m "Use one persistent RSA-OAEP secret cipher for authentication and encrypted provider credentials, remove password-specific abstractions, and fail startup when production requires a missing private key."
```

---

### Task 3: Signed Verification Proofs and Connection Fingerprints

**Files:**
- Create: `image-code/src/design_hub/ports/model_verification.py`
- Create: `image-code/src/design_hub/infrastructure/security/model_verification.py`
- Create: `image-code/tests/test_model_verification.py`
- Modify: `image-code/src/design_hub/domain/model_config.py`
- Modify: `image-code/src/design_hub/config/settings.py`

- [ ] **Step 1: Write failing proof and fingerprint tests**

Cover:

- canonical fingerprints are key-order independent;
- display name and unit cost do not change the fingerprint;
- base URL, upstream model, provider type, allowed extra, or secret plaintext changes it;
- secret plaintext is represented only by SHA-256 digest in canonical input;
- proof is bound to manager ID, model ID, model type, fingerprint, and expiry;
- expired, tampered, wrong-manager, wrong-model, and wrong-fingerprint proofs fail.

Run:

```bash
uv run pytest tests/test_model_verification.py -q
```

Expected: FAIL.

- [ ] **Step 2: Implement canonical fingerprinting**

```python
def connection_fingerprint(
    *,
    model_type: ModelType,
    provider_type: ProviderType,
    base_url: str,
    upstream_model: str,
    extra: Mapping[str, object],
    credentials_plaintext: Mapping[str, str | tuple[str, ...]],
) -> str:
    credential_digests: dict[str, str | list[str]] = {}
    for key, value in sorted(credentials_plaintext.items()):
        if isinstance(value, tuple):
            credential_digests[key] = [
                hashlib.sha256(item.encode()).hexdigest() for item in value
            ]
        else:
            credential_digests[key] = hashlib.sha256(value.encode()).hexdigest()
    payload = {
        "base_url": base_url.rstrip("/"),
        "credentials": credential_digests,
        "extra": dict(sorted(extra.items())),
        "model": upstream_model,
        "model_type": model_type.value,
        "provider_type": provider_type.value,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
```

Validate Provider-specific credential keys and extras before computing the fingerprint. Reject unknown fields.

- [ ] **Step 3: Implement short-lived proof signing**

Use HS256 with `Settings.jwt_secret`, a dedicated audience `model-config-verification`, and `Settings.model_verification_ttl_seconds = 600`. Do not reuse authentication claims or return decoded proof payloads.

- [ ] **Step 4: Run tests and checks**

```bash
uv run pytest tests/test_model_verification.py -q
uv run ruff check src tests/test_model_verification.py
uv run mypy
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add image-code/src/design_hub/domain/model_config.py \
  image-code/src/design_hub/ports/model_verification.py \
  image-code/src/design_hub/infrastructure/security/model_verification.py \
  image-code/src/design_hub/config/settings.py \
  image-code/tests/test_model_verification.py
git commit -m "feat: bind model saves to verified connections" \
  -m "Add canonical secret-safe connection fingerprints and short-lived manager-bound proofs so only the exact tested runtime configuration can be enabled."
```

---

### Task 4: Refactor Model Repository, Admin API, and User Catalog

**Files:**
- Modify: `image-code/src/design_hub/ports/model_config_repository.py`
- Modify: `image-code/src/design_hub/infrastructure/db/model_config_repo.py`
- Modify: `image-code/src/design_hub/application/admin/model_config_service.py`
- Modify: `image-code/src/design_hub/interface/admin_schemas.py`
- Modify: `image-code/src/design_hub/interface/api/routes/admin.py`
- Create: `image-code/src/design_hub/interface/model_schemas.py`
- Create: `image-code/src/design_hub/interface/api/routes/models.py`
- Create: `image-code/tests/test_model_catalog.py`
- Modify: `image-code/tests/test_model_config.py`

**Repository interface:**

```python
@dataclass(frozen=True)
class ModelConfigRecord:
    name: str
    display_name: str
    model_type: ModelType
    provider_type: ProviderType
    base_url: str
    model: str
    credentials_ciphertext: dict[str, str | list[str]]
    unit_cost: Decimal
    enabled: bool
    revision: int
    verified_at: datetime | None
    verified_fingerprint: str | None
    extra: dict[str, object]
```

- [ ] **Step 1: Replace legacy model-config tests**

Test:

- create/update round-trip all non-secret fields;
- output reports `has_credentials` and required credential-field booleans only;
- output contains neither ciphertext nor credential digest;
- connection-field updates increment revision and clear verification;
- display-name/unit-cost updates do not clear verification;
- credentials can be retained by omitting them and replaced by providing new ciphertext;
- creating a connection or changing connection fields requires a valid proof matching the
  recomputed fingerprint, even when the row will remain disabled;
- enabling an already saved row requires its stored verification fingerprint to match its
  current connection fingerprint;
- default selection is transactional, same-type only, enabled, and verified;
- deletion of an active default fails;
- deletion of a model referenced by a non-terminal generation item fails;
- audit snapshots contain `credentials_changed` only;
- `GET /models/image` returns enabled verified image models, marks the enabled configured
  default exactly once, and returns an empty list before any model is activated.

Run:

```bash
uv run pytest tests/test_model_config.py tests/test_model_catalog.py -q
```

Expected: FAIL against the old repository/API.

- [ ] **Step 2: Implement strict provider-field validation**

Use one allowlist:

```python
PROVIDER_RULES = {
    ProviderType.OPENAI_COMPAT_IMAGE: ProviderRule(
        model_type=ModelType.IMAGE,
        credential_fields=("standard_api_keys", "four_k_api_key"),
        required_credential_fields=("standard_api_keys",),
        extra_fields=("input_fidelity", "response_format"),
    ),
    ProviderType.DASHSCOPE_WAN_IMAGE: ProviderRule(
        model_type=ModelType.IMAGE,
        credential_fields=("api_key",),
        required_credential_fields=("api_key",),
        extra_fields=("watermark",),
    ),
    ProviderType.OPENAI_COMPAT_CHAT: ProviderRule(
        model_type=ModelType.CHAT,
        credential_fields=("api_key",),
        required_credential_fields=("api_key",),
        extra_fields=("thinking_disabled",),
    ),
}
```

Reject provider/model-type mismatches and unknown extras or credential fields. Trim base URL trailing slashes.

- [ ] **Step 3: Implement safe API shapes**

Admin output includes internal unit cost and verification timestamp but never connection secrets:

```python
class ModelCredentialStatusOut(BaseModel):
    has_credentials: bool
    configured_fields: dict[str, bool]


class ImageModelCatalogItemOut(BaseModel):
    id: str
    display_name: str
    is_default: bool
```

Create/update inputs accept `credentials: dict[str, str | list[str]] | None`, where values are
browser-produced RSA ciphertext. `standard_api_keys` is a non-empty ciphertext array with
each key encrypted independently; single-key fields remain one ciphertext string. Saving
uses the verification proof and the server-decrypted fingerprint.

- [ ] **Step 4: Register the user catalog route**

Register `models.router` in ASGI. Require authenticated current user, not manager role, for `GET /models/image`.

- [ ] **Step 5: Run focused and audit tests**

```bash
uv run pytest tests/test_model_config.py tests/test_model_catalog.py tests/test_admin_console.py -q
uv run ruff check src tests/test_model_config.py tests/test_model_catalog.py
uv run mypy
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add image-code/src/design_hub/ports/model_config_repository.py \
  image-code/src/design_hub/infrastructure/db/model_config_repo.py \
  image-code/src/design_hub/application/admin/model_config_service.py \
  image-code/src/design_hub/interface/admin_schemas.py \
  image-code/src/design_hub/interface/model_schemas.py \
  image-code/src/design_hub/interface/api/routes/admin.py \
  image-code/src/design_hub/interface/api/routes/models.py \
  image-code/src/design_hub/interface/api/asgi.py \
  image-code/tests/test_model_config.py image-code/tests/test_model_catalog.py
git commit -m "feat: expose verified live model catalog" \
  -m "Refactor model CRUD around encrypted credentials, revisioned verification, typed defaults, secret-safe auditing, and a minimal user-facing image catalog."
```

---

### Task 5: Convert Image Runtime Types from Enum to Stable Strings

**Files:**
- Modify: `image-code/src/design_hub/domain/tasking.py`
- Modify: `image-code/src/design_hub/ports/model_provider.py`
- Modify: `image-code/src/design_hub/application/registry.py`
- Modify: `image-code/src/design_hub/application/listing/sizing.py`
- Modify: `image-code/src/design_hub/application/listing/task_planner.py`
- Modify: `image-code/src/design_hub/infrastructure/db/generation_work_repo.py`
- Modify: all backend tests importing `ModelName`

- [ ] **Step 1: Write failing stable-ID and render-tier tests**

Update domain/repository tests to assert:

```python
spec = GenerationItemSpec(
    item_id="item-1",
    operation_id="operation-1",
    sequence=1,
    image_type=None,
    operation_type=OperationType.GENERATE_IMAGE,
    render_tier=RenderTier.FOUR_K,
    final_prompt="render",
    model="gpt-image-2",
    ratio="16:9",
    size=(3840, 2160),
    quality="high",
    seed=1,
    references=(),
    reserved_cost=Decimal("0.18"),
)
assert spec.model == "gpt-image-2"
```

Add sizing tests that accept `(render_tier, ratio)` rather than infer tier from model ID. Wan and GPT use the same standard ratio map.

Run:

```bash
uv run pytest tests/test_tasking_domain.py tests/test_generation_work_repo.py \
  tests/test_listing_validation.py tests/test_provider_contract.py -q
```

Expected: FAIL because `ModelName` is still required.

- [ ] **Step 2: Refactor the domain and registry**

- `GenerationItemSpec.model: str` with non-empty validation.
- `AbstractModelProvider.name: str`.
- `ProviderRegistry` keys are strings.
- metrics, errors, and slot names use the string directly, never `.value`.
- `generation_size(render_tier, ratio)` owns 4K validation.
- delete `ModelName` from `domain/enums.py`.

The registry remains useful only for Mock-focused unit tests. Production live resolution is introduced later.

- [ ] **Step 3: Run affected tests and type checks**

```bash
uv run pytest tests/test_tasking_domain.py tests/test_generation_work_repo.py \
  tests/test_listing_validation.py tests/test_provider_contract.py \
  tests/test_provider_execution.py tests/test_provider_resilience.py -q
uv run ruff check src tests
uv run mypy
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add image-code/src/design_hub/domain/enums.py \
  image-code/src/design_hub/domain/tasking.py \
  image-code/src/design_hub/ports/model_provider.py \
  image-code/src/design_hub/application/registry.py \
  image-code/src/design_hub/application/listing/sizing.py \
  image-code/src/design_hub/application/listing/task_planner.py \
  image-code/src/design_hub/infrastructure/db/generation_work_repo.py \
  image-code/tests/integration/test_stage_a_task_chain.py \
  image-code/tests/test_async_provider.py \
  image-code/tests/test_background_replacement.py \
  image-code/tests/test_chat.py \
  image-code/tests/test_chat_rendering_intent.py \
  image-code/tests/test_generation_work_repo.py \
  image-code/tests/test_generation_worker.py \
  image-code/tests/test_image_model_composition.py \
  image-code/tests/test_listing_cancellation.py \
  image-code/tests/test_listing_submission.py \
  image-code/tests/test_listing_validation.py \
  image-code/tests/test_model_call_recording.py \
  image-code/tests/test_process_composition.py \
  image-code/tests/test_provider_contract.py \
  image-code/tests/test_provider_execution.py \
  image-code/tests/test_provider_resilience.py \
  image-code/tests/test_tasking_domain.py
git commit -m "refactor: use stable image model identifiers" \
  -m "Remove the closed image-model enum, persist stable string IDs, and separate render tier from provider identity so GPT and Wan can share the task pipeline."
```

---

### Task 6: Implement Provider Factory and Live Resolvers

**Files:**
- Create: `image-code/src/design_hub/ports/model_resolution.py`
- Create: `image-code/src/design_hub/infrastructure/providers/factory.py`
- Create: `image-code/src/design_hub/infrastructure/providers/live_resolution.py`
- Create: `image-code/tests/test_live_model_resolution.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/openai_compat.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/openai_compat_text.py`
- Modify: `image-code/src/design_hub/composition.py`

**Runtime interfaces:**

```python
class ImageExecutorResolver(Protocol):
    async def resolve(self, model_id: str, render_tier: RenderTier) -> ProviderExecutor:
        raise NotImplementedError


class TextLLMResolver(Protocol):
    async def resolve_default(self) -> TextLLMPort:
        raise NotImplementedError
```

- [ ] **Step 1: Write failing resolver tests**

Test:

- resolver loads the model row for every resolve call;
- disabled, unverified, wrong-type, missing, and unsupported-provider rows fail;
- provider objects are cached by `(name, revision, render_tier)`;
- a revision change returns a newly constructed provider on the next call;
- no `.env` field is read;
- default Chat resolution reads `model_default`, then constructs only that enabled verified Chat model;
- secret decryption errors are sanitized and never include ciphertext.

Run:

```bash
uv run pytest tests/test_live_model_resolution.py -q
```

Expected: FAIL.

- [ ] **Step 2: Implement the strict factory**

The factory accepts one already validated `ModelConfigRecord`, decrypted credential map, recorder, image store, and settings for network time budgets only. It switches on `ProviderType`; no reflection and no generic payload template.

For GPT:

- standard tier uses `standard_api_keys`;
- 4K tier requires `four_k_api_key`;
- both use the same stable provider name `gpt-image-2`;
- 4K injects required size `(3840, 2160)`, quality `high`, and count `1`.

For Chat:

- construct `OpenAICompatTextProvider` from DB base URL, upstream model, API key, and allowlisted `thinking_disabled`.

Both image and Chat providers record `model_config.name` as the model-call identity. The
upstream request still uses `model_config.model`, but administrator call counts aggregate by
the stable configured ID rather than a provider-specific upstream alias.

- [ ] **Step 3: Implement revision-keyed live resolvers**

Query the repository first, then cache only the constructed adapter. The DB row decides whether the cache entry is still current. Do not use TTL-based stale reads or configuration events.

- [ ] **Step 4: Remove production environment composition**

Delete `_resolve_image_connection`, `build_gpt_image_providers`, environment-driven `build_text_llm`, and production `real_gpt_image` switching. Keep explicit Mock constructors used by unit tests/local isolated test composition; do not let production routes select them.

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_live_model_resolution.py tests/test_image_model_composition.py \
  tests/test_process_composition.py tests/test_text_llm_adapter.py -q
uv run ruff check src tests/test_live_model_resolution.py
uv run mypy
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add image-code/src/design_hub/ports/model_resolution.py \
  image-code/src/design_hub/infrastructure/providers/factory.py \
  image-code/src/design_hub/infrastructure/providers/live_resolution.py \
  image-code/src/design_hub/infrastructure/providers/openai_compat.py \
  image-code/src/design_hub/infrastructure/providers/openai_compat_text.py \
  image-code/src/design_hub/composition.py \
  image-code/tests/test_live_model_resolution.py \
  image-code/tests/test_image_model_composition.py \
  image-code/tests/test_process_composition.py \
  image-code/tests/test_text_llm_adapter.py
git commit -m "feat: resolve providers from live database config" \
  -m "Build allowlisted image and chat adapters from encrypted revisioned records on each operation while caching only exact revisions and removing runtime environment fallback."
```

---

### Task 7: Implement the Recoverable DashScope Wan Provider

**Files:**
- Create: `image-code/src/design_hub/infrastructure/providers/dashscope_wan.py`
- Create: `image-code/tests/test_dashscope_wan.py`
- Modify: `image-code/src/design_hub/infrastructure/providers/factory.py`
- Modify: `image-code/src/design_hub/config/settings.py`
- Modify: `image-code/src/design_hub/infrastructure/db/admin_console_repo.py`
- Modify: `image-code/tests/test_admin_console.py`
- Modify: `image-code/tests/test_model_call_recording.py`

- [ ] **Step 1: Write HTTP-contract tests with `httpx.MockTransport`**

Cover:

- submit POST URL is `/api/v1/services/aigc/image-generation/generation`;
- header `X-DashScope-Async: enable` is present;
- payload uses `input.messages[0].content` with text and zero or more image URLs;
- parameters include exact size, `n: 1`, and allowlisted watermark only;
- response task ID is required;
- resume polls `/api/v1/tasks/{task_id}`;
- `PENDING`/`RUNNING` wait, `SUCCEEDED` downloads exactly one result, terminal failure raises;
- transient transport/429/5xx polling errors use bounded I/O retries;
- malformed JSON and invalid state fail fast;
- downloaded bytes are stored immediately because upstream URLs expire;
- reference count 0–9, dimensions 240–8000, file types, 20 MB, and aspect ratio 1:8–8:1 are enforced;
- Worker restart resumes with the persisted task ID and does not submit again;
- model-call accounting records one generation call, not each poll/download.
- administrator usage aggregates Wan and GPT request counts by stable configured model ID,
  while Chat keeps token totals by its stable Chat model ID.

Run:

```bash
uv run pytest tests/test_dashscope_wan.py tests/test_async_provider.py \
  tests/test_provider_execution.py -q
```

Expected: FAIL.

- [ ] **Step 2: Implement `RecoverableTaskProvider`**

```python
class DashScopeWanImageProvider(AbstractModelProvider):
    reference_mode: ReferenceMode = "url"

    async def submit_task(
        self,
        request: ProviderRequest,
        *,
        operation_id: str,
    ) -> str:
        response = await self._post_async(request)
        return self._task_id(response)

    async def resume_task(
        self,
        provider_task_id: str,
        request: ProviderRequest,
    ) -> GeneratedImage:
        result_url = await self._poll_until_complete(provider_task_id)
        stored = await self._download_and_store(result_url)
        return GeneratedImage(
            url=stored.url,
            seed=request.seed,
            latency_ms=0,
            cost=self.unit_cost,
        )
```

Use the existing provider recorder and `ImageStore`. Redact authorization and upstream response details in all raised/logged errors.

- [ ] **Step 3: Add Wan network settings**

Keep only operational budgets in settings: request timeout, polling interval, polling wall-clock limit, retry count/backoff, and maximum download bytes. Credentials and endpoint remain DB-only.

- [ ] **Step 4: Run provider and worker tests**

```bash
uv run pytest tests/test_dashscope_wan.py tests/test_async_provider.py \
  tests/test_provider_execution.py tests/test_generation_worker.py \
  tests/test_model_call_recording.py tests/test_admin_console.py -q
uv run ruff check src tests/test_dashscope_wan.py
uv run mypy
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add image-code/src/design_hub/infrastructure/providers/dashscope_wan.py \
  image-code/src/design_hub/infrastructure/providers/factory.py \
  image-code/src/design_hub/config/settings.py \
  image-code/src/design_hub/infrastructure/db/admin_console_repo.py \
  image-code/tests/test_dashscope_wan.py \
  image-code/tests/test_async_provider.py \
  image-code/tests/test_provider_execution.py \
  image-code/tests/test_generation_worker.py \
  image-code/tests/test_model_call_recording.py \
  image-code/tests/test_admin_console.py
git commit -m "feat: add recoverable Wan 2.7 provider" \
  -m "Implement DashScope asynchronous submission, restart-safe task resumption, bounded polling, immediate result storage, validation, and accurate outbound-call accounting."
```

---

### Task 8: Add Real Capability Testing to the Admin API

**Files:**
- Create: `image-code/src/design_hub/application/admin/model_capability_service.py`
- Create: `image-code/tests/test_model_capability_service.py`
- Modify: `image-code/src/design_hub/interface/admin_schemas.py`
- Modify: `image-code/src/design_hub/interface/api/admin_deps.py`
- Modify: `image-code/src/design_hub/interface/api/routes/admin.py`
- Modify: `image-code/src/design_hub/interface/api/asgi.py`

- [ ] **Step 1: Write failing capability-service tests**

Test:

- image test performs one text generation and one edit with a deterministic in-memory PNG;
- Chat test requires streamed text and one named tool call;
- success returns `{verification_proof, tested_at, checks}`;
- failed tests return sanitized protocol/check information and no upstream body, key, ciphertext, base URL query, or authorization header;
- the proof contains the exact fingerprint used for the test;
- update tests can reuse stored credentials only when the request omits credential fields;
- concurrent duplicate test requests for the same manager/config fingerprint are rejected while one is active.

Run:

```bash
uv run pytest tests/test_model_capability_service.py -q
```

Expected: FAIL.

- [ ] **Step 2: Implement the test service**

Create a 1024×1024 deterministic PNG in memory using Pillow. Build providers with an in-memory probe image store. For image providers:

1. generate one image from a fixed neutral product prompt;
2. edit one image using the synthetic PNG as the reference;
3. discard outputs after validating that bytes were stored.

For Chat:

1. send a small system/user exchange;
2. expose one required function tool named `model_configuration_probe`;
3. require both at least one text chunk and a valid tool call.

- [ ] **Step 3: Add the endpoint**

Add:

```text
POST /admin/models/test
```

It accepts the complete proposed runtime connection plus optional existing model name, and returns a signed proof. It does not mutate the model row.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_model_capability_service.py tests/test_model_config.py -q
uv run ruff check src tests/test_model_capability_service.py
uv run mypy
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add image-code/src/design_hub/application/admin/model_capability_service.py \
  image-code/src/design_hub/interface/admin_schemas.py \
  image-code/src/design_hub/interface/api/admin_deps.py \
  image-code/src/design_hub/interface/api/routes/admin.py \
  image-code/src/design_hub/interface/api/asgi.py \
  image-code/tests/test_model_capability_service.py \
  image-code/tests/test_model_config.py
git commit -m "feat: test model capabilities before activation" \
  -m "Add real generation/edit and streamed chat/tool probes that issue short-lived configuration-bound proofs without persisting or exposing credentials."
```

---

### Task 9: Require Image Model Selection in Every Listing Submission

**Files:**
- Modify: `image-code/src/design_hub/application/listing/requests.py`
- Modify: `image-code/src/design_hub/application/listing/submission_service.py`
- Modify: `image-code/src/design_hub/application/listing/task_planner.py`
- Modify: `image-code/src/design_hub/interface/api/routes/listing.py`
- Modify: `image-code/tests/test_listing_submission.py`
- Modify: `image-code/tests/test_listing_validation.py`
- Modify: `image-code/tests/test_background_replacement.py`

- [ ] **Step 1: Write failing selection tests**

Add `image_model: str` to:

- `ListingGenerateRequest`
- `CloneRequest`
- `EditRequest`
- `BackgroundReplaceRequest`

Test each endpoint rejects:

- missing/blank model;
- nonexistent model;
- disabled model;
- unverified model;
- Chat model used as image model.

Test a successful job persists the selected stable ID in every `generation_item.model`, includes it in the idempotency fingerprint, and persists the resolved internal cost at submission time.

Run:

```bash
uv run pytest tests/test_listing_submission.py tests/test_listing_validation.py \
  tests/test_background_replacement.py -q
```

Expected: FAIL.

- [ ] **Step 2: Resolve the model once before planning**

Inject `ModelConfigRepository` into `ListingSubmissionService`. Each async submit method calls `require_available_image(request.image_model)`, then passes:

```python
model_id=config.name
unit_cost=config.unit_cost
render_tier=resolved_render_tier
```

into the planner. Remove every default argument that selects GPT implicitly.

- [ ] **Step 3: Keep render tier independent**

Normal workbench requests use `RenderTier.STANDARD`. Chat can request `FOUR_K` only for GPT, and the submission service validates provider capability before planning.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_listing_submission.py tests/test_listing_validation.py \
  tests/test_background_replacement.py tests/test_generation_work_repo.py -q
uv run ruff check src tests
uv run mypy
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add image-code/src/design_hub/application/listing/requests.py \
  image-code/src/design_hub/application/listing/submission_service.py \
  image-code/src/design_hub/application/listing/task_planner.py \
  image-code/src/design_hub/interface/api/routes/listing.py \
  image-code/tests/test_listing_submission.py \
  image-code/tests/test_listing_validation.py \
  image-code/tests/test_background_replacement.py \
  image-code/tests/test_generation_work_repo.py
git commit -m "feat: snapshot selected image model on submission" \
  -m "Require an enabled verified image model in every listing flow and persist its stable ID, render tier, idempotency fingerprint, and internal cost without an implicit GPT default."
```

---

### Task 10: Resolve the Exact Model Revision in the Worker

**Files:**
- Modify: `image-code/src/design_hub/application/tasking/worker.py`
- Modify: `image-code/src/design_hub/interface/worker.py`
- Modify: `image-code/src/design_hub/infrastructure/queue/redis_slots.py`
- Modify: `image-code/tests/test_generation_worker.py`
- Modify: `image-code/tests/test_process_composition.py`

- [ ] **Step 1: Write failing async-resolver tests**

Test:

- `GenerationWorker` awaits `executor_resolver.resolve(model_id, render_tier)` after loading the task;
- reference materialization uses the resolved adapter mode;
- a model revision update is used by the very next task without worker restart;
- a disabled/missing model fails the task with a sanitized `model_unavailable` code;
- resume uses the same stable model ID and the persisted Wan task ID;
- slots are keyed by stable model ID and render tier.

Run:

```bash
uv run pytest tests/test_generation_worker.py tests/test_process_composition.py -q
```

Expected: FAIL because the worker takes synchronous startup maps.

- [ ] **Step 2: Replace startup maps with resolvers**

Change constructor dependencies:

```python
class GenerationWorker:
    def __init__(
        self,
        *,
        executor_resolver: ImageExecutorResolver,
        slots_for: Callable[[str, RenderTier], ProviderSlots],
        repository: GenerationWorkRepository,
        broker: TaskBroker,
        materializer: ReferenceMaterializer,
        worker_id: str,
        lease_seconds: int,
        heartbeat_seconds: float = 15,
        slot_refresh_seconds: float = 10,
    ) -> None:
```

`interface/worker.py` constructs one `LiveImageExecutorResolver`; it does not list model configs or build a registry at startup.

- [ ] **Step 3: Run worker tests**

```bash
uv run pytest tests/test_generation_worker.py tests/test_process_composition.py \
  tests/integration/test_stage_a_task_chain.py -q
uv run ruff check src tests/test_generation_worker.py tests/test_process_composition.py
uv run mypy
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add image-code/src/design_hub/application/tasking/worker.py \
  image-code/src/design_hub/interface/worker.py \
  image-code/src/design_hub/infrastructure/queue/redis_slots.py \
  image-code/tests/test_generation_worker.py \
  image-code/tests/test_process_composition.py \
  image-code/tests/integration/test_stage_a_task_chain.py
git commit -m "refactor: resolve providers per worker task" \
  -m "Remove startup snapshots from the worker and resolve the selected stable model and current revision immediately before execution while preserving resumable Wan task state."
```

---

### Task 11: Make Chat and Reverse Prompt Use Live Chat Configuration

**Files:**
- Modify: `image-code/src/design_hub/application/chat/rendering_intent.py`
- Modify: `image-code/src/design_hub/application/chat/pending_store.py`
- Modify: `image-code/src/design_hub/application/chat/orchestrator.py`
- Modify: `image-code/src/design_hub/application/image_prompts/reverse_prompt.py`
- Modify: `image-code/src/design_hub/interface/chat_schemas.py`
- Modify: `image-code/src/design_hub/interface/api/routes/chat.py`
- Modify: `image-code/src/design_hub/interface/api/asgi.py`
- Modify: `image-code/tests/test_chat_rendering_intent.py`
- Modify: `image-code/tests/test_chat.py`
- Modify: `image-code/tests/test_reverse_prompt.py`
- Create: `image-code/tests/test_chat_knowledge.py`

- [ ] **Step 1: Write failing Chat model tests**

Test:

- `ChatMessageRequest.image_model` is required for a generation-capable turn;
- Chat resolves the default Chat provider for each LLM operation;
- reverse prompt resolves the default Chat provider for each request;
- rendering intent returns `RenderTier`, not an image model;
- the user's `image_model` is used for generate/clone/edit/background tools;
- pending confirmation retains that exact model when the frontend or DB default later changes;
- disabling the selected model before confirmation rejects the launch;
- 4K is accepted only with GPT and count one;
- the LLM tool arguments cannot supply or override `image_model`;
- event name changes from `cost_confirm` to `generation_confirm`;
- confirmation payload contains model ID/display name and count, with no unit cost, estimate, or billing language.

Run:

```bash
uv run pytest tests/test_chat_rendering_intent.py tests/test_chat.py \
  tests/test_reverse_prompt.py -q
```

Expected: FAIL.

- [ ] **Step 2: Refactor Chat dependencies**

Replace concrete `text_llm` with `TextLLMResolver`. Resolve once per LLM request/loop iteration. The pending action shape becomes:

```python
@dataclass
class PendingAction:
    confirm_token: str
    tool: str
    req: ListingReq
    count: int
    image_model: str
    render_tier: RenderTier
    expires_at: float
```

Remove `estimate` and all user-facing price data.

- [ ] **Step 3: Update Chat knowledge**

Update `chat_knowledge.md` to:

- list GPT Image 2.0 and Wan 2.7 Image Pro;
- explain that users select the image model in every workbench and Chat;
- explain current generation, clone, edit, background replacement, reverse prompt, history, and admin-review capabilities accurately;
- direct users to the relevant page for each function;
- state that pricing/wallet is not publicly available yet;
- remove all fixed price and “confirm fee” claims.

Add `test_chat_knowledge.py` to assert the two image model names, supported feature/page
guidance, and unpublished-wallet statement are present, while fixed prices and obsolete
models are absent.

- [ ] **Step 4: Run tests and checks**

```bash
uv run pytest tests/test_chat_rendering_intent.py tests/test_chat.py \
  tests/test_reverse_prompt.py tests/test_chat_knowledge.py -q
uv run ruff check src tests
uv run mypy
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add image-code/src/design_hub/application/chat/rendering_intent.py \
  image-code/src/design_hub/application/chat/pending_store.py \
  image-code/src/design_hub/application/chat/orchestrator.py \
  image-code/src/design_hub/application/image_prompts/reverse_prompt.py \
  image-code/src/design_hub/interface/chat_schemas.py \
  image-code/src/design_hub/interface/api/routes/chat.py \
  image-code/src/design_hub/interface/api/asgi.py \
  image-code/src/design_hub/config/chat_knowledge.md \
  image-code/tests/test_chat_rendering_intent.py \
  image-code/tests/test_chat.py \
  image-code/tests/test_reverse_prompt.py \
  image-code/tests/test_chat_knowledge.py
git commit -m "feat: honor selected image model in chat" \
  -m "Resolve the default chat provider live, keep image selection user-controlled through confirmation, separate 4K render intent, remove price confirmation, and refresh the platform knowledge base."
```

---

### Task 12: Add the Secure One-Time Bootstrap Command

**Files:**
- Create: `image-code/src/design_hub/cli/__init__.py`
- Create: `image-code/src/design_hub/cli/bootstrap_models.py`
- Create: `image-code/tests/test_bootstrap_models.py`
- Modify: `image-code/README.md`

- [ ] **Step 1: Write failing bootstrap tests**

Using temporary env values and a temporary vertical key/value CSV, test:

- GPT standard/4K, Doubao Chat, and Wan connection fields are parsed correctly;
- values are encrypted field-by-field with the server RSA key;
- the database never contains plaintext;
- stdout/stderr never contains plaintext, ciphertext, CSV content, or full input path;
- the same capability service is called;
- only models whose real checks pass are enabled;
- failures stop immediately and leave the failing model disabled;
- a missing persistent private key, missing CSV field, invalid CSV, or wrong host/path fails fast.

Run:

```bash
uv run pytest tests/test_bootstrap_models.py -q
```

Expected: FAIL.

- [ ] **Step 2: Implement the CLI**

Entry usage:

```bash
cd /Users/Zhuanz/CLAUDE/image-gen/image-code
uv run python -m design_hub.cli.bootstrap_models \
  --wan-csv "/absolute/path/to/the-private.csv"
```

The command reads:

- existing `GPT_IMAGE_*` and `TEXT_LLM_*` only for this bootstrap process;
- Wan `apiKey`, `apiHost`, and `dashScope` path from the explicit CSV;
- current persistent RSA private key from `AUTH_RSA_PRIVATE_KEY_PEM`.

It encrypts with the matching public key, calls the capability service, saves proofs, sets GPT as image default and Doubao as Chat default, then prints only model IDs and success/failure status.

- [ ] **Step 3: Document safe operation**

Document:

- run once in the target environment;
- verify the file is outside the repository;
- remove local access to the CSV after successful bootstrap according to the operator's credential policy;
- do not paste the command output or secret file into issues.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_bootstrap_models.py -q
uv run ruff check src tests/test_bootstrap_models.py
uv run mypy
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add image-code/src/design_hub/cli \
  image-code/tests/test_bootstrap_models.py \
  image-code/README.md
git commit -m "feat: bootstrap encrypted model credentials" \
  -m "Add a one-time secret-safe command that imports existing GPT and Doubao settings plus an explicit Wan CSV, performs real capability checks, enables verified models, and configures typed defaults."
```

---

### Task 13: Regenerate the OpenAPI Contract and Build Frontend Model State

**Files:**
- Modify: `image-web/openapi.json`
- Modify: `image-web/src/api/schema.d.ts`
- Create: `image-web/src/api/models.ts`
- Create: `image-web/src/stores/image-model-store.ts`
- Create: `image-web/src/stores/image-model-store.test.ts`
- Create: `image-web/src/components/models/ImageModelSelector.tsx`
- Create: `image-web/src/components/models/ImageModelGate.tsx`
- Create: `image-web/src/components/models/ImageModelSelector.test.tsx`

- [ ] **Step 1: Regenerate API types**

```bash
cd /Users/Zhuanz/CLAUDE/image-gen/image-code
uv run python -c 'import json; from design_hub.interface.api.asgi import app; print(json.dumps(app.openapi(), ensure_ascii=False))' > ../image-web/openapi.json
cd /Users/Zhuanz/CLAUDE/image-gen/image-web
npm run gen:api
```

Expected: generated types include image catalog, `image_model`, `generation_confirm`, encrypted credential inputs, and model-test proof output.

- [ ] **Step 2: Write failing frontend state tests**

Test:

- storage key is scoped as `image-model-selection:<user_id>`;
- no stored selection initializes from server default;
- a still-valid stored selection wins over default;
- a stale stored selection is removed and returns `selectionRequired`;
- switching user IDs cannot leak another user's selection;
- loading, error, retry, empty, and stale states render distinct accessible UI;
- selector is keyboard operable and exposes label/help text;
- no state silently switches to another model after catalog refresh.

Run:

```bash
npm test -- src/stores/image-model-store.test.ts src/components/models/ImageModelSelector.test.tsx
```

Expected: FAIL.

Use pure reconciliation helpers plus `react-dom/server` for selector markup assertions; do not
introduce a new frontend test dependency.

- [ ] **Step 3: Implement catalog query and persisted state**

`useImageModels()` calls `GET /models/image`. `ImageModelGate` owns catalog readiness and exposes:

```ts
export interface ImageModelSelection {
  modelId: string | null
  models: ImageModelCatalogItem[]
  state: 'loading' | 'ready' | 'error' | 'empty' | 'selection_required'
  select: (modelId: string) => void
  retry: () => void
}
```

Do not persist catalog data, internal costs, or display-name snapshots.

- [ ] **Step 4: Run tests and checks**

```bash
npm test -- src/stores/image-model-store.test.ts src/components/models/ImageModelSelector.test.tsx
npm run typecheck
npm run lint
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add image-web/openapi.json image-web/src/api/schema.d.ts \
  image-web/src/api/models.ts \
  image-web/src/stores/image-model-store.ts \
  image-web/src/stores/image-model-store.test.ts \
  image-web/src/components/models/ImageModelSelector.tsx \
  image-web/src/components/models/ImageModelGate.tsx \
  image-web/src/components/models/ImageModelSelector.test.tsx
git commit -m "feat: add robust shared image model selection" \
  -m "Generate the new API contract and add an authenticated per-user selector with explicit loading, retry, empty, and stale-selection behavior and no silent switching."
```

---

### Task 14: Wire the Shared Selector into All Four Workbenches

**Files:**
- Modify: `image-web/src/api/listing.ts`
- Modify: `image-web/src/api/listing.test.ts`
- Modify: `image-web/src/lib/listing.ts`
- Modify: `image-web/src/lib/listing.test.ts`
- Modify: `image-web/src/stores/workbench-store.ts`
- Modify: `image-web/src/components/listing/ListingConfigPanel.tsx`
- Modify: `image-web/src/components/listing/CloneConfigPanel.tsx`
- Modify: `image-web/src/components/listing/EditConfigPanel.tsx`
- Modify: `image-web/src/components/listing/BackgroundConfigPanel.tsx`
- Modify: `image-web/src/pages/WorkbenchPage.tsx`
- Modify: `image-web/src/pages/CloneWorkbenchPage.tsx`
- Modify: `image-web/src/pages/EditWorkbenchPage.tsx`
- Modify: `image-web/src/pages/BackgroundWorkbenchPage.tsx`
- Modify: existing component tests

- [ ] **Step 1: Write failing request-builder tests**

Assert all four bodies include the currently selected `image_model`. Assert no builder has a GPT default.

Test page behavior:

- uploaded images, prompt, modifiers, ratio, source image, and background inputs survive catalog load failure/retry;
- Generate buttons remain disabled until catalog ready and a valid model is selected;
- a model disabled between catalog load and submit preserves the form, refreshes the catalog, clears only the stale selection, and shows a specific message;
- selector is locked while the request/SSE job is active;
- reset/new-task keeps the user's global model choice.

Run:

```bash
npm test -- src/api/listing.test.ts src/lib/listing.test.ts \
  src/components/listing/BackgroundConfigPanel.test.ts
```

Expected: FAIL.

- [ ] **Step 2: Add `imageModel` to frontend input types**

Every builder maps `imageModel` to `image_model`. Workbench pages read the same global per-user store and pass one selector into their panel. Do not duplicate selector state inside individual pages.

- [ ] **Step 3: Implement stale-model response handling**

When the backend returns `model_unavailable` or the equivalent validated API error:

1. keep all form/upload/source state;
2. invalidate `['models', 'image']`;
3. reconcile selection against the refreshed catalog;
4. require explicit reselection if stale.

- [ ] **Step 4: Run tests and checks**

```bash
npm test -- src/api/listing.test.ts src/lib/listing.test.ts \
  src/components/listing/BackgroundConfigPanel.test.ts
npm run typecheck
npm run lint
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add image-web/src/api/listing.ts image-web/src/api/listing.test.ts \
  image-web/src/lib/listing.ts image-web/src/lib/listing.test.ts \
  image-web/src/stores/workbench-store.ts \
  image-web/src/components/listing/ListingConfigPanel.tsx \
  image-web/src/components/listing/CloneConfigPanel.tsx \
  image-web/src/components/listing/EditConfigPanel.tsx \
  image-web/src/components/listing/BackgroundConfigPanel.tsx \
  image-web/src/components/listing/BackgroundConfigPanel.test.ts \
  image-web/src/pages/WorkbenchPage.tsx \
  image-web/src/pages/CloneWorkbenchPage.tsx \
  image-web/src/pages/EditWorkbenchPage.tsx \
  image-web/src/pages/BackgroundWorkbenchPage.tsx
git commit -m "feat: select image model in every workbench" \
  -m "Use the same per-user model selection for generate, clone, edit, and background replacement while preserving form state through catalog and submission races."
```

---

### Task 15: Wire Model Selection and Generation Confirmation into Chat

**Files:**
- Modify: `image-web/src/api/chat.ts`
- Modify: `image-web/src/api/chat.test.ts`
- Modify: `image-web/src/lib/chat.ts`
- Modify: `image-web/src/lib/chat.test.ts`
- Modify: `image-web/src/pages/ChatPage.tsx`

- [ ] **Step 1: Write failing Chat frontend tests**

Test:

- message body carries `image_model`;
- parser/reducer handles `generation_confirm`;
- confirmation card shows selected display name and count only;
- no cost fields or price text are rendered;
- selector is locked during streaming and while awaiting confirmation;
- pending card retains its snapshotted model even if the global selection later changes;
- Chat hero seeded message waits for catalog readiness;
- catalog error/empty preserves the seed as editable draft and does not auto-send;
- stale model response refreshes catalog and preserves draft/uploads/edit source.

Run:

```bash
npm test -- src/api/chat.test.ts src/lib/chat.test.ts
```

Expected: FAIL.

- [ ] **Step 2: Replace cost confirmation types**

```ts
export interface GenerationConfirm {
  confirmToken: string
  tool: ChatTool
  count: number
  modelId: string
  modelDisplayName: string
}
```

Rename reducer fields from `cost`/`awaiting: CostConfirm` to `generation`/`awaiting: GenerationConfirm`. Update comments and visible copy.

- [ ] **Step 3: Integrate the shared selector**

Chat reads the same store as the workbenches. Sending a message passes the selected model. Awaiting confirmation stores the event's snapshotted model and ignores later selector changes until resolved.

- [ ] **Step 4: Run tests and checks**

```bash
npm test -- src/api/chat.test.ts src/lib/chat.test.ts
npm run typecheck
npm run lint
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add image-web/src/api/chat.ts image-web/src/api/chat.test.ts \
  image-web/src/lib/chat.ts image-web/src/lib/chat.test.ts \
  image-web/src/pages/ChatPage.tsx
git commit -m "feat: use selected image model in chat" \
  -m "Send the shared user selection through Chat, preserve it through generation confirmation, handle catalog races safely, and remove all user-facing cost confirmation data."
```

---

### Task 16: Rebuild the Administrator Model Form as a Real Runtime Configuration UI

**Files:**
- Modify: `image-web/src/api/crypto.ts`
- Modify: `image-web/src/api/crypto.test.ts`
- Modify: `image-web/src/api/admin.ts`
- Modify: `image-web/src/components/admin/ModelConfigDialog.tsx`
- Modify: `image-web/src/components/admin/ModelRowActions.tsx`
- Modify: `image-web/src/pages/AdminModelsPage.tsx`
- Create: `image-web/src/components/admin/ModelConfigDialog.test.tsx`

- [ ] **Step 1: Write failing admin form/state tests**

Test:

- tabs/filters clearly distinguish image and Chat models;
- initial rows contain GPT, Wan, and Doubao only;
- provider choices are filtered by model type;
- provider-specific credential and extra fields render exactly from the allowlist;
- `encryptSecret` encrypts each credential independently;
- the GPT standard key pool encrypts each key separately and never joins plaintext keys;
- ciphertext is never placed back into the form;
- edit shows configured/not-configured status and blank replacement secret fields;
- Test Configuration performs a real test and shows generation/edit or stream/tool checks;
- saving/enabling is disabled until the current field fingerprint has a proof;
- any runtime field/credential edit invalidates the proof immediately;
- display name/internal cost edits keep a valid proof;
- duplicate test clicks are blocked;
- closing create mode clears all plaintext secrets;
- sanitized error UI does not print raw upstream response;
- no “restart required”, `.env`, arbitrary protocol, or automatic compatibility claims remain.

Run:

```bash
npm test -- src/api/crypto.test.ts src/components/admin/ModelConfigDialog.test.tsx
```

Expected: FAIL.

Use Vitest with exported pure form-state/fingerprint helpers and
`react-dom/server` static rendering where markup inspection is needed. Do not add a DOM test
framework dependency for this task.

- [ ] **Step 2: Generalize frontend encryption**

Rename `encryptPassword` to `encryptSecret`; update login/register callers directly. Do not leave an alias.

- [ ] **Step 3: Implement the form state machine**

Use explicit states:

```ts
type VerificationState =
  | { kind: 'untested' }
  | { kind: 'testing' }
  | { kind: 'passed'; proof: string; testedFingerprint: string }
  | { kind: 'failed'; message: string }
```

Compute a browser-side convenience fingerprint only to invalidate UI state; the server remains authoritative and recomputes the secret-aware fingerprint.

- [ ] **Step 4: Update the model table**

Show:

- model type;
- display name and stable ID;
- provider;
- enabled state;
- verification timestamp/state;
- internal unit cost;
- default marker within its type.

Keep price visible here because this is administrator-only.

- [ ] **Step 5: Run tests and checks**

```bash
npm test -- src/api/crypto.test.ts src/components/admin/ModelConfigDialog.test.tsx
npm run typecheck
npm run lint
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add image-web/src/api/crypto.ts image-web/src/api/crypto.test.ts \
  image-web/src/api/auth.ts image-web/src/api/admin.ts \
  image-web/src/components/admin/ModelConfigDialog.tsx \
  image-web/src/components/admin/ModelConfigDialog.test.tsx \
  image-web/src/components/admin/ModelRowActions.tsx \
  image-web/src/pages/AdminModelsPage.tsx
git commit -m "feat: make admin model configuration executable" \
  -m "Add typed image/chat provider forms, per-field secret encryption, real capability testing, proof-bound activation, immediate runtime semantics, and secret-safe form cleanup."
```

---

### Task 17: Remove User-Facing Prices and Preserve Historical Model Identity

**Files:**
- Modify: `image-web/src/components/listing/ListingConfigPanel.tsx`
- Modify: `image-web/src/components/listing/CloneConfigPanel.tsx`
- Modify: `image-web/src/components/listing/EditConfigPanel.tsx`
- Modify: `image-web/src/components/listing/BackgroundConfigPanel.tsx`
- Modify: `image-web/src/pages/HistoryPage.tsx`
- Modify: `image-web/src/pages/HistoryDetailPage.tsx`
- Modify: `image-web/src/lib/home.ts`
- Modify: `image-web/src/lib/home.test.ts`
- Modify: `image-web/src/lib/listing.ts`
- Modify: `image-web/src/lib/listing.test.ts`
- Modify: relevant backend history schemas/query if model ID is not currently returned

- [ ] **Step 1: Write failing copy and history tests**

Assert user surfaces contain no:

- `¥`, `￥`, `元/张`;
- `费用`, `预计价格`, `实付`, `成本`, `计费`;
- fixed GPT unit-cost helper.

Keep legal-policy wording outside generation UI unchanged unless it quotes a current model price.

Test history list/detail render the persisted stable model ID or display snapshot. If the model is later deleted, history falls back to the stored stable ID and does not fail or substitute another model.

Run:

```bash
npm test -- src/lib/home.test.ts src/lib/listing.test.ts
```

Expected: FAIL.

- [ ] **Step 2: Remove price helpers and copy**

Delete `LISTING_UNIT_COST`, `estimateCost`, and user-facing `fmtListingCost` use. Buttons show count/action only. History keeps status, count, date, and model identity.

Do not alter administrator cost views or backend ledger fields.

- [ ] **Step 3: Run targeted tests and source scan**

```bash
npm test -- src/lib/home.test.ts src/lib/listing.test.ts
grep -R -n "¥\\|￥\\|元/张\\|预计价格\\|实付\\|确认费用" \
  src/pages src/components src/lib src/api \
  --exclude='schema.d.ts' \
  --exclude-dir='admin'
```

Expected: tests PASS; scan contains no active user-generation pricing copy. Style-preview-only fixtures may be removed or updated rather than exempted.

- [ ] **Step 4: Commit**

```bash
git add image-web/src/components/listing/ListingConfigPanel.tsx \
  image-web/src/components/listing/CloneConfigPanel.tsx \
  image-web/src/components/listing/EditConfigPanel.tsx \
  image-web/src/components/listing/BackgroundConfigPanel.tsx \
  image-web/src/pages/HistoryPage.tsx \
  image-web/src/pages/HistoryDetailPage.tsx \
  image-web/src/lib/home.ts image-web/src/lib/home.test.ts \
  image-web/src/lib/listing.ts image-web/src/lib/listing.test.ts \
  image-code/src/design_hub/interface/listing_history_schemas.py \
  image-code/src/design_hub/infrastructure/db/listing_query_repo.py
git commit -m "refactor: hide generation prices from users" \
  -m "Remove public model pricing and billing confirmation copy while preserving internal accounting, administrator cost visibility, and stable model identity in historical jobs."
```

---

### Task 18: Full Verification, Real Wan/GPT Smoke, and Local UI Check

**Files:**
- Modify only files required by failures discovered in this task.
- Do not commit the private Wan CSV, generated images, local database, `.env`, logs, or screenshots containing secrets.

- [ ] **Step 1: Verify generated contract is clean**

```bash
cd /Users/Zhuanz/CLAUDE/image-gen/image-code
uv run python -c 'import json; from design_hub.interface.api.asgi import app; print(json.dumps(app.openapi(), ensure_ascii=False))' > ../image-web/openapi.json
cd /Users/Zhuanz/CLAUDE/image-gen/image-web
npm run gen:api
git diff --exit-code -- openapi.json src/api/schema.d.ts
```

Expected: no diff after regeneration.

- [ ] **Step 2: Run the complete backend gate**

```bash
cd /Users/Zhuanz/CLAUDE/image-gen/image-code
uv run pytest -q
uv run ruff check src tests
uv run mypy
```

Expected: all tests PASS, Ruff clean, Mypy clean.

- [ ] **Step 3: Run the complete frontend gate**

```bash
cd /Users/Zhuanz/CLAUDE/image-gen/image-web
npm test
npm run typecheck
npm run lint
npm run build
```

Expected: all tests PASS and production build succeeds.

- [ ] **Step 4: Run secret and fallback scans**

```bash
cd /Users/Zhuanz/CLAUDE/image-gen
grep -R -n "api_key_env\\|GPT_IMAGE_API_KEY\\|TEXT_LLM_API_KEY\\|fallback.*env\\|回落.*env" \
  image-code/src image-web/src \
  --exclude-dir='__pycache__'
grep -R -n "wanxiang-2.7-pro\\|seedream-5\\|lingdong-2\\|gpt-image-2-4k" \
  image-code/src image-web/src \
  --exclude-dir='__pycache__'
```

Expected: no runtime legacy configuration or user-selectable old model IDs. Bootstrap-only reads of legacy env names are allowed only in `bootstrap_models.py`.

- [ ] **Step 5: Bootstrap and perform real capability checks**

Use the user-provided CSV only through the explicit local argument. This step performs two billable Wan image calls.

```bash
cd /Users/Zhuanz/CLAUDE/image-gen/image-code
: "${IMAGE_GEN_WAN_CSV:?Set IMAGE_GEN_WAN_CSV to the private CSV path outside the repository}"
uv run python -m design_hub.cli.bootstrap_models \
  --wan-csv "$IMAGE_GEN_WAN_CSV"
```

Expected output contains only model IDs and pass/fail status. Confirm:

- GPT generation and edit pass;
- Wan generation and edit pass;
- Doubao stream and required tool call pass;
- GPT is the image default;
- Doubao is the Chat default;
- both image models are enabled and appear in the user catalog.

- [ ] **Step 6: Verify Wan async recovery**

Submit one Wan job in a non-production local environment, wait until `provider_task_id` is persisted, stop the worker cleanly, restart it, and confirm it resumes rather than submits a second upstream task. Verify the result is stored locally/TOS and remains available after the upstream URL expires.

- [ ] **Step 7: Start local API, Worker, and Web**

Use the repository's normal local commands and persistent RSA key. Verify:

- `/admin/models` can test/save without restart;
- Workbench, Clone, Edit, Background, and Chat show the same selector;
- switching models affects the next task;
- form state survives catalog failure/retry;
- stale selection requires explicit reselection;
- Chat seed waits for catalog;
- no user price appears;
- admin usage counts GPT/Wan image API calls and Doubao token usage;
- history renders the task's stable model identity.

- [ ] **Step 8: Inspect repository status and commit only verification fixes**

```bash
cd /Users/Zhuanz/CLAUDE/image-gen
git status --short
git diff --check
git log -18 --oneline
```

If verification required code changes, stage exact files and commit:

```bash
git commit -m "fix: complete live model integration verification" \
  -m "Resolve issues found by full backend, frontend, real-provider, restart-recovery, and five-entry local verification without adding fallbacks or exposing credentials."
```

If no code changed, do not create an empty commit.

---

## Final Acceptance Checklist

- [ ] Database is the only runtime source for image and Chat connection configuration.
- [ ] GPT Image 2.0 and Wan 2.7 Image Pro are enabled, verified image choices.
- [ ] Doubao is an enabled, verified default Chat model.
- [ ] No mock model or `gpt-image-2-4k` appears in the selector.
- [ ] Configuration changes affect the next operation without restart.
- [ ] No provider fallback or automatic model switch exists.
- [ ] Every generation entry point uses the same per-user selection.
- [ ] Chat snapshots the user's model through confirmation.
- [ ] Wan async tasks survive Worker restart without duplicate submission.
- [ ] Credentials are encrypted at rest and never returned or logged.
- [ ] Enabling/saving requires a non-expired proof for the exact tested connection.
- [ ] User catalog and all five entry points handle loading, error, empty, stale, and disabled-during-submit states without losing user input.
- [ ] User-facing prices are absent; administrator costs and usage remain.
- [ ] Chat knowledge reflects current platform capabilities and no longer quotes prices.
- [ ] Full backend/frontend gates and real GPT/Wan/Doubao checks pass.
- [ ] Private CSV, generated smoke images, local DB, secrets, and unrelated dirty files are absent from commits.
