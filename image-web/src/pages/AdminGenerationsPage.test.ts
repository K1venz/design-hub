import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { moderationPayload } from '@/lib/moderation'
import { AdminGenerationsPage } from './AdminGenerationsPage'

const mockUseAdminImages = vi.hoisted(() => vi.fn())
const mockUseAdminJobs = vi.hoisted(() => vi.fn())
const mockUseModerateAdminImage = vi.hoisted(() => vi.fn())

vi.mock('@/api/admin', () => ({
  useAdminImages: mockUseAdminImages,
  useAdminJobs: mockUseAdminJobs,
  useModerateAdminImage: mockUseModerateAdminImage,
}))

describe('image moderation payload', () => {
  it('requires a reason when blocking', () => {
    expect(moderationPayload('blocked', '', 'review')).toBeNull()
    expect(
      moderationPayload('blocked', 'illegal', 'manual review'),
    ).toEqual({
      status: 'blocked',
      reason: 'illegal',
      note: 'manual review',
    })
  })

  it('clears the reason and note when restoring', () => {
    expect(
      moderationPayload('normal', 'illegal', 'stale note'),
    ).toEqual({
      status: 'normal',
      reason: null,
      note: null,
    })
  })
})

describe('AdminGenerationsPage', () => {
  beforeEach(() => {
    mockUseAdminImages.mockReset()
    mockUseAdminJobs.mockReset()
    mockUseModerateAdminImage.mockReset()
    mockUseAdminImages.mockReturnValue({
      data: { items: [], total: 0, limit: 20, offset: 0 },
      isLoading: false,
      isError: false,
    })
    mockUseAdminJobs.mockReturnValue({
      data: { items: [], total: 0, limit: 20, offset: 0 },
      isLoading: false,
      isError: false,
    })
    mockUseModerateAdminImage.mockReturnValue({
      mutateAsync: vi.fn(),
      isPending: false,
    })
  })

  it('renders the direct admin generations route and empty state', () => {
    const html = renderToStaticMarkup(
      createElement(
        MemoryRouter,
        { initialEntries: ['/admin/generations'] },
        createElement(AdminGenerationsPage),
      ),
    )

    expect(html).toContain('出图管理')
    expect(html).toContain('图片审核')
    expect(html).toContain('当前筛选下没有图片')
  })
})
