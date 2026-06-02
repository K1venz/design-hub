import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { STATUS_TONE, type ProjectStatus } from '@/lib/project-status'

export function StatusBadge({
  status,
  className,
}: {
  status: ProjectStatus
  className?: string
}) {
  return (
    <Badge variant="outline" className={cn('font-medium', STATUS_TONE[status], className)}>
      {status}
    </Badge>
  )
}
