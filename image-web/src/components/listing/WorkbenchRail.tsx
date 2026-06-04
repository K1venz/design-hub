import { useState } from 'react'
import { ShoppingBagIcon, FlameIcon } from 'lucide-react'
import { toast } from 'sonner'

import { cn } from '@/lib/utils'

const ITEMS = [
  { key: 'product-set', label: '商品套图', icon: ShoppingBagIcon, enabled: true },
  { key: 'replica', label: '爆款图复刻', icon: FlameIcon, enabled: false },
]

/** Left category rail. Only 商品套图 is live; 爆款图复刻 toasts "敬请期待". */
export function WorkbenchRail() {
  const [active, setActive] = useState('product-set')
  return (
    <div className="flex w-20 shrink-0 flex-col items-center gap-2 border-r border-[#ece8e2] bg-white py-4">
      {ITEMS.map((it) => {
        const on = active === it.key && it.enabled
        return (
          <button
            key={it.key}
            onClick={() => (it.enabled ? setActive(it.key) : toast('🔥 爆款图复刻 · 敬请期待'))}
            className={cn(
              'w-16 rounded-[13px] py-2.5 text-center text-[11.5px] text-[#7a746c]',
              on && 'bg-[#f4f0ff] font-semibold text-[#4733b8]',
            )}
          >
            <span
              className={cn(
                'mx-auto mb-1.5 grid size-[30px] place-items-center rounded-[10px] bg-[#efeae3]',
                on && 'bg-gradient-to-br from-[#7c6cff] to-[#ff9a62] text-white',
              )}
            >
              <it.icon className="size-4" />
            </span>
            {it.label}
          </button>
        )
      })}
    </div>
  )
}
