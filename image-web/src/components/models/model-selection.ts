import type { ModelCatalogItem } from '@/api/models'

export interface ModelSelection {
  modelId: string | null
  models: ModelCatalogItem[]
  state:
    | 'loading'
    | 'ready'
    | 'error'
    | 'empty'
    | 'selection_required'
  select: (modelId: string) => void
  retry: () => void
}

export function requireSelectedModel(
  selection: ModelSelection,
  label: string,
): string {
  if (selection.state !== 'ready' || !selection.modelId) {
    throw new Error(`请先选择可用的${label}模型`)
  }
  return selection.modelId
}
