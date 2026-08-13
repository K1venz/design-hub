# Product Lobby Hierarchy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refresh `/home` into the approved capability-dispatch hierarchy while preserving the existing chat entry, showcase cards, and lazy-loading behavior.

**Architecture:** Keep `HomePage` as the composition boundary and retain its existing `Hero`, `ShowcaseSection`, and showcase card logic. Restyle the shared shell background and top navigation, then reshape only the tool-section presentation so core workspaces and utility destinations have distinct weights. No data-flow, route, API, or dependency changes are required.

**Tech Stack:** React 19, TypeScript 6, Tailwind CSS 4, Motion, Vitest, React Router

**Spec:** `docs/superpowers/specs/2026-08-13-product-lobby-hierarchy-design.md`

## Global Constraints

- Preserve the three-layer product architecture and every existing route responsibility.
- Preserve the current `/home` chat entry structure, visual language, and navigation behavior.
- Preserve `ShowcaseCard`, `ShowcaseSkeleton`, `SHOWCASE_BATCH`, original-ratio masonry, browser image lazy loading, and the intersection sentinel.
- Use the approved low-saturation mist-blue background palette without adding dependencies or backend APIs.
- Do not modify `/chat`, structured workbench business forms, or the admin UI.

---

### Task 1: Lock the approved product-lobby contract

**Files:**
- Modify: `image-web/src/pages/HomePage.test.ts`
- Modify: `image-web/src/components/layout/navigation-source.test.ts`

**Interfaces:**
- Consumes: current server-rendered markup from `HomePage` and `AppTopBar`
- Produces: regression assertions for hierarchy labels, current chat surface, showcase cards, and full-width navigation

- [ ] **Step 1: Add failing assertions**

Assert that `/home` contains the section labels `选择一个工作台`, `快捷工具`, and `看看实朴出的图`; retains `glass-panel`, `添加商品图`, `下载原图`, `break-inside-avoid`, and `columns-1`; and no longer renders the legacy top-bar width `max-w-[840px]`.

- [ ] **Step 2: Run focused tests and verify failure**

Run: `npm test -- src/pages/HomePage.test.ts src/components/layout/navigation-source.test.ts`

Expected: hierarchy and navigation-frame assertions fail before implementation.

- [ ] **Step 3: Commit the contract tests**

Run: `git add image-web/src/pages/HomePage.test.ts image-web/src/components/layout/navigation-source.test.ts && git commit -m "test: define product lobby hierarchy" -m "Lock the approved home sections, retained chat entry and showcase behavior, and the unified navigation frame before changing the UI."`

### Task 2: Implement the unified shell and navigation surface

**Files:**
- Modify: `image-web/src/index.css`
- Modify: `image-web/src/components/layout/AppShell.tsx`
- Modify: `image-web/src/components/layout/AppTopBar.tsx`
- Test: `image-web/src/components/layout/navigation-source.test.ts`

**Interfaces:**
- Consumes: `PRIMARY_NAV_ITEMS`, auth store, existing `ProfileMenu` and `MobileNavigation`
- Produces: the same `AppShell({ children })` and `AppTopBar()` interfaces with an approved low-saturation background and stable full-width navigation frame

- [ ] **Step 1: Add the mist background utility and aligned tokens**

Replace the current colored blob canvas with a static low-frequency background built from `#EEF1F7`, `#E7E7F3`, `#EEEAF3`, and `#E8EEF3`. Keep the center neutral and use no animated or saturated layers.

- [ ] **Step 2: Restyle the top bar without changing destinations**

Use a quiet full-width near-white frame with a faint bottom border. Keep brand left, product navigation centered, and account right; display desktop labels directly instead of hover-only expansion.

- [ ] **Step 3: Run navigation tests**

Run: `npm test -- src/components/layout/navigation.test.ts src/components/layout/navigation-source.test.ts`

Expected: PASS.

- [ ] **Step 4: Commit the shell unit**

Run: `git add image-web/src/index.css image-web/src/components/layout/AppShell.tsx image-web/src/components/layout/AppTopBar.tsx image-web/src/components/layout/navigation-source.test.ts && git commit -m "feat: unify product shell styling" -m "Introduce the approved mist-blue background and stable full-width product navigation while preserving destinations, account behavior, and mobile access."`

### Task 3: Recompose the product lobby hierarchy

**Files:**
- Modify: `image-web/src/pages/HomePage.tsx`
- Modify: `image-web/src/lib/home.ts`
- Test: `image-web/src/pages/HomePage.test.ts`
- Test: `image-web/src/lib/home.test.ts`

**Interfaces:**
- Consumes: `TOOL_BANNERS`, `TOOL_TILES`, `useShowcase`, existing chat `askAgent(q)` navigation
- Produces: L1 chat entry, L2 core-workspace cards, L3 utility cards, and unchanged L4 showcase behavior

- [ ] **Step 1: Preserve and place the existing chat entry**

Keep the current title, glass panel, textarea, product-image control, send control, keyboard behavior, and `/chat` navigation. Adjust only surrounding spacing and content width.

- [ ] **Step 2: Separate core workspaces from utilities**

Render `选择一个工作台` above the two `TOOL_BANNERS` cards and `快捷工具` above `TOOL_TILES`. Give core cards larger media-led layouts and utility cards a compact horizontal treatment.

- [ ] **Step 3: Preserve showcase rendering and lazy loading**

Leave the showcase query gate, `SHOWCASE_GRID`, `SHOWCASE_BATCH`, `IntersectionObserver`, `ShowcaseCard`, and `ShowcaseSkeleton` behavior intact. Permit only token-aligned card surface changes.

- [ ] **Step 4: Run home tests**

Run: `npm test -- src/pages/HomePage.test.ts src/lib/home.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit the lobby unit**

Run: `git add image-web/src/pages/HomePage.tsx image-web/src/lib/home.ts image-web/src/pages/HomePage.test.ts image-web/src/lib/home.test.ts && git commit -m "feat: establish product lobby hierarchy" -m "Separate the AI entry, primary workspaces, utility tools, and existing showcase flow while retaining the current chat and lazy-loading interactions."`

### Task 4: Verify and launch the local review build

**Files:**
- Verify only: `image-web`

**Interfaces:**
- Consumes: completed product-lobby implementation
- Produces: tested production build and a running local Vite review URL

- [ ] **Step 1: Run the complete test suite**

Run: `npm test`

Expected: all tests pass.

- [ ] **Step 2: Run lint and production build**

Run: `npm run lint`

Expected: no ESLint errors.

Run: `npm run build`

Expected: TypeScript and Vite build complete successfully.

- [ ] **Step 3: Start the local Vite server**

Run: `npm run dev -- --host 127.0.0.1`

Expected: Vite serves `http://127.0.0.1:3000/` and `/home` is reachable.

- [ ] **Step 4: Visually inspect desktop and mobile**

Verify `/home` at desktop width and a 390px mobile viewport: hierarchy, no horizontal overflow, unchanged chat controls, intact showcase cards, and successful lazy loading when real showcase data is available.

- [ ] **Step 5: Commit verification fixes if required**

Any implementation defect found during visual inspection must be fixed in the responsible component and committed using `fix: ...` with a detailed body before requesting user review.
