import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { AmbientBackground } from './AmbientBackground'
import { calculateLayerOffset } from './ambient-parallax'

describe('ambient product background', () => {
  it('renders three decorative depth planes behind the application', () => {
    const html = renderToStaticMarkup(createElement(AmbientBackground))

    expect(html).toContain('aria-hidden="true"')
    expect(html).toContain('data-depth="far"')
    expect(html).toContain('data-depth="middle"')
    expect(html).toContain('data-depth="near"')
    expect(html).toContain('ambient-orbit')
    expect(html).toContain('ambient-speck')
  })

  it('moves nearer planes farther while scroll introduces vertical depth', () => {
    expect(calculateLayerOffset(0.25, 1, -1, 200)).toEqual({ x: 4, y: -5 })
    expect(calculateLayerOffset(0.9, 1, -1, 200)).toEqual({ x: 14.4, y: -18 })
  })
})
