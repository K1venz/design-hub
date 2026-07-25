import { describe, expect, it } from 'vitest'

import { PREVIEW_RESULTS } from './preview-data'

describe('style preview pricing', () => {
  it('uses the fixed ordinary image price', () => {
    expect(new Set(PREVIEW_RESULTS.map((image) => image.cost))).toEqual(
      new Set(['¥0.05']),
    )
  })
})
