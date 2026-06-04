import { describe, it, expect } from 'vitest'
import {
  MODIFIER_FIELDS,
  DEFAULT_LISTING_CONFIG,
  buildModifiers,
  buildListingFormData,
  type ListingConfig,
  type ListingGenerateInput,
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

describe('buildListingFormData', () => {
  const input: ListingGenerateInput = {
    images: [new File(['a'], 'a.png', { type: 'image/png' }),
             new File(['b'], 'b.png', { type: 'image/png' })],
    prompt: '早餐桌场景',
    ratio: '3:4',
    n: 6,
    modifiers: { platform: '亚马逊', region: '美国', language: '英文' },
  }

  it('appends each image under the same "images" key', () => {
    const fd = buildListingFormData(input)
    expect(fd.getAll('images')).toHaveLength(2)
  })

  it('appends scalar fields and JSON-stringified modifiers', () => {
    const fd = buildListingFormData(input)
    expect(fd.get('prompt')).toBe('早餐桌场景')
    expect(fd.get('ratio')).toBe('3:4')
    expect(fd.get('n')).toBe('6')
    expect(fd.get('modifiers')).toBe('{"platform":"亚马逊","region":"美国","language":"英文"}')
  })
})
