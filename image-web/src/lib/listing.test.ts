import { describe, it, expect } from 'vitest'
import {
  MODIFIER_FIELDS,
  DEFAULT_LISTING_CONFIG,
  buildModifiers,
  buildListingFormData,
  parseListingEvent,
  estimateCost,
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

describe('parseListingEvent', () => {
  it('maps image_generated (url+seed, no index) to an image event', () => {
    const e = parseListingEvent('image_generated', JSON.stringify({ url: 'http://x/2.png', seed: 7 }))
    expect(e).toEqual({ kind: 'image', url: 'http://x/2.png', seed: 7 })
  })
  it('maps task_completed (with total_cost) to completed', () => {
    expect(parseListingEvent('task_completed', JSON.stringify({ total_cost: '7.14' })))
      .toEqual({ kind: 'completed', totalCost: '7.14' })
  })
  it('maps task_failed to failed with message', () => {
    expect(parseListingEvent('task_failed', JSON.stringify({ error: '超时' })))
      .toEqual({ kind: 'failed', error: '超时' })
  })
  it('maps task_started / model_called to meta', () => {
    expect(parseListingEvent('task_started', '{}')).toEqual({ kind: 'meta' })
    expect(parseListingEvent('model_called', JSON.stringify({ model: 'gpt-image-2' }))).toEqual({ kind: 'meta' })
  })
  it('returns unknown for unrecognized type', () => {
    expect(parseListingEvent('whatever', '{}')).toEqual({ kind: 'unknown' })
  })
})

describe('estimateCost', () => {
  it('multiplies n by unit cost', () => {
    expect(estimateCost(6)).toBeCloseTo(6 * 1.19, 2)
  })
})
