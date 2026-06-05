import { cn } from '@/lib/utils'

const STATUS_STYLE: Record<string, string> = {
  完成: 'bg-emerald-50 text-emerald-700',
  部分完成: 'bg-amber-50 text-amber-700',
  失败: 'bg-rose-50 text-rose-700',
  生成中: 'bg-violet-50 text-violet-700',
}

/** listing 任务状态徽章（完成/部分完成/失败/生成中）。 */
export function JobStatusBadge({ status, className }: { status: string; className?: string }) {
  return (
    <span
      className={cn(
        'rounded-md px-2 py-0.5 text-[11px] font-medium',
        STATUS_STYLE[status] ?? 'bg-stone-100 text-stone-600',
        className,
      )}
    >
      {status}
    </span>
  )
}
