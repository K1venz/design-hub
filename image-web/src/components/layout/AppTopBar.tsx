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
    <header className="shrink-0 px-4 pb-1 pt-3">
      <div className="glass-panel flex h-12 items-center justify-between rounded-full pl-3 pr-2">
        <div className="flex items-center gap-3">
          <NavLink to="/" className="flex items-center gap-2 font-semibold tracking-[-0.01em] text-wb-ink-1">
            <span className="grid size-7 place-items-center rounded-[9px] bg-gradient-to-br from-wb-grad-from to-wb-grad-to text-[12px] font-bold text-white">
              朴
            </span>
            实朴
            <span className="hidden text-[11.5px] font-normal text-wb-ink-7 sm:inline">电商图片工作站</span>
          </NavLink>
          {children}
        </div>
        <div className="flex items-center gap-1.5">
          <nav className="flex items-center gap-1">
            {items.map((i) => (
              <NavLink
                key={i.to}
                to={i.to}
                end={i.end}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] text-wb-ink-5 transition-colors hover:bg-white/80 hover:text-wb-ink-2',
                    isActive && 'bg-wb-ink-2 font-medium text-white hover:bg-wb-ink-2 hover:text-white',
                  )
                }
              >
                <i.icon className="size-4" />
                {i.label}
              </NavLink>
            ))}
          </nav>
          <div className="mx-1 h-5 w-px bg-wb-line-1" />
          <DropdownMenu>
            <DropdownMenuTrigger className="rounded-full outline-none focus-visible:ring-2 focus-visible:ring-wb-brand-soft">
              <span className="block rounded-full bg-gradient-to-br from-wb-grad-from to-wb-grad-to p-[2px]">
                <Avatar className="size-7">
                  <AvatarFallback className="bg-white text-xs font-semibold text-wb-brand-deep">
                    {user.name.slice(-1)}
                  </AvatarFallback>
                </Avatar>
              </span>
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
      </div>
    </header>
  )
}
