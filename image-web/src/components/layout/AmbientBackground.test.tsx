import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { AmbientBackground } from './AmbientBackground'
import { calculateGridDisplacement } from './kinetic-grid-math'

describe('kinetic grid background', () => {
  it('renders one inert canvas instead of the retired layered decoration', () => {
    const html = renderToStaticMarkup(createElement(AmbientBackground))

    expect(html).toContain('aria-hidden="true"')
    expect(html).toContain('data-kinetic-grid="true"')
    expect(html).toContain('<canvas')
    expect(html).not.toContain('ambient-orbit')
    expect(html).not.toContain('ambient-speck')
  })

  it('pulls nearby grid points toward the pointer with distance falloff', () => {
    expect(
      calculateGridDisplacement(
        { x: 100, y: 100 },
        { x: 120, y: 100 },
        0,
        [],
      ),
    ).toEqual({ x: 112.64197530864197, y: 100 })
  })

  it('moves only points near an expanding click wavefront', () => {
    const ripples = [{ x: 100, y: 100, startedAt: 0 }]

    const onWave = calculateGridDisplacement(
      { x: 230, y: 100 },
      null,
      500,
      ripples,
    )
    const awayFromWave = calculateGridDisplacement(
      { x: 100, y: 100 },
      null,
      500,
      ripples,
    )

    expect(onWave.x).toBeGreaterThan(230)
    expect(awayFromWave).toEqual({ x: 100, y: 100 })
  })
})
