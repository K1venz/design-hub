import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { moderationPayload } from '@/lib/moderation'
import { showcaseIneligibility, showcasePayload } from '@/lib/showcase'
import { AdminGenerationsPage } from './AdminGenerationsPage'

const mockUseAdminImages = vi.hoisted(() => vi.fn())
const mockUseAdminJobs = vi.hoisted(() => vi.fn())
const mockUseModerateAdminImage = vi.hoisted(() => vi.fn())
const mockUseUpdateAdminImageShowcase = vi.hoisted(() => vi.fn())

vi.mock('@/api/admin', () => ({
  useAdminImages: mockUseAdminImages,
  useAdminJobs: mockUseAdminJobs,
  useModerateAdminImage: mockUseModerateAdminImage,
  useUpdateAdminImageShowcase: mockUseUpdateAdminImageShowcase,
}))

describe('public showcase state', () => {
  it('never leaves download enabled after an image is unpublished', () => {
    expect(showcasePayload(true, true)).toEqual({
      is_public: true,
      download_allowed: true,
    })
    expect(showcasePayload(false, true)).toEqual({
      is_public: false,
      download_allowed: false,
    })
  })

  it('explains why an image cannot be published', () => {
    const eligible = {
      status: '成功',
      moderation_status: 'normal',
      prompt: '暖色早餐桌商品摄影',
      image_type: '场景',
    }
    expect(showcaseIneligibility(eligible)).toBeNull()
    expect(
      showcaseIneligibility({ ...eligible, moderation_status: 'blocked' }),
    ).toBe('已屏蔽图片不能公开展示')
    expect(showcaseIneligibility({ ...eligible, prompt: '   ' })).toBe(
      '缺少用户提示词，不能公开展示',
    )
    expect(showcaseIneligibility({ ...eligible, image_type: null })).toBeNull()
  })
})

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
    mockUseUpdateAdminImageShowcase.mockReset()
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
    mockUseUpdateAdminImageShowcase.mockReturnValue({
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

  it('shows public status, download permission, prompt, and filters', () => {
    mockUseAdminImages.mockReturnValue({
      data: {
        items: [
          {
            image_id: 1,
            image_key: 'original.png',
            job_id: 'job-1',
            user_id: 2,
            user_email: 'user@example.com',
            user_name: '测试用户',
            prompt: '用户输入的暖色早餐桌提示词',
            image_type: '场景',
            status: '成功',
            moderation_status: 'normal',
            moderation_reason: null,
            moderation_note: null,
            moderated_by: null,
            moderated_at: null,
            is_public_showcase: true,
            showcase_download_allowed: true,
            showcase_preview_width: 1200,
            showcase_preview_height: 600,
            showcased_at: '2026-08-07T12:00:00Z',
            showcased_by: 1,
            operation_type: 'image_generation',
            model: 'gpt-image-2',
            cost: '0.05',
            created_at: '2026-08-07T11:00:00Z',
            url: 'https://example.com/image.png',
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
      },
      isLoading: false,
      isError: false,
    })

    const html = renderToStaticMarkup(
      createElement(
        MemoryRouter,
        { initialEntries: ['/admin/generations'] },
        createElement(AdminGenerationsPage),
      ),
    )

    expect(html).toContain('全部展示状态')
    expect(html).toContain('公开展示')
    expect(html).toContain('未展示')
    expect(html).toContain('展示中')
    expect(html).toContain('允许下载')
    expect(html).toContain('用户输入的暖色早餐桌提示词')
    expect(html).toContain('展示设置')
  })
})
