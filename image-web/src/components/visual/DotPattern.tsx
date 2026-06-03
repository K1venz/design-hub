import { useId } from 'react'

import { cn } from '@/lib/utils'

interface DotPatternProps {
  /** 点阵格距（px） */
  gap?: number
  /** 点半径（px） */
  radius?: number
  className?: string
}

/**
 * 极淡点阵底纹：给大片留白加一层若有若无的质感。
 * 配 [mask-image:radial-gradient(...)] 可做边缘淡出。
 */
export function DotPattern({ gap = 22, radius = 1, className }: DotPatternProps) {
  const id = useId()
  return (
    <svg
      aria-hidden
      className={cn('text-foreground/[0.045] pointer-events-none absolute inset-0 h-full w-full fill-current', className)}
    >
      <defs>
        <pattern id={id} width={gap} height={gap} patternUnits="userSpaceOnUse">
          <circle cx={radius} cy={radius} r={radius} />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${id})`} />
    </svg>
  )
}
