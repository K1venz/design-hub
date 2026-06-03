import { useCallback, type ReactNode } from 'react'
import { motion, useMotionTemplate, useMotionValue } from 'motion/react'

import { cn } from '@/lib/utils'

interface MagicCardProps {
  children: ReactNode
  className?: string
  /** 聚光半径（px） */
  gradientSize?: number
  /** 聚光颜色（含透明度，建议用 oklch + alpha） */
  gradientColor?: string
}

/**
 * 聚光卡：一束径向高光随鼠标在卡内移动，悬停淡入。motion 驱动，仅 hover 时活动。
 */
export function MagicCard({
  children,
  className,
  gradientSize = 240,
  gradientColor = 'oklch(0.55 0.08 196 / 0.18)',
}: MagicCardProps) {
  const x = useMotionValue(-gradientSize)
  const y = useMotionValue(-gradientSize)

  const onMove = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const rect = e.currentTarget.getBoundingClientRect()
      x.set(e.clientX - rect.left)
      y.set(e.clientY - rect.top)
    },
    [x, y],
  )
  const onLeave = useCallback(() => {
    x.set(-gradientSize)
    y.set(-gradientSize)
  }, [x, y, gradientSize])

  const background = useMotionTemplate`radial-gradient(${gradientSize}px circle at ${x}px ${y}px, ${gradientColor}, transparent 72%)`

  return (
    <div
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      className={cn('group border-border/70 bg-card relative overflow-hidden rounded-xl border', className)}
    >
      <motion.div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{ background }}
      />
      <div className="relative">{children}</div>
    </div>
  )
}
