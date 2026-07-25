import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { ChatResultBlock } from '@/components/chat/ChatResultBlock'

describe('ChatResultBlock', () => {
  it('offers preview, edit, and download for a stable result image', () => {
    const html = renderToStaticMarkup(
      createElement(ChatResultBlock, {
        slots: [{
          url: 'https://img/result.png',
          imageKey: 'result.png',
          imageType: '场景',
        }],
        done: 1,
        total: 1,
        onPreview: () => undefined,
        onEdit: () => undefined,
      }),
    )

    expect(html).toContain('预览第 1 张图片')
    expect(html).toContain('继续编辑')
    expect(html).toContain('下载')
  })

  it('keeps preview and download but hides edit until imageKey is stable', () => {
    const html = renderToStaticMarkup(
      createElement(ChatResultBlock, {
        slots: [{ url: 'https://img/live.png' }],
        done: 1,
        total: 1,
        onPreview: () => undefined,
        onEdit: () => undefined,
      }),
    )

    expect(html).toContain('预览第 1 张图片')
    expect(html).not.toContain('继续编辑')
    expect(html).toContain('下载')
  })
})
