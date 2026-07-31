import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import type { components } from '@/api/schema'

export type ModelCatalogItem = components['schemas']['ModelCatalogItemOut']

export const modelKeys = {
  all: ['models'] as const,
  chat: ['models', 'chat'] as const,
  image: ['models', 'image'] as const,
}

export function useImageModels() {
  return useQuery({
    queryKey: modelKeys.image,
    queryFn: async (): Promise<ModelCatalogItem[]> => {
      const { data, error } = await api.GET('/models/image')
      if (error || !data) {
        throw new Error(errorMessage(error, '获取可用图片模型失败'))
      }
      return data
    },
    retry: false,
  })
}

export function useChatModels() {
  return useQuery({
    queryKey: modelKeys.chat,
    queryFn: async (): Promise<ModelCatalogItem[]> => {
      const { data, error } = await api.GET('/models/chat')
      if (error || !data) {
        throw new Error(errorMessage(error, '获取可用文本模型失败'))
      }
      return data
    },
    retry: false,
  })
}
