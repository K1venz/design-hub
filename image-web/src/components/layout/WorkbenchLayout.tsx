import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { PlusIcon, LogOutIcon } from 'lucide-react'

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
import { WorkbenchRail } from '@/components/listing/WorkbenchRail'
import { newTaskBus } from '@/components/listing/new-task-bus'
import { navItemsFor } from '@/components/layout/nav'
import { useAuthStore, useCurrentUser } from '@/stores/auth-store'

/** Full-bleed workbench shell: top bar (logo + 新建任务 + avatar w/ management entries) + rail + content. */
export function WorkbenchLayout() {
  const user = useCurrentUser()
  const navigate = useNavigate()
  const clear = useAuthStore((s) => s.clear)
  const manageItems = navItemsFor(user.role).filter((i) => i.to !== '/')

  function logout() {
    clear()
    queryClient.clear()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex h-svh flex-col bg-[#f6f4f1] text-[#1c1b1a]">
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-[#ece8e2] bg-white px-5">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 font-bold">
            <span className="size-6 rounded-[7px] bg-gradient-to-br from-[#7c6cff] to-[#ff9a62]" />出图
          </div>
          <button
            onClick={() => newTaskBus.emit()}
            className="flex items-center gap-1.5 rounded-[10px] border border-[#ece8e2] bg-white px-3 py-1.5 text-[13.5px] text-[#4a443d]"
          >
            <PlusIcon className="size-4" /> 新建任务
          </button>
        </div>
        <div className="flex items-center gap-1.5">
          <nav className="flex items-center gap-0.5">
            {manageItems.map((i) => (
              <NavLink
                key={i.to}
                to={i.to}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-1.5 rounded-[10px] px-3 py-1.5 text-[13px] text-[#5b554e] transition-colors hover:bg-[#f4f0ff] hover:text-[#4733b8]',
                    isActive && 'bg-[#f4f0ff] font-medium text-[#4733b8]',
                  )
                }
              >
                <i.icon className="size-4" />
                {i.label}
              </NavLink>
            ))}
          </nav>
          <div className="mx-1.5 h-5 w-px bg-[#ece8e2]" />
          <DropdownMenu>
            <DropdownMenuTrigger className="rounded-full outline-none focus-visible:ring-2 focus-visible:ring-[#cdbfff]">
              <Avatar className="size-8">
                <AvatarFallback className="bg-[#f4f0ff] text-xs font-semibold text-[#4733b8]">
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
      <div className="flex min-h-0 flex-1">
        <WorkbenchRail />
        <Outlet />
      </div>
    </div>
  )
}
