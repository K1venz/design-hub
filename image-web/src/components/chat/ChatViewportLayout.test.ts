import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { SessionListViewport } from '@/components/chat/SessionSidebar'
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
})
