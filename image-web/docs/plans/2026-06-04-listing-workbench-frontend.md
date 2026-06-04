# Listing 出图工作台前端重做 · 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `/`（工作台）从「项目列表」重做成 designkit product-kit 式的「左配置 / 右画布」单页，对接后端 `/listing/*`（multipart 直传 + 纯 prompt 直出 + SSE 逐张到达），删除项目/改稿/导出，满意即下载。

**Architecture:** 纯领域逻辑（枚举/FormData/事件解析）放 `src/lib/listing.ts`（vitest 单测）；React Query/SSE hooks 放 `src/api/listing.ts`；UI 放 `src/components/listing/*`；`/` 走独立全屏 `WorkbenchLayout`（自带左 rail），管理页留在 `AppLayout`，入口收进头像菜单。无 project 概念。

**Tech Stack:** React 19 + Vite 8 + TS + Tailwind v4 + Radix(select-rich) + TanStack Query + Zustand(auth) + motion；新增 **vitest**（仅测纯逻辑）。

**契约源（以此为准）：** `image-code/docs/superpowers/specs/2026-06-04-listing-image-generation-design.md` §4；设计稿 `image-web/docs/出图工作台-v2-商品套图重做-设计.md`。

**全局约束（来自 CLAUDE.md）：** 老代码适配新架构、禁兼容层；fail-fast、不静默吞错；依赖只用 CLI 装、不手改 manifest；注释英文、面向用户中文；每完成一个任务**立即提交**（共享工作树：`git add` 只加自己明确路径，**禁 `git add -A`**）；提交信息无 co-author。

**✅ SSE 契约已核实（read image-code `routes/listing.py` + `application/listing/commands.py` + `domain/enums.py`）：**
- 传输 = **命名 SSE 事件**：`event: <type>\ndata: <json(payload)>\n\n`（`data` **不含** type）。前端**必须** `es.addEventListener(<type>, ...)`；原生 `EventSource.onmessage` 收不到命名事件。
- 事件序（`TaskEventType`）：`task_started{}` → `model_called{model}` → `image_generated{url,seed}` × N → `task_completed{total_cost}`；异常 `task_failed{error}`。
- **`image_generated` 无 index** → 前端按**到达顺序**填槽（非按下标）。
- 后端 `await service.generate()`（全部 N 张）后才连发事件 → 图"一波到达"，但 POST 立即返回 job_id，已解同步阻塞（ISSUE-0018）。

**⚠️ 仍待对齐：成本预估** —— listing 链路后端**无** cost-preview 端点；CTA 用客户端常量 `LISTING_UNIT_COST` 估算并标注"约"，待 PM/后端给真实单价（ISSUE-0021）。`task_completed.total_cost` 可在完成后显示真实总价。

---

## 文件结构

**新增**
- `src/lib/listing.ts` — 枚举(PLATFORMS/REGIONS/LANGUAGES/RATIOS)、`MODIFIER_FIELDS`、类型、`buildListingFormData`、`parseListingEvent`、`estimateCost`（纯函数，无 React/IO）
- `src/lib/listing.test.ts` — 纯逻辑单测
- `src/api/listing.ts` — `useListingGenerate`(mutation→job_id)、`useListingEvents`(SSE 订阅 hook)
- `src/components/listing/ConfigSelect.tsx` — 带 label 的下拉（包 select-rich 原语）
- `src/components/listing/ImageUploader.tsx` — 本地选图 ≤3，缩略图+删除
- `src/components/listing/ListingConfigPanel.tsx` — 配置栏（上传+5下拉+卖点+开始出图）
- `src/components/listing/ResultGallery.tsx` — 右画布（逐张到达+进度条+下载）
- `src/components/listing/WorkbenchRail.tsx` — 左导航（商品套图/爆款图复刻）
- `src/components/layout/WorkbenchLayout.tsx` — 全屏布局（顶栏+rail+内容+头像菜单）

**修改**
- `vite.config.ts` — 引入 vitest（改 `defineConfig` 来源 + 加 `test` 块）
- `src/pages/WorkbenchPage.tsx` — **重写**为两栏页编排
- `src/App.tsx` — 路由重构（`/` 走 WorkbenchLayout；管理页留 AppLayout）

**删除**（确认孤儿后）
- `src/pages/ProjectDetailPage.tsx`、`src/components/generate/GenerateStudio.tsx`、`src/components/revision/RevisionTab.tsx`、`src/components/export/ExportTab.tsx`、`src/api/generation.ts` 中的 `useProjectGenerate`、及仅服务旧项目列表/详情的 `src/components/project/*`（逐一 grep 确认）

---

## Task 0：引入 vitest

**Files:**
- Modify: `vite.config.ts`
- Modify: `package.json`（经 CLI，不手改）
- Create: `src/lib/smoke.test.ts`（验证 runner，过后删）

- [ ] **Step 1: 装 vitest（CLI，取最新）**

Run:
```bash
cd image-web && npm install -D vitest
```
Expected: `added ... vitest` 写入 devDependencies。

- [ ] **Step 2: 加 test 脚本（CLI，勿手改 package.json）**

Run:
```bash
cd image-web && npm pkg set scripts.test="vitest run" && npm pkg set scripts.test:watch="vitest"
```

- [ ] **Step 3: 让 vite.config 支持 test 块**

把 `vite.config.ts` 顶部 import 那行
```ts
import { defineConfig } from 'vite'
```
改为
```ts
import { defineConfig } from 'vitest/config'
```
并在 `export default defineConfig({ ... })` 的配置对象里、`server` 同级加：
```ts
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
```

- [ ] **Step 4: 写冒烟测试**

`src/lib/smoke.test.ts`:
```ts
import { describe, it, expect } from 'vitest'

describe('vitest runner', () => {
  it('works', () => {
    expect(1 + 1).toBe(2)
  })
})
```

- [ ] **Step 5: 跑通**

Run: `cd image-web && npm test`
Expected: PASS（1 passed）。

- [ ] **Step 6: 删冒烟 + 提交**

```bash
cd image-web && rm src/lib/smoke.test.ts
git add image-web/package.json image-web/package-lock.json image-web/vite.config.ts
git commit -m "chore(web): 引入 vitest（仅测纯逻辑单元）"
```

---

## Task 1：领域枚举 + 类型 + buildModifiers

**Files:**
- Create: `src/lib/listing.ts`
- Test: `src/lib/listing.test.ts`

- [ ] **Step 1: 写失败测试**

`src/lib/listing.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import {
  MODIFIER_FIELDS,
  DEFAULT_LISTING_CONFIG,
  buildModifiers,
  type ListingConfig,
} from '@/lib/listing'

describe('MODIFIER_FIELDS', () => {
  it('covers platform/region/language with user-confirmed enums', () => {
    const keys = MODIFIER_FIELDS.map((f) => f.key)
    expect(keys).toEqual(['platform', 'region', 'language'])
    const platform = MODIFIER_FIELDS.find((f) => f.key === 'platform')!
    expect(platform.options).toContain('TikTok Shop')
    expect(platform.options).toContain('抖音电商')
  })
})

describe('buildModifiers', () => {
  it('serializes only the modifier bag to JSON', () => {
    const cfg: ListingConfig = {
      ...DEFAULT_LISTING_CONFIG,
      modifiers: { platform: '京东', region: '中国', language: '中文' },
    }
    expect(buildModifiers(cfg)).toBe('{"platform":"京东","region":"中国","language":"中文"}')
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd image-web && npx vitest run src/lib/listing.test.ts`
Expected: FAIL（Cannot find module '@/lib/listing'）。

- [ ] **Step 3: 实现 `src/lib/listing.ts`（首段）**

```ts
// Domain types & pure helpers for the listing one-shot generation flow.
// No React, no IO — unit-tested in listing.test.ts.

export const PLATFORMS = [
  '亚马逊', '淘宝天猫1688', '拼多多', '京东', 'Temu', 'TikTok Shop', '抖音电商',
] as const
export const REGIONS = ['中国', '美国', '欧洲', '俄罗斯', '东南亚'] as const
export const LANGUAGES = ['英文', '中文', '俄语', '西语'] as const
export const RATIOS = ['1:1', '3:4', '9:16', '16:9'] as const
export type Ratio = (typeof RATIOS)[number]

export const N_MIN = 1
export const N_MAX = 7

/** A dropdown that maps into the generic `modifiers` bag. Add a dropdown = add here. */
export interface ModifierField {
  key: string
  label: string
  options: readonly string[]
}
export const MODIFIER_FIELDS: ModifierField[] = [
  { key: 'platform', label: '电商平台', options: PLATFORMS },
  { key: 'region', label: '国家地区', options: REGIONS },
  { key: 'language', label: '语言', options: LANGUAGES },
]

export interface ListingConfig {
  modifiers: Record<string, string>
  ratio: Ratio
  n: number
  prompt: string
}

export const DEFAULT_LISTING_CONFIG: ListingConfig = {
  modifiers: { platform: '亚马逊', region: '美国', language: '英文' },
  ratio: '1:1',
  n: 6,
  prompt: '',
}

export function buildModifiers(config: ListingConfig): string {
  return JSON.stringify(config.modifiers)
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd image-web && npx vitest run src/lib/listing.test.ts`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add image-web/src/lib/listing.ts image-web/src/lib/listing.test.ts
git commit -m "feat(web): listing 领域枚举与 modifiers 序列化"
```

---

## Task 2：buildListingFormData（组 multipart）

**Files:**
- Modify: `src/lib/listing.ts`
- Test: `src/lib/listing.test.ts`

- [ ] **Step 1: 追加失败测试**

在 `src/lib/listing.test.ts` 末尾追加：
```ts
import { buildListingFormData, type ListingGenerateInput } from '@/lib/listing'

describe('buildListingFormData', () => {
  const input: ListingGenerateInput = {
    images: [new File(['a'], 'a.png', { type: 'image/png' }),
             new File(['b'], 'b.png', { type: 'image/png' })],
    prompt: '早餐桌场景',
    ratio: '3:4',
    n: 6,
    modifiers: { platform: '亚马逊', region: '美国', language: '英文' },
  }

  it('appends each image under the same "images" key', () => {
    const fd = buildListingFormData(input)
    expect(fd.getAll('images')).toHaveLength(2)
  })

  it('appends scalar fields and JSON-stringified modifiers', () => {
    const fd = buildListingFormData(input)
    expect(fd.get('prompt')).toBe('早餐桌场景')
    expect(fd.get('ratio')).toBe('3:4')
    expect(fd.get('n')).toBe('6')
    expect(fd.get('modifiers')).toBe('{"platform":"亚马逊","region":"美国","language":"英文"}')
  })
})
```

- [ ] **Step 2: 跑确认失败**

Run: `cd image-web && npx vitest run src/lib/listing.test.ts`
Expected: FAIL（buildListingFormData 未导出）。

- [ ] **Step 3: 追加实现到 `src/lib/listing.ts`**

```ts
export interface ListingGenerateInput {
  images: File[]
  prompt: string
  ratio: string
  n: number
  modifiers: Record<string, string>
}

export function buildListingFormData(input: ListingGenerateInput): FormData {
  const fd = new FormData()
  for (const file of input.images) fd.append('images', file)
  fd.append('prompt', input.prompt)
  fd.append('ratio', input.ratio)
  fd.append('n', String(input.n))
  fd.append('modifiers', JSON.stringify(input.modifiers))
  return fd
}
```

- [ ] **Step 4: 跑确认通过**

Run: `cd image-web && npx vitest run src/lib/listing.test.ts`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add image-web/src/lib/listing.ts image-web/src/lib/listing.test.ts
git commit -m "feat(web): buildListingFormData 组装 multipart 出图入参"
```

---

## Task 3：parseListingEvent（SSE 事件解析）+ estimateCost

**Files:**
- Modify: `src/lib/listing.ts`
- Test: `src/lib/listing.test.ts`

> 事件名沿用 ISSUE-0018 观测：`image_generated`(单张完成,含 url/index/seed/latency/cost)、`task_completed`(全部完成)、`task_failed`(失败)、`task_started`/`model_called`(进度)。后端字段若不同，仅改本函数与其测试。

- [ ] **Step 1: 追加失败测试**

> 签名 = `parseListingEvent(type, rawData)`：type 来自 SSE `event:` 行，rawData 是 `data:` 行的 JSON。

```ts
import { parseListingEvent, estimateCost } from '@/lib/listing'

describe('parseListingEvent', () => {
  it('maps image_generated (url+seed, no index) to an image event', () => {
    const e = parseListingEvent('image_generated', JSON.stringify({ url: 'http://x/2.png', seed: 7 }))
    expect(e).toEqual({ kind: 'image', url: 'http://x/2.png', seed: 7 })
  })
  it('maps task_completed (with total_cost) to completed', () => {
    expect(parseListingEvent('task_completed', JSON.stringify({ total_cost: '7.14' })))
      .toEqual({ kind: 'completed', totalCost: '7.14' })
  })
  it('maps task_failed to failed with message', () => {
    expect(parseListingEvent('task_failed', JSON.stringify({ error: '超时' })))
      .toEqual({ kind: 'failed', error: '超时' })
  })
  it('maps task_started / model_called to meta', () => {
    expect(parseListingEvent('task_started', '{}')).toEqual({ kind: 'meta' })
    expect(parseListingEvent('model_called', JSON.stringify({ model: 'gpt-image-2' }))).toEqual({ kind: 'meta' })
  })
  it('returns unknown for unrecognized type', () => {
    expect(parseListingEvent('whatever', '{}')).toEqual({ kind: 'unknown' })
  })
})

describe('estimateCost', () => {
  it('multiplies n by unit cost', () => {
    expect(estimateCost(6)).toBeCloseTo(6 * 1.19, 2)
  })
})
```

- [ ] **Step 2: 跑确认失败**

Run: `cd image-web && npx vitest run src/lib/listing.test.ts`
Expected: FAIL。

- [ ] **Step 3: 追加实现**

```ts
/** TaskEventType values emitted by backend (design_hub/domain/enums.py). */
export const LISTING_EVENT_TYPES = [
  'task_started', 'model_called', 'image_generated', 'task_completed', 'task_failed',
] as const

export type ListingEvent =
  | { kind: 'image'; url: string; seed?: number }
  | { kind: 'completed'; totalCost?: string }
  | { kind: 'failed'; error: string }
  | { kind: 'meta' } // task_started / model_called — 无需渲染
  | { kind: 'unknown' }

/**
 * Map a named SSE event to a typed ListingEvent.
 * `type` = SSE `event:` line; `rawData` = `data:` line JSON (payload only, NO type field).
 * Backend contract: routes/listing.py `_sse()` + application/listing/commands.py.
 */
export function parseListingEvent(type: string, rawData: string): ListingEvent {
  const d = JSON.parse(rawData) as Record<string, unknown>
  switch (type) {
    case 'image_generated':
      // 注意：后端不带 index；调用方按到达顺序填槽。
      return { kind: 'image', url: String(d.url ?? ''), seed: d.seed == null ? undefined : Number(d.seed) }
    case 'task_completed':
      return { kind: 'completed', totalCost: d.total_cost == null ? undefined : String(d.total_cost) }
    case 'task_failed':
      return { kind: 'failed', error: String(d.error ?? '出图失败') }
    case 'task_started':
    case 'model_called':
      return { kind: 'meta' }
    default:
      return { kind: 'unknown' }
  }
}

/** ⚠️ 占位单价，待 PM/后端确认（ISSUE-0021）。仅用于 CTA「约 ¥x」估算，非权威；完成后用 total_cost 显示真实总价。 */
export const LISTING_UNIT_COST = 1.19
export function estimateCost(n: number): number {
  return n * LISTING_UNIT_COST
}
```

- [ ] **Step 4: 跑确认通过**

Run: `cd image-web && npx vitest run src/lib/listing.test.ts`
Expected: PASS（全部）。

- [ ] **Step 5: 提交**

```bash
git add image-web/src/lib/listing.ts image-web/src/lib/listing.test.ts
git commit -m "feat(web): SSE 事件解析与成本估算（纯函数）"
```

---

## Task 4：出图与 SSE hooks

**Files:**
- Create: `src/api/listing.ts`

> 多 multipart 直接用原生 `fetch`（openapi-fetch 处理 FormData 不便，且 schema 可能未含 /listing/*）；鉴权手动塞 Bearer。SSE 用原生 `EventSource`，token 走 query（ISSUE-0011）。

- [ ] **Step 1: 实现 `src/api/listing.ts`**

```ts
import { useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'

import {
  LISTING_EVENT_TYPES, buildListingFormData, parseListingEvent,
  type ListingEvent, type ListingGenerateInput,
} from '@/lib/listing'
import { useAuthStore } from '@/stores/auth-store'

/** POST /listing/generate (multipart) -> { job_id }. fail-fast：非 2xx 抛错。 */
export function useListingGenerate() {
  return useMutation({
    mutationFn: async (input: ListingGenerateInput): Promise<{ job_id: string }> => {
      const token = useAuthStore.getState().token
      const res = await fetch('/api/listing/generate', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: buildListingFormData(input),
      })
      if (!res.ok) throw new Error(`出图请求失败（${res.status}）：${await res.text()}`)
      return res.json() as Promise<{ job_id: string }>
    },
  })
}

/**
 * 订阅 GET /listing/{jobId}/events (SSE)。jobId 为空时不连接。
 * 后端发**命名事件**（event: <type>），故须对每个 type 注册 addEventListener；
 * onmessage 不会触发。组件卸载/换 job 时断开；收到 completed/failed 主动关闭。
 */
export function useListingEvents(jobId: string | null, onEvent: (e: ListingEvent) => void) {
  const cb = useRef(onEvent)
  cb.current = onEvent
  useEffect(() => {
    if (!jobId) return
    const token = useAuthStore.getState().token ?? ''
    const url = `/api/listing/${jobId}/events?access_token=${encodeURIComponent(token)}`
    const es = new EventSource(url)
    for (const type of LISTING_EVENT_TYPES) {
      es.addEventListener(type, (ev: MessageEvent) => {
        const parsed = parseListingEvent(type, ev.data)
        cb.current(parsed)
        if (parsed.kind === 'completed' || parsed.kind === 'failed') es.close()
      })
    }
    return () => es.close()
  }, [jobId])
}
```

- [ ] **Step 2: 类型检查**

Run: `cd image-web && npm run typecheck`
Expected: 无 listing.ts 相关报错。

- [ ] **Step 3: 提交**

```bash
git add image-web/src/api/listing.ts
git commit -m "feat(web): useListingGenerate + useListingEvents（multipart + SSE）"
```

---

## Task 5：ConfigSelect（下拉封装）

**Files:**
- Create: `src/components/listing/ConfigSelect.tsx`

- [ ] **Step 1: 实现**

```tsx
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select-rich'

interface ConfigSelectProps {
  label: string
  value: string
  options: readonly string[]
  onChange: (value: string) => void
}

/** designkit 风格的带 label 行内下拉：左 label、右当前值，点开 Radix 富下拉。 */
export function ConfigSelect({ label, value, options, onChange }: ConfigSelectProps) {
  return (
    <label className="flex items-center justify-between rounded-xl border border-[#ece8e2] bg-white px-3 py-2.5 text-[13px] text-[#7a746c]">
      <span>{label}</span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="h-auto border-0 bg-transparent px-0 py-0 font-semibold text-[#2c2824] shadow-none focus-visible:ring-0">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o} value={o}>{o}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  )
}
```

- [ ] **Step 2: 类型检查**

Run: `cd image-web && npm run typecheck`
Expected: 无报错。（若 `select-rich` 的 SelectTrigger 不接受 `className` 覆盖，改用其暴露的 size 变体；先以 typecheck 为准。）

- [ ] **Step 3: 提交**

```bash
git add image-web/src/components/listing/ConfigSelect.tsx
git commit -m "feat(web): ConfigSelect 配置下拉封装"
```

---

## Task 6：ImageUploader（本地选图 ≤3）

**Files:**
- Create: `src/components/listing/ImageUploader.tsx`

- [ ] **Step 1: 实现**

```tsx
import { useRef, type ChangeEvent } from 'react'
import { UploadIcon, XIcon } from 'lucide-react'

interface ImageUploaderProps {
  files: File[]
  onChange: (files: File[]) => void
  max?: number
}

/** 本地多图选择（不传资产库）：最多 max 张，缩略图可删。 */
export function ImageUploader({ files, onChange, max = 3 }: ImageUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  function onPick(e: ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(e.target.files ?? [])
    onChange([...files, ...picked].slice(0, max))
    e.target.value = ''
  }
  function removeAt(i: number) {
    onChange(files.filter((_, idx) => idx !== i))
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={files.length >= max}
        className="flex w-full items-center justify-center gap-2 rounded-2xl border border-dashed border-[#d8d1c6] bg-[#fbfaf8] px-4 py-5 text-[13px] text-[#9b958c] transition-colors hover:border-[#cdbfff] disabled:opacity-50"
      >
        <UploadIcon className="size-4" /> 上传图片（最多 {max} 张）
      </button>
      <input ref={inputRef} type="file" accept="image/*" multiple hidden onChange={onPick} />
      {files.length > 0 && (
        <div className="mt-2.5 flex gap-2">
          {files.map((f, i) => (
            <div key={i} className="relative size-14 overflow-hidden rounded-xl border border-[#ece8e2]">
              <img src={URL.createObjectURL(f)} alt="" className="size-full object-cover" />
              <button
                type="button"
                onClick={() => removeAt(i)}
                className="absolute -right-1.5 -top-1.5 grid size-4.5 place-items-center rounded-full bg-[#2c2824] text-[10px] text-white"
              >
                <XIcon className="size-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 类型检查**

Run: `cd image-web && npm run typecheck`
Expected: 无报错。

- [ ] **Step 3: 提交**

```bash
git add image-web/src/components/listing/ImageUploader.tsx
git commit -m "feat(web): ImageUploader 本地选图（≤3，可删）"
```

---

## Task 7：ListingConfigPanel（配置栏）

**Files:**
- Create: `src/components/listing/ListingConfigPanel.tsx`

- [ ] **Step 1: 实现**

```tsx
import { Loader2Icon } from 'lucide-react'

import { GradientButton } from '@/components/visual/GradientButton'
import { ConfigSelect } from '@/components/listing/ConfigSelect'
import { ImageUploader } from '@/components/listing/ImageUploader'
import {
  MODIFIER_FIELDS, RATIOS, N_MIN, N_MAX, estimateCost, type ListingConfig,
} from '@/lib/listing'

interface ListingConfigPanelProps {
  config: ListingConfig
  files: File[]
  pending: boolean
  onConfigChange: (next: ListingConfig) => void
  onFilesChange: (files: File[]) => void
  onGenerate: () => void
}

const N_OPTIONS = Array.from({ length: N_MAX - N_MIN + 1 }, (_, i) => String(N_MIN + i))

export function ListingConfigPanel(props: ListingConfigPanelProps) {
  const { config, files, pending, onConfigChange, onFilesChange, onGenerate } = props
  const setModifier = (key: string, value: string) =>
    onConfigChange({ ...config, modifiers: { ...config.modifiers, [key]: value } })
  const canGenerate = files.length > 0 && config.prompt.trim().length > 0 && !pending

  return (
    <div className="flex w-[392px] shrink-0 flex-col border-r border-[#ece8e2] bg-white">
      <div className="flex-1 overflow-auto p-5">
        <h4 className="mb-2.5 text-[13px] font-bold">产品原图（最多 3 张）</h4>
        <ImageUploader files={files} onChange={onFilesChange} max={3} />

        <h4 className="mb-2.5 mt-5 text-[13px] font-bold">生成设置</h4>
        <div className="grid grid-cols-2 gap-2.5">
          {MODIFIER_FIELDS.map((f) => (
            <ConfigSelect
              key={f.key}
              label={f.label}
              value={config.modifiers[f.key] ?? f.options[0]}
              options={f.options}
              onChange={(v) => setModifier(f.key, v)}
            />
          ))}
          <ConfigSelect
            label="比例"
            value={config.ratio}
            options={RATIOS}
            onChange={(v) => onConfigChange({ ...config, ratio: v as ListingConfig['ratio'] })}
          />
          <ConfigSelect
            label="张数"
            value={String(config.n)}
            options={N_OPTIONS}
            onChange={(v) => onConfigChange({ ...config, n: Number(v) })}
          />
        </div>

        <h4 className="mb-2.5 mt-5 text-[13px] font-bold">商品卖点 &amp; 要求</h4>
        <textarea
          value={config.prompt}
          onChange={(e) => onConfigChange({ ...config, prompt: e.target.value })}
          placeholder="描述你想要的画面与卖点…"
          className="min-h-[104px] w-full resize-none rounded-xl border border-[#ece8e2] p-3 text-[13.5px] leading-relaxed text-[#2c2824] outline-none focus-visible:border-[#cdbfff]"
        />
      </div>

      <div className="border-t border-[#ece8e2] bg-white p-4">
        <GradientButton onClick={onGenerate} disabled={!canGenerate} className="w-full">
          {pending ? <Loader2Icon className="size-4 animate-spin" /> : null}
          开始出图
          <span className="ml-2 text-[13px] font-normal opacity-90">
            约 ¥{estimateCost(config.n).toFixed(2)} · {config.n} 张
          </span>
        </GradientButton>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 类型检查 + 构建**

Run: `cd image-web && npm run typecheck && npm run build`
Expected: 通过（若 GradientButton 不接受多 children，确认其签名为 ButtonHTMLAttributes，已支持）。

- [ ] **Step 3: 提交**

```bash
git add image-web/src/components/listing/ListingConfigPanel.tsx
git commit -m "feat(web): ListingConfigPanel 配置栏（上传+5下拉+卖点+开始出图）"
```

---

## Task 8：ResultGallery（结果画廊）

**Files:**
- Create: `src/components/listing/ResultGallery.tsx`

> 槽位模型：发起出图时按 n 铺 n 个 `null` 占位；`image` 事件按 index 填入 url。

- [ ] **Step 1: 实现**

```tsx
import { DownloadIcon } from 'lucide-react'
import { motion } from 'motion/react'

export interface ResultSlot {
  url: string | null // null = 出图中
}

interface ResultGalleryProps {
  title: string
  slots: ResultSlot[]
  done: number
  total: number
  generating: boolean
}

function download(url: string, name: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
}

export function ResultGallery({ title, slots, done, total, generating }: ResultGalleryProps) {
  const ready = slots.filter((s) => s.url)
  return (
    <div className="flex-1 overflow-auto p-6 lg:px-8">
      <div className="mb-3.5 flex items-center justify-between">
        <h2 className="text-[22px] font-semibold">{title}</h2>
        {ready.length > 0 && (
          <button
            onClick={() => ready.forEach((s, i) => download(s.url!, `listing-${i + 1}.png`))}
            className="rounded-[10px] border border-[#ece8e2] bg-white px-3.5 py-2 text-[13px] text-[#4a443d]"
          >
            <DownloadIcon className="mr-1 inline size-4" /> 下载全部
          </button>
        )}
      </div>

      {generating && total > 0 && (
        <>
          <div className="mb-1.5 h-1.5 overflow-hidden rounded-full bg-[#eee7df]">
            <div
              className="h-full bg-gradient-to-r from-[#7c6cff] via-[#a855f7] to-[#ff9a62] transition-[width] duration-300"
              style={{ width: `${total ? (done / total) * 100 : 0}%` }}
            />
          </div>
          <p className="mb-4 text-[12.5px] text-[#8a857e]">已出 {done} / {total} 张…</p>
        </>
      )}

      {slots.length === 0 ? (
        <div className="grid min-h-[40vh] place-items-center text-[14px] text-[#bdb6ab]">
          上传产品图、写下卖点，点「开始出图」
        </div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(208px,1fr))] gap-4">
          {slots.map((s, i) =>
            s.url ? (
              <motion.div
                key={i}
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: 1, scale: 1 }}
                className="group relative aspect-square overflow-hidden rounded-2xl border border-[#ece8e2] bg-white"
              >
                <img src={s.url} alt="" className="size-full object-cover" />
                <button
                  onClick={() => download(s.url!, `listing-${i + 1}.png`)}
                  className="absolute bottom-2.5 right-2.5 rounded-[10px] bg-[#2c2824]/90 px-3 py-1.5 text-[12.5px] text-white opacity-0 transition-opacity group-hover:opacity-100"
                >
                  <DownloadIcon className="mr-1 inline size-3.5" /> 下载
                </button>
              </motion.div>
            ) : (
              <div
                key={i}
                className="grid aspect-square place-items-center rounded-2xl border border-dashed border-[#e4ddd2] bg-[#faf8f5]"
              >
                <div className="size-7 animate-spin rounded-full border-[3px] border-[#e7e0d6] border-t-[#7c6cff]" />
              </div>
            ),
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 类型检查 + 构建**

Run: `cd image-web && npm run typecheck && npm run build`
Expected: 通过（确认 `motion/react` 导出 `motion`；项目已装 `motion`）。

- [ ] **Step 3: 提交**

```bash
git add image-web/src/components/listing/ResultGallery.tsx
git commit -m "feat(web): ResultGallery 结果画廊（逐张到达+进度+下载）"
```

---

## Task 9：WorkbenchRail + WorkbenchLayout

**Files:**
- Create: `src/components/listing/WorkbenchRail.tsx`
- Create: `src/components/layout/WorkbenchLayout.tsx`

- [ ] **Step 1: WorkbenchRail**

```tsx
import { useState } from 'react'
import { ShoppingBagIcon, FlameIcon } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

const ITEMS = [
  { key: 'product-set', label: '商品套图', icon: ShoppingBagIcon, enabled: true },
  { key: 'replica', label: '爆款图复刻', icon: FlameIcon, enabled: false },
]

export function WorkbenchRail() {
  const [active, setActive] = useState('product-set')
  return (
    <div className="flex w-20 shrink-0 flex-col items-center gap-2 border-r border-[#ece8e2] bg-white py-4">
      {ITEMS.map((it) => (
        <button
          key={it.key}
          onClick={() => (it.enabled ? setActive(it.key) : toast('🔥 爆款图复刻 · 敬请期待'))}
          className={cn(
            'w-16 rounded-[13px] py-2.5 text-center text-[11.5px] text-[#7a746c]',
            active === it.key && it.enabled && 'bg-[#f4f0ff] font-semibold text-[#4733b8]',
          )}
        >
          <span
            className={cn(
              'mx-auto mb-1.5 grid size-[30px] place-items-center rounded-[10px] bg-[#efeae3]',
              active === it.key && it.enabled && 'bg-gradient-to-br from-[#7c6cff] to-[#ff9a62] text-white',
            )}
          >
            <it.icon className="size-4" />
          </span>
          {it.label}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: WorkbenchLayout**

> 全屏布局：顶栏（logo + 新建任务 + 头像菜单含管理页入口）+ rail + Outlet。`onNewTask` 经路由 state 或简单 `window` 事件触发 WorkbenchPage 清空——这里用 React context 最干净；MVP 用一个 `key` 重挂方案：顶栏「新建任务」调用 `navigate(0)` 过重，改为下方 WorkbenchPage 自管，本布局只提供入口按钮占位（Task 10 用 context 接）。

```tsx
import { Outlet, useNavigate } from 'react-router-dom'
import { PlusIcon, LogOutIcon } from 'lucide-react'

import { queryClient } from '@/api/query-client'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { WorkbenchRail } from '@/components/listing/WorkbenchRail'
import { navItemsFor } from '@/components/layout/nav'
import { useAuthStore, useCurrentUser } from '@/stores/auth-store'
import { newTaskBus } from '@/components/listing/new-task-bus'

export function WorkbenchLayout() {
  const user = useCurrentUser()
  const navigate = useNavigate()
  const clear = useAuthStore((s) => s.clear)
  const manageItems = navItemsFor(user.role).filter((i) => i.to !== '/')

  function logout() {
    clear()
    queryClient.clear()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex h-svh flex-col bg-[#f6f4f1] text-[#1c1b1a]">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-[#ece8e2] bg-white px-5">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 font-bold">
            <span className="size-6 rounded-[7px] bg-gradient-to-br from-[#7c6cff] to-[#ff9a62]" />出图
          </div>
          <button
            onClick={() => newTaskBus.emit()}
            className="flex items-center gap-1.5 rounded-[10px] border border-[#ece8e2] bg-white px-3 py-1.5 text-[13.5px] text-[#4a443d]"
          >
            <PlusIcon className="size-4" /> 新建任务
          </button>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger className="rounded-full outline-none focus-visible:ring-2 focus-visible:ring-[#cdbfff]">
            <Avatar className="size-8">
              <AvatarFallback className="bg-[#f4f0ff] text-xs font-semibold text-[#4733b8]">
                {user.name.slice(-1)}
              </AvatarFallback>
            </Avatar>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            <DropdownMenuLabel>{user.name} · {user.role}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {manageItems.map((i) => (
              <DropdownMenuItem key={i.to} onClick={() => navigate(i.to)}>
                <i.icon className="size-4" /> {i.label}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onClick={logout}>
              <LogOutIcon className="size-4" /> 退出登录
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </header>
      <div className="flex min-h-0 flex-1">
        <WorkbenchRail />
        <Outlet />
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 新建任务事件总线（极简）**

`src/components/listing/new-task-bus.ts`:
```ts
// Tiny pub/sub so the layout's "新建任务" button can reset WorkbenchPage state.
type Listener = () => void
const listeners = new Set<Listener>()
export const newTaskBus = {
  emit: () => listeners.forEach((l) => l()),
  subscribe: (l: Listener) => {
    listeners.add(l)
    return () => listeners.delete(l)
  },
}
```

- [ ] **Step 4: 类型检查 + 构建**

Run: `cd image-web && npm run typecheck && npm run build`
Expected: 通过。

- [ ] **Step 5: 提交**

```bash
git add image-web/src/components/listing/WorkbenchRail.tsx image-web/src/components/layout/WorkbenchLayout.tsx image-web/src/components/listing/new-task-bus.ts
git commit -m "feat(web): WorkbenchLayout 全屏布局 + 左 rail + 管理页入口收头像菜单"
```

---

## Task 10：重写 WorkbenchPage（编排）

**Files:**
- Modify (全量重写): `src/pages/WorkbenchPage.tsx`

- [ ] **Step 1: 重写**

```tsx
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { useListingGenerate, useListingEvents } from '@/api/listing'
import { ListingConfigPanel } from '@/components/listing/ListingConfigPanel'
import { ResultGallery, type ResultSlot } from '@/components/listing/ResultGallery'
import { newTaskBus } from '@/components/listing/new-task-bus'
import { DEFAULT_LISTING_CONFIG, type ListingConfig } from '@/lib/listing'

export function WorkbenchPage() {
  const [config, setConfig] = useState<ListingConfig>(DEFAULT_LISTING_CONFIG)
  const [files, setFiles] = useState<File[]>([])
  const [jobId, setJobId] = useState<string | null>(null)
  const [slots, setSlots] = useState<ResultSlot[]>([])
  const [done, setDone] = useState(0)
  const generate = useListingGenerate()

  // 「新建任务」：清空一切回到初始
  useEffect(() => newTaskBus.subscribe(() => {
    setConfig(DEFAULT_LISTING_CONFIG); setFiles([]); setJobId(null); setSlots([]); setDone(0)
  }), [])

  useListingEvents(jobId, (e) => {
    if (e.kind === 'image') {
      // 后端 image_generated 不带 index：按到达顺序填第一个空槽
      setSlots((prev) => {
        const i = prev.findIndex((s) => s.url === null)
        if (i < 0) return prev
        const next = [...prev]
        next[i] = { url: e.url }
        return next
      })
      setDone((d) => d + 1)
    } else if (e.kind === 'failed') {
      toast.error(`出图失败：${e.error}`)
      setJobId(null)
    } else if (e.kind === 'completed') {
      setJobId(null)
    }
  })

  async function onGenerate() {
    setSlots(Array.from({ length: config.n }, () => ({ url: null })))
    setDone(0)
    try {
      const { job_id } = await generate.mutateAsync({
        images: files, prompt: config.prompt, ratio: config.ratio, n: config.n, modifiers: config.modifiers,
      })
      setJobId(job_id)
    } catch (err) {
      setSlots([])
      toast.error(err instanceof Error ? err.message : '出图请求失败')
    }
  }

  const generating = generate.isPending || jobId !== null

  return (
    <>
      <ListingConfigPanel
        config={config}
        files={files}
        pending={generating}
        onConfigChange={setConfig}
        onFilesChange={setFiles}
        onGenerate={onGenerate}
      />
      <ResultGallery title="商品套图" slots={slots} done={done} total={config.n} generating={generating} />
    </>
  )
}
```

- [ ] **Step 2: 类型检查 + 构建**

Run: `cd image-web && npm run typecheck && npm run build`
Expected: 通过。**若报错来自旧 import（如旧 WorkbenchPage 依赖的 useProjects/CreateProjectDialog 仍被引用）→ 它们的清理在 Task 12，先确保本文件无残留旧 import。**

- [ ] **Step 3: 提交**

```bash
git add image-web/src/pages/WorkbenchPage.tsx
git commit -m "feat(web): 重写 WorkbenchPage 为 listing 两栏编排"
```

---

## Task 11：路由重构

**Files:**
- Modify: `src/App.tsx`

- [ ] **Step 1: 改路由——`/` 走 WorkbenchLayout，管理页留 AppLayout**

在 `src/App.tsx`：
1. 顶部加 import：`import { WorkbenchLayout } from '@/components/layout/WorkbenchLayout'`
2. 删除 import：`import { ProjectDetailPage } from '@/pages/ProjectDetailPage'`
3. 把受保护区路由改成两个布局并存（删掉 `projects/:id` 路由）：

```tsx
      <Route element={<ProtectedRoute />}>
        <Route element={<WorkbenchLayout />}>
          <Route index element={<WorkbenchPage />} />
        </Route>
        <Route element={<AppLayout />}>
          <Route path="customers" element={<CustomersPage />} />
          <Route path="dashboard" element={<RoleRoute allow={[ROLE_MANAGER]}><DashboardPage /></RoleRoute>} />
          <Route path="admin/models" element={<RoleRoute allow={[ROLE_MANAGER]}><AdminModelsPage /></RoleRoute>} />
          <Route path="admin/users" element={<RoleRoute allow={[ROLE_MANAGER]}><AdminUsersPage /></RoleRoute>} />
        </Route>
      </Route>
```
（`Suspense`/`DashboardPage` lazy 包裹保持原样，只是从 AppLayout 子路由里保留。）

- [ ] **Step 2: 类型检查 + 构建**

Run: `cd image-web && npm run typecheck && npm run build`
Expected: 报错仅来自「ProjectDetailPage 已删 import 但文件还在被别处引用」→ 进入 Task 12 清理。若除此之外通过即可。

- [ ] **Step 3: 提交**

```bash
git add image-web/src/App.tsx
git commit -m "feat(web): 路由重构——/ 走 WorkbenchLayout，管理页留 AppLayout"
```

---

## Task 12：清理孤儿（删旧链路）

**Files:**
- Delete: `src/pages/ProjectDetailPage.tsx`、`src/components/generate/GenerateStudio.tsx`、`src/components/revision/RevisionTab.tsx`、`src/components/export/ExportTab.tsx`
- Modify: `src/api/generation.ts`（删 `useProjectGenerate`；若整文件无人引用则整删）
- Delete（**grep 确认孤儿后**）：`src/components/project/*` 中仅服务旧列表/详情者

- [ ] **Step 1: 逐个确认引用面**

Run（在 image-web 下）：
```bash
cd image-web
for f in ProjectDetailPage GenerateStudio RevisionTab ExportTab ProjectPipeline CreateProjectDialog ProjectStatusControl StatusBadge useProjectGenerate; do
  echo "== $f =="; grep -rl "$f" src --include=*.tsx --include=*.ts | grep -v -E "$f\.(tsx|ts)$"
done
```
Expected: 列出仍引用各符号的文件。**只删"除自身外无引用"的；仍被 CustomersPage 等引用的（如 StatusBadge/CreateCustomerDialog）保留。**

- [ ] **Step 2: 删确认无引用的文件**

对 Step 1 中确认为孤儿的执行 `git rm`，例如（按实际结果增减）：
```bash
cd image-web
git rm src/pages/ProjectDetailPage.tsx \
       src/components/generate/GenerateStudio.tsx \
       src/components/revision/RevisionTab.tsx \
       src/components/export/ExportTab.tsx
```

- [ ] **Step 3: 清 generation.ts 里的同步出图 hook**

打开 `src/api/generation.ts`，删除 `useProjectGenerate`（及其仅服务它的 import）。若删后整文件再无导出被引用（Step 1 已知），`git rm src/api/generation.ts`。

- [ ] **Step 4: 类型检查 + 构建 + lint**

Run: `cd image-web && npm run typecheck && npm run build && npm run lint`
Expected: 全过。**若有"未使用 import/变量"报错，顺手清掉再过。**

- [ ] **Step 5: 提交**

```bash
git add -u image-web/src
git commit -m "refactor(web): 删除旧项目/出图/改稿/导出链路（孤儿清理）"
```
> 注：`git add -u image-web/src` 只暂存 image-web/src 下的「已跟踪文件改动（含删除）」，不波及他人未跟踪文件，符合共享工作树约束。

---

## Task 13：联调与视觉验收（Playwright）

**Files:** 无（验证任务）

- [ ] **Step 1: 起后端 + 前端**

按 `image-web/README.md` 起 dev（`npm run dev`，默认 3000，proxy → 后端 8000）。确认后端 `/listing/*` 已上线（见 ISSUE-0020 进度）。若后端未就绪，先只验证页面渲染与本地校验（出图请求会 4xx/404，属预期）。

- [ ] **Step 2: 登录并打开工作台**

用 Playwright 导航 `http://localhost:3000`，登录后落到 `/`。截图。
Expected：两栏页——左 rail（商品套图/爆款图复刻）+ 配置栏（上传/5 下拉/卖点/开始出图）+ 右画布空态提示。无项目列表。

- [ ] **Step 3: 比对设计 mockup**

对照 `docs/出图工作台-v2-商品套图重做-设计.md` §三 与 brainstorm v4 mockup：rail 两项、5 个下拉值正确、上传无"从资产库选"、CTA 文案"开始出图 · 约 ¥x · n 张"。
点「爆款图复刻」→ 出现「敬请期待」toast。

- [ ] **Step 4: 出图链路（后端就绪时）**

上传 1–3 张图 + 写 prompt + 点开始出图：右画布铺 n 个转圈占位 → 逐张替换为图 + 进度条推进 → 可单张/全部下载。失败有 toast，不静默。
Expected：multipart 请求 `POST /api/listing/generate` 返回 job_id；`EventSource` 连 `/api/listing/{job_id}/events?access_token=` 收到 image/completed 事件。
**若事件未渲染**：到浏览器 Network 看 SSE 原始 `data:`，比对 `parseListingEvent` 的 type/字段名，按实际改 `src/lib/listing.ts` 的映射 + 更新其单测（呼应顶部不确定点 1）。

- [ ] **Step 5: 全量校验 + 收尾提交**

Run: `cd image-web && npm test && npm run typecheck && npm run build && npm run lint`
Expected：全过。
若 Step 4 改了 `parseListingEvent`：
```bash
git add image-web/src/lib/listing.ts image-web/src/lib/listing.test.ts
git commit -m "fix(web): 对齐后端 SSE 事件实际字段"
```

- [ ] **Step 6: 回写 ISSUE-0020**

在 `image-issues/ISSUE-0020-...md` 处理记录追加一行：前端实现完成、自验通过项、状态→待验证、owner→QA（按多 agent 协议交球）。提交：
```bash
git add image-issues/ISSUE-0020-前端按新listing契约返工multipart直传纯prompt.md
git commit -m "docs(issue): ISSUE-0020 前端实现完成，转待验证(owner=QA)"
```

---

## 自检（写计划者已核对）

- **Spec 覆盖**：v2 设计稿 §二(路由)→T11；§三(组件)→T5–T10；§四(契约/枚举)→T1–T4；§五(SSE)→T3/T4/T10/T13;§六(删除)→T12；§八(视觉)→各组件用 designkit 暖色 token。✅
- **占位扫描**：无 TODO/TBD；唯二不确定点（SSE 形状、单价）已显式标注 + 隔离在纯函数/常量 + 给了对齐步骤。✅
- **类型一致**：`ListingConfig`/`ListingGenerateInput`/`ListingEvent`/`ResultSlot` 跨任务命名一致；`buildListingFormData` 入参与 `useListingGenerate` 一致；`MODIFIER_FIELDS.key` 与 `modifiers` 键一致。✅
