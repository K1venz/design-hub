# Chat 中央布局与单一滚动条 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Chat 中央列放宽到 960px，并让消息区成为桌面端唯一显示纵向滚动条的业务区域。

**Architecture:** 把 `ChatPage` 中负责高度、宽度和滚动的 JSX 提取为专用 `ChatViewportLayout`，由它明确拥有主工作区、中央列、消息滚动区和输入台的层级。`SessionSidebar` 保留独立滚动能力，但通过一个全局 Tailwind utility 隐藏滚动条；业务状态、SSE 和输入台内部交互不变。

**Tech Stack:** React 19、TypeScript 6、Tailwind CSS 4、Vitest、React DOM server rendering、Vite 8

## Global Constraints

- 中央 Chat 列桌面最大宽度必须是 `960px`。
- `AppShell` 和 Chat 主工作区不得产生页面级纵向滚动。
- 消息区是唯一显示纵向滚动条的业务区域，并继续由现有 `scrollRef` 控制自动滚动。
- 左侧历史列表必须继续支持鼠标、触控板、触摸和键盘滚动，但不得显示滚动条。
- 输入台位于消息滚动区外并固定在中央列底部，不使用覆盖层或绝对定位。
- `md` 以下保持左侧历史隐藏，中央列使用可用空间全宽。
- 不修改 Chat 状态、SSE、任务结果、顶部导航、输入台内部交互或任何后端代码。
- 不新增依赖。

---

## File Structure

- Create: `image-web/src/components/chat/ChatViewportLayout.tsx` — 单一职责：定义 Chat 主工作区、960px 中央列、消息滚动区和输入台的 DOM 层级。
- Create: `image-web/src/components/chat/ChatViewportLayout.test.ts` — 验证中央宽度、滚动所有权和输入台不在消息滚动区内。
- Modify: `image-web/src/pages/ChatPage.tsx:423-523` — 用 `ChatViewportLayout` 组合现有消息内容、`SessionSidebar` 与 `ChatComposer`。
- Modify: `image-web/src/components/chat/SessionSidebar.tsx:36-46` — 为历史列表增加可访问名称与隐藏滚动条 utility。
- Modify: `image-web/src/index.css:270-300` — 定义跨浏览器的 `scrollbar-hidden` Tailwind utility。

### Task 1: 建立中央 Chat 布局边界

**Files:**
- Create: `image-web/src/components/chat/ChatViewportLayout.tsx`
- Create: `image-web/src/components/chat/ChatViewportLayout.test.ts`
- Modify: `image-web/src/pages/ChatPage.tsx:423-523`

**Interfaces:**
- Consumes: `ReactNode` 消息内容、侧栏、输入台，以及 `RefObject<HTMLDivElement | null>` 的现有 `scrollRef`。
- Produces: `ChatViewportLayout(props): ReactElement`；消息容器暴露 `role="log"`、`aria-label="对话消息"` 和传入的 ref。

- [ ] **Step 1: 写失败测试，固定 960px 与滚动职责**

创建 `image-web/src/components/chat/ChatViewportLayout.test.ts`：

```tsx
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { ChatViewportLayout } from '@/components/chat/ChatViewportLayout'

describe('ChatViewportLayout', () => {
  it('keeps the composer outside the only visible message scroll region', () => {
    const markup = renderToStaticMarkup(
      createElement(ChatViewportLayout, {
        sidebar: createElement('aside', null, 'sessions'),
        messageViewportRef: { current: null },
        messages: createElement('p', null, 'message'),
        composer: createElement('form', { 'aria-label': 'composer' }, 'compose'),
      }),
    )

    expect(markup).toContain('max-w-[960px]')
    expect(markup).toContain('overflow-hidden')
    expect(markup).toContain('overflow-y-auto')
    expect(markup).toContain('role="log"')
    expect(markup).toContain('aria-label="对话消息"')

    const logEnd = markup.indexOf('</div>', markup.indexOf('role="log"'))
    const composer = markup.indexOf('aria-label="composer"')
    expect(logEnd).toBeGreaterThan(-1)
    expect(composer).toBeGreaterThan(logEnd)
  })
})
```

- [ ] **Step 2: 运行测试并确认因组件不存在而失败**

Run:

```bash
cd image-web
npm test -- src/components/chat/ChatViewportLayout.test.ts
```

Expected: FAIL，错误包含 `Cannot find module '@/components/chat/ChatViewportLayout'`。

- [ ] **Step 3: 实现最小布局组件**

创建 `image-web/src/components/chat/ChatViewportLayout.tsx`：

```tsx
import type { ReactNode, RefObject } from 'react'

export function ChatViewportLayout({
  sidebar,
  messages,
  composer,
  messageViewportRef,
}: {
  sidebar: ReactNode
  messages: ReactNode
  composer: ReactNode
  messageViewportRef: RefObject<HTMLDivElement | null>
}) {
  return (
    <main className="flex min-h-0 flex-1 gap-3 overflow-hidden pb-3 pr-3">
      {sidebar}
      <section
        aria-label="对话工作区"
        className="mx-auto flex h-full w-full min-w-0 max-w-[960px] flex-1 flex-col"
      >
        <div
          ref={messageViewportRef}
          role="log"
          aria-label="对话消息"
          tabIndex={0}
          className="min-h-0 flex-1 space-y-4 overflow-x-hidden overflow-y-auto px-2 py-4"
        >
          {messages}
        </div>
        {composer}
      </section>
    </main>
  )
}
```

- [ ] **Step 4: 让 `ChatPage` 只负责提供内容，不再拥有布局类**

在 `image-web/src/pages/ChatPage.tsx` 导入 `ChatViewportLayout`，把现有 `<main>`、中央 `max-w-3xl` 容器和消息滚动容器替换为：

```tsx
<ChatViewportLayout
  sidebar={
    <SessionSidebar
      activeId={state.sessionId}
      loadingId={loadSession.isPending ? loadSession.variables ?? null : null}
      onSelect={selectSession}
      onNew={newSession}
    />
  }
  messageViewportRef={scrollRef}
  messages={
    <>
      <div className="flex items-center gap-2 text-[13px] font-semibold text-wb-ink-2">
        <span className="grid size-7 place-items-center rounded-[9px] bg-gradient-to-br from-wb-grad-from to-wb-grad-to text-white">
          <WandSparklesIcon className="size-4" />
        </span>
        帮我设计
        <span className="rounded-full bg-wb-tint-1 px-2 py-0.5 text-[11px] font-medium text-wb-brand-deep">内测</span>
      </div>

      {shouldShowChatWelcome(state) && (
        <div className="flex items-start gap-2 pt-4">
          <span className="mt-1 grid size-7 shrink-0 place-items-center rounded-[9px] bg-wb-tint-1 text-wb-brand-deep">
            <SparklesIcon className="size-4" />
          </span>
          <div className="max-w-[88%] rounded-2xl rounded-tl-md border border-white/80 bg-white/85 px-4 py-3 text-[14px] leading-7 text-wb-ink-3 shadow-[0_10px_30px_-20px_rgba(40,40,90,.35)]">
            {CHAT_WELCOME_COPY}
          </div>
        </div>
      )}

      {state.bubbles.map((b, i) => (
        <Fragment key={i}>
          <Bubble
            bubble={b}
            awaiting={state.awaiting}
            onResolve={resolveConfirm}
            onOpenAction={openActionCard}
          />
          {b.jobId && (
            b.jobId === state.activeJobId ? (
              <CurrentJobResult
                state={state}
                onPreview={setPreviewImage}
                onEdit={selectEditSource}
                onBackground={openBackground}
                onReversePrompt={reverseGeneratedImage}
              />
            ) : (
              <ChatJobResult
                jobId={b.jobId}
                onPreview={setPreviewImage}
                onEdit={selectEditSource}
                onBackground={openBackground}
                onReversePrompt={reverseGeneratedImage}
              />
            )
          )}
        </Fragment>
      ))}

      {state.streaming && !state.awaiting && (
        <div className="flex items-center gap-2 px-1 text-[12.5px] text-wb-ink-6">
          <Loader2Icon className="size-3.5 animate-spin" /> 思考中…
        </div>
      )}

      {state.error && (
        <div className="rounded-xl border border-wb-red-line bg-wb-red-tint px-3 py-2 text-[12.5px] text-wb-red">
          {state.error.message}
        </div>
      )}
    </>
  }
  composer={
    <ChatComposer
      draft={draft}
      onDraftChange={(value) => {
        pendingSeedRef.current = null
        setDraft(value)
      }}
      attached={attached}
      selectedEditSource={selectedEditSource}
      token={token}
      busy={busy}
      modelsReady={modelsReady}
      uploadPending={upload.isPending}
      imageOptions={imageOptions}
      onImageOptionsChange={setImageOptions}
      chatSelection={chatModelSelection}
      imageSelection={composerImageModelSelection}
      onPickFiles={(files) => void onPickFiles(files)}
      onFileSelection={onFileSelection}
      onRemoveAttachment={(index) =>
        setAttached((current) => current.filter((_, itemIndex) => itemIndex !== index))
      }
      onCancelEdit={() => setSelectedEditSource(null)}
      onReversePrompt={() => void send('反推这张图的提示词', [attached[0].id])}
      onClear={() => {
        setDraft('')
        setAttached([])
        setSelectedEditSource(null)
      }}
      onSend={() => void send(draft, attached.map((image) => image.id))}
    />
  }
/>
```

迁移 JSX 时不得改变任何事件处理器、条件渲染、`ChatComposer` prop 或结果卡选择逻辑。

- [ ] **Step 5: 运行聚焦测试并确认通过**

Run:

```bash
cd image-web
npm test -- src/components/chat/ChatViewportLayout.test.ts src/lib/chat.test.ts src/components/chat/ChatComposer.test.ts src/components/chat/ChatJobResult.test.ts
```

Expected: 所有聚焦测试 PASS。

- [ ] **Step 6: 提交中央布局单元**

```bash
git add image-web/src/components/chat/ChatViewportLayout.tsx image-web/src/components/chat/ChatViewportLayout.test.ts image-web/src/pages/ChatPage.tsx
git commit -m "refactor: define the chat viewport layout" -m "Move Chat width and scroll ownership into a focused layout component. Use a 960px central column, keep the composer outside the message viewport, and preserve all existing Chat behavior."
```

### Task 2: 隐藏历史列表滚动条并完成界面验收

**Files:**
- Modify: `image-web/src/components/chat/SessionSidebar.tsx:36-46`
- Modify: `image-web/src/index.css:270-300`
- Modify: `image-web/src/components/chat/ChatViewportLayout.test.ts`

**Interfaces:**
- Consumes: Task 1 的 `ChatViewportLayout` 与现有 `SessionSidebar` 查询/交互契约。
- Produces: `scrollbar-hidden` Tailwind utility；历史列表暴露 `aria-label="历史对话"` 并保持 `overflow-y-auto`。

- [ ] **Step 1: 扩展失败测试，要求真实侧栏滚动容器同时具备滚动能力与隐藏滚动条标记**

在 `ChatViewportLayout.test.ts` 增加导入：

```tsx
import { SessionListViewport } from '@/components/chat/SessionSidebar'
```

再增加测试：

```tsx
it('keeps the session navigation separate from the message viewport', () => {
  const markup = renderToStaticMarkup(
    createElement(ChatViewportLayout, {
      sidebar: createElement(
        SessionListViewport,
        null,
        createElement('span', null, 'sessions'),
      ),
      messageViewportRef: { current: null },
      messages: createElement('p', null, 'message'),
      composer: createElement('form', null, 'compose'),
    }),
  )

  expect(markup).toContain('aria-label="历史对话"')
  expect(markup).toContain('overflow-y-auto')
  expect(markup).toContain('scrollbar-hidden')
  expect(markup.indexOf('历史对话')).toBeLessThan(markup.indexOf('role="log"'))
})
```

- [ ] **Step 2: 运行测试并确认当前实现不满足真实侧栏契约**

Run:

```bash
cd image-web
npm test -- src/components/chat/ChatViewportLayout.test.ts
```

Expected: FAIL，错误包含 `SessionListViewport` 未导出。

- [ ] **Step 3: 增加跨浏览器隐藏滚动条 utility**

在 `image-web/src/index.css` 的自定义 utilities 区加入：

```css
@utility scrollbar-hidden {
  scrollbar-width: none;

  &::-webkit-scrollbar {
    display: none;
  }
}
```

- [ ] **Step 4: 提取并使用真实的历史列表滚动容器**

在 `SessionSidebar.tsx` 中定义并导出：

```tsx
export function SessionListViewport({ children }: { children: ReactNode }) {
  return (
    <div
      aria-label="历史对话"
      tabIndex={0}
      className="scrollbar-hidden min-h-0 flex-1 space-y-0.5 overflow-y-auto"
    >
      {children}
    </div>
  )
}
```

导入 `ReactNode` 类型，并用 `SessionListViewport` 包住现有 loading、error、empty 和 session map 分支。不得改变查询、删除、选中或新建逻辑。

测试改为渲染真实 `SessionListViewport`：

```tsx
sidebar: createElement(
  SessionListViewport,
  null,
  createElement('span', null, 'sessions'),
),
```

断言仍使用 `aria-label="历史对话"`、`overflow-y-auto`、`scrollbar-hidden` 和相对消息区的 DOM 顺序。

- [ ] **Step 5: 运行聚焦测试、完整前端门禁和生产构建**

Run:

```bash
cd image-web
npm test -- src/components/chat/ChatViewportLayout.test.ts
npm test
npm run lint
npm run typecheck
npm run build
```

Expected: 所有测试 PASS；ESLint、TypeScript 和 Vite build 均 exit 0。

- [ ] **Step 6: 浏览器验收桌面与移动布局**

在本地生产构建或开发服务器中检查：

- 桌面 1862×925：中央工作区计算宽度为 960px；消息区与输入台左右边界一致。
- 长消息场景：`document.documentElement.scrollHeight === document.documentElement.clientHeight`，页面没有纵向滚动。
- 中央消息区：`scrollHeight > clientHeight` 时出现唯一可见滚动条，输入台仍在视口底部。
- 历史列表：可用滚轮与键盘滚动，但 Firefox `scrollbar-width` 为 `none`，Chromium 不显示 `::-webkit-scrollbar`。
- 移动宽度 390px：侧栏隐藏，中央列不横向溢出，输入台完整可见。

- [ ] **Step 7: 提交滚动条与验收单元**

```bash
git add image-web/src/components/chat/SessionSidebar.tsx image-web/src/components/chat/ChatViewportLayout.test.ts image-web/src/index.css
git commit -m "fix: keep one visible chat scrollbar" -m "Hide the session-list scrollbar without disabling navigation, keep message scrolling as the only visible scroll region, and preserve the viewport-anchored composer across desktop and mobile layouts."
```

## Completion Gate

- [ ] 两个任务均有独立的 red-green 测试证据和提交。
- [ ] `git diff --check` 无错误，工作区只包含本计划范围内的文件。
- [ ] 完整 Vitest、ESLint、TypeScript 和 Vite build 均通过。
- [ ] 浏览器实测确认 960px、单一可见滚动条、输入台底部固定和移动端无横向溢出。
- [ ] 不推送远端、不部署生产，除非用户另行明确授权。
