import type { ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { LogOutIcon } from 'lucide-react'

import { cn } from '@/lib/utils'
import { queryClient } from '@/api/query-client'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { navItemsFor } from '@/components/layout/nav'
import { useAuthStore, useCurrentUser } from '@/stores/auth-store'

/**
 * Shared top navigation bar for the whole authenticated app.
 * Logo → home, role-filtered nav links (active highlight), avatar dropdown (logout).
 * `children` is an optional left-side slot (e.g. workbench's 新建任务 button).
 */
export function AppTopBar({ children }: { children?: ReactNode }) {
  const user = useCurrentUser()
  const navigate = useNavigate()
  const clear = useAuthStore((s) => s.clear)
  const items = navItemsFor(user.role)

  function logout() {
    clear()
    queryClient.clear()
    navigate('/login', { replace: true })
  }

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-wb-line-1 bg-white px-5">
      <div className="flex items-center gap-4">
        <NavLink to="/" className="flex items-center gap-2 font-bold text-wb-ink-1">
          <span className="size-6 rounded-[7px] bg-gradient-to-br from-wb-grad-from to-wb-grad-to" />出图
        </NavLink>
        {children}
      </div>
      <div className="flex items-center gap-1.5">
        <nav className="flex items-center gap-0.5">
          {items.map((i) => (
            <NavLink
              key={i.to}
              to={i.to}
              end={i.end}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-1.5 rounded-[10px] px-3 py-1.5 text-[13px] text-wb-ink-4 transition-colors hover:bg-wb-tint-1 hover:text-wb-brand-deep',
                  isActive && 'bg-wb-tint-1 font-medium text-wb-brand-deep',
                )
              }
            >
              <i.icon className="size-4" />
              {i.label}
            </NavLink>
          ))}
        </nav>
        <div className="mx-1.5 h-5 w-px bg-wb-line-1" />
        <DropdownMenu>
          <DropdownMenuTrigger className="rounded-full outline-none focus-visible:ring-2 focus-visible:ring-wb-brand-soft">
            <Avatar className="size-8">
              <AvatarFallback className="bg-wb-tint-1 text-xs font-semibold text-wb-brand-deep">
                {user.name.slice(-1)}
              </AvatarFallback>
            </Avatar>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            <DropdownMenuLabel>
              {user.name} · {user.role}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onClick={logout}>
              <LogOutIcon className="size-4" /> 退出登录
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
