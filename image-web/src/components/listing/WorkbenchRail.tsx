import { NavLink } from 'react-router-dom'
import { ShoppingBagIcon, FlameIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

// 爆款图复刻挪最左第一位（用户拍板）；默认路由 `/` 仍进商品套图。
const ITEMS = [
  { to: '/clone', label: '爆款图复刻', icon: FlameIcon },
  { to: '/', label: '商品套图', icon: ShoppingBagIcon, end: true },
]

/** Left category rail — route-driven (active = current page). */
export function WorkbenchRail() {
  return (
    <div className="flex w-20 shrink-0 flex-col items-center gap-2 border-r border-wb-line-1 bg-white py-4">
      {ITEMS.map((it) => (
        <NavLink
          key={it.to}
          to={it.to}
          end={it.end}
          className={({ isActive }) =>
            cn(
              'w-16 rounded-[13px] py-2.5 text-center text-[11.5px] text-wb-ink-5',
              isActive && 'bg-wb-tint-1 font-semibold text-wb-brand-deep',
            )
          }
        >
          {({ isActive }) => (
            <>
              <span
                className={cn(
                  'mx-auto mb-1.5 grid size-[30px] place-items-center rounded-[10px] bg-wb-surface-5',
                  isActive && 'bg-gradient-to-br from-wb-grad-from to-wb-grad-to text-white',
                )}
              >
                <it.icon className="size-4" />
              </span>
              {it.label}
            </>
          )}
        </NavLink>
      ))}
    </div>
  )
}
