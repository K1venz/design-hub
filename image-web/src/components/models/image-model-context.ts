import { createContext, useContext } from 'react'

import {
  requireSelectedModel,
  type ModelSelection,
} from '@/components/models/model-selection'

export type ImageModelSelection = ModelSelection

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
  return requireSelectedModel(selection, '图片')
}
