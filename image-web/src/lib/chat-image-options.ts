export const CHAT_IMAGE_RATIOS = ['auto', '1:1', '3:4', '4:3', '9:16', '16:9'] as const

export type ChatImageRatio = (typeof CHAT_IMAGE_RATIOS)[number]
export type ChatImageCount = 'auto' | 1 | 2 | 3 | 4 | 5 | 6 | 7
export type ChatRenderTier = 'auto' | 'standard' | '4k'

export interface ChatImageOptionDraft {
  renderTier: ChatRenderTier
  count: ChatImageCount
  ratio: ChatImageRatio
}

export interface ChatImageOptionsPayload {
  render_tier: ChatRenderTier
  count: number | null
  ratio: ChatImageRatio
}

export const INITIAL_CHAT_IMAGE_OPTIONS: ChatImageOptionDraft = {
  renderTier: 'standard',
  count: 'auto',
  ratio: 'auto',
}

export function resolveChatImageOptions(
  draft: ChatImageOptionDraft,
): ChatImageOptionsPayload {
  if (draft.renderTier === '4k') {
    return {
      render_tier: '4k',
      count: 1,
      ratio: '16:9',
    }
  }
  return {
    render_tier: draft.renderTier,
    count: draft.count === 'auto' ? null : draft.count,
    ratio: draft.ratio,
  }
}
