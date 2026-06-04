import { describe, it, expect } from 'vitest'
import {
  MODIFIER_FIELDS,
  DEFAULT_LISTING_CONFIG,
  buildModifiers,
  type ListingConfig,
} from '@/lib/listing'

describe('MODIFIER_FIELDS', () => {
  it('covers platform/region/language with user-confirmed enums', () => {
    const keys = MODIFIER_FIELDS.map((f) => f.key)
    expect(keys).toEqual(['platform', 'region', 'language'])
    const platform = MODIFIER_FIELDS.find((f) => f.key === 'platform')!
    expect(platform.options).toContain('TikTok Shop')
    expect(platform.options).toContain('抖音电商')
  })
})

describe('buildModifiers', () => {
  it('serializes only the modifier bag to JSON', () => {
    const cfg: ListingConfig = {
      ...DEFAULT_LISTING_CONFIG,
      modifiers: { platform: '京东', region: '中国', language: '中文' },
    }
    expect(buildModifiers(cfg)).toBe('{"platform":"京东","region":"中国","language":"中文"}')
  })
})
