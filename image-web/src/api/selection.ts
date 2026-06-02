import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import type { components } from '@/api/schema'

export type JobImage = components['schemas']['ImageOut']
export type UsableRate = components['schemas']['UsableRateOut']

export const selectionKeys = {
  images: (jobId: string) => ['jobs', jobId, 'images'] as const,
  rate: (jobId: string) => ['jobs', jobId, 'usable-rate'] as const,
}

export function useJobImages(jobId: string | undefined) {
  return useQuery({
    queryKey: jobId ? selectionKeys.images(jobId) : ['jobs', 'nil', 'images'],
    enabled: !!jobId,
    queryFn: async (): Promise<JobImage[]> => {
      const { data, error } = await api.GET('/jobs/{job_id}/images', {
        params: { path: { job_id: jobId as string } },
      })
      if (error || !data) throw new Error(errorMessage(error, '获取候选图失败'))
      return data
    },
  })
}

export function useUsableRate(jobId: string | undefined) {
  return useQuery({
    queryKey: jobId ? selectionKeys.rate(jobId) : ['jobs', 'nil', 'usable-rate'],
    enabled: !!jobId,
    queryFn: async (): Promise<UsableRate> => {
      const { data, error } = await api.GET('/jobs/{job_id}/usable-rate', {
        params: { path: { job_id: jobId as string } },
      })
      if (error || !data) throw new Error(errorMessage(error, '获取可用率失败'))
      return data
    },
  })
}

function useImageMutation(jobId: string) {
  const qc = useQueryClient()
  return () => {
    qc.invalidateQueries({ queryKey: selectionKeys.images(jobId) })
    qc.invalidateQueries({ queryKey: selectionKeys.rate(jobId) })
  }
}

export function useScoreImage(jobId: string) {
  const invalidate = useImageMutation(jobId)
  return useMutation({
    mutationFn: async ({ imageId, score }: { imageId: number; score: number }) => {
      const { data, error } = await api.POST('/jobs/{job_id}/images/{image_id}/score', {
        params: { path: { job_id: jobId, image_id: imageId } },
        body: { score },
      })
      if (error || !data) throw new Error(errorMessage(error, '评分失败'))
      return data
    },
    onSuccess: invalidate,
  })
}

export function useKeepImage(jobId: string) {
  const invalidate = useImageMutation(jobId)
  return useMutation({
    mutationFn: async ({ imageId, kept }: { imageId: number; kept: boolean }) => {
      const { data, error } = await api.POST('/jobs/{job_id}/images/{image_id}/keep', {
        params: { path: { job_id: jobId, image_id: imageId } },
        body: { kept },
      })
      if (error || !data) throw new Error(errorMessage(error, '保留操作失败'))
      return data
    },
    onSuccess: invalidate,
  })
}
