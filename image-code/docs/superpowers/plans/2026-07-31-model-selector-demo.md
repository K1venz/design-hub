# Model Selector Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a DEV-only interactive page that compares three unified text-and-image model selector styles without changing Chat or calling production APIs.

**Architecture:** Keep fixtures and filtering as a tested pure module, then render three style variants from one shared demo state so selections can be compared consistently. Register the page through the existing DEV-only lazy-route pattern, ensuring no demo chunk is emitted by the production build.

**Tech Stack:** React 19, TypeScript 6, React Router 7, Tailwind CSS 4, Radix dropdown primitives already exposed by the project, Lucide React, Vitest.

## Global Constraints

- The demo is DEV-only and uses static fixtures; it cannot call model APIs.
- It presents exactly three variants: DeerFlow minimal, brand cards, and dual-model compact.
- Every variant supports search, `文本模型` and `图片模型` groups, immediate selection, selected checks, busy-state preview, and responsive truncation.
- Do not add dependencies or edit global design tokens.
- Do not modify the current Chat page, model stores, or backend.
- Do not display price, token usage, or estimated cost.
- Run all `npm` commands in `image-web/`.

---

## File structure

- `image-web/src/pages/model-selector-demo/demo-models.ts`: static model fixtures, model types, brand-logo source mapping, and pure search helper.
- `image-web/src/pages/model-selector-demo/demo-models.test.ts`: fixture and search behavior tests.
- `image-web/src/pages/model-selector-demo/ModelSelectorDemoPage.tsx`: page layout, shared selection state, three preview cards, and selector variants.
- `image-web/public/model-brands/{deepseek,doubao,openai,wan}.svg`: local provider marks used by every variant.
- `image-web/src/App.tsx`: DEV-only lazy import and `/model-selector-demo` route.

### Task 1: Demo model data and filtering

**Files:**
- Create: `image-web/src/pages/model-selector-demo/demo-models.ts`
- Test: `image-web/src/pages/model-selector-demo/demo-models.test.ts`
- Create: `image-web/public/model-brands/deepseek.svg`
- Create: `image-web/public/model-brands/doubao.svg`
- Create: `image-web/public/model-brands/openai.svg`
- Create: `image-web/public/model-brands/wan.svg`

**Interfaces:**
- Produces: `DemoModelKind`, `DemoBrand`, `DemoModel`, `DEMO_MODELS`, `brandLogoPath(brand)`, and `filterDemoModels(models, query)`.
- Consumes: no application state or API types; the demo remains isolated from production catalogs.

- [ ] **Step 1: Write the failing fixture and search tests**

```ts
import { describe, expect, it } from 'vitest'

import { DEMO_MODELS, brandLogoPath, filterDemoModels } from './demo-models'

describe('model selector demo fixtures', () => {
  it('contains two chat and two image models without pricing fields', () => {
    expect(DEMO_MODELS.filter((model) => model.kind === 'chat')).toHaveLength(2)
    expect(DEMO_MODELS.filter((model) => model.kind === 'image')).toHaveLength(2)
    expect(DEMO_MODELS.every((model) => !('price' in model))).toBe(true)
  })

  it('searches display name, model id, and brand case-insensitively', () => {
    expect(filterDemoModels(DEMO_MODELS, 'deepseek').map((model) => model.id))
      .toEqual(['deepseek-v4-flash'])
    expect(filterDemoModels(DEMO_MODELS, 'GPT IMAGE').map((model) => model.id))
      .toEqual(['gpt-image-2'])
    expect(filterDemoModels(DEMO_MODELS, '通义').map((model) => model.id))
      .toEqual(['wan2.7-image-pro'])
  })

  it('provides a local logo path for every fixture brand', () => {
    expect(DEMO_MODELS.every((model) => brandLogoPath(model.brand).startsWith('/model-brands/')))
      .toBe(true)
  })
})
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `npm test -- src/pages/model-selector-demo/demo-models.test.ts`

Expected: FAIL because `./demo-models` does not exist.

- [ ] **Step 3: Implement the isolated model fixtures and search helper**

```ts
export type DemoModelKind = 'chat' | 'image'
export type DemoBrand = 'deepseek' | 'doubao' | 'openai' | 'alibaba'

export interface DemoModel {
  id: string
  displayName: string
  brand: DemoBrand
  brandName: string
  kind: DemoModelKind
}

export const DEMO_MODELS: DemoModel[] = [
  { id: 'deepseek-v4-flash', displayName: 'DeepSeek V4 Flash', brand: 'deepseek', brandName: 'DeepSeek', kind: 'chat' },
  { id: 'doubao-chat', displayName: 'Doubao', brand: 'doubao', brandName: '豆包', kind: 'chat' },
  { id: 'gpt-image-2', displayName: 'GPT Image 2.0', brand: 'openai', brandName: 'OpenAI', kind: 'image' },
  { id: 'wan2.7-image-pro', displayName: 'Wan 2.7 Image Pro', brand: 'alibaba', brandName: '通义万相', kind: 'image' },
]

const LOGO_PATH: Record<DemoBrand, string> = {
  deepseek: '/model-brands/deepseek.svg',
  doubao: '/model-brands/doubao.svg',
  openai: '/model-brands/openai.svg',
  alibaba: '/model-brands/wan.svg',
}

export function brandLogoPath(brand: DemoBrand): string {
  return LOGO_PATH[brand]
}

export function filterDemoModels(models: DemoModel[], query: string): DemoModel[] {
  const normalized = query.trim().toLocaleLowerCase()
  if (!normalized) return models
  return models.filter((model) =>
    [model.displayName, model.id, model.brandName, model.brand]
      .some((value) => value.toLocaleLowerCase().includes(normalized)),
  )
}
```

- [ ] **Step 4: Add the four local SVG assets**

Use the current `@lobehub/icons-static-svg` package only as an asset source, not as an installed project dependency. Read `deepseek-color.svg`, `doubao-color.svg`, `openai.svg`, and `alibaba-color.svg` from the package archive, then add their exact SVG contents with `apply_patch` as `deepseek.svg`, `doubao.svg`, `openai.svg`, and `wan.svg`. The Alibaba mark represents its Wan image-model family without incorrectly borrowing another model's identity. Record the source package version in the commit body so the copied assets remain auditable.

- [ ] **Step 5: Run the focused test and verify it passes**

Run: `npm test -- src/pages/model-selector-demo/demo-models.test.ts`

Expected: PASS with 3 tests.

- [ ] **Step 6: Commit the tested demo data unit**

```bash
git add image-web/src/pages/model-selector-demo/demo-models.ts image-web/src/pages/model-selector-demo/demo-models.test.ts image-web/public/model-brands
git commit -m "test: define model selector demo fixtures" -m "Add isolated text and image model fixtures with deterministic search behavior and locally bundled provider marks sourced from the current @lobehub/icons-static-svg release for the DEV-only selector comparison page."
```

### Task 2: Three interactive selector variants

**Files:**
- Create: `image-web/src/pages/model-selector-demo/ModelSelectorDemoPage.tsx`

**Interfaces:**
- Consumes: `DemoModel`, `DEMO_MODELS`, `brandLogoPath`, and `filterDemoModels` from Task 1.
- Produces: named export `ModelSelectorDemoPage(): JSX.Element` for the DEV route.

- [ ] **Step 1: Build the shared page state and comparison shell**

Use one shared selection for all three previews so choosing a model in one style immediately updates the other two:

```tsx
export function ModelSelectorDemoPage() {
  const [chatModelId, setChatModelId] = useState('deepseek-v4-flash')
  const [imageModelId, setImageModelId] = useState('gpt-image-2')
  const [busy, setBusy] = useState(false)

  return (
    <main className="min-h-screen bg-[#f3f4f8] px-4 py-8 text-wb-ink-2 sm:px-8">
      <header className="mx-auto max-w-5xl">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-wb-brand-deep">Model picker study</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-[-0.025em]">统一模型入口 · 三种交互风格</h1>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-wb-ink-6">三款使用同一组模型与选择状态，便于只比较入口和下拉层级。</p>
        <label className="mt-5 inline-flex items-center gap-2 text-sm text-wb-ink-5">
          <input type="checkbox" checked={busy} onChange={(event) => setBusy(event.target.checked)} />
          模拟生成中（锁定选择器）
        </label>
      </header>
      <section className="mx-auto mt-7 grid max-w-5xl gap-6">
        {VARIANTS.map((variant) => (
          <SelectorPreview key={variant.id} variant={variant} chatModelId={chatModelId} imageModelId={imageModelId} busy={busy} onChatModelChange={setChatModelId} onImageModelChange={setImageModelId} />
        ))}
      </section>
    </main>
  )
}
```

- [ ] **Step 2: Implement the shared dropdown behavior**

Use the existing `DropdownMenu` exports. Render the search input first, then a `文本模型` label and chat rows, separator, and an `图片模型` label and image rows. Each row renders `BrandLogo`, a two-line label, and `CheckIcon` only when selected. Set a fixed `w-[min(360px,calc(100vw-32px))]` content width and open above the composer with `side="top"`.

The search input must stop `keydown` propagation so typing letters does not trigger Radix menu typeahead:

```tsx
<input
  value={query}
  onChange={(event) => setQuery(event.target.value)}
  onKeyDown={(event) => event.stopPropagation()}
  placeholder="搜索模型"
  aria-label="搜索模型"
  className="h-9 w-full rounded-lg border border-wb-line-1 bg-wb-surface-2 px-3 text-xs outline-none focus:border-wb-brand-soft"
/>
```

When an item is selected, call the matching change callback. Radix closes the menu after the selection; use `onOpenChange` to clear the search string on close.

- [ ] **Step 3: Implement the three trigger and row visual treatments**

Define these exact variants in the same file:

```ts
const VARIANTS = [
  { id: 'deerflow', name: 'A · DeerFlow 极简型', description: '最像成熟 AI 对话产品，信息密度高，入口紧邻发送。' },
  { id: 'brand-card', name: 'B · 品牌卡片型', description: '品牌识别最强，模型项更舒展，适合强调差异。' },
  { id: 'dual-compact', name: 'C · 双模型紧凑型', description: '触发器直接显示文本与图片模型，当前状态最透明。' },
] as const
```

- `deerflow`: one 32px-high neutral trigger with chat logo, chat display name, small overlaid image logo, and chevron. Dropdown rows are 44px high and neutral.
- `brand-card`: one 36px-high tinted trigger. Dropdown rows use a 32px brand tile and a light selected background, but no gradients.
- `dual-compact`: one shared bordered trigger containing two compact inner segments separated by a vertical rule; show both logos and truncate both display names.

Each preview must place the trigger immediately before a round send button inside the same composer mock:

```tsx
<div className="rounded-[22px] border border-white/80 bg-white/80 p-3 shadow-[0_18px_50px_-28px_rgba(40,40,90,.34)] backdrop-blur-xl">
  <textarea readOnly value="帮我生成一组适合电商首页的产品场景图" className="h-20 w-full resize-none bg-transparent px-2 py-1 text-sm outline-none" />
  <div className="flex items-center justify-between gap-3">
    <button type="button" className="rounded-full border border-wb-line-1 px-3 py-1.5 text-xs text-wb-ink-5">添加图片</button>
    <div className="flex min-w-0 items-center gap-2">
      <UnifiedDemoSelector />
      <button type="button" className="grid size-8 shrink-0 place-items-center rounded-full bg-wb-brand text-white" aria-label="发送"><SendIcon className="size-3.5" /></button>
    </div>
  </div>
</div>
```

- [ ] **Step 4: Check keyboard and responsive behavior manually**

Run: `npm run dev -- --host 127.0.0.1`

Open: `http://127.0.0.1:3000/model-selector-demo`

Expected:

- Tab reaches each selector and the busy checkbox.
- Enter/Space opens the selector above the composer.
- Typing filters both categories.
- Selecting a row updates all three preview triggers.
- At 390px viewport width, trigger content truncates and the dropdown stays inside the viewport.
- Busy mode disables all three triggers without hiding the current choices.

- [ ] **Step 5: Commit the interactive comparison page**

```bash
git add image-web/src/pages/model-selector-demo/ModelSelectorDemoPage.tsx
git commit -m "feat: add interactive model selector demos" -m "Compare DeerFlow-minimal, brand-card, and dual-model trigger treatments with shared searchable text and image model selection."
```

### Task 3: DEV-only route and verification

**Files:**
- Modify: `image-web/src/App.tsx`

**Interfaces:**
- Consumes: named export `ModelSelectorDemoPage` from Task 2.
- Produces: local route `GET /model-selector-demo` only when `import.meta.env.DEV` is true.

- [ ] **Step 1: Add the lazy DEV-only page import**

Place this beside the existing style-preview lazy imports:

```tsx
const ModelSelectorDemoPage = devLazy(() =>
  import('@/pages/model-selector-demo/ModelSelectorDemoPage').then((module) => ({
    default: module.ModelSelectorDemoPage,
  })),
)
```

- [ ] **Step 2: Register the route inside the existing DEV route guard**

Add this before `/style-preview` while retaining `Suspense` and the project loader:

```tsx
{import.meta.env.DEV && (
  <Route
    path="/model-selector-demo"
    element={
      <Suspense fallback={<FullPageLoader label="载入模型选择器演示…" />}>
        <ModelSelectorDemoPage />
      </Suspense>
    }
  />
)}
```

- [ ] **Step 3: Run focused tests and type checking**

Run:

```bash
npm test -- src/pages/model-selector-demo/demo-models.test.ts
npm run typecheck
```

Expected: both commands exit 0.

- [ ] **Step 4: Verify the production build excludes the demo page**

Run: `npm run build`

Expected: build exits 0 and `grep -R "统一模型入口" dist` returns no matches because the lazy import is guarded by `import.meta.env.DEV`.

- [ ] **Step 5: Commit the route and verified demo**

```bash
git add image-web/src/App.tsx
git commit -m "feat: expose model selector demo in development" -m "Register the comparison page through the existing DEV-only lazy route so production bundles remain unaffected."
```
