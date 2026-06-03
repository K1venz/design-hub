import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { LogOutIcon } from 'lucide-react'

import { queryClient } from '@/api/query-client'
import { Wordmark } from '@/components/brand/Wordmark'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { navItemsFor } from '@/components/layout/nav'
import { DotPattern } from '@/components/visual/DotPattern'
import { cn } from '@/lib/utils'
import { useAuthStore, useCurrentUser } from '@/stores/auth-store'

function initials(name: string): string {
  const trimmed = name.trim()
  if (!trimmed) return '–'
  // 中文取末字，拉丁取首字母
  return /[一-龥]/.test(trimmed) ? trimmed.slice(-1) : trimmed.slice(0, 1).toUpperCase()
}

function Sidebar() {
  const user = useCurrentUser()
  const items = navItemsFor(user.role)
  return (
    <aside className="bg-sidebar border-sidebar-border hidden w-60 shrink-0 flex-col border-r md:flex">
      <div className="flex h-16 items-center px-5">
        <Wordmark />
      </div>
      <nav className="flex flex-1 flex-col gap-0.5 px-3 py-2">
        <p className="text-muted-foreground/70 px-3 pt-2 pb-1.5 text-[11px] font-medium tracking-wider uppercase">
          导航
        </p>
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                'group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                  : 'text-sidebar-foreground/72 hover:bg-sidebar-accent/55 hover:text-sidebar-foreground',
              )
            }
          >
            {({ isActive }) => (
              <>
                <item.icon
                  className={cn(
                    'size-4.5 shrink-0 transition-colors',
                    isActive ? 'text-primary' : 'text-muted-foreground group-hover:text-foreground',
                  )}
                />
                {item.label}
              </>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="text-muted-foreground/70 border-sidebar-border border-t px-5 py-3.5 text-[11px]">
        <span className="font-mono">design_hub</span> · 图生图引擎
      </div>
    </aside>
  )
}

function TopBar() {
  const user = useCurrentUser()
  const navigate = useNavigate()
  const clear = useAuthStore((s) => s.clear)
  const { pathname } = useLocation()
  const current = navItemsFor(user.role).find((i) =>
    i.end ? pathname === i.to : pathname.startsWith(i.to),
  )

  function logout() {
    clear()
    queryClient.clear()
    navigate('/login', { replace: true })
  }

  return (
    <header className="bg-background/85 border-border sticky top-0 z-10 flex h-16 items-center justify-between border-b px-6 backdrop-blur">
      <div className="flex items-center gap-3">
        <h1 className="text-[15px] font-semibold text-foreground">{current?.label ?? '工作台'}</h1>
      </div>
      <DropdownMenu>
        <DropdownMenuTrigger className="hover:bg-accent/60 flex items-center gap-2.5 rounded-full py-1 pr-2 pl-1 transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring/50">
          <Avatar className="size-8">
            <AvatarFallback className="bg-primary/12 text-primary text-xs font-semibold">
              {initials(user.name)}
            </AvatarFallback>
          </Avatar>
          <div className="hidden flex-col items-start leading-none sm:flex">
            <span className="text-[13px] font-medium text-foreground">{user.name}</span>
            <span className="text-[11px] text-muted-foreground">{user.role}</span>
          </div>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel className="flex flex-col gap-1">
            <span className="text-sm font-medium">{user.name}</span>
            <span className="flex items-center gap-1.5 text-xs font-normal text-muted-foreground">
              <Badge variant="secondary" className="h-5 px-1.5 text-[10px] font-medium">
                {user.role}
              </Badge>
              {user.dept && <span>{user.dept}</span>}
            </span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem variant="destructive" onClick={logout}>
            <LogOutIcon className="size-4" />
            退出登录
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  )
}

export function AppLayout() {
  return (
    <div className="flex min-h-svh bg-background">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="relative flex-1 px-6 py-7">
          <DotPattern className="[mask-image:radial-gradient(ellipse_at_top,white,transparent_72%)]" />
          <div className="relative mx-auto w-full max-w-6xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
