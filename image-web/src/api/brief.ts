import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import type { components } from '@/api/schema'

export type Brief = components['schemas']['BriefOut']
export type BriefUpsert = components['schemas']['BriefUpsert']

export const briefKeys = {
  detail: (projectId: number) => ['brief', projectId] as const,
}

/** GET /projects/{id}/brief —— 无需求单(404) 返回 null（首次进入空表单）. */
export function useBrief(projectId: number | undefined) {
  return useQuery({
    queryKey: projectId == null ? ['brief', 'nil'] : briefKeys.detail(projectId),
    enabled: projectId != null,
    queryFn: async (): Promise<Brief | null> => {
      const { data, error, response } = await api.GET('/projects/{project_id}/brief', {
        params: { path: { project_id: projectId as number } },
      })
      if (response.status === 404) return null
      if (error || !data) throw new Error(errorMessage(error, '获取需求单失败'))
      return data
    },
  })
}

export function useUpsertBrief(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: BriefUpsert): Promise<Brief> => {
      const { data, error } = await api.PUT('/projects/{project_id}/brief', {
        params: { path: { project_id: projectId } },
        body,
      })
      if (error || !data) throw new Error(errorMessage(error, '保存需求单失败'))
      return data
    },
    onSuccess: (brief) => qc.setQueryData(briefKeys.detail(projectId), brief),
  })
}
