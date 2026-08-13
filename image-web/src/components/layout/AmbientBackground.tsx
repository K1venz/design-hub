import { useEffect, useRef } from 'react'

import {
  calculateGridDisplacement,
  type Point,
  type Ripple,
} from './kinetic-grid-math'

const GRID_GAP = 34
const RIPPLE_LIFETIME = 2200

function drawGrid(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  pointer: Point | null,
  ripples: readonly Ripple[],
  now: number,
) {
  context.clearRect(0, 0, width, height)

  for (let row = GRID_GAP / 2; row < height; row += GRID_GAP) {
    for (let column = GRID_GAP / 2; column < width; column += GRID_GAP) {
      const point = calculateGridDisplacement(
        { x: column, y: row },
        pointer,
        now,
        ripples,
      )
      const pointerDistance = pointer
        ? Math.hypot(pointer.x - column, pointer.y - row)
        : Number.POSITIVE_INFINITY
      const prominence = Math.max(0, 1 - pointerDistance / 220)

      context.beginPath()
      context.arc(point.x, point.y, 1.15 + prominence * 1.45, 0, Math.PI * 2)
      context.fillStyle = prominence > 0
        ? `rgba(91, 91, 214, ${0.23 + prominence * 0.38})`
        : 'rgba(76, 91, 124, 0.2)'
      context.fill()
    }
  }
}

export function AmbientBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const context = canvas.getContext('2d')
    if (!context) throw new Error('Kinetic grid requires a 2D canvas context')

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let pointer: Point | null = null
    let ripples: Ripple[] = []
    let frame = 0

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.round(window.innerWidth * ratio)
      canvas.height = Math.round(window.innerHeight * ratio)
      canvas.style.width = `${window.innerWidth}px`
      canvas.style.height = `${window.innerHeight}px`
      context.setTransform(ratio, 0, 0, ratio, 0, 0)
    }

    const render = (now: number) => {
      ripples = ripples.filter((ripple) => now - ripple.startedAt < RIPPLE_LIFETIME)
      drawGrid(context, window.innerWidth, window.innerHeight, pointer, ripples, now)
      frame = reducedMotion ? 0 : window.requestAnimationFrame(render)
    }

    const handlePointerMove = (event: PointerEvent) => {
      pointer = { x: event.clientX, y: event.clientY }
    }

    const handlePointerLeave = () => {
      pointer = null
    }

    const handlePointerDown = (event: PointerEvent) => {
      if (reducedMotion) return
      ripples.push({ x: event.clientX, y: event.clientY, startedAt: performance.now() })
    }

    resize()
    frame = window.requestAnimationFrame(render)
    window.addEventListener('resize', resize, { passive: true })
    window.addEventListener('pointermove', handlePointerMove, { passive: true })
    document.documentElement.addEventListener('pointerleave', handlePointerLeave)
    window.addEventListener('pointerdown', handlePointerDown, { passive: true })

    return () => {
      window.removeEventListener('resize', resize)
      window.removeEventListener('pointermove', handlePointerMove)
      document.documentElement.removeEventListener('pointerleave', handlePointerLeave)
      window.removeEventListener('pointerdown', handlePointerDown)
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [])

  return (
    <div aria-hidden="true" data-ambient-background="true" className="kinetic-grid-scene">
      <canvas ref={canvasRef} data-kinetic-grid="true" className="kinetic-grid-canvas" />
    </div>
  )
}
