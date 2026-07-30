import { describe, expect, it } from 'vitest'

import { adminSearchParams } from './admin'

describe('adminSearchParams', () => {
  it('serializes defined filters in insertion order', () => {
    expect(
      adminSearchParams({
        limit: 20,
        offset: 0,
        status: 'failed',
      }).toString(),
    ).toBe('limit=20&offset=0&status=failed')
  })

  it('omits empty filters and preserves false', () => {
    expect(
      adminSearchParams({
        q: '',
        role: undefined,
        enabled: false,
      }).toString(),
    ).toBe('enabled=false')
  })
})
