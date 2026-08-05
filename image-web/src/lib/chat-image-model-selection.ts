import type { ModelSelection } from '@/components/models/model-selection'
import type { ModelCatalogItem } from '@/api/models'

export function decorateChatImageModelSelection(
  wrapped: ModelSelection,
  onModelChanged: (model: ModelCatalogItem) => void,
): ModelSelection {
  return {
    ...wrapped,
    select: (modelId) => {
      wrapped.select(modelId)
      const model = wrapped.models.find((item) => item.id === modelId)
      if (!model) throw new Error(`图片模型目录中不存在 ${modelId}`)
      onModelChanged(model)
    },
  }
}
