import type { CSSProperties } from 'react'

import { cn } from '@/lib/utils'

interface BorderBeamProps {
  /** 光点尺寸（px） */
  size?: number
  /** 环绕一圈时长（s） */
  duration?: number
  /** 负向延迟，多条光束错峰用（s） */
  delay?: number
  /** 描边粗细（px） */
  borderWidth?: number
  className?: string
}

/**
 * 流光描边：一颗渐变光点沿元素边框匀速环绕（Magic UI 思路）。
 * 用「padding + mask exclude」把可见区裁成一圈细边，光点扫过即成流光。
 * 用法：放进一个 `relative` 且 `rounded-*` 的容器里，描边自动贴合该圆角。
 *
 * 性能：环绕由纯 CSS `border-beam-orbit`（offset-distance，transform 系）
 * 驱动，合成器直跑；替代原 motion 版每帧 JS 写样式 + 主线程 style recalc。
 * prefers-reduced-motion 下整条隐藏（index.css）。
 */
export function BorderBeam({
  size = 70,
  duration = 7,
  delay = 0,
  borderWidth = 1.5,
  className,
}: BorderBeamProps) {
  const maskStyle: CSSProperties = {
    padding: borderWidth,
    WebkitMask: 'linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)',
    WebkitMaskComposite: 'xor',
    maskComposite: 'exclude',
  }
  const beamStyle: CSSProperties = {
    width: size,
    offsetPath: `rect(0 auto auto 0 round ${size}px)`,
    animationDuration: `${duration}s`,
    animationDelay: `${-delay}s`,
  }
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 rounded-[inherit]" style={maskStyle}>
      <div
        className={cn(
          'border-beam absolute aspect-square rounded-full bg-gradient-to-l from-[var(--primary)] via-[var(--highlight)] to-transparent',
          className,
        )}
        style={beamStyle}
      />
    </div>
  )
}
