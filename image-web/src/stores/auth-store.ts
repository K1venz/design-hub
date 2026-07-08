import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

import type { components } from '@/api/schema'
import { rememberAwareStorage } from '@/stores/auth-storage'

export type Role = components['schemas']['Role']
export type AuthUser = components['schemas']['MeResponse']

export const ROLE_DESIGNER: Role = '设计师'
export const ROLE_MANAGER: Role = '管理者'

/** 鉴权会话持久化键（persist name）。多标签登出同步监听 storage 事件复用此键。 */
export const AUTH_STORAGE_KEY = 'design-hub-auth'

/**
 * 角色**显示名**映射（DB 枚举值保持不变，仅前端展示）。
 * 世界 A 移除后实朴为纯 toC，普通用户不再叫「设计师」→ 展示为「用户」。
 */
export const ROLE_LABELS: Record<Role, string> = {
  设计师: '用户',
  管理者: '管理者',
}

/** 取角色的对外显示名（回退到原值以防未来新增枚举）。 */
export function roleLabel(role: Role): string {
  return ROLE_LABELS[role] ?? role
}

interface AuthState {
  /** JWT (Bearer). null = 未登录. */
  token: string | null
  /** 当前用户（GET /me 解析后写入）. */
  user: AuthUser | null
  setToken: (token: string) => void
  setUser: (user: AuthUser) => void
  clear: () => void
}

/**
 * 鉴权会话单一事实源。token 经「记住我」存储路由持久化（勾选→localStorage 重开仍在、
 * 不勾→sessionStorage 关浏览器即登出，见 auth-storage）；刷新后免重登；
 * user 由 ProtectedRoute / AuthHydrator 经 /me 重新拉取（不强依赖持久化副本）。
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setToken: (token) => set({ token }),
      setUser: (user) => set({ user }),
      clear: () => set({ token: null, user: null }),
    }),
    {
      name: AUTH_STORAGE_KEY,
      storage: createJSONStorage(() => rememberAwareStorage),
      partialize: (s) => ({ token: s.token }),
    },
  ),
)

/** 受保护区内读当前用户（由 ProtectedRoute 保证已就绪）. */
export function useCurrentUser(): AuthUser {
  const user = useAuthStore((s) => s.user)
  if (!user) throw new Error('useCurrentUser 必须在 ProtectedRoute 内使用')
  return user
}

export function isManager(role: Role): boolean {
  return role === ROLE_MANAGER
}
