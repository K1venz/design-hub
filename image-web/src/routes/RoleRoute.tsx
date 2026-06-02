import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'

import { useCurrentUser, type Role } from '@/stores/auth-store'

/** 角色闸门：当前用户角色不在 allow 列表 → 跳 403. */
export function RoleRoute({
  allow,
  children,
}: {
  allow: Role[]
  children: ReactNode
}) {
  const user = useCurrentUser()
  if (!allow.includes(user.role)) return <Navigate to="/403" replace />
  return <>{children}</>
}
