import { NavLink } from 'react-router-dom'
import {
  HomeIcon, WandSparklesIcon, LayersIcon, FlameIcon, HistoryIcon,
  SlidersHorizontalIcon, UsersRoundIcon, type LucideIcon,
} from 'lucide-react'

import { cn } from '@/lib/utils'
import { useAuthStore, isManager } from '@/stores/auth-store'

interface NavEntry {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
  /** 「内测」等角标（纯氛围）。 */
  badge?: string
}

// 决策 2（spec §二.2）：左侧导航按实朴真实能力映射。首页公开，其余为保护项
// （未登录点击 → ProtectedRoute 带回跳去登录）。管理组仅 manager 可见。
const PRIMARY: NavEntry[] = [
  { to: '/', label: '首页', icon: HomeIcon, end: true },
  { to: '/chat', label: '帮我设计', icon: WandSparklesIcon, badge: '内测' },
  { to: '/set', label: '商品套图', icon: LayersIcon },
  { to: '/clone', label: '爆款复刻', icon: FlameIcon },
  { to: '/history', label: '历史', icon: HistoryIcon },
]

const ADMIN: NavEntry[] = [
  { to: '/admin/models', label: '模型配置', icon: SlidersHorizontalIcon },
  { to: '/admin/users', label: '用户管理', icon: UsersRoundIcon },
]

function NavRow({ entry }: { entry: NavEntry }) {
  return (
    <NavLink
      to={entry.to}
      end={entry.end}
      className={({ isActive }) =>
        cn(
          'flex items-center gap-2.5 rounded-[11px] px-3 py-2 text-[13.5px] text-wb-ink-5 transition-colors hover:bg-white/70 hover:text-wb-ink-2',
          isActive &&
            'bg-wb-brand font-semibold text-white shadow-[0_6px_16px_-8px_rgba(91,91,214,.6)] hover:bg-wb-brand hover:text-white',
        )
      }
    >
      <entry.icon className="size-[18px] shrink-0" />
      <span className="flex-1 truncate">{entry.label}</span>
      {entry.badge && (
        <span className="rounded-full bg-wb-tint-1 px-1.5 py-px text-[10px] font-semibold text-wb-brand-deep">
          {entry.badge}
        </span>
      )}
    </NavLink>
  )
}

/** 全局左侧竖导航（Style 4 玻璃浮卡）：品牌字标 + 主导航 + 管理组（仅 manager）。 */
export function SideNav() {
  const user = useAuthStore((s) => s.user)
  const showAdmin = user != null && isManager(user.role)

  return (
    <nav className="glass-panel flex w-[212px] shrink-0 flex-col self-stretch overflow-y-auto p-3">
      <NavLink to="/" className="mb-3 flex items-center gap-2 px-2 pt-1 font-semibold tracking-[-0.01em] text-wb-ink-1">
        <span className="grid size-7 place-items-center rounded-[9px] bg-gradient-to-br from-wb-grad-from to-wb-grad-to text-[12px] font-bold text-white">
          朴
        </span>
        实朴
      </NavLink>

      <div className="space-y-0.5">
        {PRIMARY.map((e) => (
          <NavRow key={e.to} entry={e} />
        ))}
      </div>

      {showAdmin && (
        <>
          <div className="mt-4 mb-1 px-3 text-[10.5px] font-medium uppercase tracking-[0.1em] text-wb-faint-1">
            管理
          </div>
          <div className="space-y-0.5">
            {ADMIN.map((e) => (
              <NavRow key={e.to} entry={e} />
            ))}
          </div>
        </>
      )}

      <div className="mt-auto px-2 pt-4 text-[10.5px] leading-relaxed text-wb-faint-1">
        实朴 · 电商图片工作站
      </div>
    </nav>
  )
}
