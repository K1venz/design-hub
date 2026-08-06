import type { ModelCatalogItem } from '@/api/models'
import type { components } from '@/api/schema'

type ChatImageOptionsRequest = components['schemas']['ChatImageOptionsRequest']

export type ChatImageRatio = ChatImageOptionsRequest['ratio']
export type ChatImageCount = 'auto' | 1 | 2 | 3 | 4 | 5 | 6 | 7
export type ChatRenderTier = ChatImageOptionsRequest['render_tier']

export interface ChatImageOptionDraft {
  renderTier: ChatRenderTier
  count: ChatImageCount
  ratio: ChatImageRatio
}

export type ChatImageOptionsPayload = ChatImageOptionsRequest

export interface ChatRenderTierOption {
  id: ChatRenderTier
  label: string
}

export const INITIAL_CHAT_IMAGE_OPTIONS: ChatImageOptionDraft = {
  renderTier: 'standard',
  count: 'auto',
  ratio: 'auto',
}

export function chatRenderTiersFor(
  model: ModelCatalogItem | null,
  hasReferences: boolean,
): readonly ChatRenderTierOption[] {
  return [
    { id: 'auto', label: '自动判断' },
    ...(model?.image_capabilities?.render_tiers ?? [])
      .filter((tier) => !hasReferences || tier.supports_references)
      .map((tier) => ({
        id: tier.id,
        label: tier.label,
      })),
  ]
}

export function chatImageRatiosFor(
  model: ModelCatalogItem | null,
  renderTier: ChatRenderTier,
  hasReferences: boolean,
): readonly ChatImageRatio[] {
  const tiers = (model?.image_capabilities?.render_tiers ?? []).filter(
    (tier) => !hasReferences || tier.supports_references,
  )
  const ratios =
    renderTier === 'auto'
      ? unique(tiers.flatMap((tier) => tier.ratios))
      : (tiers.find((tier) => tier.id === renderTier)?.ratios ?? [])
  return ['auto', ...ratios] as ChatImageRatio[]
}

export function chatImageCountsFor(
  model: ModelCatalogItem | null,
): readonly ChatImageCount[] {
  const maxCount = Math.min(model?.image_capabilities?.max_count ?? 1, 7)
  return [
    'auto',
    ...Array.from({ length: maxCount }, (_, index) =>
      (index + 1) as ChatImageCount,
    ),
  ]
}

export function normalizeChatImageOptionsForModel(
  draft: ChatImageOptionDraft,
  model: ModelCatalogItem,
  hasReferences: boolean,
): ChatImageOptionDraft {
  const tiers = chatRenderTiersFor(model, hasReferences)
  const renderTier = tiers.some((tier) => tier.id === draft.renderTier)
    ? draft.renderTier
    : 'auto'
  const ratios = chatImageRatiosFor(model, renderTier, hasReferences)
  const ratio = ratios.includes(draft.ratio) ? draft.ratio : 'auto'
  const counts = chatImageCountsFor(model)
  const count = counts.includes(draft.count) ? draft.count : 'auto'
  return { renderTier, ratio, count }
}

export function resolveChatImageOptions(
  draft: ChatImageOptionDraft,
): ChatImageOptionsPayload {
  return {
    render_tier: draft.renderTier,
    count: draft.count === 'auto' ? null : draft.count,
    ratio: draft.ratio,
  }
}

function unique(values: string[]): string[] {
  return [...new Set(values)]
}
