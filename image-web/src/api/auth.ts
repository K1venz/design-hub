import { useMutation, useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { useAuthStore, type AuthUser } from '@/stores/auth-store'

export interface LoginVars {
  /** OAuth 提供方：feishu | dingtalk（mock 后端暂不分流）. */
  provider: string
  /** OAuth 授权 code（mock：前缀决定角色，见后端 MockOAuthClient）. */
  code: string
}

/** POST /auth/{provider}/callback —— 换 JWT 并写入会话. */
export function useLogin() {
  const setToken = useAuthStore((s) => s.setToken)
  return useMutation({
    mutationFn: async ({ provider, code }: LoginVars) => {
      const { data, error } = await api.POST('/auth/{provider}/callback', {
        params: { path: { provider } },
        body: { code },
      })
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
