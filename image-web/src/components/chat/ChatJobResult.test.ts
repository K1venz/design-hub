import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { ChatJobResultView } from '@/components/chat/ChatJobResult'
import {
  IMAGE_SUCCESS_STATUS,
  JOB_STATUS,
  type ListingJobDetail,
  type ListingJobImage,
} from '@/lib/listing'

const actions = {
  onPreview: () => undefined,
  onEdit: () => undefined,
  onBackground: () => undefined,
  onReversePrompt: () => undefined,
}

const detail = (overrides: Partial<ListingJobDetail> = {}): ListingJobDetail => ({
  job_id: 'job-1',
  prompt: '',
  modifiers: {},
  platform: null,
  ratio: '1:1',
  size: '1024x1024',
  n: 3,
  status: JOB_STATUS.generating,
  total_cost: '0',
  error: null,
  created_at: '2026-08-06T00:00:00Z',
  completed_at: null,
  images: [],
  input_urls: [],
  input_roles: [],
  ...overrides,
} as ListingJobDetail)

const successfulImage = {
  url: 'https://img/k1.png',
  available: true,
  image_key: 'k1',
  seed: 1,
  cost: '0.05',
  status: IMAGE_SUCCESS_STATUS,
  image_type: '白底',
} as ListingJobImage

describe('ChatJobResultView', () => {
  it('renders persisted progress with completed and pending slots', () => {
    const html = renderToStaticMarkup(createElement(ChatJobResultView, {
      detail: detail({ images: [successfulImage] }),
      loading: false,
      error: false,
      ...actions,
    }))

    expect(html).toContain('1/3')
    expect(html).toContain('图片生成中')
    expect(html).toContain('https://img/k1.png')
  })

  it('renders explicit loading and unavailable states', () => {
    const renderView = (loading: boolean, error: boolean) =>
      renderToStaticMarkup(createElement(ChatJobResultView, {
        detail: undefined,
        loading,
        error,
        ...actions,
      }))

    expect(renderView(true, false)).toContain('正在载入出图结果')
    expect(renderView(false, true)).toContain('出图结果已失效或无法载入')
  })
})
