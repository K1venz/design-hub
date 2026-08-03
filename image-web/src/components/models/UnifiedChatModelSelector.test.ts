import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import type { ModelSelection } from '@/components/models/model-selection'
import {
  filterModelCatalog,
  modelBrand,
} from '@/components/models/model-brand'
import { UnifiedChatModelSelector } from '@/components/models/UnifiedChatModelSelector'

const chatModels = [
  { id: 'doubao-chat', display_name: 'Doubao', is_default: true },
  { id: 'deepseek-v4-flash', display_name: 'DeepSeek V4 Flash', is_default: false },
]
const imageModels = [
  { id: 'gpt-image-2', display_name: 'GPT Image 2.0', is_default: true },
  { id: 'wan2.7-image-pro', display_name: 'Wan 2.7', is_default: false },
]

function selection(
  kind: 'chat' | 'image',
  state: ModelSelection['state'] = 'ready',
): ModelSelection {
  const models = kind === 'chat' ? chatModels : imageModels
  return {
    modelId: state === 'ready' ? models[0].id : null,
    models: state === 'empty' ? [] : models,
    state,
    select: vi.fn(),
    retry: vi.fn(),
  }
}

describe('UnifiedChatModelSelector', () => {
  it('renders the selected C-style text and image segments', () => {
    const html = renderToStaticMarkup(
      createElement(UnifiedChatModelSelector, {
        chatSelection: selection('chat'),
        imageSelection: selection('image'),
      }),
    )
    expect(html).toContain('Doubao')
    expect(html).toContain('GPT Image 2.0')
    expect(html).toContain('选择文本和图片模型')
    expect(html).toContain('/model-brands/doubao.svg')
    expect(html).toContain('/model-brands/openai.svg')
  })

  it('locks the trigger while a chat turn is running', () => {
    const html = renderToStaticMarkup(
      createElement(UnifiedChatModelSelector, {
        chatSelection: selection('chat'),
        imageSelection: selection('image'),
        disabled: true,
      }),
    )
    expect(html).toContain('disabled=""')
  })

  it('shows independent unresolved states in the compact trigger', () => {
    const html = renderToStaticMarkup(
      createElement(UnifiedChatModelSelector, {
        chatSelection: selection('chat', 'error'),
        imageSelection: selection('image', 'selection_required'),
      }),
    )
    expect(html).toContain('文本模型异常')
    expect(html).toContain('选择图片模型')
  })

  it('uses a neutral brand for future model IDs', () => {
    expect(modelBrand('custom-private-model')).toEqual({
      name: '其他',
      logoPath: null,
    })
  })

  it('filters by display name, model id, and brand', () => {
    expect(filterModelCatalog(chatModels, 'deepseek')).toEqual([
      chatModels[1],
    ])
    expect(filterModelCatalog(imageModels, 'openai')).toEqual([
      imageModels[0],
    ])
  })
})
