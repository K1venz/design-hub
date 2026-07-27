import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { Dialog as DialogPrimitive } from 'radix-ui'
import {
  LogInIcon,
  LogOutIcon,
  MenuIcon,
  UserPlusIcon,
  UserRoundIcon,
  XIcon,
} from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'

import { queryClient } from '@/api/query-client'
import brandMarkUrl from '@/assets/brand/shipu-mark.png'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  PRIMARY_NAV_ITEMS,
  getAccountNavItems,
  type NavigationItem,
} from '@/components/layout/navigation'
import { cn } from '@/lib/utils'
import { roleLabel, useAuthStore } from '@/stores/auth-store'

function DesktopNavItem({ item }: { item: NavigationItem }) {
  return (
    <NavLink
      to={item.to}
      end={item.end}
      aria-label={item.label}
      className={({ isActive }) =>
        cn(
          'group/nav inline-flex h-9 items-center justify-center overflow-hidden rounded-full px-2.5 text-wb-ink-5 outline-none transition-[color,background-color,box-shadow] duration-200 hover:bg-white/75 hover:text-wb-ink-2 focus-visible:ring-2 focus-visible:ring-wb-brand-soft',
          isActive &&
            'bg-wb-brand font-semibold text-white shadow-[0_7px_18px_-10px_rgba(91,91,214,.85)] hover:bg-wb-brand hover:text-white',
        )
      }
    >
      <item.icon className="size-[18px] shrink-0" />
      <span className="max-w-0 overflow-hidden whitespace-nowrap text-[13px] opacity-0 transition-[max-width,opacity,margin] duration-200 group-hover/nav:ml-1.5 group-hover/nav:max-w-24 group-hover/nav:opacity-100 group-focus-visible/nav:ml-1.5 group-focus-visible/nav:max-w-24 group-focus-visible/nav:opacity-100">
        {item.label}
      </span>
    </NavLink>
  )
}

function MobileNavigation() {
  const [open, setOpen] = useState(false)

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Trigger asChild>
        <button
          type="button"
          aria-label="打开导航菜单"
          className="grid size-9 place-items-center rounded-full text-wb-ink-4 outline-none transition-colors hover:bg-white/75 hover:text-wb-ink-2 focus-visible:ring-2 focus-visible:ring-wb-brand-soft md:hidden"
        >
          <MenuIcon className="size-5" />
        </button>
      </DialogPrimitive.Trigger>
      <AnimatePresence>
        {open && (
          <DialogPrimitive.Portal forceMount>
            <DialogPrimitive.Overlay asChild forceMount>
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18 }}
                className="fixed inset-0 z-50 bg-black/25 backdrop-blur-sm md:hidden"
              />
            </DialogPrimitive.Overlay>
            <DialogPrimitive.Content asChild forceMount aria-describedby={undefined}>
              <motion.nav
                initial={{ opacity: 0, y: -16, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -12, scale: 0.98 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                className="glass-panel fixed left-3 right-3 top-3 z-50 rounded-[22px] p-3 md:hidden"
              >
                <div className="mb-2 flex items-center justify-between px-1">
                  <DialogPrimitive.Title className="text-sm font-semibold text-wb-ink-2">
                    导航菜单
                  </DialogPrimitive.Title>
                  <DialogPrimitive.Close asChild>
                    <button
                      type="button"
                      aria-label="关闭导航菜单"
                      className="grid size-8 place-items-center rounded-full text-wb-ink-4 transition-colors hover:bg-white/70 hover:text-wb-ink-2"
                    >
                      <XIcon className="size-4" />
                    </button>
                  </DialogPrimitive.Close>
                </div>
                <div className="grid gap-1">
                  {PRIMARY_NAV_ITEMS.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.end}
                      onClick={() => setOpen(false)}
                      className={({ isActive }) =>
                        cn(
                          'flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-wb-ink-4 transition-colors hover:bg-white/75 hover:text-wb-ink-2',
                          isActive && 'bg-wb-brand text-white hover:bg-wb-brand hover:text-white',
                        )
                      }
                    >
                      <item.icon className="size-[18px]" />
                      {item.label}
                    </NavLink>
                  ))}
                </div>
              </motion.nav>
            </DialogPrimitive.Content>
          </DialogPrimitive.Portal>
        )}
      </AnimatePresence>
    </DialogPrimitive.Root>
  )
}

function ProfileMenu() {
  const user = useAuthStore((state) => state.user)
  const clear = useAuthStore((state) => state.clear)
  const navigate = useNavigate()
  const managementItems = user ? getAccountNavItems(user.role) : []

  function logout() {
    clear()
    queryClient.clear()
    navigate('/', { replace: true })
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="个人中心"
          className="group/profile inline-flex h-9 items-center justify-center justify-self-end overflow-hidden rounded-full px-2.5 text-wb-ink-5 outline-none transition-[color,background-color] duration-200 hover:bg-white/75 hover:text-wb-ink-2 focus-visible:ring-2 focus-visible:ring-wb-brand-soft"
        >
          <UserRoundIcon className="size-[18px] shrink-0" />
          <span className="max-w-0 overflow-hidden whitespace-nowrap text-[13px] opacity-0 transition-[max-width,opacity,margin] duration-200 group-hover/profile:ml-1.5 group-hover/profile:max-w-20 group-hover/profile:opacity-100 group-focus-visible/profile:ml-1.5 group-focus-visible/profile:max-w-20 group-focus-visible/profile:opacity-100">
            个人中心
          </span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        {user ? (
          <>
            <DropdownMenuLabel>
              {user.name} · {roleLabel(user.role)}
            </DropdownMenuLabel>
            {managementItems.length > 0 && (
              <>
                <DropdownMenuSeparator />
                {managementItems.map((item) => (
                  <DropdownMenuItem key={item.to} asChild>
                    <Link to={item.to}>
                      <item.icon className="size-4" />
                      {item.label}
                    </Link>
                  </DropdownMenuItem>
                ))}
              </>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onClick={logout}>
              <LogOutIcon className="size-4" />
              退出登录
            </DropdownMenuItem>
          </>
        ) : (
          <>
            <DropdownMenuItem asChild>
              <Link to="/login">
                <LogInIcon className="size-4" />
                登录
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link to="/register">
                <UserPlusIcon className="size-4" />
                注册
              </Link>
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function AppTopBar() {
  return (
    <header className="shrink-0 px-3 pb-2 pt-3">
      <div className="glass-panel mx-auto grid h-14 w-full max-w-[840px] grid-cols-[1fr_auto_1fr] items-center rounded-[22px] px-3 shadow-[0_16px_42px_-28px_rgba(31,41,55,.42)] sm:px-4">
        <a
          href="https://image.sepaitech.com/"
          aria-label="前往实朴图片平台首页"
          className="inline-flex w-fit items-center rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-wb-brand-soft"
        >
          <img src={brandMarkUrl} alt="" className="h-[30px] w-[26px] object-contain" />
        </a>

        <nav aria-label="主导航" className="hidden items-center justify-center gap-1.5 md:flex">
          {PRIMARY_NAV_ITEMS.map((item) => (
            <DesktopNavItem key={item.to} item={item} />
          ))}
        </nav>
        <MobileNavigation />

        <ProfileMenu />
      </div>
    </header>
  )
}
