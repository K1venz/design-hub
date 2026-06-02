import { useMutation, useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useAuthStore, type AuthUser } from '@/stores/auth-store'

export interface RegisterVars {
  email: string
  password: string
  name: string
}

export interface LoginVars {
  email: string
  password: string
}

/** POST /auth/register —— 自助注册（默认设计师）并写入会话. */
export function useRegister() {
  const setToken = useAuthStore((s) => s.setToken)
  return useMutation({
    mutationFn: async (vars: RegisterVars) => {
      const { data, error } = await api.POST('/auth/register', { body: vars })
      if (error || !data) throw new Error(errorMessage(error, '注册失败'))
      return data
    },
    onSuccess: (data) => setToken(data.jwt),
  })
}

/** POST /auth/login —— 邮箱密码登录并写入会话. */
export function useLogin() {
  const setToken = useAuthStore((s) => s.setToken)
  return useMutation({
    mutationFn: async (vars: LoginVars) => {
      const { data, error } = await api.POST('/auth/login', { body: vars })
      if (error || !data) throw new Error(errorMessage(error, '登录失败'))
      return data
    },
    onSuccess: (data) => setToken(data.jwt),
  })
}

/** GET /me —— 取当前用户（含角色）；token 就绪后启用. */
export function useMe(enabled: boolean) {
  return useQuery({
    queryKey: ['me'],
    enabled,
    queryFn: async (): Promise<AuthUser> => {
      const { data, error } = await api.GET('/me')
      if (error || !data) throw new Error(errorMessage(error, '获取用户信息失败'))
      return data
    },
  })
}
