import { describe, expect, it } from 'vitest'

import { PREVIEW_RESULTS } from './preview-data'

describe('style preview results', () => {
  it('does not carry user-facing price fixtures', () => {
    expect(PREVIEW_RESULTS).toHaveLength(5)
    expect(PREVIEW_RESULTS.every((image) => !('cost' in image))).toBe(true)
  })
})
