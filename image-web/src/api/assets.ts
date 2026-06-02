import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import type { components } from '@/api/schema'

export type Asset = components['schemas']['AssetOut']
export type AssetKind = components['schemas']['AssetKind']

type UploadBody = components['schemas']['Body_upload_asset_projects__project_id__assets_post']

export const assetKeys = {
  list: (projectId: number) => ['assets', projectId] as const,
}

export function useAssets(projectId: number | undefined) {
  return useQuery({
    queryKey: projectId == null ? ['assets', 'nil'] : assetKeys.list(projectId),
    enabled: projectId != null,
    queryFn: async (): Promise<Asset[]> => {
      const { data, error } = await api.GET('/projects/{project_id}/assets', {
        params: { path: { project_id: projectId as number } },
      })
      if (error || !data) throw new Error(errorMessage(error, '获取素材失败'))
      return data
    },
  })
}

export function useUploadAsset(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ file, kind }: { file: File; kind: AssetKind }): Promise<Asset> => {
      const { data, error } = await api.POST('/projects/{project_id}/assets', {
        params: { path: { project_id: projectId } },
        // multipart：schema 把 file 标为 string(binary)，运行时传 File，经 bodySerializer 组 FormData
        body: { file, kind } as unknown as UploadBody,
        bodySerializer(body: UploadBody) {
          const fd = new FormData()
          fd.set('file', body.file as unknown as Blob)
          fd.set('kind', body.kind)
          return fd
        },
      })
      if (error || !data) throw new Error(errorMessage(error, '上传素材失败'))
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: assetKeys.list(projectId) }),
  })
}
