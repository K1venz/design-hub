import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { LogOutIcon, MenuIcon, SparklesIcon } from 'lucide-react'

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
import { useAuthStore, roleLabel } from '@/stores/auth-store'

/**
 * 顶栏（玻璃 pill）：左=页面上下文 slot（如工作台「新建任务」）；
 * 右=「内测免费」徽标（纯氛围）+ 已登录头像菜单 / 未登录 登录·注册。
 * 主导航已移到左侧 SideNav；本栏对未登录态容忍（公开首页复用）。
 */
export function AppTopBar({ children, onMenu }: { children?: ReactNode; onMenu?: () => void }) {
  const user = useAuthStore((s) => s.user)
  const navigate = useNavigate()
  const clear = useAuthStore((s) => s.clear)

  function logout() {
    clear()
    queryClient.clear()
    navigate('/', { replace: true })
  }

  return (
    <header className="shrink-0 px-4 pb-1 pt-3">
      <div className="glass-panel flex h-12 items-center justify-between rounded-full pl-4 pr-2">
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          {onMenu && (
            <button
              type="button"
              onClick={onMenu}
              aria-label="打开菜单"
              className="-ml-1 shrink-0 rounded-full p-1.5 text-wb-ink-4 transition-colors hover:bg-white/70 hover:text-wb-ink-2 md:hidden"
            >
              <MenuIcon className="size-5" />
            </button>
          )}
          {children}
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1 rounded-full bg-wb-tint-1 px-2.5 py-1 text-[12px] font-medium text-wb-brand-deep">
            <SparklesIcon className="size-3.5" /> 内测免费
          </span>
          {user ? (
            <>
              <div className="mx-0.5 h-5 w-px bg-wb-line-1" />
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
                    {user.name} · {roleLabel(user.role)}
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem variant="destructive" onClick={logout}>
                    <LogOutIcon className="size-4" /> 退出登录
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          ) : (
            <>
              <Link
                to="/login"
                className="rounded-full px-3.5 py-1.5 text-[13px] font-medium text-wb-ink-4 transition-colors hover:bg-white/70 hover:text-wb-ink-2"
              >
                登录
              </Link>
              <Link
                to="/register"
                className="rounded-full bg-wb-ink-2 px-3.5 py-1.5 text-[13px] font-medium text-white transition-opacity hover:opacity-90"
              >
                注册
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
