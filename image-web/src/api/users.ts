import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/api/client'
import type { AppUserOut } from '@/api/contract-ext'
import { errorMessage } from '@/api/errors'
import type { Role } from '@/stores/auth-store'

export type AppUser = AppUserOut

export const userKeys = {
  all: ['admin', 'users'] as const,
}

export function useUsers() {
  return useQuery({
    queryKey: userKeys.all,
    queryFn: async (): Promise<AppUser[]> => {
      const { data, error } = await api.GET('/admin/users')
      if (error || !data) throw new Error(errorMessage(error, '获取用户列表失败'))
      return data
    },
  })
}

export function useSetRole() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ id, role }: { id: number; role: Role }): Promise<AppUser> => {
      const { data, error } = await api.PUT('/admin/users/{user_id}/role', {
        params: { path: { user_id: id } },
        body: { role },
      })
      if (error || !data) throw new Error(errorMessage(error, '更新角色失败'))
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: userKeys.all }),
  })
}
