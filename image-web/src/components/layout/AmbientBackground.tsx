import { useEffect, useRef } from 'react'

import { calculateLayerOffset } from './ambient-parallax'

const DEPTHS = {
  far: 0.25,
  middle: 0.55,
  near: 0.9,
} as const

export function AmbientBackground() {
  const sceneRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const scene = sceneRef.current
    if (!scene || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    let pointerX = 0
    let pointerY = 0
    let frame = 0

    const paint = () => {
      for (const [name, depth] of Object.entries(DEPTHS)) {
        const layer = scene.querySelector<HTMLElement>(`[data-depth="${name}"]`)
        if (!layer) throw new Error(`Missing ambient depth plane: ${name}`)

        const offset = calculateLayerOffset(depth, pointerX, pointerY, window.scrollY)
        layer.style.setProperty('--parallax-x', `${offset.x}px`)
        layer.style.setProperty('--parallax-y', `${offset.y}px`)
      }
      frame = 0
    }

    const schedulePaint = () => {
      if (!frame) frame = window.requestAnimationFrame(paint)
    }

    const handlePointerMove = (event: PointerEvent) => {
      pointerX = event.clientX / window.innerWidth * 2 - 1
      pointerY = event.clientY / window.innerHeight * 2 - 1
      schedulePaint()
    }

    window.addEventListener('pointermove', handlePointerMove, { passive: true })
    window.addEventListener('scroll', schedulePaint, { passive: true })
    schedulePaint()

    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('scroll', schedulePaint)
      if (frame) window.cancelAnimationFrame(frame)
    }
  }, [])

  return (
    <div
      ref={sceneRef}
      aria-hidden="true"
      data-ambient-background="true"
      className="ambient-scene"
    >
      <div data-depth="far" className="ambient-plane ambient-plane-far">
        <span className="ambient-spot ambient-spot-violet" />
        <span className="ambient-spot ambient-spot-cyan" />
        <span className="ambient-spot ambient-spot-rose" />
      </div>

      <div data-depth="middle" className="ambient-plane ambient-plane-middle">
        <span className="ambient-orbit ambient-orbit-one" />
        <span className="ambient-orbit ambient-orbit-two" />
        <span className="ambient-orbit ambient-orbit-three" />
        <span className="ambient-orbit ambient-orbit-four" />
      </div>

      <div data-depth="near" className="ambient-plane ambient-plane-near">
        {Array.from({ length: 12 }, (_, index) => (
          <span key={index} className={`ambient-speck ambient-speck-${index + 1}`} />
        ))}
      </div>
    </div>
  )
}
