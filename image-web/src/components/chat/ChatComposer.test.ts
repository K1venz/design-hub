import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { ChatComposer } from '@/components/chat/ChatComposer'
import type { ModelSelection } from '@/components/models/model-selection'

function selection(modelId: string): ModelSelection {
  const isNano = modelId === 'nano-banana-2'
  return {
    modelId,
    models: [
      {
        id: modelId,
        display_name: isNano ? 'Nano Banana 2' : modelId,
        is_default: true,
        ...(modelId === 'doubao-chat'
          ? {}
          : {
              image_capabilities: {
                max_count: 7,
                supports_references: true,
                render_tiers: isNano
                  ? [
                      { id: 'standard' as const, label: '1K 标准', ratios: ['1:1', '4:5'] },
                      { id: '2k' as const, label: '2K 高清', ratios: ['1:1', '4:5', '21:9'] },
                      { id: '4k' as const, label: '4K 超清', ratios: ['1:1', '4:5', '21:9'] },
                    ]
                  : [
                      { id: 'standard' as const, label: '1K 标准', ratios: ['1:1', '3:2', '2:3', '3:4', '4:3', '9:16', '16:9', '4:5', '5:4', '1:2', '2:1'] },
                      { id: '4k' as const, label: '4K 超清', ratios: ['16:9'] },
                    ],
              },
            }),
      },
    ],
    state: 'ready',
    select: vi.fn(),
    retry: vi.fn(),
  }
}

function renderComposer(
  renderTier: 'standard' | '2k' | '4k',
  count: 1 | 7,
  modelId = 'gpt-image-2',
) {
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
        ratio: renderTier === '4k' && modelId === 'gpt-image-2' ? '16:9' : '1:1',
      },
      onImageOptionsChange: vi.fn(),
      chatSelection: selection('doubao-chat'),
      imageSelection: selection(modelId),
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
  it('renders every live-verified standard ratio', () => {
    const markup = renderComposer('standard', 1)

    expect(markup).toContain('<option value="1:1" selected="">1:1</option>')
    expect(markup).toContain('<option value="3:2">3:2</option>')
    expect(markup).toContain('<option value="2:3">2:3</option>')
    expect(markup).toContain('<option value="3:4">3:4</option>')
    expect(markup).toContain('<option value="4:3">4:3</option>')
    expect(markup).toContain('<option value="9:16">9:16</option>')
    expect(markup).toContain('<option value="16:9">16:9</option>')
    expect(markup).toContain('<option value="4:5">4:5</option>')
    expect(markup).toContain('<option value="5:4">5:4</option>')
    expect(markup).toContain('<option value="1:2">1:2</option>')
    expect(markup).toContain('<option value="2:1">2:1</option>')
  })

  it('keeps batch count selectable in 4K mode', () => {
    const markup = renderComposer('4k', 7)
    const countSelect = markup.match(/<select aria-label="生成数量"[^>]*>/)?.[0]

    expect(countSelect).toBeDefined()
    expect(countSelect).not.toContain(' disabled=""')
    expect(markup).toContain('<option value="7" selected="">7 张</option>')
  })

  it('renders Nano Banana 2K and its model-provided ratios', () => {
    const markup = renderComposer('2k', 1, 'nano-banana-2')

    expect(markup).toContain('<option value="2k" selected="">2K 高清</option>')
    expect(markup).toContain('<option value="4:5">4:5</option>')
    expect(markup).toContain('<option value="21:9">21:9</option>')
    expect(markup).toContain('Nano Banana 2')
  })
})
