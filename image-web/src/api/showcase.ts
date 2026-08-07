import { useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import type { components } from '@/api/schema'

/** GET /showcase 列表项：现签 url（TTL 1h）+ 图型 + 首页说明（公开、无用户数据）。 */
export type ShowcaseItem = components['schemas']['ShowcaseItemOut']
export type ShowcaseDownload = components['schemas']['ShowcaseDownloadOut']

/**
 * 首页成果展示案例（公开只读）。`enabled` 由视口懒加载控制——进入视口才发请求。
 * url 是 TTL 1h 现签 TOS url：staleTime 控短 + 窗口聚焦重取，避免久留页面用到过期 url。
 */
export function useShowcase(enabled: boolean) {
  return useQuery({
    queryKey: ['showcase'],
    enabled,
    staleTime: 10 * 60_000,
    queryFn: async (): Promise<ShowcaseItem[]> => {
      const { data, error } = await api.GET('/showcase')
      if (error || !data) throw new Error(errorMessage(error, '获取展示案例失败'))
      return data
    },
  })
}

export async function getShowcaseDownloadUrl(
  imageId: number,
): Promise<string> {
  const { data, error } = await api.GET('/showcase/{image_id}/download', {
    params: { path: { image_id: imageId } },
  })
  if (error || !data) {
    throw new Error(errorMessage(error, '获取原图下载地址失败'))
  }
  return data.url
}
