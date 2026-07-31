import { useMutation, useQuery } from '@tanstack/react-query'

import { api } from '@/api/client'
import { encryptSecret } from '@/api/crypto'
import { errorMessage } from '@/api/errors'
import { useAuthStore, type AuthUser } from '@/stores/auth-store'

/** 登录/注册错误人话化（ISSUE-0058 §三.2）：429（nginx 限流·可能非 JSON body）+ 断网/超时。 */
const RATE_LIMIT_ERROR = '尝试太频繁，请稍等 1 分钟再试'
const NETWORK_ERROR = '网络异常，请检查连接后重试'

export interface RegisterVars {
  email: string
  password: string
  name: string
}

export interface LoginVars {
  email: string
  password: string
}

/** POST /auth/register —— 自助注册（默认设计师）并写入会话. 密码公钥加密后传输（§三.0）。 */
export function useRegister() {
  const setToken = useAuthStore((s) => s.setToken)
  return useMutation({
    mutationFn: async (vars: RegisterVars) => {
      const password = await encryptSecret(vars.password)
      const { data, error, response } = await api
        .POST('/auth/register', { body: { email: vars.email, name: vars.name, password } })
        .catch((): never => {
          throw new Error(NETWORK_ERROR)
        })
      if (response.status === 429) throw new Error(RATE_LIMIT_ERROR)
      if (error || !data) throw new Error(errorMessage(error, '注册失败'))
      return data
    },
    onSuccess: (data) => setToken(data.jwt),
  })
}

/** POST /auth/login —— 邮箱密码登录并写入会话. 密码公钥加密后传输（§三.0）。 */
export function useLogin() {
  const setToken = useAuthStore((s) => s.setToken)
  return useMutation({
    mutationFn: async (vars: LoginVars) => {
      const password = await encryptSecret(vars.password)
      const { data, error, response } = await api
        .POST('/auth/login', { body: { email: vars.email, password } })
        .catch((): never => {
          throw new Error(NETWORK_ERROR)
        })
      if (response.status === 429) throw new Error(RATE_LIMIT_ERROR)
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
