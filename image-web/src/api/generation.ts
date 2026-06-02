import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import type { components } from '@/api/schema'

export type GenerateConfig = components['schemas']['ProjectGenerateRequest']
export type ProjectGenerateResponse = components['schemas']['ProjectGenerateResponse']
export type CostPreview = components['schemas']['CostPreviewResponse']
export type ProjectJob = components['schemas']['ProjectJobOut']

export const jobKeys = {
  list: (projectId: number) => ['projects', projectId, 'jobs'] as const,
}

export function useProjectJobs(projectId: number | undefined) {
  return useQuery({
    queryKey: projectId == null ? ['projects', 'nil', 'jobs'] : jobKeys.list(projectId),
    enabled: projectId != null,
    queryFn: async (): Promise<ProjectJob[]> => {
      const { data, error } = await api.GET('/projects/{project_id}/jobs', {
        params: { path: { project_id: projectId as number } },
      })
      if (error || !data) throw new Error(errorMessage(error, '获取任务失败'))
      return data
    },
  })
}

/** 成本预估（只读，不预扣）。flat /generate/cost-preview 需 customer；asset_ids 不参与计价. */
export function useCostPreview() {
  return useMutation({
    mutationFn: async (
      vars: GenerateConfig & { customer: string },
    ): Promise<CostPreview> => {
      const { data, error } = await api.POST('/generate/cost-preview', {
        body: {
          customer: vars.customer,
          subscene: vars.subscene,
          family: vars.family,
          category: vars.category,
          tier: vars.tier,
          style: vars.style,
          width: vars.width,
          height: vars.height,
          n: vars.n,
        },
      })
      if (error || !data) throw new Error(errorMessage(error, '成本预估失败'))
      return data
    },
  })
}

/** 项目下同步出图（返回候选图 + job_id）。*/
export function useProjectGenerate(projectId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (cfg: GenerateConfig): Promise<ProjectGenerateResponse> => {
      const { data, error } = await api.POST('/projects/{project_id}/generate', {
        params: { path: { project_id: projectId } },
        body: cfg,
      })
      if (error || !data) throw new Error(errorMessage(error, '出图失败'))
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: jobKeys.list(projectId) }),
  })
}
