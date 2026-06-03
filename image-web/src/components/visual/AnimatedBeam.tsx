import { useEffect, useId, useState, type RefObject } from 'react'
import { motion } from 'motion/react'

import { cn } from '@/lib/utils'

interface AnimatedBeamProps {
  containerRef: RefObject<HTMLElement | null>
  fromRef: RefObject<HTMLElement | null>
  toRef: RefObject<HTMLElement | null>
  curvature?: number
  reverse?: boolean
  duration?: number
  delay?: number
  pathColor?: string
  pathWidth?: number
  pathOpacity?: number
  gradientStartColor?: string
  gradientStopColor?: string
  /** 该段是否点亮（流动光束）；false 只画静态暗线 */
  active?: boolean
  className?: string
}

/**
 * 连接两个元素的动画光束（Magic UI 思路，motion 驱动）：
 * 量两端中心点画一条 SVG 路径，点亮段有一束渐变沿路径流动。
 * 监听容器/两端尺寸变化重算路径（ResizeObserver）。
 */
export function AnimatedBeam({
  containerRef,
  fromRef,
  toRef,
  curvature = 0,
  reverse = false,
  duration = 3,
  delay = 0,
  pathColor = 'var(--border)',
  pathWidth = 2,
  pathOpacity = 1,
  gradientStartColor = 'var(--primary)',
  gradientStopColor = 'var(--highlight)',
  active = true,
  className,
}: AnimatedBeamProps) {
  const id = useId()
  const [path, setPath] = useState('')
  const [box, setBox] = useState({ w: 0, h: 0 })

  useEffect(() => {
    const compute = () => {
      const container = containerRef.current
      const from = fromRef.current
      const to = toRef.current
      if (!container || !from || !to) return
      const cRect = container.getBoundingClientRect()
      const fRect = from.getBoundingClientRect()
      const tRect = to.getBoundingClientRect()
      setBox({ w: cRect.width, h: cRect.height })
      const sx = fRect.left - cRect.left + fRect.width / 2
      const sy = fRect.top - cRect.top + fRect.height / 2
      const ex = tRect.left - cRect.left + tRect.width / 2
      const ey = tRect.top - cRect.top + tRect.height / 2
      const mid = (sy + ey) / 2 - curvature
      setPath(`M ${sx},${sy} Q ${(sx + ex) / 2},${mid} ${ex},${ey}`)
    }
    compute()
    const ro = new ResizeObserver(compute)
    if (containerRef.current) ro.observe(containerRef.current)
    window.addEventListener('resize', compute)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', compute)
    }
  }, [containerRef, fromRef, toRef, curvature])

  const gid = `beam-${id.replace(/[:]/g, '')}`

  return (
    <svg
      fill="none"
      width={box.w}
      height={box.h}
      className={cn('pointer-events-none absolute top-0 left-0', className)}
      viewBox={`0 0 ${box.w} ${box.h}`}
    >
      <path d={path} stroke={pathColor} strokeWidth={pathWidth} strokeOpacity={pathOpacity} strokeLinecap="round" />
      {active && (
        <>
          <path d={path} strokeWidth={pathWidth} stroke={`url(#${gid})`} strokeOpacity={1} strokeLinecap="round" />
          <defs>
            <motion.linearGradient
              id={gid}
              gradientUnits="userSpaceOnUse"
              initial={{ x1: '0%', x2: '0%', y1: '0%', y2: '0%' }}
              animate={{
                x1: reverse ? ['90%', '-10%'] : ['10%', '110%'],
                x2: reverse ? ['100%', '0%'] : ['0%', '100%'],
                y1: ['0%', '0%'],
                y2: ['0%', '0%'],
              }}
              transition={{ duration, delay, repeat: Infinity, ease: 'linear' }}
            >
              <stop stopColor={gradientStartColor} stopOpacity={0} />
              <stop stopColor={gradientStartColor} />
              <stop offset="32.5%" stopColor={gradientStopColor} />
              <stop offset="100%" stopColor={gradientStopColor} stopOpacity={0} />
            </motion.linearGradient>
          </defs>
        </>
      )}
    </svg>
  )
}
