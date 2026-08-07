# Admin-Managed Public Showcase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let managers publish generated images from image moderation to both public pages, show the user's original prompt on `/home`, use adaptive preview proportions, and expose original-image downloads only when explicitly allowed.

**Architecture:** `listing_image` becomes the showcase source of truth. A focused showcase application service validates publication, creates a content-addressed 1200px WebP preview through the existing `ImageStore`, persists publication state atomically with the audit record, and serves public read/download policies through a dedicated repository. React consumes the database-backed public contract; `/home` renders adaptive preview cards and `/` reuses the same preview list for its marquee.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Alembic, Pillow, pytest, React 19, TypeScript 6, TanStack Query, Vitest, Tailwind CSS 4.

## Global Constraints

- Use `uv run` for every Python command; do not use system Python or `uv pip`.
- Do not add dependencies: Pillow, SQLAlchemy, FastAPI, React, and Vitest already exist.
- Public previews are WebP quality `82`, preserve orientation and aspect ratio, never upscale, and have a longest edge of at most `1200px`.
- `GET /showcase` must never expose `listing_image.image_key`, an original URL, a user identity, moderation data, or `generation_item.final_prompt`.
- Original download authorization is per image and returns 404 unless the image is public, normal, successful, and download-enabled at request time.
- `/home` shows a two-to-three-line original user prompt summary and the complete prompt in details.
- `/home` preview cards keep each image's aspect ratio and natural card height; `/` retains the current marquee card shape.
- Blocking or unpublishing an image disables original download; restoring moderation does not republish it.
- Tests must follow red-green-refactor, and each independently testable task must be committed before the next task.

---

### Task 1: Showcase persistence and preview processing

**Files:**
- Create: `migrations/versions/c6d7e8f9a0b1_admin_public_showcase.py`
- Create: `src/design_hub/application/showcase/__init__.py`
- Create: `src/design_hub/application/showcase/preview.py`
- Modify: `src/design_hub/infrastructure/db/models.py`
- Modify: `src/design_hub/domain/admin.py`
- Test: `tests/test_showcase_preview.py`
- Test: `tests/test_admin_console_migration.py`

**Interfaces:**
- Produces: `ShowcasePreview(data: bytes, width: int, height: int)`.
- Produces: `render_showcase_preview(source: bytes) -> ShowcasePreview`.
- Produces model fields `is_public_showcase`, `showcase_download_allowed`, `showcase_preview_key`, `showcase_preview_width`, `showcase_preview_height`, `showcased_at`, and `showcased_by`.
- Produces audit action `AdminAction.IMAGE_SHOWCASE_UPDATE = "image.showcase.update"`.

- [ ] **Step 1: Write failing preview and migration tests**

Add literal Pillow fixtures covering a 2400×1200 JPEG, an 800×400 PNG, and malformed bytes. Assert that the preview format is WebP, output dimensions are respectively 1200×600 and 800×400, aspect ratio is preserved, and malformed bytes raise `ValueError("公开预览图无法解码")`. Extend the migration test to assert all seven columns, false defaults for the two booleans, nullable preview/audit columns, and the showcase query index.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `uv run pytest tests/test_showcase_preview.py tests/test_admin_console_migration.py -q`

Expected: failures because the preview module, model fields, and migration do not exist.

- [ ] **Step 3: Implement the preview processor and migration**

Implement `render_showcase_preview` with `ImageOps.exif_transpose`, RGB conversion for modes incompatible with WebP, `thumbnail((1200, 1200), Image.Resampling.LANCZOS)`, and `save(..., format="WEBP", quality=82, method=6)`. Add SQLAlchemy fields and an Alembic revision on current head `b5c6d7e8f9a0`, including a composite descending showcase index appropriate to MySQL/SQLite-supported Alembic operations.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `uv run pytest tests/test_showcase_preview.py tests/test_admin_console_migration.py -q`

Expected: all focused tests pass.

- [ ] **Step 5: Commit**

```powershell
git add migrations/versions/c6d7e8f9a0b1_admin_public_showcase.py src/design_hub/application/showcase src/design_hub/infrastructure/db/models.py src/design_hub/domain/admin.py tests/test_showcase_preview.py tests/test_admin_console_migration.py
git commit -m "feat: add public showcase preview state" -m "Persist per-image publication and download policy, and add deterministic compressed preview rendering for public pages."
```

### Task 2: Manager publication workflow and moderation coupling

**Files:**
- Create: `src/design_hub/ports/showcase.py`
- Create: `src/design_hub/application/showcase/service.py`
- Create: `src/design_hub/infrastructure/db/showcase_repo.py`
- Modify: `src/design_hub/ports/admin_console.py`
- Modify: `src/design_hub/infrastructure/db/admin_console_repo.py`
- Modify: `src/design_hub/application/admin/admin_console_service.py`
- Modify: `src/design_hub/interface/admin_console_schemas.py`
- Modify: `src/design_hub/interface/api/admin_deps.py`
- Modify: `src/design_hub/interface/api/routes/admin_console.py`
- Modify: `src/design_hub/interface/api/asgi.py`
- Test: `tests/test_showcase_service.py`
- Test: `tests/test_admin_console.py`

**Interfaces:**
- Consumes: `render_showcase_preview(source: bytes) -> ShowcasePreview` and `ImageStore.load/save`.
- Produces: `ShowcaseStatusUpdate(is_public: bool, download_allowed: bool)` request schema.
- Produces: `ShowcaseService.set_publication(actor_id: int, image_id: int, is_public: bool, download_allowed: bool) -> AdminImageSummary`.
- Produces: admin list filter `showcase_status: Literal["public", "private"] | None` and summary fields for publication, prompt, preview dimensions, and download policy.

- [ ] **Step 1: Write failing service and API tests**

Cover publishing a normal successful image with a non-empty `listing_job.prompt`, preview upload and persisted dimensions, independent download-policy update, unpublishing, no-op 409, private+download 400, blocked/failed/blank-prompt 400, manager authorization, public/private filtering, audit action contents, and preview-processing failure leaving database publication fields unchanged. Extend the existing moderation test so blocking a published image clears publication/download state while restoring remains private.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `uv run pytest tests/test_showcase_service.py tests/test_admin_console.py -q`

Expected: failures for missing repository, service, route, fields, and moderation coupling.

- [ ] **Step 3: Implement repository, service, schemas, route, and wiring**

Add a dedicated showcase port/repository rather than pushing preview I/O into the existing admin repository. The service validates before I/O, reuses stored preview metadata when complete, otherwise loads the immutable original and saves the WebP preview, then calls one transactional repository method that updates publication fields and inserts `image.showcase.update`. Extend admin image queries with prompt/publication data and `showcase_status`. Update `set_image_moderation` so its existing transaction clears public/download state when blocking. Register one `ShowcaseService` in app state and expose it through a typed dependency.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `uv run pytest tests/test_showcase_service.py tests/test_admin_console.py -q`

Expected: all focused tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/design_hub/ports/showcase.py src/design_hub/application/showcase/service.py src/design_hub/infrastructure/db/showcase_repo.py src/design_hub/ports/admin_console.py src/design_hub/infrastructure/db/admin_console_repo.py src/design_hub/application/admin/admin_console_service.py src/design_hub/interface/admin_console_schemas.py src/design_hub/interface/api/admin_deps.py src/design_hub/interface/api/routes/admin_console.py src/design_hub/interface/api/asgi.py tests/test_showcase_service.py tests/test_admin_console.py
git commit -m "feat: manage public showcase from moderation" -m "Add audited publication controls, download policy, filters, and fail-fast preview creation to the existing image moderation workflow."
```

### Task 3: Database-backed public showcase and original-download authorization

**Files:**
- Modify: `src/design_hub/ports/showcase.py`
- Modify: `src/design_hub/application/showcase/service.py`
- Modify: `src/design_hub/infrastructure/db/showcase_repo.py`
- Modify: `src/design_hub/interface/showcase_schemas.py`
- Modify: `src/design_hub/interface/api/routes/showcase.py`
- Delete: `src/design_hub/config/showcase.py`
- Modify: `src/design_hub/interface/api/asgi.py`
- Test: `tests/test_showcase.py`

**Interfaces:**
- Produces: `ShowcaseItemOut(url, image_type, caption, prompt, download_allowed, width, height, recipe)`.
- Produces: `GET /showcase/{image_id}/download` response `{ "url": str }` only for currently authorized originals.
- Consumes: public repository rows joined from `listing_image` and `listing_job`, ordered by `showcased_at DESC, image_id DESC`.

- [ ] **Step 1: Replace static-list tests with failing database-backed contract tests**

Seed public/private, normal/blocked, successful/failed, downloadable/non-downloadable rows. Assert only eligible rows appear, order is deterministic, returned URLs sign preview keys, prompts equal `listing_job.prompt`, recipe plan derives from successful images in the same job, and no original/user/moderation/internal-prompt fields appear. Assert the download route signs `image_key` only for an eligible downloadable row and returns 404 for every other state.

- [ ] **Step 2: Run focused test and verify RED**

Run: `uv run pytest tests/test_showcase.py -q`

Expected: failures because `/showcase` still reads `SHOWCASE_ENTRIES` and no download route exists.

- [ ] **Step 3: Implement public query, schema mapping, download policy, and remove static config**

Build recipes strictly from persisted user fields (`category`, `ratio`, job image-type counts, `prompt`, and `modifiers`). Generate captions from category/image type without identity data. Route all public reads through `ShowcaseService`; sign only preview keys in list responses and original keys only after repository authorization in the download endpoint. Remove the static showcase config and update stale comments/imports.

- [ ] **Step 4: Run focused and backend regression tests**

Run: `uv run pytest tests/test_showcase.py tests/test_listing_history_repository.py tests/test_admin_console.py -q`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/design_hub/ports/showcase.py src/design_hub/application/showcase/service.py src/design_hub/infrastructure/db/showcase_repo.py src/design_hub/interface/showcase_schemas.py src/design_hub/interface/api/routes/showcase.py src/design_hub/interface/api/asgi.py tests/test_showcase.py
git add -u src/design_hub/config/showcase.py
git commit -m "feat: serve selected public showcase images" -m "Replace the static showcase with preview-only database queries and authorize original downloads from current per-image policy."
```

### Task 4: Regenerate the API contract and add manager UI controls

**Files:**
- Modify: `openapi.json`
- Modify: `../image-web/openapi.json`
- Modify: `../image-web/src/api/schema.d.ts`
- Modify: `../image-web/src/api/admin.ts`
- Create: `../image-web/src/components/admin/ShowcaseDialog.tsx`
- Modify: `../image-web/src/pages/AdminGenerationsPage.tsx`
- Modify: `../image-web/src/pages/AdminGenerationsPage.test.ts`

**Interfaces:**
- Consumes generated schemas `ShowcaseStatusUpdate` and expanded `AdminImageSummaryOut`.
- Produces hook `useUpdateAdminImageShowcase()` that invalidates admin images, audit, and `['showcase']` queries.
- Produces query filter `showcase_status: "public" | "private"`.

- [ ] **Step 1: Write failing manager-page tests**

Use complete admin image fixtures. Assert publication/download badges, user prompt preview, public/private filter options, disabled publication for blocked/failed/blank-prompt images, dialog copy warning that image and prompt become public, default-off download switch, and update payloads for publish, permission change, and unpublish.

- [ ] **Step 2: Run focused frontend test and verify RED**

Run from `../image-web`: `npm test -- src/pages/AdminGenerationsPage.test.ts`

Expected: failures because the new hook, controls, fields, and dialog do not exist.

- [ ] **Step 3: Regenerate OpenAPI artifacts and implement admin controls**

Generate backend OpenAPI using the repository's existing app export, copy it to the frontend, run `npm run gen:api`, then implement the typed mutation, filter, badges, prompt display, and focused dialog. Keep moderation and showcase actions separate but colocated on each image card.

- [ ] **Step 4: Run focused test and typecheck**

Run from `../image-web`: `npm test -- src/pages/AdminGenerationsPage.test.ts && npm run typecheck`

Expected: test and typecheck pass.

- [ ] **Step 5: Commit**

```powershell
git add openapi.json ../image-web/openapi.json ../image-web/src/api/schema.d.ts ../image-web/src/api/admin.ts ../image-web/src/components/admin/ShowcaseDialog.tsx ../image-web/src/pages/AdminGenerationsPage.tsx ../image-web/src/pages/AdminGenerationsPage.test.ts
git commit -m "feat: add showcase controls to image moderation" -m "Let managers publish images, review the public prompt, configure the download button, and filter by showcase state."
```

### Task 5: Adaptive `/home` cards and dynamic `/` marquee

**Files:**
- Modify: `../image-web/src/api/showcase.ts`
- Modify: `../image-web/src/pages/HomePage.tsx`
- Modify: `../image-web/src/pages/HomePage.test.ts`
- Modify: `../image-web/src/components/listing/ShowcaseDetailDialog.tsx`
- Modify: `../image-web/src/pages/HeroPage.tsx`
- Modify: `../image-web/src/components/home/MarqueeHero.tsx`
- Create: `../image-web/src/pages/HeroPage.test.ts`
- Delete: `../image-web/src/assets/hero/0d92feb99fbab119.jpg`
- Delete: `../image-web/src/assets/hero/1eefddf7817977db.jpg`
- Delete: `../image-web/src/assets/hero/246f6ede041a4db9.jpg`
- Delete: `../image-web/src/assets/hero/3098e021000cb9df.jpg`
- Delete: `../image-web/src/assets/hero/38649ef18aab21f6.jpg`
- Delete: `../image-web/src/assets/hero/41456dfd19a59f9c.jpg`
- Delete: `../image-web/src/assets/hero/45e44b0be1d71108.jpg`
- Delete: `../image-web/src/assets/hero/60c21b4106db5193.jpg`
- Delete: `../image-web/src/assets/hero/646a4327d24c053c.jpg`
- Delete: `../image-web/src/assets/hero/800dafd30b57c1e5.jpg`
- Delete: `../image-web/src/assets/hero/829999e37d136090.jpg`
- Delete: `../image-web/src/assets/hero/90b1ad78f8d61757.jpg`

**Interfaces:**
- Consumes: preview-only `ShowcaseItem` fields and `GET /showcase/{image_id}/download`.
- Produces: `downloadShowcaseOriginal(imageId: number, filename: string)`.
- Produces: `/home` adaptive column cards and `/` preview marquee.

- [ ] **Step 1: Write failing public-page tests**

For `/home`, assert preview image style/aspect comes from literal width/height, no fixed `aspect-[4/3]` wrapper is rendered, prompt summary and full detail prompt exist, download is absent when false, and allowed download calls the authorization API before the existing downloader. For `/`, assert it calls `useShowcase(true)`, passes preview URLs into `MarqueeHero`, keeps text/CTA with an empty/error result, and has no static hero imports.

- [ ] **Step 2: Run focused tests and verify RED**

Run from `../image-web`: `npm test -- src/pages/HomePage.test.ts src/pages/HeroPage.test.ts`

Expected: failures for fixed-ratio cards, missing prompt/download behavior, and static hero images.

- [ ] **Step 3: Implement adaptive cards, prompt, authorized download, and dynamic marquee**

Use CSS multi-column responsive layout with `break-inside: avoid` cards so natural heights do not stretch to row maxima. Set the preview container `aspectRatio` from `width / height`, render the image without cropping, clamp prompt summary to three lines, and show the full prompt in details. Add conditional download buttons wired to the authorization endpoint. Replace static hero imports with `useShowcase(true)` preview URLs and remove the unused assets.

- [ ] **Step 4: Run focused tests, lint, typecheck, and production build**

Run from `../image-web`: `npm test -- src/pages/HomePage.test.ts src/pages/HeroPage.test.ts && npm run lint && npm run typecheck && npm run build`

Expected: all commands pass with no errors.

- [ ] **Step 5: Commit**

```powershell
git add ../image-web/src/api/showcase.ts ../image-web/src/pages/HomePage.tsx ../image-web/src/pages/HomePage.test.ts ../image-web/src/components/listing/ShowcaseDetailDialog.tsx ../image-web/src/pages/HeroPage.tsx ../image-web/src/components/home/MarqueeHero.tsx ../image-web/src/pages/HeroPage.test.ts
git add -u ../image-web/src/assets/hero
git commit -m "feat: render adaptive public showcase cards" -m "Show preview-only selected images with original prompts and authorized downloads on home, and drive the landing marquee from the same public list."
```

### Task 6: Full verification

**Files:**
- Modify only files required by failures found during verification.

**Interfaces:**
- Consumes all earlier task outputs.
- Produces fresh evidence that migrations, backend contracts, frontend behavior, static analysis, and builds pass together.

- [ ] **Step 1: Run full backend verification**

Run from `image-code`:

```powershell
uv run alembic upgrade head
uv run pytest -q
uv run ruff check src tests
uv run mypy src
```

- [ ] **Step 2: Run full frontend verification**

Run from `image-web`:

```powershell
npm test
npm run lint
npm run typecheck
npm run build
```

- [ ] **Step 3: Verify contracts and repository state**

Run `git diff --check`, `git status --short`, and inspect the final OpenAPI paths/schemas for showcase publication and download authorization. Confirm no static `SHOWCASE_ENTRIES` or hero asset imports remain and no original key is serialized by public schemas.

- [ ] **Step 4: Commit verification fixes if needed**

If verification required code changes, repeat the failing command until green and commit those scoped fixes with a detailed `fix:` message. If no files changed, do not create an empty commit.
