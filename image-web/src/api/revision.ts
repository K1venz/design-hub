import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import type { components } from '@/api/schema'

export type Revision = components['schemas']['RevisionOut']
export type RevisionItem = components['schemas']['RevisionItemOut']

export const revisionKeys = {
  list: (projectId: number) => ['projects', projectId, 'revisions'] as const,
}

export function useRevisions(projectId: number | undefined) {
  return useQuery({
    queryKey: projectId == null ? ['projects', 'nil', 'revisions'] : revisionKeys.list(projectId),
    enabled: projectId != null,
    queryFn: async (): Promise<Revision[]> => {
      const { data, error } = await api.GET('/projects/{project_id}/revisions', {
        params: { path: { project_id: projectId as number } },
      })
      if (error || !data) throw new Error(errorMessage(error, '获取改稿单失败'))
      return data
    },
  })
}

export function useOpenRevision(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (): Promise<Revision> => {
      const { data, error } = await api.POST('/projects/{project_id}/revisions', {
        params: { path: { project_id: projectId } },
        body: {},
      })
      if (error || !data) throw new Error(errorMessage(error, '开改稿单失败'))
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: revisionKeys.list(projectId) }),
  })
}

export function useAddItem(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ revisionId, text }: { revisionId: number; text: string }) => {
      const { data, error } = await api.POST('/revisions/{revision_id}/items', {
        params: { path: { revision_id: revisionId } },
        body: { text },
      })
      if (error || !data) throw new Error(errorMessage(error, '添加条目失败'))
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: revisionKeys.list(projectId) }),
  })
}

export function useToggleItem(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      revisionId,
      seq,
      done,
    }: {
      revisionId: number
      seq: number
      done: boolean
    }) => {
      const { data, error } = await api.PUT('/revisions/{revision_id}/items/{seq}', {
        params: { path: { revision_id: revisionId, seq } },
        body: { done },
      })
      if (error || !data) throw new Error(errorMessage(error, '勾选失败'))
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: revisionKeys.list(projectId) }),
  })
}
