import { describe, expect, it } from 'vitest'

import {
  backgroundWorkbenchStateFromPrefill,
  buildBackgroundReplaceBody,
  buildReversePromptBody,
  closestSupportedRatio,
} from '@/lib/image-tools'

describe('background replacement request', () => {
  it('builds a strict upload + description request and trims the description', () => {
    expect(
      buildBackgroundReplaceBody({
        source: { kind: 'upload', uploadId: 'u/product.png' },
        background: {
          kind: 'description',
          description: '  明亮的现代咖啡店  ',
        },
      }),
    ).toEqual({
      source: { kind: 'upload', upload_id: 'u/product.png' },
      background: {
        kind: 'description',
        description: '明亮的现代咖啡店',
      },
    })
  })

  it('builds a generated + reference request and trims the optional instruction', () => {
    expect(
      buildBackgroundReplaceBody({
        source: { kind: 'generated', imageKey: 'generated/result.png' },
        background: {
          kind: 'reference',
          uploadId: 'u/background.png',
          instruction: '  商品居中，背景轻微虚化  ',
        },
      }),
    ).toEqual({
      source: { kind: 'generated', image_key: 'generated/result.png' },
      background: {
        kind: 'reference',
        upload_id: 'u/background.png',
        instruction: '商品居中，背景轻微虚化',
      },
    })
  })

  it('uses the same source contract for prompt reversal', () => {
    expect(
      buildReversePromptBody({
        kind: 'generated',
        imageKey: 'generated/result.png',
      }),
    ).toEqual({
      source: { kind: 'generated', image_key: 'generated/result.png' },
    })
  })
})

describe('background workbench prefill', () => {
  it('restores upload source and description without placing ids in the URL', () => {
    expect(
      backgroundWorkbenchStateFromPrefill(
        {
          source_kind: 'upload',
          source_id: 'u/product.png',
          background_kind: 'description',
          background_description: '极简摄影棚',
        },
        (id) => `/api/uploads/${id}?access_token=T`,
      ),
    ).toEqual({
      source: {
        kind: 'upload',
        uploadId: 'u/product.png',
        previewUrl: '/api/uploads/u/product.png?access_token=T',
      },
      backgroundMode: 'description',
      description: '极简摄影棚',
      reference: null,
      instruction: '',
    })
  })

  it('keeps a generated result preview supplied by an in-app result card', () => {
    expect(
      backgroundWorkbenchStateFromPrefill(
        {
          source_kind: 'generated',
          source_id: 'generated/result.png',
          source_url: 'https://img/result.png',
        },
        () => '',
      ).source,
    ).toEqual({
      kind: 'generated',
      imageKey: 'generated/result.png',
      previewUrl: 'https://img/result.png',
    })
  })
})

describe('closestSupportedRatio', () => {
  it.each([
    [1000, 1000, '1:1'],
    [900, 1200, '3:4'],
    [1200, 900, '4:3'],
    [900, 1600, '9:16'],
    [1600, 900, '16:9'],
  ])('maps %d×%d to %s', (width, height, expected) => {
    expect(closestSupportedRatio(width, height)).toBe(expected)
  })
})
