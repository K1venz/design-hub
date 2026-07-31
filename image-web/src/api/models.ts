import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import type { components } from '@/api/schema'

export type ImageModelCatalogItem =
  components['schemas']['ImageModelCatalogItemOut']

export const imageModelKeys = {
  image: ['models', 'image'] as const,
}

export function useImageModels() {
  return useQuery({
    queryKey: imageModelKeys.image,
    queryFn: async (): Promise<ImageModelCatalogItem[]> => {
      const { data, error } = await api.GET('/models/image')
      if (error || !data) {
        throw new Error(errorMessage(error, '获取可用图片模型失败'))
      }
      return data
    },
    retry: false,
  })
}
