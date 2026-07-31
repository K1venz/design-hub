import {
  useEffect,
  useMemo,
  type ReactNode,
} from 'react'

import { useImageModels } from '@/api/models'
import {
  ImageModelContext,
  type ImageModelSelection,
} from '@/components/models/image-model-context'
import { useCurrentUser } from '@/stores/auth-store'
import { useImageModelStore } from '@/stores/image-model-store'

export function ImageModelGate({ children }: { children: ReactNode }) {
  const user = useCurrentUser()
  const query = useImageModels()
  const storeUserId = useImageModelStore((store) => store.userId)
  const initialized = useImageModelStore((store) => store.initialized)
  const modelId = useImageModelStore((store) => store.modelId)
  const selectionRequired = useImageModelStore(
    (store) => store.selectionRequired,
  )
  const activateUser = useImageModelStore((store) => store.activateUser)
  const reconcile = useImageModelStore((store) => store.reconcile)
  const selectModel = useImageModelStore((store) => store.select)
  const activeForUser = initialized && storeUserId === user.user_id

  useEffect(() => {
    activateUser(user.user_id)
  }, [activateUser, user.user_id])

  useEffect(() => {
    if (activeForUser && query.data) reconcile(query.data)
  }, [activeForUser, query.data, reconcile])

  const value = useMemo<ImageModelSelection>(() => {
    const models = query.data ?? []
    let state: ImageModelSelection['state']
    if (!activeForUser || (!query.data && query.isLoading)) {
      state = 'loading'
    } else if (!query.data && query.isError) {
      state = 'error'
    } else if (models.length === 0) {
      state = 'empty'
    } else if (
      selectionRequired ||
      modelId === null ||
      !models.some((model) => model.id === modelId)
    ) {
      state = 'selection_required'
    } else {
      state = 'ready'
    }
    return {
      modelId: activeForUser ? modelId : null,
      models,
      state,
      select: (nextModelId) => selectModel(nextModelId, models),
      retry: () => {
        void query.refetch()
      },
    }
  }, [
    activeForUser,
    modelId,
    query,
    selectModel,
    selectionRequired,
  ])

  return (
    <ImageModelContext.Provider value={value}>
      {children}
    </ImageModelContext.Provider>
  )
}
