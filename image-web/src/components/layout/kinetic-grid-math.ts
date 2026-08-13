export type Point = { x: number; y: number }
export type Ripple = Point & { startedAt: number }

const POINTER_RADIUS = 180
const POINTER_PULL = 16
const RIPPLE_SPEED = 0.26
const RIPPLE_WIDTH = 38
const RIPPLE_PUSH = 8

export function calculateGridDisplacement(
  point: Point,
  pointer: Point | null,
  now: number,
  ripples: readonly Ripple[],
): Point {
  let x = point.x
  let y = point.y

  if (pointer) {
    const dx = pointer.x - point.x
    const dy = pointer.y - point.y
    const distance = Math.hypot(dx, dy)

    if (distance > 0 && distance < POINTER_RADIUS) {
      const strength = (1 - distance / POINTER_RADIUS) ** 2 * POINTER_PULL
      x += dx / distance * strength
      y += dy / distance * strength
    }
  }

  for (const ripple of ripples) {
    const dx = point.x - ripple.x
    const dy = point.y - ripple.y
    const distance = Math.hypot(dx, dy)
    const radius = (now - ripple.startedAt) * RIPPLE_SPEED
    const distanceFromWave = Math.abs(distance - radius)

    if (distance > 0 && distanceFromWave < RIPPLE_WIDTH) {
      const strength = (1 - distanceFromWave / RIPPLE_WIDTH) * RIPPLE_PUSH
      x += dx / distance * strength
      y += dy / distance * strength
    }
  }

  return { x, y }
}
