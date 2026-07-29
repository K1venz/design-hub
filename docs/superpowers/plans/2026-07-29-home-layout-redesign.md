# Home Page Centered Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the `/home` content below the Navbar around one centered chat action, remove duplicate or unreal content, and make the layout safe at 390, 768, 1280, and 1440px.

**Architecture:** Keep the change inside the existing `HomePage` and Home static-data module. Use Tailwind Grid/Flex and natural document flow for layout, retain the current chat navigation and showcase request, and render the showcase section only after a non-empty real response.

**Tech Stack:** React 19, TypeScript 6, React Router, TanStack Query, Tailwind CSS 4, Vitest, React server-side static rendering for component contracts.

## Global Constraints

- Navbar, routes, chat submission behavior, login redirects, backend APIs, result-card behavior, and Footer are out of scope.
- The page content rail is at most about 1060px; the centered chat panel is at most about 920px.
- Remove the six Hero quick cards, the right-side decorative area, the two “coming soon” cards, and all fake showcase placeholders.
- Keep only the five real tool destinations: 商品套图, 爆款图复刻, 单图出图, 二次编辑, 出图历史.
- Preserve viewport-triggered showcase loading; do not add a request, dependency, image, video, blur effect, or continuous animation.
- At 390, 768, 1280, and 1440px there must be no text overlap, horizontal overflow, clipped action, or fixed-position drift.
- Do not add compatibility shims; delete retired constants and their unused imports.
- Code comments remain concise and in English unless an existing local comment is being updated.

---

## File Structure

- Modify `image-web/src/pages/HomePage.tsx`
  - Owns the centered Hero, real-tool layout, showcase loading sentinel, and conditional showcase rendering.
- Create `image-web/src/pages/HomePage.test.tsx`
  - Owns Home page rendering contracts for content, empty states, and retained real showcase data.
- Modify `image-web/src/lib/home.ts`
  - Owns only the static definitions for real Home tool destinations.
- Modify `image-web/src/lib/home.test.ts`
  - Owns static-data contracts: exact tool inventory, price copy, and absence of retired exports.

No CSS file, API file, route file, shared layout, or backend file is added or modified.

---

### Task 1: Center the Hero and retain only real tool entry points

**Files:**
- Create: `image-web/src/pages/HomePage.test.tsx`
- Modify: `image-web/src/pages/HomePage.tsx:12-164`
- Modify: `image-web/src/lib/home.ts:1-99`
- Modify: `image-web/src/lib/home.test.ts:1-13`

**Interfaces:**
- Consumes: existing `useNavigate()` and `navigate('/chat', { state: { q } })` contract.
- Consumes: existing `TOOL_BANNERS` and `TOOL_TILES` arrays.
- Produces: `HomePage` with `max-w-[1060px]` page rail, `max-w-[920px]` chat panel, `aria-label="描述你的设计需求"`, and only real tool links.
- Produces: `home.ts` exports only `TOOL_BANNERS`, `TOOL_TILES`, and their corresponding interfaces.

- [ ] **Step 1: Add failing static-data tests**

Replace `image-web/src/lib/home.test.ts` with:

```ts
import { describe, expect, it } from 'vitest'

import * as home from './home'

describe('home tool content', () => {
  it('exposes only the five real tool destinations', () => {
    expect(home.TOOL_BANNERS.map(({ key, to }) => ({ key, to }))).toEqual([
      { key: 'set', to: '/set' },
      { key: 'clone', to: '/clone' },
    ])
    expect(home.TOOL_TILES.map(({ key, to }) => ({ key, to }))).toEqual([
      { key: 'single', to: '/set' },
      { key: 'edit', to: '/history' },
      { key: 'history', to: '/history' },
    ])
  })

  it('does not export retired quick cards or coming-soon cards', () => {
    expect(Object.keys(home)).not.toContain('QUICK_CARDS')
    expect(Object.keys(home)).not.toContain('COMING_SOON')
  })

  it('shows the fixed ordinary image price', () => {
    expect(home.TOOL_TILES.find((tile) => tile.key === 'single')?.desc).toBe(
      '只出一张 · ¥0.05',
    )
  })
})
```

- [ ] **Step 2: Add a failing Home layout contract test**

Create `image-web/src/pages/HomePage.test.tsx`:

```tsx
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { HomePage } from './HomePage'

const mockUseShowcase = vi.hoisted(() => vi.fn())

vi.mock('@/api/showcase', () => ({
  useShowcase: mockUseShowcase,
}))

vi.mock('@/components/listing/ShowcaseDetailDialog', () => ({
  ShowcaseDetailDialog: () => null,
}))

function renderHome() {
  return renderToStaticMarkup(
    createElement(
      MemoryRouter,
      { initialEntries: ['/home'] },
      createElement(HomePage),
    ),
  )
}

describe('HomePage layout', () => {
  beforeEach(() => {
    mockUseShowcase.mockReset()
    mockUseShowcase.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    })
  })

  it('centers one resilient chat action above the real tools', () => {
    const html = renderHome()

    expect(html).toContain('max-w-[1060px]')
    expect(html).toContain('max-w-[920px]')
    expect(html).toContain('aria-label="描述你的设计需求"')
    expect(html).toContain('用大白话描述你的产品和想要的效果')
    expect(html).toContain('flex-wrap')
    expect(html).toContain('min-[900px]:grid-cols-2')
    expect(html).toContain('min-[900px]:grid-cols-3')
  })

  it('does not render duplicate or unavailable feature cards', () => {
    const html = renderHome()

    expect(html).not.toContain('纯白底 · 平台合规主图')
    expect(html).not.toContain('生活使用场景 · 有氛围')
    expect(html).not.toContain('AI 消除')
    expect(html).not.toContain('智能扩图')
  })
})
```

- [ ] **Step 3: Run the focused tests and verify they fail for the intended reasons**

Run:

```bash
cd image-web
npm test -- src/lib/home.test.ts src/pages/HomePage.test.tsx
```

Expected:

- `home.test.ts` fails because `QUICK_CARDS` and `COMING_SOON` are still exported.
- `HomePage.test.tsx` fails because the page still uses `max-w-5xl`, `max-w-2xl`, renders quick cards, and renders coming-soon cards.
- There are no unrelated module-resolution or test-environment failures.

- [ ] **Step 4: Remove retired Home static data**

Change the icon import at the top of `image-web/src/lib/home.ts` to:

```ts
import {
  ImageIcon,
  LayersIcon,
  FlameIcon,
  SquarePenIcon,
  HistoryIcon,
  type LucideIcon,
} from 'lucide-react'
```

Delete these declarations completely:

```ts
export interface QuickCard {
  key: string
  label: string
  desc: string
  icon: LucideIcon
  intent: string
}

export const QUICK_CARDS: QuickCard[] = [
  { key: 'white', label: '白底主图', desc: '纯白底 · 平台合规主图', icon: ImageIcon,
    intent: '帮我的产品出一张白底主图，产品居中、细节清晰。' },
  { key: 'scene', label: '场景图', desc: '生活使用场景 · 有氛围', icon: SparklesIcon,
    intent: '帮我的产品出一张生活使用场景图，自然光、有氛围。' },
  { key: 'sell', label: '卖点图', desc: '核心卖点 · 细节特写', icon: TagIcon,
    intent: '帮我的产品出一张卖点图，突出核心卖点和细节特写。' },
  { key: 'set', label: '整套套图', desc: '白底+场景+卖点 一键成套', icon: LayersIcon,
    intent: '给我的产品出一整套电商图，白底、场景、卖点都要。' },
  { key: 'clone', label: '爆款复刻', desc: '照着爆款图出你的', icon: FlameIcon,
    intent: '我有一张想参考的爆款图，帮我照它的风格出我的产品图。' },
  { key: 'edit', label: '二次编辑', desc: '对已出的图再调整', icon: SquarePenIcon,
    intent: '我想对之前出好的一张图再改一下。' },
]

export interface ComingSoonTile {
  key: string
  label: string
  desc: string
  icon: LucideIcon
}

export const COMING_SOON: ComingSoonTile[] = [
  { key: 'erase', label: 'AI 消除', desc: '一键擦除画面里的多余物件', icon: EraserIcon },
  { key: 'expand', label: '智能扩图', desc: '自动补全画面、改比例不裁切', icon: ExpandIcon },
]
```

Keep `TOOL_BANNERS`, `TOOL_TILES`, and the showcase placeholders temporarily; Task 2 removes showcase placeholders together with their renderer so the branch remains compilable after each task.

- [ ] **Step 5: Replace the Home content rail and Hero**

In `image-web/src/pages/HomePage.tsx`, change the Home static-data import to:

```ts
import {
  TOOL_BANNERS,
  TOOL_TILES,
  SHOWCASE_PLACEHOLDERS,
} from '@/lib/home'
```

Change the page rail to:

```tsx
<div className="mx-auto w-full max-w-[1060px] px-4 sm:px-6">
```

Replace the current `Hero` return value with:

```tsx
return (
  <section className="pt-8 text-center sm:pt-12">
    <h1 className="font-display text-[30px] font-semibold leading-[1.12] tracking-tight sm:text-[40px] lg:text-[44px]">
      和我聊聊，<span className="aurora-text">你想要什么设计？</span>
    </h1>

    <div className="glass-panel mx-auto mt-6 flex min-h-[184px] w-full max-w-[920px] flex-col rounded-[22px] p-4 text-left sm:p-5">
      <textarea
        aria-label="描述你的设计需求"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') askAgent(text)
        }}
        placeholder={'用大白话描述你的产品和想要的效果，实朴帮你完成白底、场景、卖点等电商图片。\\n例如：帮我的高山七彩花生礼盒出一套电商图，早餐桌场景、暖光…'}
        className="min-h-[112px] w-full flex-1 resize-none bg-transparent px-1 py-1 text-[14.5px] leading-relaxed text-wb-ink-2 outline-none placeholder:text-wb-faint-1"
      />
      <div className="mt-auto flex flex-wrap items-center justify-between gap-3 pt-4">
        <button
          onClick={() => askAgent(text)}
          className="flex items-center gap-1.5 rounded-full border border-wb-line-1 bg-white/70 px-3 py-1.5 text-[12.5px] font-medium text-wb-ink-4 transition-colors hover:border-wb-brand-soft hover:text-wb-brand-deep"
        >
          <ImagePlusIcon className="size-4" /> 添加商品图
        </button>
        <button
          onClick={() => askAgent(text)}
          className="flex items-center gap-1.5 rounded-full bg-gradient-to-r from-wb-grad-from to-wb-grad-to px-4 py-1.5 text-[13px] font-semibold text-white shadow-[0_8px_20px_-8px_rgba(91,91,214,.6)] transition-shadow hover:shadow-[0_10px_24px_-8px_rgba(91,91,214,.75)]"
        >
          发送 <SendIcon className="size-3.5" />
        </button>
      </div>
    </div>
  </section>
)
```

Delete the old subtitle paragraph and the complete `QUICK_CARDS.map(...)` grid. Update the nearby Hero comment so it no longer claims that six quick cards exist.

- [ ] **Step 6: Make the tool grid responsive without unavailable cards**

In `ToolSection`:

- Change the section spacing to `className="mt-10 sm:mt-12"`.
- Change the main-tool grid to:

```tsx
<div className="grid gap-3 min-[900px]:grid-cols-2">
```

- Change the auxiliary-tool grid to:

```tsx
<div className="mt-3 grid gap-3 min-[900px]:grid-cols-3">
```

- Delete the entire `COMING_SOON.map(...)` block.
- Update the section comment so it describes two real banners and three real tool tiles only.

- [ ] **Step 7: Run focused tests and type checking**

Run:

```bash
cd image-web
npm test -- src/lib/home.test.ts src/pages/HomePage.test.tsx
npm run typecheck
```

Expected: all focused tests pass and TypeScript reports no errors.

- [ ] **Step 8: Commit the centered Hero and real tools**

Run:

```bash
git add image-web/src/pages/HomePage.tsx image-web/src/pages/HomePage.test.tsx image-web/src/lib/home.ts image-web/src/lib/home.test.ts
git commit -m "feat: center the Home chat experience" -m "Remove duplicate Hero shortcuts and unavailable tool cards, widen the resilient chat panel, and keep only real tool destinations across desktop and mobile layouts."
```

---

### Task 2: Hide the showcase until real content exists

**Files:**
- Modify: `image-web/src/pages/HomePage.tsx:166-243`
- Modify: `image-web/src/pages/HomePage.test.tsx`
- Modify: `image-web/src/lib/home.ts:79-99`
- Modify: `image-web/src/lib/home.test.ts`

**Interfaces:**
- Consumes: `useShowcase(enabled: boolean)` returning TanStack Query state with `data?: ShowcaseItem[]`.
- Consumes: `useInView<HTMLDivElement>()` returning a trigger ref and a sticky `inView` boolean.
- Produces: a one-pixel invisible load sentinel before data exists.
- Produces: no visible showcase markup for loading, empty, or error states.
- Produces: the existing showcase section unchanged for non-empty real data.

- [ ] **Step 1: Extend the Home component tests for all showcase states**

Add this fixture near the top of `image-web/src/pages/HomePage.test.tsx`:

```tsx
const REAL_SHOWCASE_ITEM = {
  url: 'https://img.example.com/peanut.png',
  image_type: '场景',
  caption: '花生礼盒早餐场景',
  recipe: {
    category: '食品',
    ratio: '1:1',
    plan: { scene: 1 },
    styling: '自然暖光',
    modifiers: {},
  },
}

function setShowcaseState(state: Record<string, unknown>) {
  mockUseShowcase.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    ...state,
  })
}
```

Change the existing `beforeEach` to call:

```tsx
beforeEach(() => {
  mockUseShowcase.mockReset()
  setShowcaseState({ isLoading: true })
})
```

Add:

```tsx
describe('HomePage showcase visibility', () => {
  it.each([
    ['loading', { data: undefined, isLoading: true }],
    ['empty', { data: [], isLoading: false }],
    ['error', { data: undefined, isError: true, error: new Error('showcase unavailable') }],
  ])('hides the entire showcase for %s state', (_name, state) => {
    setShowcaseState(state)

    const html = renderHome()

    expect(html).not.toContain('看看实朴出的图')
    expect(html).not.toContain('案例即将上线')
  })

  it('renders the showcase when a real item exists', () => {
    setShowcaseState({ data: [REAL_SHOWCASE_ITEM] })

    const html = renderHome()

    expect(html).toContain('看看实朴出的图')
    expect(html).toContain('花生礼盒早餐场景')
    expect(html).not.toContain('案例即将上线')
  })
})
```

- [ ] **Step 2: Run the Home component test and verify the empty-state cases fail**

Run:

```bash
cd image-web
npm test -- src/pages/HomePage.test.tsx
```

Expected: loading, empty, and error cases fail because the page still renders the showcase heading and placeholder cards.

- [ ] **Step 3: Replace the visible placeholder branch with an invisible load sentinel**

In `ShowcaseSection`, keep all hooks before any conditional return. After the `useEffect` that handles incremental batches, add:

```tsx
if (!real) {
  return <div ref={ref} className="h-px w-full" aria-hidden />
}
```

Replace the existing conditional `<section ref={ref}>...</section>` with:

```tsx
return (
  <>
    <div ref={ref} className="h-px w-full" aria-hidden />
    <section className="mt-14">
      <SectionHead title="看看实朴出的图" sub="实朴真实出品 · 一键做同款" />
      <div className={SHOWCASE_GRID}>
        {real.slice(0, shown).map((item, index) => (
          <ShowcaseCard
            key={index}
            item={item}
            onMakeSame={() => makeSame(item.recipe)}
          />
        ))}
        {more &&
          Array.from({ length: Math.min(SHOWCASE_BATCH, real.length - shown) }).map((_, index) => (
            <ShowcaseSkeleton key={`sk-${index}`} />
          ))}
      </div>
      {more && <div ref={sentinelRef} className="h-1 w-full" aria-hidden />}
    </section>
  </>
)
```

This keeps the first request lazy, removes the visible loading/empty/error block, and preserves incremental rendering after real data exists.

- [ ] **Step 4: Delete showcase placeholder data and stale comments**

In `image-web/src/pages/HomePage.tsx`:

- Remove `SHOWCASE_PLACEHOLDERS` from the `@/lib/home` import.
- Rewrite the showcase section comment to state that loading, empty, and error states are visually hidden.

In `image-web/src/lib/home.ts`, delete:

```ts
export interface ShowcaseItem {
  key: string
  title: string
  tag: string
}

export const SHOWCASE_PLACEHOLDERS: ShowcaseItem[] = [
  { key: 's1', title: '花生礼盒 · 整套套图', tag: '套图' },
  { key: 's2', title: '零食袋 · 爆款复刻', tag: '复刻' },
  { key: 's3', title: '坚果罐 · 场景图', tag: '场景' },
  { key: 's4', title: '糖果 · 白底主图', tag: '白底' },
  { key: 's5', title: '茶饮 · 卖点图', tag: '卖点' },
  { key: 's6', title: '干货 · 二次编辑', tag: '编辑' },
]
```

In `image-web/src/lib/home.test.ts`, extend the retired-export test:

```ts
expect(Object.keys(home)).not.toContain('SHOWCASE_PLACEHOLDERS')
```

- [ ] **Step 5: Run the complete front-end verification suite**

Run:

```bash
cd image-web
npm test
npm run typecheck
npm run lint
npm run build
```

Expected:

- all Vitest tests pass;
- TypeScript reports no errors;
- ESLint reports no errors;
- Vite production build completes successfully.

- [ ] **Step 6: Verify layout behavior in a browser**

Start or reuse the local Vite app and open `http://127.0.0.1:3000/home`. Check viewport widths 390, 768, 1280, and 1440px.

At each width, verify:

```text
document.documentElement.scrollWidth <= window.innerWidth
```

Also verify:

- the chat panel does not intersect the “用实朴的工具” heading;
- the upload and send buttons remain inside the chat panel;
- the title wraps without clipping;
- 390px and 768px show one tool column;
- 1280px and 1440px show two main-tool columns and three auxiliary-tool columns;
- no Hero quick card, right-side filler, coming-soon card, or fake showcase card is visible;
- a real showcase response still renders the section.

If a viewport check fails, add a focused regression assertion to `HomePage.test.tsx`, apply the smallest Grid/Flex class correction in `HomePage.tsx`, and rerun Step 5 before continuing.

- [ ] **Step 7: Commit showcase visibility and responsive completion**

Run:

```bash
git add image-web/src/pages/HomePage.tsx image-web/src/pages/HomePage.test.tsx image-web/src/lib/home.ts image-web/src/lib/home.test.ts
git commit -m "fix: hide empty Home showcase content" -m "Keep showcase loading lazy while rendering the section only for real items, remove fake placeholders, and verify the centered Home layout across mobile and desktop widths."
```

---

## Final Completion Check

- [ ] `git diff --check HEAD~2..HEAD` reports no whitespace errors across both implementation commits.
- [ ] `git status --short` contains no uncommitted files from this implementation.
- [ ] The two implementation commits contain only the four planned Home files.
- [ ] The Navbar, API schema, backend, routes, shared design tokens, and Footer have no diff.
- [ ] Report the exact test, typecheck, lint, build, and viewport evidence to the user.
