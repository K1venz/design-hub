import { describe, it, expect } from 'vitest'
import {
  MODIFIER_FIELDS,
  DEFAULT_LISTING_CONFIG,
  DEFAULT_PLAN,
  EDIT_MODES,
  EDIT_OVERLAY_NOTICE,
  applyListingEventToSlots,
  buildCloneBody,
  buildEditBody,
  buildModifiers,
  buildListingBody,
  buildSetListingBody,
  detailToResultSlots,
  editModeLabel,
  mergeSlotsWithDetail,
  parseListingEvent,
  planTotal,
  settledSlotCount,
  JOB_STATUS,
  type ListingConfig,
  type ListingGenerateInput,
  type ListingJobDetail,
  type ListingJobImage,
  type ResultSlot,
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
    imageModel: 'wan2.7-image-pro',
    uploadIds: ['u1', 'u2'],
    prompt: '早餐桌场景',
    ratio: '3:4',
    n: 6,
    category: 'FOOD',
    modifiers: { platform: '亚马逊', region: '美国', language: '英文' },
  }

  it('maps uploadIds → upload_ids, passes fields through, tags category', () => {
    expect(buildListingBody(input)).toEqual({
      image_model: 'wan2.7-image-pro',
      upload_ids: ['u1', 'u2'],
      prompt: '早餐桌场景',
      ratio: '3:4',
      n: 6,
      modifiers: { platform: '亚马逊', region: '美国', language: '英文' },
      category: 'FOOD',
    })
  })

  it('用户选的品类透传进请求（非 FOOD）', () => {
    expect(buildListingBody({ ...input, category: 'FASHION' }).category).toBe('FASHION')
  })
})

describe('套图 plan / buildSetListingBody', () => {
  const base = {
    imageModel: 'gpt-image-2',
    uploadIds: ['u1'],
    prompt: '花生礼盒',
    ratio: '1:1',
    category: 'FOOD' as const,
    modifiers: { platform: '淘宝天猫1688', region: '中国', language: '中文' },
  }

  it('planTotal sums all image types; default plan = 5', () => {
    expect(planTotal(DEFAULT_PLAN)).toBe(5)
    expect(planTotal({ 白底: 0, 场景: 0, 卖点: 3 })).toBe(3)
  })

  it('builds set body with plan + category, no n', () => {
    const body = buildSetListingBody({ ...base, plan: { 白底: 1, 场景: 2, 卖点: 2 }, overlayTexts: [] })
    expect(body).toEqual({
      image_model: 'gpt-image-2',
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

describe('buildCloneBody（复刻：双角色 + 两档 + prompt 选填）', () => {
  const base = {
    imageModel: 'wan2.7-image-pro',
    productUploadIds: ['p1'],
    referenceUploadIds: ['r1', 'r2'],
    cloneMode: '参考风格' as const,
    ratio: '1:1',
    modifiers: { platform: '淘宝天猫1688', region: '中国', language: '中文' },
  }

  it('builds clone body with explicit dual-role fields + category, no n/plan', () => {
    const body = buildCloneBody({ ...base, prompt: '' })
    expect(body).toEqual({
      image_model: 'wan2.7-image-pro',
      product_upload_ids: ['p1'],
      reference_upload_ids: ['r1', 'r2'],
      clone_mode: '参考风格',
      ratio: '1:1',
      prompt: '', // 选填：空=空串（后端默认 ""，dev #564 等价形态）
      modifiers: base.modifiers,
      category: 'FOOD',
    })
    expect('n' in body).toBe(false)
    expect('plan' in body).toBe(false)
  })

  it('trims the optional unified-requirement prompt', () => {
    expect(buildCloneBody({ ...base, prompt: '  文案统一中文 ' }).prompt).toBe('文案统一中文')
    expect(buildCloneBody({ ...base, prompt: '   ' }).prompt).toBe('')
  })
})

describe('buildEditBody（二次编辑：终契约 #657/#659）', () => {
  const base = {
    imageModel: 'gpt-image-2',
    sourceImageKey: 'a1b2c3d4e5f60708',
    prompt: ' 背景换成厨房木桌 ',
    ratio: '3:4',
    modifiers: { platform: '京东', region: '中国', language: '中文' },
  }

  it('delta：省略 ratio（显式传→400 契约）、不带 category（R2）、prompt trim', () => {
    const body = buildEditBody({ ...base, editMode: 'delta' })
    expect(body).toEqual({
      image_model: 'gpt-image-2',
      source_image_key: 'a1b2c3d4e5f60708',
      edit_mode: 'delta',
      prompt: '背景换成厨房木桌',
      modifiers: base.modifiers,
    })
    expect('ratio' in body).toBe(false)
    expect('category' in body).toBe(false)
    expect('n' in body).toBe(false)
    expect('plan' in body).toBe(false)
  })

  it('full：显式带 UI 选值 ratio（None=继承/显式=覆盖，UI 恒显式）', () => {
    const body = buildEditBody({ ...base, editMode: 'full' })
    expect(body.ratio).toBe('3:4')
    expect('category' in body).toBe(false)
  })

  it('档位卡文案 = prompt #651 定稿 verbatim（前端侧逐字回归闸）', () => {
    expect(EDIT_MODES.map((m) => m.key)).toEqual(['delta', 'full'])
    expect(EDIT_MODES[0].desc).toBe(
      '只按你的修改要求做最小幅度调整，构图、场景与光线基本保持原图不变；产品包装与文字以最初上传的产品图为准、不会被改动。',
    )
    expect(EDIT_MODES[0].note).toBe('未修改的区域可能有细微差异。')
    expect(EDIT_MODES[1].desc).toBe(
      '保留你的产品（包装与文字不变），按新要求重新设计整个场景与构图；画面会明显不同于原图。',
    )
    expect(EDIT_OVERLAY_NOTICE).toBe(
      '图上文案暂不支持在编辑中修改；要更换文案，请回「商品套图」重新生成卖点图。',
    )
  })
})

describe('mergeSlotsWithDetail（完成态补拉合并 → 结果区编辑入口）', () => {
  const img = (key: string, type: string | null, status = '成功', url = `http://x/${key}.png`) =>
    ({
      url,
      available: true,
      image_key: key,
      seed: 0,
      cost: '0.40',
      status,
      image_type: type,
    }) as ListingJobImage

  it('套图：成功槽按图型组内序对位、取 image_key 并刷新 url；失败槽保留 SSE 原因', () => {
    const slots = [
      { url: 'sse://b1', imageType: '白底' },
      { url: 'sse://s1', imageType: '场景' },
      { url: null, imageType: '场景', error: 'provider 500' },
      { url: 'sse://m1', imageType: '卖点' },
    ]
    const merged = mergeSlotsWithDetail(slots, [
      img('k-b1', '白底'),
      img('k-s1', '场景'),
      img('k-m1', '卖点'),
    ])
    expect(merged[0]).toEqual({ url: 'http://x/k-b1.png', imageType: '白底', imageKey: 'k-b1' })
    expect(merged[1]).toEqual({ url: 'http://x/k-s1.png', imageType: '场景', imageKey: 'k-s1' })
    expect(merged[2]).toEqual({ url: null, imageType: '场景', error: 'provider 500' }) // 失败槽不动
    expect(merged[3]).toEqual({ url: 'http://x/k-m1.png', imageType: '卖点', imageKey: 'k-m1' })
  })

  it('单图流（无图型）：同一组对位；详情失败张不参与对位', () => {
    const merged = mergeSlotsWithDetail(
      [{ url: 'sse://1' }],
      [img('k-fail', null, '失败'), img('k-ok', null)],
    )
    expect(merged[0]).toEqual({ url: 'http://x/k-ok.png', imageKey: 'k-ok' })
  })

  it('详情多余成功张（如 ISSUE-0045 异常单）不影响既有槽位', () => {
    const merged = mergeSlotsWithDetail(
      [{ url: 'sse://1' }],
      [img('k1', null), img('k2', null)],
    )
    expect(merged).toHaveLength(1)
    expect(merged[0].imageKey).toBe('k1')
  })

  it('详情缺张（补拉与落库竞态兜底）：对不上的槽保持 SSE 态', () => {
    const merged = mergeSlotsWithDetail(
      [{ url: 'sse://1', imageType: '白底' }, { url: 'sse://2', imageType: '场景' }],
      [img('k-b1', '白底')],
    )
    expect(merged[0].imageKey).toBe('k-b1')
    expect(merged[1]).toEqual({ url: 'sse://2', imageType: '场景' })
  })
})

describe('detailToResultSlots（恢复最近一单：终态详情 → 结果槽）', () => {
  const okImg = (key: string, type: string | null): ListingJobImage =>
    ({
      url: `http://x/${key}.png`,
      available: true,
      image_key: key,
      seed: 0,
      cost: '0.40',
      status: '成功',
      image_type: type,
    }) as ListingJobImage
  const failImg = (type: string | null): ListingJobImage =>
    ({
      url: null,
      available: false,
      image_key: '',
      seed: 0,
      cost: '0',
      status: '失败',
      image_type: type,
    }) as ListingJobImage
  const detail = (over: Partial<ListingJobDetail>): ListingJobDetail =>
    ({
      job_id: 'j1', prompt: '', modifiers: {}, platform: null, ratio: '1:1', size: '1024x1024',
      n: 1, status: JOB_STATUS.done, total_cost: '0', error: null,
      created_at: '2026-07-01T00:00:00Z', completed_at: null, images: [], input_urls: [], input_roles: [],
      ...over,
    }) as ListingJobDetail

  it('完成：每张成功图 → 图槽（带 image_key + image_type），无失败槽', () => {
    const slots = detailToResultSlots(
      detail({
        status: JOB_STATUS.done,
        images: [okImg('k-b1', '白底'), okImg('k-s1', '场景'), okImg('k-m1', '卖点')],
      }),
    )
    expect(slots).toEqual([
      { url: 'http://x/k-b1.png', imageType: '白底', imageKey: 'k-b1' },
      { url: 'http://x/k-s1.png', imageType: '场景', imageKey: 'k-s1' },
      { url: 'http://x/k-m1.png', imageType: '卖点', imageKey: 'k-m1' },
    ])
    expect(slots.filter((s) => s.url)).toHaveLength(3) // done=3 / total=3
  })

  it('部分完成：失败张铺失败槽（保 image_type + 顶层 error），分母含失败张 → X/N（M 失败）', () => {
    const slots = detailToResultSlots(
      detail({
        status: JOB_STATUS.partial,
        error: '卖点：boom',
        images: [okImg('k-b1', '白底'), okImg('k-s1', '场景'), failImg('卖点')],
      }),
    )
    expect(slots).toEqual([
      { url: 'http://x/k-b1.png', imageType: '白底', imageKey: 'k-b1' },
      { url: 'http://x/k-s1.png', imageType: '场景', imageKey: 'k-s1' },
      { url: null, imageType: '卖点', error: '卖点：boom' },
    ])
    expect(slots).toHaveLength(3) // 分母含失败张
    expect(slots.filter((s) => s.url)).toHaveLength(2) // done=2
    expect(slots.filter((s) => s.error)).toHaveLength(1) // 1 失败
  })

  it('部分完成缺顶层 error：失败槽回退默认原因', () => {
    const slots = detailToResultSlots(
      detail({ status: JOB_STATUS.partial, error: null, images: [okImg('k1', '白底'), failImg('场景')] }),
    )
    expect(slots[1]).toEqual({ url: null, imageType: '场景', error: '生成失败' })
  })

  it('屏蔽图片保留槽位但不暴露 URL 或下游操作 handle', () => {
    const blocked = {
      ...okImg('blocked', '场景'),
      url: null,
      available: false,
    }

    expect(
      detailToResultSlots(
        detail({ status: JOB_STATUS.done, images: [blocked] }),
      ),
    ).toEqual([
      {
        url: null,
        imageType: '场景',
        unavailable: true,
      },
    ])
  })

  it('整单失败（无图行）：合成单一失败槽，顶层原因可见', () => {
    expect(detailToResultSlots(detail({ status: JOB_STATUS.failed, error: '超时' }))).toEqual([
      { url: null, error: '超时' },
    ])
  })

  it('整单失败缺原因：失败槽回退默认文案', () => {
    expect(detailToResultSlots(detail({ status: JOB_STATUS.failed, error: null }))).toEqual([
      { url: null, error: '出图失败' },
    ])
  })

  it('空（新账号 / 无图非失败 / 进行中无图）：空数组', () => {
    expect(detailToResultSlots(detail({ status: JOB_STATUS.done, images: [] }))).toEqual([])
    expect(detailToResultSlots(detail({ status: JOB_STATUS.generating, images: [] }))).toEqual([])
  })
})

describe('editModeLabel', () => {
  it('maps delta/full to 微调/重做, falls through unknown', () => {
    expect(editModeLabel('delta')).toBe('微调')
    expect(editModeLabel('full')).toBe('重做')
    expect(editModeLabel('???')).toBe('???')
  })
})

describe('parseListingEvent', () => {
  it('parses the complete image presentation contract', () => {
    const e = parseListingEvent('image_generated', JSON.stringify({
      item_id: 'item-1',
      image_key: 'result.png',
      url: 'https://img.test/result.png?signed=1',
      seed: 7,
      image_type: '卖点',
    }))
    expect(e).toEqual({
      kind: 'image',
      itemId: 'item-1',
      imageKey: 'result.png',
      url: 'https://img.test/result.png?signed=1',
      seed: 7,
      imageType: '卖点',
    })
  })
  it.each(['item_id', 'image_key', 'url'])('rejects image events with empty %s', (field) => {
    const data: Record<string, string> = {
      item_id: 'item-1',
      image_key: 'result.png',
      url: 'https://img.test/result.png',
    }
    data[field] = ''
    expect(() => parseListingEvent('image_generated', JSON.stringify(data)))
      .toThrow(`${field} must be a non-empty string`)
  })
  it('parses image_failed with stable item identity', () => {
    expect(parseListingEvent('image_failed', JSON.stringify({
      item_id: 'item-2', image_type: '场景', error: '生成失败',
    }))).toEqual({
      kind: 'image_failed', itemId: 'item-2', imageType: '场景', error: '生成失败',
    })
  })
  it('maps task_completed without exposing accounting data', () => {
    expect(parseListingEvent('task_completed', JSON.stringify({ total_cost: '7.14' })))
      .toEqual({ kind: 'completed' })
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

describe('applyListingEventToSlots', () => {
  const slots: ResultSlot[] = [
    { url: null, imageType: '白底' },
    { url: null, imageType: '场景' },
    { url: null, imageType: '场景' },
  ]

  it('fills by image type and derives settled count', () => {
    const one = applyListingEventToSlots(slots, {
      kind: 'image', itemId: 'i1', imageKey: 'k1', url: 'https://x/1', imageType: '场景',
    })
    const two = applyListingEventToSlots(one, {
      kind: 'image_failed', itemId: 'i2', imageType: '白底', error: '失败',
    })
    expect(two[0]).toMatchObject({ itemId: 'i2', error: '失败' })
    expect(two[1]).toMatchObject({ itemId: 'i1', imageKey: 'k1', url: 'https://x/1' })
    expect(settledSlotCount(two)).toBe(2)
  })

  it('replays the same item idempotently', () => {
    const event = {
      kind: 'image', itemId: 'i1', imageKey: 'k1', url: 'https://x/1', imageType: '场景',
    } as const
    const once = applyListingEventToSlots(slots, event)
    expect(applyListingEventToSlots(once, event)).toEqual(once)
    expect(settledSlotCount(once)).toBe(1)
  })
})
