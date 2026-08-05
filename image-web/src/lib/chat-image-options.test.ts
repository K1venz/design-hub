import { describe, expect, it, vi } from 'vitest'

import type { ModelSelection } from '@/components/models/model-selection'
import {
  chatImageRatiosFor,
  resolveChatImageOptions,
  type ChatImageOptionDraft,
} from '@/lib/chat-image-options'
import { decorateChatImageModelSelection } from '@/lib/chat-image-model-selection'

const standardDraft: ChatImageOptionDraft = {
  renderTier: 'standard',
  count: 3,
  ratio: '3:4',
}

describe('resolveChatImageOptions', () => {
  it('keeps supported standard output settings', () => {
    expect(resolveChatImageOptions(standardDraft)).toEqual({
      render_tier: 'standard',
      count: 3,
      ratio: '3:4',
    })
  })

  it('forces the real 4K API constraints', () => {
    expect(
      resolveChatImageOptions({
        renderTier: '4k',
        count: 7,
        ratio: '9:16',
      }),
    ).toEqual({
      render_tier: '4k',
      count: 7,
      ratio: '16:9',
    })
  })

  it('keeps automatic ratio and count as explicit request values', () => {
    expect(
      resolveChatImageOptions({
        renderTier: 'standard',
        count: 'auto',
        ratio: 'auto',
      }),
    ).toEqual({
      render_tier: 'standard',
      count: null,
      ratio: 'auto',
    })
  })
})

describe('chatImageRatiosFor', () => {
  it('returns every live-verified GPT Image 2 standard ratio', () => {
    expect(chatImageRatiosFor('gpt-image-2', 'standard')).toEqual([
      'auto',
      '1:1',
      '3:2',
      '2:3',
      '3:4',
      '4:3',
      '9:16',
      '16:9',
      '4:5',
      '5:4',
      '1:2',
      '2:1',
    ])
  })
})

describe('decorateChatImageModelSelection', () => {
  it('preserves the model-selection contract and delegates selection', () => {
    const select = vi.fn()
    const onFourKUnavailable = vi.fn()
    const selection: ModelSelection = {
      modelId: 'gpt-image-2',
      models: [],
      state: 'ready',
      select,
      retry: vi.fn(),
    }

    const decorated = decorateChatImageModelSelection(
      selection,
      onFourKUnavailable,
    )
    decorated.select('wan2.7-image-pro')

    expect(decorated.modelId).toBe(selection.modelId)
    expect(decorated.state).toBe(selection.state)
    expect(select).toHaveBeenCalledWith('wan2.7-image-pro')
    expect(onFourKUnavailable).toHaveBeenCalledWith('wan2.7-image-pro')
  })

  it('notifies the option decorator for GPT Image 2 selections', () => {
    const onFourKUnavailable = vi.fn()
    const selection: ModelSelection = {
      modelId: 'wan2.7-image-pro',
      models: [],
      state: 'ready',
      select: vi.fn(),
      retry: vi.fn(),
    }

    decorateChatImageModelSelection(selection, onFourKUnavailable)
      .select('gpt-image-2')

    expect(onFourKUnavailable).toHaveBeenCalledWith('gpt-image-2')
  })
})
