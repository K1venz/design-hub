<div align="center">
  <img src="image-web/src/assets/hero/shipu-logo.png" alt="Shipu" height="72">
  <h1>Shipu</h1>
  <p><strong>An AI workspace for commerce-ready product imagery.</strong></p>
  <p>Turn a brief, a product photo, or a visual reference into a coherent set of product images—without leaving one production workflow.</p>
  <p><strong>English</strong> · <a href="README.zh-CN.md">简体中文</a></p>
</div>

![Shipu conversational design workspace](image-web/docs/screenshots/chat-real-result.png)

## What Shipu does

Shipu brings image generation, visual direction, revision, and operational control into one workspace. It is designed around real product-image workflows rather than isolated prompt experiments.

- **Design by conversation.** Describe the product and desired result in natural language, attach references, review the estimated cost, and continue refining in the same session.
- **Generate complete listing sets.** Produce coordinated hero, lifestyle, and selling-point images from product assets and a commercial brief.
- **Clone a visual direction.** Transfer the composition and atmosphere of a reference image while preserving the product as the subject.
- **Edit and replace backgrounds.** Revise generated images, keep their lineage, or place a product into a described or referenced scene.
- **Keep every result traceable.** Browse generation history, inspect individual jobs, download outputs, and continue from an earlier image.

## Built for creative teams and operators

Shipu combines a focused creator experience with the controls needed to run image generation as a service.

| Creative workflow | Operational control |
| --- | --- |
| Conversational image creation with attachments | Designer and manager roles |
| Product-set, clone, edit, and background workflows | User, generation, and usage views |
| Model-aware ratios and standard, 2K, or 4K tiers | Live model configuration and capability checks |
| Persistent chat sessions and generation history | Cost budgets, call records, audit trails, and runtime logs |
| Curated public showcase | Moderation and showcase management |

## Model-flexible by design

The model layer is configured at runtime instead of being embedded in the interface. The current capability catalog includes GPT Image 2, Nano Banana 2, and Wan 2.7 Image Pro, backed by four provider contracts:

- OpenAI-compatible image APIs
- Gemini native image APIs
- Alibaba Cloud Model Studio Wan APIs
- OpenAI-compatible chat APIs

Each model declares its own output ratios, render tiers, reference-image support, provider limits, and unit cost. Credentials are encrypted before persistence, and managers can verify a connection before enabling it.

## Architecture

```text
React 19 + Vite 8
        │  typed OpenAPI client
        ▼
FastAPI API ───── JWT auth · SSE events · Prometheus metrics
        │
        ├── MySQL / SQLite ── users · sessions · jobs · model calls · audit data
        ├── Redis Streams ─── durable queue · admission control · progress events
        └── Generation worker
                 ├── model providers
                 └── local storage / Volcengine TOS
```

The API accepts and validates work, persists it through an outbox, and streams progress to clients. Separate workers claim generation items, enforce concurrency slots, call the selected provider, and store results. Explicit task-state transitions make cancellation, timeout, failure, and uncertain submission visible instead of silently losing work.

Production composition adds Nginx, Redis persistence, MySQL, API and worker health checks, SMTP with DKIM signing, immutable release directories, and automatic rollback protection.

## Repository layout

```text
image-code/   FastAPI service, domain logic, workers, migrations, and Python tests
image-web/    React application, typed API client, components, and browser tests
image-ops/    Docker, Nginx, mail, release, rollback, and infrastructure scripts
image-qa/     Real-service acceptance, boundary, security, and regression probes
```

## Local development

### Prerequisites

- Python 3.12 or later
- [uv](https://docs.astral.sh/uv/)
- Node.js and npm
- Redis 8

### Start the backend

From `image-code/`:

```bash
uv sync --group dev
uv run alembic upgrade head
uv run uvicorn design_hub.interface.api.asgi:app --reload
```

The development defaults use SQLite and local file storage. The API expects Redis at `redis://127.0.0.1:6379/0`; override `REDIS_URL` when needed.

Start the generation worker in a second terminal:

```bash
cd image-code
uv run python -m design_hub.interface.worker
```

To seed a local manager account, set `SEED_ADMIN_EMAIL` and `SEED_ADMIN_PASSWORD` before starting the API. Image and chat providers are then added, verified, and enabled from the manager model console.

### Start the frontend

From `image-web/`:

```bash
npm ci
npm run dev
```

Open `http://localhost:3000`. Vite proxies `/api` to `http://127.0.0.1:8000`; set `VITE_API_TARGET` to use another backend.

For UI work without provider credentials, the backend also includes a local mock launcher:

```bash
cd image-code
bash scripts/run_local_mock.sh
```

The launcher uses SQLite, local storage, and mock text and image providers, so it does not call a paid upstream service.

## Quality checks

The repository currently contains 67 Python test files and 38 frontend test files, complemented by real-provider QA probes. Run the same core checks used by CI:

```bash
cd image-code
uv run ruff check
uv run mypy
uv run pytest

cd ../image-web
npm run lint
npm run typecheck
npm run test
npm run build
```

## Production delivery

The production stack is defined in `image-ops/deploy/compose.yml`. Release scripts build the SPA, stage an immutable release, run database migrations, verify service health, switch the active release, and preserve a rollback path.

Production requires externally managed secrets and infrastructure values, including the MySQL connection, Redis credentials, JWT and encryption keys, storage settings, mail identity, and provider configurations. Do not use development defaults in a public deployment.

---

<div align="center">
  <strong>Shipu turns product-image creation from a chain of disconnected tools into one observable workflow.</strong>
</div>
