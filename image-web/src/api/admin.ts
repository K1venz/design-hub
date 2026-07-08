import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import type { components } from '@/api/schema'

export type ModelConfig = components['schemas']['ModelConfigOut']
export type ModelConfigCreate = components['schemas']['ModelConfigCreate']
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

export function useCreateModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: ModelConfigCreate): Promise<ModelConfig> => {
      const { data, error } = await api.POST('/admin/models', { body })
      if (error || !data) throw new Error(errorMessage(error, '新增模型失败'))
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: modelKeys.all }),
  })
}

/** 设为默认渠道（PUT …/default）：事务保证恰一默认，即「备用渠道切换」，重启生效。 */
export function useSetDefaultModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (name: string): Promise<ModelConfig> => {
      const { data, error } = await api.PUT('/admin/models/{name}/default', {
        params: { path: { name } },
      })
      if (error || !data) throw new Error(errorMessage(error, '设为默认渠道失败'))
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: modelKeys.all }),
  })
}

export function useDeleteModel() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (name: string): Promise<void> => {
      const { error } = await api.DELETE('/admin/models/{name}', {
        params: { path: { name } },
      })
      if (error) throw new Error(errorMessage(error, '删除模型失败'))
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: modelKeys.all }),
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
