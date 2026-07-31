import { afterEach, describe, expect, it } from 'vitest'

import type { ModelCatalogItem } from '@/api/models'
import {
  modelSelectionStorageKey,
  reconcileModelSelection,
  useModelSelectionStore,
} from '@/stores/model-selection-store'

const imageModels: ModelCatalogItem[] = [
  { id: 'gpt-image-2', display_name: 'GPT Image 2', is_default: true },
  { id: 'wan2.7-image-pro', display_name: 'Wan 2.7', is_default: false },
]
const chatModels: ModelCatalogItem[] = [
  { id: 'doubao-chat', display_name: 'Doubao', is_default: true },
  { id: 'deepseek-v4-flash', display_name: 'DeepSeek', is_default: false },
]

function memoryStorage(seed: Record<string, string> = {}) {
  const values = new Map(Object.entries(seed))
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
    values,
  }
}

afterEach(() => {
  useModelSelectionStore.setState({
    userId: null,
    initialized: false,
    selections: {
      chat: { modelId: null, selectionRequired: false },
      image: { modelId: null, selectionRequired: false },
    },
  })
})

describe('account-scoped model selection', () => {
  it('uses independent model-kind and user storage keys', () => {
    expect(modelSelectionStorageKey('chat', '42')).toBe(
      'model-selection:chat:42',
    )
    expect(modelSelectionStorageKey('image', '42')).toBe(
      'model-selection:image:42',
    )
  })

  it('initializes each missing selection from its own server default', () => {
    expect(
      reconcileModelSelection({
        modelId: null,
        selectionRequired: false,
        models: chatModels,
      }).modelId,
    ).toBe('doubao-chat')
    expect(
      reconcileModelSelection({
        modelId: null,
        selectionRequired: false,
        models: imageModels,
      }).modelId,
    ).toBe('gpt-image-2')
  })

  it('removes a stale choice and requires explicit re-selection', () => {
    const next = reconcileModelSelection({
      modelId: 'disabled-model',
      selectionRequired: false,
      models: chatModels,
    })
    expect(next).toEqual({
      modelId: null,
      selectionRequired: true,
      removeStored: true,
      persistModelId: null,
    })
    expect(
      reconcileModelSelection({
        modelId: null,
        selectionRequired: true,
        models: chatModels,
      }).modelId,
    ).toBeNull()
  })

  it('loads both selections from only the active account', () => {
    const storage = memoryStorage({
      [modelSelectionStorageKey('chat', 'user-a')]: 'deepseek-v4-flash',
      [modelSelectionStorageKey('image', 'user-a')]: 'wan2.7-image-pro',
      [modelSelectionStorageKey('chat', 'user-b')]: 'doubao-chat',
      [modelSelectionStorageKey('image', 'user-b')]: 'gpt-image-2',
    })
    useModelSelectionStore.getState().activateUser('user-a', storage)
    expect(useModelSelectionStore.getState().selections).toEqual({
      chat: { modelId: 'deepseek-v4-flash', selectionRequired: false },
      image: { modelId: 'wan2.7-image-pro', selectionRequired: false },
    })

    useModelSelectionStore.getState().activateUser('user-b', storage)
    expect(useModelSelectionStore.getState().selections).toEqual({
      chat: { modelId: 'doubao-chat', selectionRequired: false },
      image: { modelId: 'gpt-image-2', selectionRequired: false },
    })
  })

  it('rejects selecting a model outside the matching catalog', () => {
    const storage = memoryStorage()
    useModelSelectionStore.getState().activateUser('user-a', storage)
    expect(() =>
      useModelSelectionStore
        .getState()
        .select('chat', 'gpt-image-2', chatModels, storage),
    ).toThrow('不能选择目录中不存在的文本模型')
  })
})
