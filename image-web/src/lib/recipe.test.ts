import { describe, expect, it } from 'vitest'

import { JOB_STATUS, type ListingJobDetail, type ListingJobImage } from '@/lib/listing'
import type { components } from '@/api/schema'
import { jobToRecipe, recipeToPrefill, showcaseRecipeToPrefill } from '@/lib/recipe'

const img = (type: string | null, status = '成功'): ListingJobImage =>
  ({ url: `http://x/${type}.png`, image_key: `k-${type}`, seed: 0, cost: '0.40', status, image_type: type }) as ListingJobImage

const detail = (over: Partial<ListingJobDetail>): ListingJobDetail =>
  ({
    job_id: 'j1', prompt: '暖色厨房桌面', modifiers: { platform: '京东', language: '中文', region: '中国' },
    platform: '京东', ratio: '3:4', size: '1024x1536', n: 5, status: JOB_STATUS.done, total_cost: '2',
    error: null, created_at: '2026-07-01T00:00:00Z', completed_at: null, images: [], input_urls: [], input_roles: [],
    ...over,
  }) as ListingJobDetail

describe('jobToRecipe', () => {
  it('套图：从每张 image_type 计数还原图型配比、可复用', () => {
    const r = jobToRecipe(detail({ images: [img('白底'), img('场景'), img('场景'), img('卖点'), img('卖点')] }))
    expect(r.kind).toBe('set')
    expect(r.reusable).toBe(true)
    expect(r.plan).toEqual({ 白底: 1, 场景: 2, 卖点: 2 })
    expect(r.prompt).toBe('暖色厨房桌面')
    expect(r.ratio).toBe('3:4')
    expect(r.platform).toBe('京东')
  })

  it('套图：失败张仍计入配比（忠实还原当初 plan）', () => {
    const r = jobToRecipe(detail({ status: JOB_STATUS.partial, images: [img('白底'), img('卖点', '失败')] }))
    expect(r.plan).toEqual({ 白底: 1, 场景: 0, 卖点: 1 })
  })

  it('复刻单：kind=clone、带 cloneMode、不可复用', () => {
    const r = jobToRecipe(detail({ clone_mode: '高度复刻', images: [img(null)] }))
    expect(r.kind).toBe('clone')
    expect(r.cloneMode).toBe('高度复刻')
    expect(r.reusable).toBe(false)
  })

  it('编辑单：kind=edit、带 editMode、不可复用', () => {
    const r = jobToRecipe(detail({ edit_mode: 'delta', images: [img(null)] }))
    expect(r.kind).toBe('edit')
    expect(r.editMode).toBe('delta')
    expect(r.reusable).toBe(false)
  })

  it('单图（无图型标签）：kind=single、不可复用（复用按钮只做套图单）', () => {
    const r = jobToRecipe(detail({ n: 1, images: [img(null)] }))
    expect(r.kind).toBe('single')
    expect(r.reusable).toBe(false)
  })
})

describe('recipeToPrefill', () => {
  it('套图：产出 set 预填（mode/plan/ratio/prompt/modifiers），不含 uploads/overlayTexts', () => {
    const prefill = recipeToPrefill(jobToRecipe(detail({ images: [img('白底'), img('场景'), img('卖点')] })))
    expect(prefill).toEqual({
      mode: 'set',
      ratio: '3:4',
      prompt: '暖色厨房桌面',
      plan: { 白底: 1, 场景: 1, 卖点: 1 },
      modifiers: { platform: '京东', language: '中文', region: '中国' },
    })
    expect(prefill).not.toHaveProperty('overlayTexts')
  })

  it('非法/未知 ratio → 回退 1:1', () => {
    const prefill = recipeToPrefill(jobToRecipe(detail({ ratio: '21:9', images: [img('白底')] })))
    expect(prefill?.ratio).toBe('1:1')
  })

  it('不可复用（复刻/编辑/单图）→ null', () => {
    expect(recipeToPrefill(jobToRecipe(detail({ clone_mode: '参考风格', images: [img(null)] })))).toBeNull()
    expect(recipeToPrefill(jobToRecipe(detail({ edit_mode: 'full', images: [img(null)] })))).toBeNull()
    expect(recipeToPrefill(jobToRecipe(detail({ n: 1, images: [img(null)] })))).toBeNull()
  })

  it('预填 modifiers/plan 是副本（不与原 job 详情共享引用）', () => {
    const r = jobToRecipe(detail({ images: [img('白底')] }))
    const prefill = recipeToPrefill(r)!
    expect(prefill.modifiers).not.toBe(r.modifiers)
    expect(prefill.plan).not.toBe(r.plan)
  })
})

describe('showcaseRecipeToPrefill（落点 B「做同款」）', () => {
  const recipe = (over: Partial<components['schemas']['RecipeOut']> = {}): components['schemas']['RecipeOut'] => ({
    category: 'FOOD', ratio: '9:16', plan: { 白底: 1, 场景: 2, 卖点: 2 }, styling: '窗边暖光野餐',
    modifiers: { platform: '抖音电商', language: '中文', region: '中国' }, ...over,
  })

  it('RecipeOut → set 预填（styling→prompt、plan 三型齐、modifiers 副本）', () => {
    const prefill = showcaseRecipeToPrefill(recipe())
    expect(prefill).toEqual({
      mode: 'set', ratio: '9:16', prompt: '窗边暖光野餐',
      plan: { 白底: 1, 场景: 2, 卖点: 2 },
      modifiers: { platform: '抖音电商', language: '中文', region: '中国' },
    })
  })

  it('plan 缺某图型 → 补 0；非法 ratio → 回退 1:1', () => {
    const prefill = showcaseRecipeToPrefill(recipe({ ratio: '2:3', plan: { 白底: 1 } }))
    expect(prefill.ratio).toBe('1:1')
    expect(prefill.plan).toEqual({ 白底: 1, 场景: 0, 卖点: 0 })
  })
})
