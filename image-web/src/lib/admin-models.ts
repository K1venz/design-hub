import type { ModelConfig } from '@/api/admin'
import type { ModelType } from '@/lib/model-config'

export type ModelFilter = 'all' | ModelType

export const MODEL_FILTERS: { value: ModelFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'image', label: '图片模型' },
  { value: 'chat', label: 'Chat 模型' },
  { value: 'vision', label: '视觉模型' },
]

export function filterModelsByType(
  models: ModelConfig[],
  filter: ModelFilter,
): ModelConfig[] {
  return filter === 'all'
    ? models
    : models.filter((model) => model.model_type === filter)
}

export function modelTypeLabel(modelType: ModelType): string {
  const labels: Record<ModelType, string> = {
    image: '图片',
    chat: 'Chat',
    vision: '视觉',
  }
  return labels[modelType]
}
