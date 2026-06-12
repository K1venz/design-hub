import { NavLink } from 'react-router-dom'
import { ShoppingBagIcon, FlameIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

// 爆款图复刻挪最左第一位（用户拍板）；默认路由 `/` 仍进商品套图。
const ITEMS = [
  { to: '/clone', label: '爆款图复刻', icon: FlameIcon },
  { to: '/', label: '商品套图', icon: ShoppingBagIcon, end: true },
]

/** Left category rail — route-driven (active = current page)；玻璃浮卡 + 实心紫选中态（Style 4）。 */
export function WorkbenchRail() {
  return (
    <div className="glass-panel flex w-[88px] shrink-0 flex-col items-center gap-1.5 self-start p-2">
      {ITEMS.map((it) => (
        <NavLink
          key={it.to}
          to={it.to}
          end={it.end}
          className={({ isActive }) =>
            cn(
              'w-full rounded-[13px] py-2.5 text-center text-[11.5px] text-wb-ink-5 transition-colors hover:bg-white/80',
              isActive &&
                'bg-wb-brand font-semibold text-white shadow-[0_6px_16px_-6px_rgba(91,91,214,.6)] hover:bg-wb-brand',
            )
          }
        >
          {({ isActive }) => (
            <>
              <span
                className={cn(
                  'mx-auto mb-1.5 grid size-[30px] place-items-center rounded-[10px] bg-wb-surface-4 text-wb-ink-5',
                  isActive && 'bg-white/20 text-white',
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
