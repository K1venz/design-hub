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
