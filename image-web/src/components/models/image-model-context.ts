import { createContext, useContext } from 'react'

import type { ImageModelCatalogItem } from '@/api/models'

export interface ImageModelSelection {
  modelId: string | null
  models: ImageModelCatalogItem[]
  state:
    | 'loading'
    | 'ready'
    | 'error'
    | 'empty'
    | 'selection_required'
  select: (modelId: string) => void
  retry: () => void
}

export const ImageModelContext =
  createContext<ImageModelSelection | null>(null)

export function useImageModelSelection(): ImageModelSelection {
  const value = useContext(ImageModelContext)
  if (!value) {
    throw new Error('useImageModelSelection 必须在 ImageModelGate 内使用')
  }
  return value
}

export function requireSelectedImageModel(
  selection: ImageModelSelection,
): string {
  if (selection.state !== 'ready' || !selection.modelId) {
    throw new Error('请先选择可用的图片模型')
  }
  return selection.modelId
}
