import {
  LayoutDashboardIcon,
  SlidersHorizontalIcon,
  UsersRoundIcon,
  type LucideIcon,
} from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'
import { DotPattern } from '@/components/visual/DotPattern'
import { cn } from '@/lib/utils'

interface AdminNavigationItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
}

const ADMIN_NAVIGATION: readonly AdminNavigationItem[] = [
  {
    to: '/admin',
    label: '总览',
    icon: LayoutDashboardIcon,
    end: true,
  },
  {
    to: '/admin/users',
    label: '用户管理',
    icon: UsersRoundIcon,
  },
  {
    to: '/admin/models',
    label: '模型配置',
    icon: SlidersHorizontalIcon,
  },
]

export function AdminLayout() {
  return (
    <AppShell>
      <div className="relative flex min-h-0 flex-1 flex-col gap-3 overflow-hidden px-3 pb-3 md:flex-row">
        <DotPattern className="[mask-image:radial-gradient(ellipse_at_top,white,transparent_72%)]" />
        <aside className="glass-lite relative z-10 shrink-0 rounded-[18px] p-2 md:w-48 md:p-3">
          <div className="mb-2 hidden px-2 py-1 md:block">
            <p className="text-sm font-semibold text-wb-ink-2">管理后台</p>
            <p className="mt-0.5 text-[11px] text-wb-ink-6">平台运营与合规</p>
          </div>
          <nav
            aria-label="管理后台导航"
            className="flex gap-1 overflow-x-auto md:grid"
          >
            {ADMIN_NAVIGATION.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    'flex shrink-0 items-center gap-2.5 rounded-xl px-3 py-2.5 text-[13px] font-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-wb-brand-soft',
                    isActive
                      ? 'bg-wb-brand text-white shadow-[0_8px_20px_-12px_rgba(91,91,214,.9)]'
                      : 'text-wb-ink-5 hover:bg-white/80 hover:text-wb-ink-2',
                  )
                }
              >
                <item.icon className="size-[17px] shrink-0" />
                {item.label}
              </NavLink>
            ))}
          </nav>
        </aside>
        <main className="relative z-10 min-h-0 flex-1 overflow-auto">
          <div className="mx-auto w-full max-w-[1440px] px-1 pb-6 pt-1 md:px-3">
            <Outlet />
          </div>
        </main>
      </div>
    </AppShell>
  )
}
