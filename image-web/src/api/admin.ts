import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { modelKeys } from '@/api/models'
import type { components } from '@/api/schema'
import { normalizeAdminFilters } from '@/lib/admin'

export type AdminOverview = components['schemas']['AdminOverviewOut']
export type AdminUser = components['schemas']['AdminUserSummaryOut']
export type AdminUserPage = components['schemas']['PageOut_AdminUserSummaryOut_']
export type AdminJob = components['schemas']['AdminJobSummaryOut']
export type AdminJobPage = components['schemas']['PageOut_AdminJobSummaryOut_']
export type AdminJobDetail = components['schemas']['AdminJobDetailOut']
export type AdminImage = components['schemas']['AdminImageSummaryOut']
export type AdminImagePage = components['schemas']['PageOut_AdminImageSummaryOut_']
export type ImageModerationUpdate = components['schemas']['ImageModerationUpdate']
export type ImageShowcaseUpdate = components['schemas']['ImageShowcaseUpdate']
export type ImageShowcaseState = components['schemas']['ImageShowcaseStateOut']
export type ModelCallSummary = components['schemas']['ModelCallSummaryOut']
export type ModelCallSummaryList = components['schemas']['ModelCallSummaryListOut']
export type ModelCallDetail = components['schemas']['ModelCallDetailOut']
export type ModelCallPage = components['schemas']['PageOut_ModelCallDetailOut_']
export type AdminAuditEntry = components['schemas']['AdminAuditEntryOut']
export type AdminAuditPage = components['schemas']['PageOut_AdminAuditEntryOut_']
export type ModelConfig = components['schemas']['ModelConfigOut']
export type ModelConfigCreate = components['schemas']['ModelConfigCreate']
export type ModelConfigUpdate = components['schemas']['ModelConfigUpdate']
export type ModelCapabilityTestInput =
  components['schemas']['ModelCapabilityTestIn']
export type ModelCapabilityTestResult =
  components['schemas']['ModelCapabilityTestOut']
export type RuntimeLogListItem =
  components['schemas']['RuntimeLogListItemOut']
export type RuntimeLogDetail = components['schemas']['RuntimeLogDetailOut']
export type RuntimeLogPage = components['schemas']['RuntimeLogPageOut']

export interface DateFilters {
  start?: string
  end?: string
}

export interface PaginationFilters {
  limit?: number
  offset?: number
}

export interface AdminJobFilters extends DateFilters, PaginationFilters {
  user_id?: number
  status?: string
  model?: string
  operation_type?: string
}

export interface AdminImageFilters extends DateFilters, PaginationFilters {
  user_id?: number
  model?: string
  operation_type?: string
  status?: string
  moderation_status?: 'normal' | 'blocked'
  showcase_status?: 'public' | 'private'
}

export interface ModelCallFilters extends AdminJobFilters {
  provider?: string
  modality?: string
}

export interface AdminAuditFilters extends DateFilters, PaginationFilters {
  actor_user_id?: number
  action?: string
  target_type?: string
}

export interface RuntimeLogFilters extends DateFilters, PaginationFilters {
  level?: 'info' | 'warning' | 'error'
  service?: 'api' | 'worker'
  chain?: string
  trace_id?: string
  job_id?: string
}

const normalized = <T extends object>(filters: T) =>
  normalizeAdminFilters(filters)

export const adminKeys = {
  root: ['admin-console'] as const,
  overviewRoot: ['admin-console', 'overview'] as const,
  overview: (filters: DateFilters) =>
    ['admin-console', 'overview', normalized(filters)] as const,
  usersRoot: ['admin-console', 'users'] as const,
  jobsRoot: ['admin-console', 'jobs'] as const,
  jobs: (filters: AdminJobFilters) =>
    ['admin-console', 'jobs', normalized(filters)] as const,
  job: (jobId: string) => ['admin-console', 'job', jobId] as const,
  imagesRoot: ['admin-console', 'images'] as const,
  images: (filters: AdminImageFilters) =>
    ['admin-console', 'images', normalized(filters)] as const,
  usageRoot: ['admin-console', 'model-calls'] as const,
  usageSummary: (filters: ModelCallFilters) =>
    ['admin-console', 'model-calls', 'summary', normalized(filters)] as const,
  usageDetails: (filters: ModelCallFilters) =>
    ['admin-console', 'model-calls', 'details', normalized(filters)] as const,
  auditRoot: ['admin-console', 'audit'] as const,
  audit: (filters: AdminAuditFilters) =>
    ['admin-console', 'audit', normalized(filters)] as const,
  logsRoot: ['admin-console', 'runtime-logs'] as const,
  logs: (filters: RuntimeLogFilters) =>
    ['admin-console', 'runtime-logs', normalized(filters)] as const,
  log: (eventId: string) =>
    ['admin-console', 'runtime-log', eventId] as const,
  logTrace: (eventId: string) =>
    ['admin-console', 'runtime-log-trace', eventId] as const,
  modelsRoot: ['admin-console', 'models'] as const,
}

export function useAdminOverview(filters: DateFilters = {}) {
  const query = normalized(filters)
  return useQuery({
    queryKey: adminKeys.overview(query),
    queryFn: async (): Promise<AdminOverview> => {
      const { data, error } = await api.GET('/admin/overview', {
        params: { query },
      })
      if (error || !data) {
        throw new Error(errorMessage(error, '获取管理总览失败'))
      }
      return data
    },
  })
}

export function useAdminJobs(filters: AdminJobFilters = {}) {
  const query = normalized(filters)
  return useQuery({
    queryKey: adminKeys.jobs(query),
    queryFn: async (): Promise<AdminJobPage> => {
      const { data, error } = await api.GET('/admin/jobs', {
        params: { query },
      })
      if (error || !data) {
        throw new Error(errorMessage(error, '获取出图任务失败'))
      }
      return data
    },
  })
}

export function useAdminJob(jobId: string | undefined) {
  return useQuery({
    queryKey: adminKeys.job(jobId ?? ''),
    queryFn: async (): Promise<AdminJobDetail> => {
      if (!jobId) throw new Error('缺少任务 ID')
      const { data, error } = await api.GET('/admin/jobs/{job_id}', {
        params: { path: { job_id: jobId } },
      })
      if (error || !data) {
        throw new Error(errorMessage(error, '获取出图任务详情失败'))
      }
      return data
    },
    enabled: Boolean(jobId),
  })
}

export function useAdminImages(filters: AdminImageFilters = {}) {
  const query = normalized(filters)
  return useQuery({
    queryKey: adminKeys.images(query),
    queryFn: async (): Promise<AdminImagePage> => {
      const { data, error } = await api.GET('/admin/images', {
        params: { query },
      })
      if (error || !data) {
        throw new Error(errorMessage(error, '获取生成图片失败'))
      }
      return data
    },
  })
}

export function useModerateAdminImage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      imageId,
      body,
    }: {
      imageId: number
      body: ImageModerationUpdate
    }) => {
      const { data, error } = await api.PUT(
        '/admin/images/{image_id}/moderation',
        {
          params: { path: { image_id: imageId } },
          body,
        },
      )
      if (error || !data) {
        throw new Error(errorMessage(error, '更新图片审核状态失败'))
      }
      return data
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminKeys.imagesRoot }),
        queryClient.invalidateQueries({ queryKey: adminKeys.jobsRoot }),
        queryClient.invalidateQueries({ queryKey: adminKeys.overviewRoot }),
        queryClient.invalidateQueries({ queryKey: adminKeys.auditRoot }),
        queryClient.invalidateQueries({ queryKey: ['listing'] }),
      ])
    },
  })
}

export function useUpdateAdminImageShowcase() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      imageId,
      body,
    }: {
      imageId: number
      body: ImageShowcaseUpdate
    }): Promise<ImageShowcaseState> => {
      const { data, error } = await api.PUT(
        '/admin/images/{image_id}/showcase',
        {
          params: { path: { image_id: imageId } },
          body,
        },
      )
      if (error || !data) {
        throw new Error(errorMessage(error, '更新公开展示设置失败'))
      }
      return data
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminKeys.imagesRoot }),
        queryClient.invalidateQueries({ queryKey: adminKeys.jobsRoot }),
        queryClient.invalidateQueries({ queryKey: adminKeys.auditRoot }),
        queryClient.invalidateQueries({ queryKey: ['showcase'] }),
      ])
    },
  })
}

export function useModelCallSummary(filters: ModelCallFilters = {}) {
  const query = normalized(filters)
  return useQuery({
    queryKey: adminKeys.usageSummary(query),
    queryFn: async (): Promise<ModelCallSummaryList> => {
      const { data, error } = await api.GET('/admin/model-calls/summary', {
        params: { query },
      })
      if (error || !data) {
        throw new Error(errorMessage(error, '获取 API 用量汇总失败'))
      }
      return data
    },
  })
}

export function useAdminModelCalls(filters: ModelCallFilters = {}) {
  const query = normalized(filters)
  return useQuery({
    queryKey: adminKeys.usageDetails(query),
    queryFn: async (): Promise<ModelCallPage> => {
      const { data, error } = await api.GET('/admin/model-calls', {
        params: { query },
      })
      if (error || !data) {
        throw new Error(errorMessage(error, '获取 API 调用明细失败'))
      }
      return data
    },
  })
}

export function useAdminAuditLogs(filters: AdminAuditFilters = {}) {
  const query = normalized(filters)
  return useQuery({
    queryKey: adminKeys.audit(query),
    queryFn: async (): Promise<AdminAuditPage> => {
      const { data, error } = await api.GET('/admin/audit-logs', {
        params: { query },
      })
      if (error || !data) {
        throw new Error(errorMessage(error, '获取操作记录失败'))
      }
      return data
    },
  })
}

export function useRuntimeLogs(filters: RuntimeLogFilters = {}) {
  const query = normalized(filters)
  return useQuery({
    queryKey: adminKeys.logs(query),
    queryFn: async (): Promise<RuntimeLogPage> => {
      const { data, error } = await api.GET('/admin/runtime-logs', {
        params: { query },
      })
      if (error || !data) {
        throw new Error(errorMessage(error, '获取运行日志失败'))
      }
      return data
    },
  })
}

export function useRuntimeLogDetail(eventId: string | undefined) {
  return useQuery({
    queryKey: adminKeys.log(eventId ?? ''),
    queryFn: async (): Promise<RuntimeLogDetail> => {
      if (!eventId) throw new Error('缺少日志事件 ID')
      const { data, error } = await api.GET(
        '/admin/runtime-logs/{event_id}',
        { params: { path: { event_id: eventId } } },
      )
      if (error || !data) {
        throw new Error(errorMessage(error, '获取运行日志详情失败'))
      }
      return data
    },
    enabled: Boolean(eventId),
  })
}

export function useRuntimeLogTrace(eventId: string | undefined) {
  return useQuery({
    queryKey: adminKeys.logTrace(eventId ?? ''),
    queryFn: async (): Promise<RuntimeLogDetail[]> => {
      if (!eventId) throw new Error('缺少日志事件 ID')
      const { data, error } = await api.GET(
        '/admin/runtime-logs/{event_id}/trace',
        { params: { path: { event_id: eventId } } },
      )
      if (error || !data) {
        throw new Error(errorMessage(error, '获取日志链路失败'))
      }
      return data
    },
    enabled: Boolean(eventId),
  })
}

export function useModels() {
  return useQuery({
    queryKey: adminKeys.modelsRoot,
    queryFn: async (): Promise<ModelConfig[]> => {
      const { data, error } = await api.GET('/admin/models')
      if (error || !data) {
        throw new Error(errorMessage(error, '获取模型列表失败'))
      }
      return data
    },
  })
}

async function invalidateModelQueries(
  queryClient: ReturnType<typeof useQueryClient>,
) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: adminKeys.modelsRoot }),
    queryClient.invalidateQueries({ queryKey: modelKeys.all }),
    queryClient.invalidateQueries({ queryKey: adminKeys.auditRoot }),
  ])
}

export function useCreateModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: ModelConfigCreate): Promise<ModelConfig> => {
      const { data, error } = await api.POST('/admin/models', { body })
      if (error || !data) {
        throw new Error(errorMessage(error, '新增模型失败'))
      }
      return data
    },
    onSuccess: () => invalidateModelQueries(queryClient),
  })
}

export function useTestModel() {
  return useMutation({
    mutationFn: async (
      body: ModelCapabilityTestInput,
    ): Promise<ModelCapabilityTestResult> => {
      const { data, error } = await api.POST('/admin/models/test', { body })
      if (error || !data) {
        throw new Error('配置测试失败，请检查连接字段与凭据')
      }
      return data
    },
  })
}

export function useSetDefaultModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (name: string): Promise<ModelConfig> => {
      const { data, error } = await api.PUT('/admin/models/{name}/default', {
        params: { path: { name } },
      })
      if (error || !data) {
        throw new Error(errorMessage(error, '设为默认渠道失败'))
      }
      return data
    },
    onSuccess: () => invalidateModelQueries(queryClient),
  })
}

export function useDeleteModel() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (name: string): Promise<void> => {
      const { error } = await api.DELETE('/admin/models/{name}', {
        params: { path: { name } },
      })
      if (error) throw new Error(errorMessage(error, '删除模型失败'))
    },
    onSuccess: () => invalidateModelQueries(queryClient),
  })
}

export function useUpdateModel() {
  const queryClient = useQueryClient()
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
      if (error || !data) {
        throw new Error(errorMessage(error, '更新模型失败'))
      }
      return data
    },
    onSuccess: () => invalidateModelQueries(queryClient),
  })
}
