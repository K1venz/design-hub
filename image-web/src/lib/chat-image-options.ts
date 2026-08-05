export const CHAT_IMAGE_RATIOS = [
  'auto',
  '1:1',
  '3:2',
  '3:4',
  '4:3',
  '9:16',
  '16:9',
] as const

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

const GPT_IMAGE_2_MODEL_ID = 'gpt-image-2'
const GPT_IMAGE_2_STANDARD_RATIOS: readonly ChatImageRatio[] = [
  'auto',
  '1:1',
  '3:2',
]
const GPT_IMAGE_2_FOUR_K_RATIOS: readonly ChatImageRatio[] = ['16:9']

export function chatImageRatiosFor(
  modelId: string | null,
  renderTier: ChatRenderTier,
): readonly ChatImageRatio[] {
  if (renderTier === '4k') return GPT_IMAGE_2_FOUR_K_RATIOS
  if (modelId === GPT_IMAGE_2_MODEL_ID) return GPT_IMAGE_2_STANDARD_RATIOS
  return CHAT_IMAGE_RATIOS
}

export function normalizeChatImageOptionsForModel(
  draft: ChatImageOptionDraft,
  modelId: string,
): ChatImageOptionDraft {
  if (modelId !== GPT_IMAGE_2_MODEL_ID) {
    return draft.renderTier === '4k'
      ? { ...draft, renderTier: 'standard' }
      : draft
  }
  if (
    draft.renderTier !== '4k' &&
    !GPT_IMAGE_2_STANDARD_RATIOS.includes(draft.ratio)
  ) {
    return { ...draft, ratio: 'auto' }
  }
  return draft
}

export function resolveChatImageOptions(
  draft: ChatImageOptionDraft,
): ChatImageOptionsPayload {
  if (draft.renderTier === '4k') {
    return {
      render_tier: '4k',
      count: draft.count === 'auto' ? null : draft.count,
      ratio: '16:9',
    }
  }
  return {
    render_tier: draft.renderTier,
    count: draft.count === 'auto' ? null : draft.count,
    ratio: draft.ratio,
  }
}
