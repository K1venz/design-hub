import { create } from 'zustand'

import type { ModelCatalogItem } from '@/api/models'

export type ModelKind = 'chat' | 'image'

interface SelectionStorage {
  getItem: (key: string) => string | null
  setItem: (key: string, value: string) => void
  removeItem: (key: string) => void
}

export interface ModelSelectionState {
  modelId: string | null
  selectionRequired: boolean
}

const EMPTY_SELECTIONS: Record<ModelKind, ModelSelectionState> = {
  chat: { modelId: null, selectionRequired: false },
  image: { modelId: null, selectionRequired: false },
}

export function modelSelectionStorageKey(
  kind: ModelKind,
  userId: string,
): string {
  return `model-selection:${kind}:${userId}`
}

function browserStorage(): SelectionStorage {
  if (typeof localStorage === 'undefined') {
    throw new Error('模型选择需要浏览器存储')
  }
  return localStorage
}

export interface ReconciledModelSelection extends ModelSelectionState {
  removeStored: boolean
  persistModelId: string | null
}

export function reconcileModelSelection(args: {
  modelId: string | null
  selectionRequired: boolean
  models: ModelCatalogItem[]
}): ReconciledModelSelection {
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
  return serverDefault
    ? {
        modelId: serverDefault.id,
        selectionRequired: false,
        removeStored: false,
        persistModelId: serverDefault.id,
      }
    : {
        modelId: null,
        selectionRequired: true,
        removeStored: false,
        persistModelId: null,
      }
}

interface ModelSelectionStoreState {
  userId: string | null
  initialized: boolean
  selections: Record<ModelKind, ModelSelectionState>
  activateUser: (userId: string, storage?: SelectionStorage) => void
  reconcile: (
    kind: ModelKind,
    models: ModelCatalogItem[],
    storage?: SelectionStorage,
  ) => void
  select: (
    kind: ModelKind,
    modelId: string,
    models: ModelCatalogItem[],
    storage?: SelectionStorage,
  ) => void
}

function kindLabel(kind: ModelKind): string {
  return kind === 'chat' ? '文本' : '图片'
}

export const useModelSelectionStore = create<ModelSelectionStoreState>(
  (set, get) => ({
    userId: null,
    initialized: false,
    selections: EMPTY_SELECTIONS,
    activateUser: (userId, storage = browserStorage()) => {
      const current = get()
      if (current.initialized && current.userId === userId) return
      set({
        userId,
        initialized: true,
        selections: {
          chat: {
            modelId: storage.getItem(
              modelSelectionStorageKey('chat', userId),
            ),
            selectionRequired: false,
          },
          image: {
            modelId: storage.getItem(
              modelSelectionStorageKey('image', userId),
            ),
            selectionRequired: false,
          },
        },
      })
    },
    reconcile: (kind, models, storage = browserStorage()) => {
      const current = get()
      if (!current.initialized || !current.userId) {
        throw new Error('模型选择尚未绑定用户')
      }
      const selection = current.selections[kind]
      const next = reconcileModelSelection({ ...selection, models })
      const key = modelSelectionStorageKey(kind, current.userId)
      if (next.removeStored) storage.removeItem(key)
      if (next.persistModelId) storage.setItem(key, next.persistModelId)
      if (
        selection.modelId === next.modelId &&
        selection.selectionRequired === next.selectionRequired
      ) {
        return
      }
      set({
        selections: {
          ...current.selections,
          [kind]: {
            modelId: next.modelId,
            selectionRequired: next.selectionRequired,
          },
        },
      })
    },
    select: (kind, modelId, models, storage = browserStorage()) => {
      const current = get()
      if (!current.initialized || !current.userId) {
        throw new Error('模型选择尚未绑定用户')
      }
      if (!models.some((model) => model.id === modelId)) {
        throw new Error(`不能选择目录中不存在的${kindLabel(kind)}模型`)
      }
      storage.setItem(modelSelectionStorageKey(kind, current.userId), modelId)
      set({
        selections: {
          ...current.selections,
          [kind]: { modelId, selectionRequired: false },
        },
      })
    },
  }),
)
