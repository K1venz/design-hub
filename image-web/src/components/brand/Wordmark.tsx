import { cn } from '@/lib/utils'

/**
 * 品牌标记：青墨圆角方内嵌「叠帧」意象——对应出图的多候选/多轮次。
 * 纯 SVG，随字号缩放。
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={cn('size-8 shrink-0', className)}
      role="img"
      aria-label="实朴"
    >
      <rect x="0.5" y="0.5" width="31" height="31" rx="8" className="fill-primary" />
      <rect
        x="8"
        y="8"
        width="13"
        height="13"
        rx="2.5"
        className="fill-none stroke-primary-foreground/45"
        strokeWidth="1.4"
      />
      <rect
        x="11.5"
        y="11.5"
        width="13"
        height="13"
        rx="2.5"
        className="fill-none stroke-primary-foreground"
        strokeWidth="1.4"
      />
      <circle cx="18" cy="18" r="2.1" className="fill-highlight" />
    </svg>
  )
}

interface WordmarkProps {
  className?: string
  /** 隐藏文字，仅留标记（折叠侧栏用）. */
  markOnly?: boolean
}

export function Wordmark({ className, markOnly = false }: WordmarkProps) {
  return (
    <div className={cn('flex items-center gap-2.5', className)}>
      <BrandMark />
      {!markOnly && (
        <div className="flex flex-col leading-none">
          <span className="text-[15px] font-semibold tracking-tight text-foreground">
            实朴
          </span>
          <span className="text-[11px] tracking-[0.18em] text-muted-foreground">
            电商图片工作站
          </span>
        </div>
      )}
    </div>
  )
}
