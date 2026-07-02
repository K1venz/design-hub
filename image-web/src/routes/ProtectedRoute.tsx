import { useEffect } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { useMe } from '@/api/auth'
import { FullPageLoader } from '@/components/feedback/FullPageLoader'
import { useAuthStore } from '@/stores/auth-store'

/**
 * 鉴权闸门：
 * - 无 token → 跳登录。
 * - 有 token 无 user → 拉 /me 引导，loading 显占位；只在 user 真正写入 store 后才渲染子路由
 *   （不能以 query.data 到达为准——setUser 在 effect 提交后才生效，否则会短暂 fallthrough 到
 *   Outlet 而 store.user 仍为空，子组件 useCurrentUser 抛错）。
 * - /me 失败（401 已被中间件清会话）→ 清会话回登录，避免 token 在而 user 取不到的死循环。
 */
export function ProtectedRoute() {
  const token = useAuthStore((s) => s.token)
  const user = useAuthStore((s) => s.user)
  const setUser = useAuthStore((s) => s.setUser)
  const clear = useAuthStore((s) => s.clear)
  const location = useLocation()

  const { data, isError } = useMe(Boolean(token) && !user)

  useEffect(() => {
    if (data) setUser(data)
  }, [data, setUser])

  useEffect(() => {
    if (isError) clear()
  }, [isError, clear])

  // 登录墙：带上当前意图（含 query，如 /chat?q=…）→ 登录后回跳原处
  if (!token) return <Navigate to="/login" state={{ from: location }} replace />
  if (!user) return <FullPageLoader label="正在载入…" />
  return <Outlet />
}
