import { cn } from '@/lib/utils'

/**
 * 流动极光背景：四团大尺寸高斯模糊色团缓慢漂移，铺在容器底。
 * 纯 CSS 动画驱动（见 index.css `aurora-drift`），零 JS、低功耗；
 * 放进任意 `relative` 容器即可，内容记得用更高的 z 层。
 */
export function AuroraBackground({ className }: { className?: string }) {
  return (
    <div aria-hidden className={cn('pointer-events-none absolute inset-0 overflow-hidden', className)}>
      <div className="absolute -top-[18%] -left-[12%] size-[58%] rounded-full bg-primary opacity-55 blur-[85px] will-change-transform [animation:aurora-drift_15s_ease-in-out_infinite]" />
      <div className="absolute -top-[8%] -right-[10%] size-[50%] rounded-full bg-chart-5 opacity-50 blur-[90px] will-change-transform [animation:aurora-drift_19s_ease-in-out_infinite_reverse]" />
      <div className="absolute -bottom-[20%] left-[14%] size-[62%] rounded-full bg-chart-4 opacity-50 blur-[95px] will-change-transform [animation:aurora-drift_23s_ease-in-out_infinite]" />
      <div className="absolute right-[10%] bottom-[2%] size-[38%] rounded-full bg-highlight opacity-60 blur-[72px] will-change-transform [animation:aurora-drift_17s_ease-in-out_infinite_reverse]" />
    </div>
  )
}
