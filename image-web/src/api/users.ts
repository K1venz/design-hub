import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { adminKeys } from '@/api/admin'
import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import type { components } from '@/api/schema'
import { normalizeAdminFilters } from '@/lib/admin'
import type { Role } from '@/stores/auth-store'

export type AdminUser = components['schemas']['AdminUserSummaryOut']
export type AdminUserDetail = components['schemas']['AdminUserDetailOut']
export type AdminUserPage = components['schemas']['PageOut_AdminUserSummaryOut_']
export type UserMutationResult = components['schemas']['UserOut']

export interface AdminUserFilters {
  q?: string
  role?: Role
  enabled?: boolean
  limit?: number
  offset?: number
}

export const userKeys = {
  root: adminKeys.usersRoot,
  list: (filters: AdminUserFilters) =>
    ['admin-console', 'users', normalizeAdminFilters(filters)] as const,
  detail: (userId: number) =>
    ['admin-console', 'user', userId] as const,
}

export function useUsers(filters: AdminUserFilters = {}) {
  const query = normalizeAdminFilters(filters)
  return useQuery({
    queryKey: userKeys.list(query),
    queryFn: async (): Promise<AdminUserPage> => {
      const { data, error } = await api.GET('/admin/users', {
        params: { query },
      })
      if (error || !data) {
        throw new Error(errorMessage(error, '获取用户列表失败'))
      }
      return data
    },
  })
}

export function useAdminUser(userId: number | undefined) {
  return useQuery({
    queryKey: userKeys.detail(userId ?? 0),
    queryFn: async (): Promise<AdminUserDetail> => {
      if (!userId) throw new Error('缺少用户 ID')
      const { data, error } = await api.GET('/admin/users/{user_id}', {
        params: { path: { user_id: userId } },
      })
      if (error || !data) {
        throw new Error(errorMessage(error, '获取用户详情失败'))
      }
      return data
    },
    enabled: Boolean(userId),
  })
}

async function invalidateUserQueries(
  queryClient: ReturnType<typeof useQueryClient>,
) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: userKeys.root }),
    queryClient.invalidateQueries({ queryKey: adminKeys.auditRoot }),
  ])
}

export function useSetRole() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      id,
      role,
    }: {
      id: number
      role: Role
    }): Promise<UserMutationResult> => {
      const { data, error } = await api.PUT(
        '/admin/users/{user_id}/role',
        {
          params: { path: { user_id: id } },
          body: { role },
        },
      )
      if (error || !data) {
        throw new Error(errorMessage(error, '更新角色失败'))
      }
      return data
    },
    onSuccess: () => invalidateUserQueries(queryClient),
  })
}

export function useSetUserStatus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      id,
      enabled,
      reason,
    }: {
      id: number
      enabled: boolean
      reason: string
    }): Promise<UserMutationResult> => {
      const { data, error } = await api.PUT(
        '/admin/users/{user_id}/status',
        {
          params: { path: { user_id: id } },
          body: { enabled, reason },
        },
      )
      if (error || !data) {
        throw new Error(errorMessage(error, '更新用户状态失败'))
      }
      return data
    },
    onSuccess: () => invalidateUserQueries(queryClient),
  })
}
