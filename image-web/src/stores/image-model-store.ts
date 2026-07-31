import { create } from 'zustand'

import type { ImageModelCatalogItem } from '@/api/models'

export const IMAGE_MODEL_STORAGE_PREFIX = 'image-model-selection:'

interface SelectionStorage {
  getItem: (key: string) => string | null
  setItem: (key: string, value: string) => void
  removeItem: (key: string) => void
}

export function imageModelStorageKey(userId: string): string {
  return `${IMAGE_MODEL_STORAGE_PREFIX}${userId}`
}

function browserStorage(): SelectionStorage {
  if (typeof localStorage === 'undefined') {
    throw new Error('图片模型选择需要浏览器存储')
  }
  return localStorage
}

export interface ReconciledImageModelSelection {
  modelId: string | null
  selectionRequired: boolean
  removeStored: boolean
  persistModelId: string | null
}

export function reconcileImageModelSelection(args: {
  modelId: string | null
  selectionRequired: boolean
  models: ImageModelCatalogItem[]
}): ReconciledImageModelSelection {
  const { modelId, selectionRequired, models } = args
  if (modelId !== null) {
    if (models.some((model) => model.id === modelId)) {
      return {
        modelId,
        selectionRequired: false,
        removeStored: false,
        persistModelId: null,
      }
    }
    return {
      modelId: null,
      selectionRequired: true,
      removeStored: true,
      persistModelId: null,
    }
  }
  if (selectionRequired) {
    return {
      modelId: null,
      selectionRequired: true,
      removeStored: false,
      persistModelId: null,
    }
  }
  const serverDefault = models.find((model) => model.is_default)
  if (serverDefault) {
    return {
      modelId: serverDefault.id,
      selectionRequired: false,
      removeStored: false,
      persistModelId: serverDefault.id,
    }
  }
  return {
    modelId: null,
    selectionRequired: true,
    removeStored: false,
    persistModelId: null,
  }
}

interface ImageModelStoreState {
  userId: string | null
  modelId: string | null
  initialized: boolean
  selectionRequired: boolean
  activateUser: (userId: string, storage?: SelectionStorage) => void
  reconcile: (
    models: ImageModelCatalogItem[],
    storage?: SelectionStorage,
  ) => void
  select: (
    modelId: string,
    models: ImageModelCatalogItem[],
    storage?: SelectionStorage,
  ) => void
}

export const useImageModelStore = create<ImageModelStoreState>((set, get) => ({
  userId: null,
  modelId: null,
  initialized: false,
  selectionRequired: false,
  activateUser: (userId, storage = browserStorage()) => {
    const current = get()
    if (current.initialized && current.userId === userId) return
    set({
      userId,
      modelId: storage.getItem(imageModelStorageKey(userId)),
      initialized: true,
      selectionRequired: false,
    })
  },
  reconcile: (models, storage = browserStorage()) => {
    const current = get()
    if (!current.initialized || !current.userId) {
      throw new Error('图片模型选择尚未绑定用户')
    }
    const next = reconcileImageModelSelection({
      modelId: current.modelId,
      selectionRequired: current.selectionRequired,
      models,
    })
    const key = imageModelStorageKey(current.userId)
    if (next.removeStored) storage.removeItem(key)
    if (next.persistModelId) storage.setItem(key, next.persistModelId)
    if (
      current.modelId === next.modelId &&
      current.selectionRequired === next.selectionRequired
    ) {
      return
    }
    set({
      modelId: next.modelId,
      selectionRequired: next.selectionRequired,
    })
  },
  select: (modelId, models, storage = browserStorage()) => {
    const current = get()
    if (!current.initialized || !current.userId) {
      throw new Error('图片模型选择尚未绑定用户')
    }
    if (!models.some((model) => model.id === modelId)) {
      throw new Error('不能选择目录中不存在的图片模型')
    }
    storage.setItem(imageModelStorageKey(current.userId), modelId)
    set({ modelId, selectionRequired: false })
  },
}))
