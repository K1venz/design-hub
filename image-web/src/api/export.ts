import { useMutation, useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import type { components } from '@/api/schema'

export type ProjectImage = components['schemas']['ProjectImageOut']
export type ExportFormat = components['schemas']['ExportFormat']
export type ExportResponse = components['schemas']['ExportResponse']

export interface ExportVars {
  image_ids: number[]
  formats: ExportFormat[]
  resize?: { w: number; h: number } | null
  zip: boolean
}

export function useProjectImages(projectId: number | undefined) {
  return useQuery({
    queryKey: projectId == null ? ['projects', 'nil', 'images'] : ['projects', projectId, 'images'],
    enabled: projectId != null,
    queryFn: async (): Promise<ProjectImage[]> => {
      const { data, error } = await api.GET('/projects/{project_id}/images', {
        params: { path: { project_id: projectId as number } },
      })
      if (error || !data) throw new Error(errorMessage(error, '获取项目图片失败'))
      return data
    },
  })
}

export function useExport(projectId: number) {
  return useMutation({
    mutationFn: async (vars: ExportVars): Promise<ExportResponse> => {
      const { data, error } = await api.POST('/projects/{project_id}/export', {
        params: { path: { project_id: projectId } },
        body: vars,
      })
      if (error || !data) throw new Error(errorMessage(error, '导出失败'))
      return data
    },
  })
}
