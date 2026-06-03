import type { CSSProperties } from 'react'
import { motion } from 'motion/react'

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
 * 流光描边：一颗渐变光点沿元素边框匀速环绕（Magic UI 思路，motion 驱动）。
 * 用「padding + mask exclude」把可见区裁成一圈细边，光点扫过即成流光。
 * 用法：放进一个 `relative` 且 `rounded-*` 的容器里，描边自动贴合该圆角。
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
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 rounded-[inherit]" style={maskStyle}>
      <motion.div
        className={cn(
          'absolute aspect-square rounded-full bg-gradient-to-l from-[var(--primary)] via-[var(--highlight)] to-transparent',
          className,
        )}
        style={{ width: size, offsetPath: `rect(0 auto auto 0 round ${size}px)` }}
        initial={{ offsetDistance: '0%' }}
        animate={{ offsetDistance: '100%' }}
        transition={{ repeat: Infinity, ease: 'linear', duration, delay: -delay }}
      />
    </div>
  )
}
