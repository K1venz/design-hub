import type { LucideIcon } from 'lucide-react'

import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

export function KpiCard({
  icon: Icon,
  label,
  value,
  hint,
  loading,
}: {
  icon: LucideIcon
  label: string
  value: string
  hint?: string
  loading?: boolean
}) {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Icon className="text-primary size-4" />
        {label}
      </div>
      {loading ? (
        <Skeleton className="mt-3 h-8 w-24" />
      ) : (
        <p className="tabular mt-2.5 text-2xl font-semibold tracking-tight text-foreground">
          {value}
        </p>
      )}
      {hint && !loading && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </Card>
  )
}
