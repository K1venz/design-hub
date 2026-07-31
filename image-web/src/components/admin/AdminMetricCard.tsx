import type { LucideIcon } from 'lucide-react'

import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface AdminMetricCardProps {
  label: string
  value: string
  detail?: string
  icon: LucideIcon
  tone?: 'primary' | 'success' | 'warning' | 'danger'
}

const toneClasses = {
  primary: 'bg-wb-tint-1 text-wb-brand',
  success: 'bg-emerald-50 text-emerald-600',
  warning: 'bg-wb-amber-tint text-wb-amber',
  danger: 'bg-wb-red-tint text-wb-red',
} as const

export function AdminMetricCard({
  label,
  value,
  detail,
  icon: Icon,
  tone = 'primary',
}: AdminMetricCardProps) {
  return (
    <Card className="gap-3 border-white/80 bg-white/82 p-4 shadow-[0_10px_28px_-20px_rgba(40,40,90,.3)]">
      <div className="flex items-start justify-between gap-3">
        <span className="text-xs font-medium text-wb-ink-5">{label}</span>
        <span
          className={cn(
            'grid size-8 shrink-0 place-items-center rounded-xl',
            toneClasses[tone],
          )}
        >
          <Icon className="size-4" />
        </span>
      </div>
      <div>
        <p className="tabular text-2xl font-semibold tracking-tight text-wb-ink-1">
          {value}
        </p>
        {detail ? (
          <p className="mt-1 text-[11px] leading-4 text-wb-ink-6">{detail}</p>
        ) : null}
      </div>
    </Card>
  )
}
