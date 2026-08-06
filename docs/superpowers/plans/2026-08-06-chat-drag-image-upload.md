# Chat Image Drag Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to drop up to three PNG, JPEG, or WebP images anywhere on the expanded Chat composer, upload them immediately, preview them as attachments, and submit their existing `upload_ids` with the Chat message.

**Architecture:** Add a focused `ChatImageDropZone` decorator around the existing composer surface. The decorator owns browser drag depth and the visual receiving state, while a pure selection function validates formats and remaining slots for both drag and click inputs; `ChatPage` remains the owner of network uploads and attachment state.

**Tech Stack:** React 19, TypeScript 6, Tailwind CSS 4, Vitest 4, jsdom, Testing Library, TanStack Query, existing `POST /uploads` API.

## Global Constraints

- The whole expanded Chat composer is the drop target; a collapsed, busy, or uploading composer ignores new files, while a full composer rejects the drop with the attachment-limit message.
- Accept only `image/png`, `image/jpeg`, and `image/webp`.
- Keep at most three attachments and upload only the first files that fit remaining slots.
- Keep the existing click-to-select flow and `POST /uploads` contract; do not add or change backend APIs.
- Dropping new images cancels a selected generated-image edit source, matching the existing click upload flow.
- Disable button and keyboard sending while an upload is pending.
- Use the existing Workbench design tokens and do not introduce a new visual system.
- Network upload failures are surfaced once and require manual retry; do not add automatic retries.

---

### Task 1: File selection contract and drop-zone decorator

**Files:**
- Create: `image-web/src/components/chat/ChatImageDropZone.tsx`
- Create: `image-web/src/components/chat/ChatImageDropZone.test.ts`
- Modify: `image-web/package.json`
- Modify: `image-web/package-lock.json`

**Interfaces:**
- Produces: `selectChatImageFiles(files: readonly File[], remainingSlots: number): ChatImageFileSelection`
- Produces: `ChatImageDropZone({ disabled, remainingSlots, onSelection, children })`
- Produces: `ChatImageFileSelection` with `accepted`, `unsupportedCount`, `overflowCount`, and `full`.
- Consumes: browser `DragEvent.dataTransfer.files` and existing Workbench color tokens.

- [ ] **Step 1: Add the DOM test runtime through the package manager**

Run from `image-web`:

```bash
npm install --save-dev jsdom @testing-library/react
```

Expected: `jsdom` and `@testing-library/react` are added to `devDependencies`, and the npm lockfile is updated by npm rather than edited manually.

- [ ] **Step 2: Write failing selection and interaction tests**

Create `ChatImageDropZone.test.ts` with a jsdom environment. This project collects only `*.test.ts`, so use `createElement` instead of JSX. Cover the pure format/limit contract and the real React drag events:

```ts
// @vitest-environment jsdom
import { createElement } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ChatImageDropZone,
  selectChatImageFiles,
} from '@/components/chat/ChatImageDropZone'

const png = (name: string) => new File(['png'], name, { type: 'image/png' })
afterEach(cleanup)

it('keeps supported images within the remaining attachment slots', () => {
  const result = selectChatImageFiles(
    [png('one.png'), new File(['txt'], 'note.txt', { type: 'text/plain' }), png('two.png')],
    1,
  )

  expect(result.accepted.map((file) => file.name)).toEqual(['one.png'])
  expect(result.unsupportedCount).toBe(1)
  expect(result.overflowCount).toBe(1)
  expect(result.full).toBe(false)
})

it('shows the receiving state and submits dropped files', () => {
  const onSelection = vi.fn()
  const file = png('product.png')
  const { container } = render(createElement(
    ChatImageDropZone,
    { disabled: false, remainingSlots: 2, onSelection },
    createElement('section', null, 'composer'),
  ))
  const zone = container.querySelector('[data-chat-image-drop-zone]')!
  const dataTransfer = { types: ['Files'], files: [file] }

  fireEvent.dragEnter(zone, { dataTransfer })
  expect(screen.getByText('松开即可上传图片')).toBeTruthy()

  fireEvent.drop(zone, { dataTransfer })
  expect(onSelection).toHaveBeenCalledWith({
    accepted: [file],
    unsupportedCount: 0,
    overflowCount: 0,
    full: false,
  })
  expect(screen.queryByText('松开即可上传图片')).toBeNull()
})
```

Add these exact cases in the same file:

```ts
it('keeps the overlay while leaving only a nested child', () => {
  const { container } = renderDropZone({ remainingSlots: 2 })
  const zone = container.querySelector('[data-chat-image-drop-zone]')!
  fireEvent.dragEnter(zone, { dataTransfer: { types: ['Files'], files: [png('one.png')] } })
  fireEvent.dragEnter(zone.firstElementChild!, { dataTransfer: { types: ['Files'], files: [png('one.png')] } })
  fireEvent.dragLeave(zone.firstElementChild!, { dataTransfer: { types: ['Files'], files: [png('one.png')] } })
  expect(screen.getByText('松开即可上传图片')).toBeTruthy()
  fireEvent.dragLeave(zone, { dataTransfer: { types: ['Files'], files: [png('one.png')] } })
  expect(screen.queryByText('松开即可上传图片')).toBeNull()
})

it.each([
  { disabled: true, remainingSlots: 2 },
  { disabled: false, remainingSlots: 0 },
])('does not highlight when unavailable: %o', ({ disabled, remainingSlots }) => {
  const { container } = renderDropZone({ disabled, remainingSlots })
  fireEvent.dragEnter(container.firstElementChild!, {
    dataTransfer: { types: ['Files'], files: [png('one.png')] },
  })
  expect(screen.queryByText('松开即可上传图片')).toBeNull()
})

it('reports a full attachment list without showing the overlay', () => {
  const onSelection = vi.fn()
  const { container } = renderDropZone({ remainingSlots: 0, onSelection })
  fireEvent.drop(container.firstElementChild!, {
    dataTransfer: { types: ['Files'], files: [png('one.png')] },
  })
  expect(onSelection).toHaveBeenCalledWith({
    accepted: [],
    unsupportedCount: 0,
    overflowCount: 1,
    full: true,
  })
})
```

`renderDropZone` is a local test helper that renders the component with `disabled=false`, `remainingSlots=2`, a `vi.fn()` selection callback, and a child `<section>composer</section>`, overridden by its input. Add a non-file drag case with `types: ['text/plain']` and assert both no overlay and no selection callback.

- [ ] **Step 3: Run the focused test and verify RED**

Run:

```bash
npm test -- src/components/chat/ChatImageDropZone.test.ts
```

Expected: FAIL because `ChatImageDropZone.tsx` does not exist, and the output lists the new test instead of only the previous 27 files.

- [ ] **Step 4: Implement the minimal decorator and selection function**

Create the component with this public contract:

```tsx
export interface ChatImageFileSelection {
  accepted: File[]
  unsupportedCount: number
  overflowCount: number
  full: boolean
}

export function selectChatImageFiles(
  files: readonly File[],
  remainingSlots: number,
): ChatImageFileSelection

export function ChatImageDropZone({
  disabled,
  remainingSlots,
  onSelection,
  children,
}: {
  disabled: boolean
  remainingSlots: number
  onSelection: (selection: ChatImageFileSelection) => void
  children: React.ReactNode
})
```

Use a `dragDepthRef` to keep the receiving state stable across child elements. Prevent the browser's file-open default for file drags and drops. On every non-disabled file drop, call `selectChatImageFiles(Array.from(event.dataTransfer.files), remainingSlots)` and pass the exact result to `onSelection`, including `full: true` when no slot remains. Highlight only when `!disabled && remainingSlots > 0`; always clear drag depth on drop, disabled transitions, and unmount. Render the overlay inside the existing rounded boundary with:

```tsx
<strong>松开即可上传图片</strong>
<span>支持 PNG、JPG、WebP · 还可添加 {remainingSlots} 张</span>
```

- [ ] **Step 5: Run the focused test and verify GREEN**

Run:

```bash
npm test -- src/components/chat/ChatImageDropZone.test.ts
```

Expected: all drop-zone tests PASS with no React act warnings.

- [ ] **Step 6: Commit the decorator unit**

```bash
git add image-web/package.json image-web/package-lock.json \
  image-web/src/components/chat/ChatImageDropZone.tsx \
  image-web/src/components/chat/ChatImageDropZone.test.ts
git commit -m "feat: add chat image drop zone"
```

Commit body: explain the nested drag-depth handling, shared format/limit contract, and why jsdom is required for real DOM event verification.

---

### Task 2: Composer integration, upload feedback, and send lock

**Files:**
- Modify: `image-web/src/components/chat/ChatComposer.tsx`
- Modify: `image-web/src/components/chat/ChatComposer.test.ts`
- Create: `image-web/src/components/chat/ChatComposer.interactions.test.ts`
- Modify: `image-web/src/pages/ChatPage.tsx`

**Interfaces:**
- Consumes: `ChatImageDropZone` and `selectChatImageFiles` from Task 1.
- Changes: `onPickFiles(files: readonly File[])` replaces the `FileList | null` callback.
- Adds: `onFileSelection(selection: ChatImageFileSelection)` owned by `ChatPage` for user-facing Toast messages.
- Preserves: `useUploadImage()`, `UploadedImage[]`, and `sendChatMessage({ uploadIds })`.

- [ ] **Step 1: Write failing composer integration tests**

Extend `ChatComposer.test.ts` to assert the upload-pending state:

```ts
it('locks sending and shows progress while an attachment is uploading', () => {
  const markup = renderComposerWith({
    draft: '生成商品海报',
    attached: [{ id: 'u/one.png', url: '/uploads/u/one.png' }],
    uploadPending: true,
  })

  expect(markup).toContain('图片上传中')
  expect(sendButton(markup)).toContain('disabled=""')
})
```

Create `ChatComposer.interactions.test.ts` with `// @vitest-environment jsdom`, `createElement`, Testing Library, and a local `composerProps(overrides)` factory containing the same ready Chat and image selections used by the existing static test. Verify the keyboard lock and decorator integration with real events:

```ts
import { createElement } from 'react'

it('does not send with Enter while an image upload is pending', () => {
  const onSend = vi.fn()
  render(createElement(
    ChatComposer,
    composerProps({ uploadPending: true, onSend }),
  ))

  fireEvent.keyDown(screen.getByLabelText('图片创作提示词'), {
    key: 'Enter',
    shiftKey: false,
  })

  expect(onSend).not.toHaveBeenCalled()
})

it('forwards a dropped image through the unified file selection action', () => {
  const onPickFiles = vi.fn()
  const onFileSelection = vi.fn()
  const { container } = render(createElement(
    ChatComposer,
    composerProps({ onPickFiles, onFileSelection }),
  ))
  const file = new File(['png'], 'product.png', { type: 'image/png' })
  fireEvent.drop(container.querySelector('[data-chat-image-drop-zone]')!, {
    dataTransfer: { types: ['Files'], files: [file] },
  })

  expect(onPickFiles).toHaveBeenCalledWith([file])
  expect(onFileSelection).toHaveBeenCalledWith({
    accepted: [file],
    unsupportedCount: 0,
    overflowCount: 0,
    full: false,
  })
})
```

- [ ] **Step 2: Run the composer test and verify RED**

Run:

```bash
npm test -- src/components/chat/ChatComposer.test.ts src/components/chat/ChatComposer.interactions.test.ts
```

Expected: FAIL because `uploadPending` does not currently lock `canSend`, the keyboard handler bypasses that lock, and no upload placeholder is rendered beside existing attachments.

- [ ] **Step 3: Integrate the decorator and unified file-array callback**

In `ChatComposer.tsx`:

```tsx
const remainingSlots = Math.max(0, 3 - attached.length)
const canSend = !busy && !uploadPending && modelsReady && draft.trim().length > 0

function submitFiles(files: readonly File[]) {
  const selection = selectChatImageFiles(files, remainingSlots)
  onFileSelection(selection)
  if (selection.accepted.length > 0) onPickFiles(selection.accepted)
}
```

Wrap the visible composer section with `ChatImageDropZone`, disabled only when collapsed, busy, or uploading. A full composer still routes the drop to the `full` rejection result without showing a receiving overlay. Its `onSelection` calls `onFileSelection` and forwards non-empty `accepted` files to `onPickFiles`. Convert hidden input files with `Array.from(event.target.files ?? [])`, run them through the same `selectChatImageFiles`, and forward the same selection contract. Render a compact loader tile labeled `图片上传中` whenever `uploadPending` is true, including when attachments already exist.

Update `handleKeyDown` so it calls `onSend()` only when both the keyboard shortcut matches and `canSend` is true.

- [ ] **Step 4: Keep page ownership of uploads and specific errors**

Change `ChatPage.onPickFiles` to accept `readonly File[]` and upload every already-accepted file in order. Add a rejection handler with exact messages:

```ts
if (selection.unsupportedCount > 0) {
  toast.error('仅支持 PNG、JPG、WebP 图片')
}
if (selection.full) {
  toast.info('最多添加 3 张图片，请先删除已有图片')
} else if (selection.overflowCount > 0) {
  toast.info(`最多添加 3 张图片，${selection.overflowCount} 张未添加`)
}
```

Keep `setSelectedEditSource(null)` immediately before accepted uploads and preserve successful attachments if a later upload fails.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
npm test -- src/components/chat/ChatImageDropZone.test.ts \
  src/components/chat/ChatComposer.test.ts \
  src/components/chat/ChatComposer.interactions.test.ts
```

Expected: all focused tests PASS; no upload can trigger a send before completion.

- [ ] **Step 6: Commit the Chat integration unit**

```bash
git add image-web/src/components/chat/ChatComposer.tsx \
  image-web/src/components/chat/ChatComposer.test.ts \
  image-web/src/components/chat/ChatComposer.interactions.test.ts \
  image-web/src/pages/ChatPage.tsx
git commit -m "feat: upload dropped images from chat"
```

Commit body: explain immediate reuse of `POST /uploads`, attachment-limit feedback, and the upload/send race that is now closed.

---

### Task 3: Quality gate and visual verification

**Files:**
- Modify only files from Tasks 1–2 if verification exposes a scoped defect.

**Interfaces:**
- Consumes the completed feature and existing frontend scripts.
- Produces a clean, production-buildable Chat drag-upload flow.

- [ ] **Step 1: Run the complete frontend test suite**

Run:

```bash
npm test
```

Expected: all existing and new Vitest tests PASS.

- [ ] **Step 2: Run static quality checks**

Run:

```bash
npm run typecheck
npm run lint
```

Expected: both commands exit 0 with no new errors.

- [ ] **Step 3: Build the production bundle**

Run:

```bash
npm run build
```

Expected: TypeScript and Vite build exit 0. Existing chunk-size warnings are acceptable if unchanged.

- [ ] **Step 4: Inspect the interaction in a browser**

Start the local frontend and verify at desktop width:

1. Drag one PNG over child controls; the overlay remains stable.
2. Leave the composer; the overlay disappears.
3. Drop one image; the loader appears, then the thumbnail replaces it.
4. Drop more images with one existing attachment; total thumbnails stop at three and excess files produce a Toast.
5. Drag a non-image; it is rejected without upload.
6. Attempt button and Enter sending during upload; neither sends.
7. Click-select, delete, reverse prompt, and normal message send still work.

- [ ] **Step 5: Commit only if verification required a correction**

```bash
git add image-web/src/components/chat/ChatImageDropZone.tsx \
  image-web/src/components/chat/ChatImageDropZone.test.ts \
  image-web/src/components/chat/ChatComposer.tsx \
  image-web/src/components/chat/ChatComposer.test.ts \
  image-web/src/components/chat/ChatComposer.interactions.test.ts \
  image-web/src/pages/ChatPage.tsx
git commit -m "fix: close chat drag upload review gaps"
```

Commit body: name the exact failing verification and why the correction resolves it without broadening scope.
