import type { ModelSelection } from '@/components/models/model-selection'

const FOUR_K_IMAGE_MODEL = 'gpt-image-2'

export function decorateChatImageModelSelection(
  wrapped: ModelSelection,
  onFourKUnavailable: () => void,
): ModelSelection {
  return {
    ...wrapped,
    select: (modelId) => {
      wrapped.select(modelId)
      if (modelId !== FOUR_K_IMAGE_MODEL) onFourKUnavailable()
    },
  }
}
