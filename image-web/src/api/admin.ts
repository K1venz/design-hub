import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import type { components } from '@/api/schema'

export type ModelConfig = components['schemas']['ModelConfigOut']
export type ModelConfigUpdate = components['schemas']['ModelConfigUpdate']

export const modelKeys = {
  all: ['admin', 'models'] as const,
}

export function useModels() {
  return useQuery({
    queryKey: modelKeys.all,
    queryFn: async (): Promise<ModelConfig[]> => {
      const { data, error } = await api.GET('/admin/models')
      if (error || !data) throw new Error(errorMessage(error, '获取模型列表失败'))
      return data
    },
  })
}

export function useUpdateModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      name,
      patch,
    }: {
      name: string
      patch: ModelConfigUpdate
    }): Promise<ModelConfig> => {
      const { data, error } = await api.PUT('/admin/models/{name}', {
        params: { path: { name } },
        body: patch,
      })
      if (error || !data) throw new Error(errorMessage(error, '更新模型失败'))
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: modelKeys.all }),
  })
}
