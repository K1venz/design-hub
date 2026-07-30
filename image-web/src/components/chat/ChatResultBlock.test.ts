import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { ChatResultBlock } from '@/components/chat/ChatResultBlock'

describe('ChatResultBlock', () => {
  it('offers preview, edit, background replacement, prompt reversal, and download for a stable result image', () => {
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
        onBackground: () => undefined,
        onReversePrompt: () => undefined,
      }),
    )

    expect(html).toContain('预览第 1 张图片')
    expect(html).toContain('继续编辑')
    expect(html).toContain('换背景')
    expect(html).toContain('反推提示词')
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
        onBackground: () => undefined,
        onReversePrompt: () => undefined,
      }),
    )

    expect(html).toContain('预览第 1 张图片')
    expect(html).not.toContain('继续编辑')
    expect(html).not.toContain('换背景')
    expect(html).not.toContain('反推提示词')
    expect(html).toContain('下载')
  })

  it('shows a neutral unavailable state without image actions', () => {
    const html = renderToStaticMarkup(
      createElement(ChatResultBlock, {
        slots: [{
          url: null,
          imageKey: 'blocked.png',
          unavailable: true,
        }],
        done: 1,
        total: 1,
        onPreview: () => undefined,
        onEdit: () => undefined,
        onBackground: () => undefined,
        onReversePrompt: () => undefined,
      }),
    )

    expect(html).toContain('该图片暂不可用')
    expect(html).not.toContain('预览第 1 张图片')
    expect(html).not.toContain('继续编辑')
    expect(html).not.toContain('换背景')
    expect(html).not.toContain('反推提示词')
    expect(html).not.toContain('下载')
  })
})
