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
        status: 'completed',
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
        status: 'generating',
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
        status: 'completed',
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

  it('shows an explicit interruption state without a spinner', () => {
    const html = renderToStaticMarkup(
      createElement(ChatResultBlock, {
        slots: [{ url: null }],
        status: 'interrupted',
        done: 0,
        total: 1,
        onPreview: () => undefined,
        onEdit: () => undefined,
        onBackground: () => undefined,
        onReversePrompt: () => undefined,
      }),
    )

    expect(html).toContain('连接已中断，任务仍在后台执行')
    expect(html).not.toContain('animate-spin')
  })

  it('only animates pending slots while the image task is generating', () => {
    const html = renderToStaticMarkup(
      createElement(ChatResultBlock, {
        slots: [{ url: null }],
        status: 'generating',
        done: 0,
        total: 1,
        onPreview: () => undefined,
        onEdit: () => undefined,
        onBackground: () => undefined,
        onReversePrompt: () => undefined,
      }),
    )

    expect(html).toContain('animate-spin')
  })
})
