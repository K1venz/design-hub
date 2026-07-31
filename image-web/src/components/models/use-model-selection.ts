import { useEffect, useMemo } from 'react'
import type { UseQueryResult } from '@tanstack/react-query'

import type { ModelCatalogItem } from '@/api/models'
import type { ModelSelection } from '@/components/models/model-selection'
import { useCurrentUser } from '@/stores/auth-store'
import {
  type ModelKind,
  useModelSelectionStore,
} from '@/stores/model-selection-store'

export function useModelSelection(
  kind: ModelKind,
  query: UseQueryResult<ModelCatalogItem[], Error>,
): ModelSelection {
  const user = useCurrentUser()
  const storeUserId = useModelSelectionStore((store) => store.userId)
  const initialized = useModelSelectionStore((store) => store.initialized)
  const modelId = useModelSelectionStore(
    (store) => store.selections[kind].modelId,
  )
  const selectionRequired = useModelSelectionStore(
    (store) => store.selections[kind].selectionRequired,
  )
  const activateUser = useModelSelectionStore((store) => store.activateUser)
  const reconcile = useModelSelectionStore((store) => store.reconcile)
  const selectModel = useModelSelectionStore((store) => store.select)
  const activeForUser = initialized && storeUserId === user.user_id

  useEffect(() => {
    activateUser(user.user_id)
  }, [activateUser, user.user_id])

  useEffect(() => {
    if (activeForUser && query.data) reconcile(kind, query.data)
  }, [activeForUser, kind, query.data, reconcile])

  return useMemo(() => {
    const models = query.data ?? []
    let state: ModelSelection['state']
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
      select: (nextModelId: string) =>
        selectModel(kind, nextModelId, models),
      retry: () => {
        void query.refetch()
      },
    }
  }, [
    activeForUser,
    kind,
    modelId,
    query,
    selectModel,
    selectionRequired,
  ])
}
