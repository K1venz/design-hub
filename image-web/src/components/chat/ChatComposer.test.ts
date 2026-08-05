import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { ChatComposer } from '@/components/chat/ChatComposer'
import type { ModelSelection } from '@/components/models/model-selection'

function selection(modelId: string): ModelSelection {
  return {
    modelId,
    models: [
      {
        id: modelId,
        display_name: modelId,
        is_default: true,
      },
    ],
    state: 'ready',
    select: vi.fn(),
    retry: vi.fn(),
  }
}

function renderComposer(renderTier: 'standard' | '4k', count: 1 | 7) {
  return renderToStaticMarkup(
    createElement(ChatComposer, {
      draft: '生成商品海报',
      onDraftChange: vi.fn(),
      attached: [],
      selectedEditSource: null,
      token: null,
      busy: false,
      modelsReady: true,
      uploadPending: false,
      imageOptions: {
        renderTier,
        count,
        ratio: renderTier === '4k' ? '16:9' : '1:1',
      },
      onImageOptionsChange: vi.fn(),
      chatSelection: selection('doubao-chat'),
      imageSelection: selection('gpt-image-2'),
      onPickFiles: vi.fn(),
      onRemoveAttachment: vi.fn(),
      onCancelEdit: vi.fn(),
      onReversePrompt: vi.fn(),
      onClear: vi.fn(),
      onSend: vi.fn(),
    }),
  )
}

describe('ChatComposer GPT Image 2 parameters', () => {
  it('renders only the documented standard ratios', () => {
    const markup = renderComposer('standard', 1)

    expect(markup).toContain('<option value="1:1" selected="">1:1</option>')
    expect(markup).toContain('<option value="3:2">3:2</option>')
    expect(markup).not.toContain('<option value="3:4">')
    expect(markup).not.toContain('<option value="4:3">')
    expect(markup).not.toContain('<option value="9:16">')
  })

  it('keeps batch count selectable in 4K mode', () => {
    const markup = renderComposer('4k', 7)
    const countSelect = markup.match(/<select aria-label="生成数量"[^>]*>/)?.[0]

    expect(countSelect).toBeDefined()
    expect(countSelect).not.toContain(' disabled=""')
    expect(markup).toContain('<option value="7" selected="">7 张</option>')
  })
})
