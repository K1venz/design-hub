import type { ModelSelection } from '@/components/models/model-selection'

export function decorateChatImageModelSelection(
  wrapped: ModelSelection,
  onModelChanged: (modelId: string) => void,
): ModelSelection {
  return {
    ...wrapped,
    select: (modelId) => {
      wrapped.select(modelId)
      onModelChanged(modelId)
    },
  }
}
