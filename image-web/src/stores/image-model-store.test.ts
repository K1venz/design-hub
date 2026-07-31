import { afterEach, describe, expect, it } from 'vitest'

import type { ImageModelCatalogItem } from '@/api/models'
import {
  imageModelStorageKey,
  reconcileImageModelSelection,
  useImageModelStore,
} from '@/stores/image-model-store'

const models: ImageModelCatalogItem[] = [
  { id: 'gpt-image-2', display_name: 'GPT Image 2', is_default: true },
  { id: 'wan2.7-image-pro', display_name: 'Wan 2.7', is_default: false },
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
  useImageModelStore.setState({
    userId: null,
    modelId: null,
    initialized: false,
    selectionRequired: false,
  })
})

describe('image model persistence', () => {
  it('scopes the storage key to the authenticated user', () => {
    expect(imageModelStorageKey('42')).toBe('image-model-selection:42')
    expect(imageModelStorageKey('43')).not.toBe(imageModelStorageKey('42'))
  })

  it('initializes a missing selection from the server default', () => {
    expect(
      reconcileImageModelSelection({
        modelId: null,
        selectionRequired: false,
        models,
      }),
    ).toEqual({
      modelId: 'gpt-image-2',
      selectionRequired: false,
      removeStored: false,
      persistModelId: 'gpt-image-2',
    })
  })

  it('keeps a still-valid stored selection instead of switching to default', () => {
    expect(
      reconcileImageModelSelection({
        modelId: 'wan2.7-image-pro',
        selectionRequired: false,
        models,
      }),
    ).toMatchObject({
      modelId: 'wan2.7-image-pro',
      selectionRequired: false,
      persistModelId: null,
    })
  })

  it('removes a stale stored selection and requires an explicit choice', () => {
    expect(
      reconcileImageModelSelection({
        modelId: 'disabled-model',
        selectionRequired: false,
        models,
      }),
    ).toEqual({
      modelId: null,
      selectionRequired: true,
      removeStored: true,
      persistModelId: null,
    })
  })

  it('does not silently choose the default after a stale selection was cleared', () => {
    expect(
      reconcileImageModelSelection({
        modelId: null,
        selectionRequired: true,
        models,
      }),
    ).toMatchObject({
      modelId: null,
      selectionRequired: true,
      persistModelId: null,
    })
  })

  it('switching users reads only the new user storage key', () => {
    const storage = memoryStorage({
      [imageModelStorageKey('user-a')]: 'wan2.7-image-pro',
      [imageModelStorageKey('user-b')]: 'gpt-image-2',
    })
    const store = useImageModelStore.getState()
    store.activateUser('user-a', storage)
    expect(useImageModelStore.getState().modelId).toBe('wan2.7-image-pro')

    useImageModelStore.getState().activateUser('user-b', storage)
    expect(useImageModelStore.getState()).toMatchObject({
      userId: 'user-b',
      modelId: 'gpt-image-2',
      selectionRequired: false,
    })
  })
})
