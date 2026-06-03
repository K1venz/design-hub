import { useEffect, useRef } from 'react'
import { useInView, useMotionValue, useSpring } from 'motion/react'

import { cn } from '@/lib/utils'

interface NumberTickerProps {
  value: number
  decimals?: number
  prefix?: string
  suffix?: string
  className?: string
}

/**
 * 数字滚动：进入视口后用弹簧从 0 滚到目标值，列对齐用等宽数字。
 * 尊重 prefers-reduced-motion（系统关动效时直接定格目标值）。
 */
export function NumberTicker({ value, decimals = 0, prefix = '', suffix = '', className }: NumberTickerProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const mv = useMotionValue(0)
  const spring = useSpring(mv, { damping: 32, stiffness: 110 })
  const inView = useInView(ref, { once: true, margin: '-40px' })

  const fmt = (n: number) =>
    prefix +
    n.toLocaleString('zh-CN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) +
    suffix

  useEffect(() => {
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (!inView) return
    if (reduce) {
      mv.jump(value)
    } else {
      mv.set(value)
    }
  }, [inView, value, mv])

  useEffect(
    () =>
      spring.on('change', (latest) => {
        if (ref.current) ref.current.textContent = fmt(latest)
      }),
    // fmt closes over decimals/prefix/suffix; re-subscribe when they change
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [spring, decimals, prefix, suffix],
  )

  return (
    <span ref={ref} className={cn('tabular', className)}>
      {fmt(0)}
    </span>
  )
}
