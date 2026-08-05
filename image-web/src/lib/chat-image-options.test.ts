import { describe, expect, it, vi } from 'vitest'

import type { ModelCatalogItem } from '@/api/models'
import type { ModelSelection } from '@/components/models/model-selection'
import {
  chatImageRatiosFor,
  chatRenderTiersFor,
  normalizeChatImageOptionsForModel,
  resolveChatImageOptions,
  type ChatImageOptionDraft,
} from '@/lib/chat-image-options'
import { decorateChatImageModelSelection } from '@/lib/chat-image-model-selection'

const gpt: ModelCatalogItem = {
  id: 'gpt-image-2',
  display_name: 'GPT Image 2.0',
  is_default: true,
  image_capabilities: {
    max_count: 7,
    supports_references: true,
    render_tiers: [
      {
        id: 'standard',
        label: '1K 标准',
        ratios: ['1:1', '3:2', '2:3', '4:5'],
      },
      { id: '4k', label: '4K 超清', ratios: ['16:9'] },
    ],
  },
}

const nano: ModelCatalogItem = {
  id: 'nano-banana-2',
  display_name: 'Nano Banana 2',
  is_default: false,
  image_capabilities: {
    max_count: 7,
    supports_references: true,
    render_tiers: [
      {
        id: 'standard',
        label: '1K 标准',
        ratios: ['1:1', '1:4', '1:8', '2:3', '3:2', '3:4', '4:1', '4:3', '4:5', '5:4', '8:1', '9:16', '16:9', '21:9'],
      },
      {
        id: '2k',
        label: '2K 高清',
        ratios: ['1:1', '1:4', '1:8', '2:3', '3:2', '3:4', '4:1', '4:3', '4:5', '5:4', '8:1', '9:16', '16:9', '21:9'],
      },
      {
        id: '4k',
        label: '4K 超清',
        ratios: ['1:1', '1:4', '1:8', '2:3', '3:2', '3:4', '4:1', '4:3', '4:5', '5:4', '8:1', '9:16', '16:9', '21:9'],
      },
    ],
  },
}

const standardDraft: ChatImageOptionDraft = {
  renderTier: 'standard',
  count: 3,
  ratio: '3:4',
}

describe('model-driven image options', () => {
  it('resolves exact Nano Banana 2K payload values', () => {
    expect(
      resolveChatImageOptions({
        renderTier: '2k',
        count: 1,
        ratio: '4:5',
      }),
    ).toEqual({ render_tier: '2k', count: 1, ratio: '4:5' })
  })

  it('derives all tiers and ratios from the selected catalog model', () => {
    expect(chatRenderTiersFor(nano).map((tier) => tier.id)).toEqual([
      'auto',
      'standard',
      '2k',
      '4k',
    ])
    expect(chatImageRatiosFor(nano, '2k')).toEqual([
      'auto',
      '1:1', '1:4', '1:8', '2:3', '3:2', '3:4', '4:1',
      '4:3', '4:5', '5:4', '8:1', '9:16', '16:9', '21:9',
    ])
  })

  it('normalizes unsupported selections when switching from Nano to GPT', () => {
    expect(
      normalizeChatImageOptionsForModel(
        { renderTier: '2k', count: 1, ratio: '21:9' },
        gpt,
      ),
    ).toEqual({ renderTier: 'auto', count: 1, ratio: 'auto' })
  })

  it('keeps supported standard output settings', () => {
    expect(resolveChatImageOptions(standardDraft)).toEqual({
      render_tier: 'standard',
      count: 3,
      ratio: '3:4',
    })
  })
})

describe('decorateChatImageModelSelection', () => {
  it('decorates selection with catalog-aware normalization', () => {
    const select = vi.fn()
    const onModelChanged = vi.fn()
    const selection: ModelSelection = {
      modelId: gpt.id,
      models: [gpt, nano],
      state: 'ready',
      select,
      retry: vi.fn(),
    }

    decorateChatImageModelSelection(selection, onModelChanged).select(nano.id)

    expect(select).toHaveBeenCalledWith(nano.id)
    expect(onModelChanged).toHaveBeenCalledWith(nano)
  })
})
