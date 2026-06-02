import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import type { components } from '@/api/schema'
import type { ProjectStatus } from '@/lib/project-status'

export type Project = components['schemas']['design_hub__interface__project_schemas__ProjectOut']
export type ProjectCreate = components['schemas']['ProjectCreate']

export const projectKeys = {
  all: ['projects'] as const,
  list: (customerId?: number) => ['projects', { customerId: customerId ?? null }] as const,
  detail: (id: number) => ['projects', 'detail', id] as const,
}

export function useProjects(customerId?: number) {
  return useQuery({
    queryKey: projectKeys.list(customerId),
    queryFn: async (): Promise<Project[]> => {
      const { data, error } = await api.GET('/projects', {
        params: { query: customerId != null ? { customer_id: customerId } : {} },
      })
      if (error || !data) throw new Error(errorMessage(error, '获取项目列表失败'))
      return data
    },
  })
}

export function useProject(id: number | undefined) {
  return useQuery({
    queryKey: id == null ? ['projects', 'detail', 'nil'] : projectKeys.detail(id),
    enabled: id != null,
    queryFn: async (): Promise<Project> => {
      const { data, error } = await api.GET('/projects/{project_id}', {
        params: { path: { project_id: id as number } },
      })
      if (error || !data) throw new Error(errorMessage(error, '获取项目失败'))
      return data
    },
  })
}

export function useCreateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: ProjectCreate): Promise<Project> => {
      const { data, error } = await api.POST('/projects', { body })
      if (error || !data) throw new Error(errorMessage(error, '创建项目失败'))
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: projectKeys.all }),
  })
}

export interface StatusTransition {
  projectId: number
  status: ProjectStatus
  /** 管理者强制（转「已交付」绕过未完成改稿校验）. */
  force?: boolean
}

export function useUpdateProjectStatus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ projectId, status, force }: StatusTransition): Promise<Project> => {
      const { data, error } = await api.PUT('/projects/{project_id}/status', {
        params: { path: { project_id: projectId }, query: force ? { force: true } : {} },
        body: { status },
      })
      if (error || !data) throw new Error(errorMessage(error, '状态流转失败'))
      return data
    },
    onSuccess: (proj) => {
      qc.invalidateQueries({ queryKey: projectKeys.all })
      qc.setQueryData(projectKeys.detail(proj.id), proj)
    },
  })
}
