import { cn } from '@/lib/utils'

/**
 * 流动极光背景：四团大尺寸柔边色晕缓慢漂移，铺在容器底。
 * 纯 CSS 动画驱动（见 index.css `aurora-drift`），零 JS、低功耗；
 * 放进任意 `relative` 容器即可，内容记得用更高的 z 层。
 *
 * 性能：柔边由 `aurora-blob` 的 radial-gradient 预渲染（无 filter:blur），
 * 每帧只有合成器 transform；盒子比原实心圆放大 ~1.5x 以补回模糊外溢的
 * 足迹，观感与旧版一致。prefers-reduced-motion 下静止（index.css）。
 */
export function AuroraBackground({ className }: { className?: string }) {
  return (
    <div aria-hidden className={cn('pointer-events-none absolute inset-0 overflow-hidden', className)}>
      <div className="aurora-blob -top-[34%] -left-[28%] size-[90%] opacity-55 [--blob:var(--primary)] [animation:aurora-drift_15s_ease-in-out_infinite]" />
      <div className="aurora-blob -top-[21%] -right-[23%] size-[76%] opacity-50 [--blob:var(--chart-5)] [animation:aurora-drift_19s_ease-in-out_infinite_reverse]" />
      <div className="aurora-blob -bottom-[37%] -left-[3%] size-[95%] opacity-50 [--blob:var(--chart-4)] [animation:aurora-drift_23s_ease-in-out_infinite]" />
      <div className="aurora-blob -right-[6%] -bottom-[14%] size-[70%] opacity-60 [--blob:var(--highlight)] [animation:aurora-drift_17s_ease-in-out_infinite_reverse]" />
    </div>
  )
}
