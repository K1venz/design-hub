import { describe, it, expect } from 'vitest'
import {
  MODIFIER_FIELDS,
  DEFAULT_LISTING_CONFIG,
  DEFAULT_PLAN,
  buildModifiers,
  buildListingBody,
  buildSetListingBody,
  parseListingEvent,
  planTotal,
  estimateCost,
  type ListingConfig,
  type ListingGenerateInput,
} from '@/lib/listing'

describe('MODIFIER_FIELDS', () => {
  it('after narrowing: only platform(4 CN) + language(zh/en) dropdowns remain', () => {
    const keys = MODIFIER_FIELDS.map((f) => f.key)
    expect(keys).toEqual(['platform', 'language'])
    const platform = MODIFIER_FIELDS.find((f) => f.key === 'platform')!
    expect(platform.options).toEqual(['淘宝天猫1688', '拼多多', '京东', '抖音电商'])
    expect(platform.options).not.toContain('亚马逊')
    expect(MODIFIER_FIELDS.find((f) => f.key === 'language')!.options).toEqual(['中文', '英文'])
  })
})

describe('DEFAULT_LISTING_CONFIG', () => {
  it('defaults are all valid post-narrowing (guards the default platform=亚马逊→400 regression)', () => {
    expect(DEFAULT_LISTING_CONFIG.modifiers).toEqual({
      platform: '淘宝天猫1688',
      region: '中国',
      language: '中文',
    })
    expect(DEFAULT_LISTING_CONFIG.n).toBe(1)
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

describe('buildListingBody', () => {
  const input: ListingGenerateInput = {
    uploadIds: ['u1', 'u2'],
    prompt: '早餐桌场景',
    ratio: '3:4',
    n: 6,
    modifiers: { platform: '亚马逊', region: '美国', language: '英文' },
  }

  it('maps uploadIds → upload_ids, passes fields through, tags MVP category FOOD', () => {
    expect(buildListingBody(input)).toEqual({
      upload_ids: ['u1', 'u2'],
      prompt: '早餐桌场景',
      ratio: '3:4',
      n: 6,
      modifiers: { platform: '亚马逊', region: '美国', language: '英文' },
      category: 'FOOD',
    })
  })
})

describe('套图 plan / buildSetListingBody', () => {
  const base = {
    uploadIds: ['u1'],
    prompt: '花生礼盒',
    ratio: '1:1',
    modifiers: { platform: '淘宝天猫1688', region: '中国', language: '中文' },
  }

  it('planTotal sums all image types; default plan = 5', () => {
    expect(planTotal(DEFAULT_PLAN)).toBe(5)
    expect(planTotal({ 白底: 0, 场景: 0, 卖点: 3 })).toBe(3)
  })

  it('builds set body with plan + category, no n', () => {
    const body = buildSetListingBody({ ...base, plan: { 白底: 1, 场景: 2, 卖点: 2 }, overlayTexts: [] })
    expect(body).toEqual({
      upload_ids: ['u1'],
      prompt: '花生礼盒',
      ratio: '1:1',
      plan: { 白底: 1, 场景: 2, 卖点: 2 },
      modifiers: base.modifiers,
      category: 'FOOD',
    })
    expect('n' in body).toBe(false)
  })

  it('carries overlay_texts only when 卖点 > 0（归 0 提交剥离）', () => {
    const withCopy = buildSetListingBody({
      ...base, plan: { 白底: 1, 场景: 1, 卖点: 1 }, overlayTexts: ['高山七彩花生'],
    })
    expect(withCopy.overlay_texts).toEqual(['高山七彩花生'])
    const stripped = buildSetListingBody({
      ...base, plan: { 白底: 2, 场景: 1, 卖点: 0 }, overlayTexts: ['高山七彩花生'],
    })
    expect('overlay_texts' in stripped).toBe(false)
  })
})

describe('parseListingEvent', () => {
  it('maps image_generated (url+seed, no index) to an image event', () => {
    const e = parseListingEvent('image_generated', JSON.stringify({ url: 'http://x/2.png', seed: 7 }))
    expect(e).toEqual({ kind: 'image', url: 'http://x/2.png', seed: 7 })
  })
  it('carries image_type through image_generated（套图落组）', () => {
    const e = parseListingEvent('image_generated', JSON.stringify({ url: 'http://x/1.png', seed: 1, image_type: '卖点' }))
    expect(e).toEqual({ kind: 'image', url: 'http://x/1.png', seed: 1, imageType: '卖点' })
  })
  it('maps image_failed to per-image failure with type + reason', () => {
    expect(parseListingEvent('image_failed', JSON.stringify({ image_type: '场景', error: 'provider 500' })))
      .toEqual({ kind: 'image_failed', imageType: '场景', error: 'provider 500' })
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
    expect(estimateCost(1)).toBeCloseTo(0.4, 2)
  })
})
