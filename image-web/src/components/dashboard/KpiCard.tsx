import type { LucideIcon } from 'lucide-react'

import { Skeleton } from '@/components/ui/skeleton'
import { MagicCard } from '@/components/visual/MagicCard'
import { NumberTicker } from '@/components/visual/NumberTicker'
import { cn } from '@/lib/utils'

type Accent = 'teal' | 'amber' | 'terracotta' | 'violet'

const ACCENT: Record<Accent, { badge: string; spot: string }> = {
  teal: { badge: 'from-[oklch(0.55_0.09_196)] to-[oklch(0.46_0.07_196)]', spot: 'oklch(0.55 0.09 196 / 0.20)' },
  amber: { badge: 'from-[oklch(0.79_0.13_76)] to-[oklch(0.66_0.12_70)]', spot: 'oklch(0.79 0.13 76 / 0.22)' },
  terracotta: { badge: 'from-[oklch(0.64_0.13_42)] to-[oklch(0.54_0.11_40)]', spot: 'oklch(0.62 0.12 42 / 0.20)' },
  violet: { badge: 'from-[oklch(0.55_0.10_300)] to-[oklch(0.50_0.12_332)]', spot: 'oklch(0.55 0.11 320 / 0.20)' },
}

export function KpiCard({
  icon: Icon,
  label,
  value,
  prefix = '',
  suffix = '',
  decimals = 0,
  hint,
  loading,
  accent = 'teal',
}: {
  icon: LucideIcon
  label: string
  value: number
  prefix?: string
  suffix?: string
  decimals?: number
  hint?: string
  loading?: boolean
  accent?: Accent
}) {
  const a = ACCENT[accent]
  return (
    <MagicCard gradientColor={a.spot} className="p-5">
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground text-sm">{label}</span>
        <span
          className={cn(
            'inline-flex size-8 items-center justify-center rounded-lg bg-gradient-to-br text-white shadow-sm',
            a.badge,
          )}
        >
          <Icon className="size-4" />
        </span>
      </div>
      {loading ? (
        <Skeleton className="mt-3.5 h-9 w-24" />
      ) : (
        <p className="text-foreground mt-2.5 text-3xl font-semibold tracking-tight">
          <NumberTicker value={value} prefix={prefix} suffix={suffix} decimals={decimals} />
        </p>
      )}
      {hint && !loading && <p className="text-muted-foreground mt-1 text-xs">{hint}</p>}
    </MagicCard>
  )
}
