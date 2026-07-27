# Top Navigation And Footer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the left sidebar with the approved centered icon navigation, add the transparent external-link brand logo and profile menu, and formalize the ICP footer.

**Architecture:** A navigation data module owns route metadata shared by desktop and mobile renderers. `AppTopBar` owns all global navigation and account interactions, while `AppShell` becomes a simple vertical frame and `WorkbenchLayout` owns its page-specific new-task action. `SiteFooter` remains the single footer source and gets one dedicated legal registration row.

**Tech Stack:** React 19, React Router 7, TypeScript 6, Tailwind CSS 4, Radix UI, Lucide React, Vitest.

## Global Constraints

- Desktop navbar maximum width is `840px` and the primary navigation group must remain centered relative to the viewport.
- Brand logo renders at `26 × 30px`, contains no text, and links to `https://image.sepaitech.com/`.
- Primary labels are `首页`, `帮我设计`, `商品套图`, `爆款复刻`, `历史`.
- Desktop labels expand on hover and keyboard focus; mobile navigation always shows labels.
- Remove `内测` and `内测免费`.
- Profile content depends on anonymous, regular-user, and manager state.
- Footer text is `浙ICP备2026024031号-1 · Copyright © 2026 浙江实朴数据科技有限公司`.
- Do not add a public-security badge or number.

---

### Task 1: Navigation Contract

**Files:**
- Create: `image-web/src/components/layout/navigation.ts`
- Test: `image-web/src/components/layout/navigation.test.ts`

**Interfaces:**
- Produces: `PRIMARY_NAV_ITEMS`, `MANAGER_NAV_ITEMS`, `getAccountNavItems(role)`

- [ ] **Step 1: Write the failing test**

Assert the exact five public labels and routes, and assert that management routes are returned only for role `管理者`.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/components/layout/navigation.test.ts`
Expected: FAIL because `navigation.ts` does not exist.

- [ ] **Step 3: Write minimal implementation**

Define typed immutable route metadata using Lucide icon components. Keep role filtering in `getAccountNavItems`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- src/components/layout/navigation.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit navigation contract and its test as one unit.

### Task 2: Centered Global Navigation

**Files:**
- Modify: `image-web/src/components/layout/AppTopBar.tsx`
- Modify: `image-web/src/components/layout/AppShell.tsx`
- Modify: `image-web/src/components/layout/WorkbenchLayout.tsx`
- Delete: `image-web/src/components/layout/SideNav.tsx`
- Create: `image-web/src/assets/brand/shipu-mark.png`
- Test: `image-web/src/components/layout/navigation-source.test.ts`

**Interfaces:**
- Consumes: `PRIMARY_NAV_ITEMS`, `getAccountNavItems(role)`
- Produces: responsive desktop/mobile navigation and account menu

- [ ] **Step 1: Write the failing source-contract test**

Assert that `AppTopBar` references the external home URL, contains the approved expansion classes, exposes mobile menu semantics, and contains neither retired beta copy nor avatar UI.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/components/layout/navigation-source.test.ts`
Expected: FAIL against the old top bar.

- [ ] **Step 3: Implement the navigation**

Build a three-column `max-w-[840px]` navbar, icon pills with hover/focus label expansion, mobile menu with visible labels, and a role-aware Profile dropdown. Simplify `AppShell` to a vertical frame and move the new-task button into `WorkbenchLayout`.

- [ ] **Step 4: Remove obsolete sidebar**

Delete `SideNav.tsx` and all imports. No compatibility wrapper remains.

- [ ] **Step 5: Run focused and full tests**

Run: `npm test -- src/components/layout/navigation-source.test.ts`
Run: `npm test`
Expected: PASS.

- [ ] **Step 6: Commit**

Commit the complete navigation refactor and transparent asset as one unit.

### Task 3: Formal ICP Footer

**Files:**
- Modify: `image-web/src/components/layout/SiteFooter.tsx`
- Test: `image-web/src/components/layout/footer.test.ts`

**Interfaces:**
- Produces: one exact, responsive legal registration row

- [ ] **Step 1: Write the failing test**

Assert the exact ICP number, full legal company name, copyright wording, MIIT URL, and absence of public-security badge copy.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/components/layout/footer.test.ts`
Expected: FAIL because the old footer splits abbreviated copyright and ICP text.

- [ ] **Step 3: Implement the footer row**

Keep existing brand, contact, main, and legal navigation. Add a separated centered row with the linked ICP number followed by `· Copyright © 2026 浙江实朴数据科技有限公司`.

- [ ] **Step 4: Run focused and full tests**

Run: `npm test -- src/components/layout/footer.test.ts`
Run: `npm test`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit footer implementation and test as one unit.

### Task 4: Verification

**Files:**
- Modify only files required by verified defects.

**Interfaces:**
- Consumes: completed navigation and footer
- Produces: build and browser evidence

- [ ] **Step 1: Run static checks**

Run: `npm run lint`
Run: `npm run typecheck`
Expected: both PASS.

- [ ] **Step 2: Run test and production build**

Run: `npm test`
Run: `npm run build`
Expected: all tests PASS and Vite build succeeds.

- [ ] **Step 3: Verify desktop behavior**

Open the local app at desktop width and verify centered navigation, active state, hover expansion, external Logo link, Profile menu, and footer line.

- [ ] **Step 4: Verify mobile behavior**

Use a 390px viewport and verify menu labels, close behavior, no overflow, and wrapped footer.

- [ ] **Step 5: Commit any verification fixes**

If verification exposes defects, fix them test-first and commit each coherent correction.
