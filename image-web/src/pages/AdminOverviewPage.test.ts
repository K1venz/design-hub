import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AdminOverviewPage } from './AdminOverviewPage'

const mockUseAdminOverview = vi.hoisted(() => vi.fn())
const mockUseAdminImages = vi.hoisted(() => vi.fn())
const mockUseAdminModelCalls = vi.hoisted(() => vi.fn())

vi.mock('@/api/admin', () => ({
  useAdminOverview: mockUseAdminOverview,
  useAdminImages: mockUseAdminImages,
  useAdminModelCalls: mockUseAdminModelCalls,
}))

const overview = {
  start: '2026-07-23T00:00:00Z',
  end: '2026-07-30T00:00:00Z',
  registered_users: 18,
  active_users: 7,
  jobs: 20,
  successful_images: 42,
  image_calls: 12,
  image_succeeded: 10,
  image_failed: 1,
  image_uncertain: 1,
  image_retries: 2,
  chat_calls: 9,
  chat_input_tokens: 300,
  chat_output_tokens: 120,
  chat_total_tokens: 420,
  platform_cost: '8.40',
  average_latency_ms: 1350,
  failure_rate: 0.0833,
}

function renderPage() {
  return renderToStaticMarkup(
    createElement(
      MemoryRouter,
      { initialEntries: ['/admin'] },
      createElement(AdminOverviewPage),
    ),
  )
}

describe('AdminOverviewPage', () => {
  beforeEach(() => {
    mockUseAdminOverview.mockReset()
    mockUseAdminImages.mockReset()
    mockUseAdminModelCalls.mockReset()
    mockUseAdminOverview.mockReturnValue({
      data: overview,
      isLoading: false,
      isError: false,
    })
    mockUseAdminImages.mockReturnValue({
      data: { items: [], total: 0, limit: 4, offset: 0 },
      isLoading: false,
      isError: false,
    })
    mockUseAdminModelCalls.mockReturnValue({
      data: { items: [], total: 0, limit: 5, offset: 0 },
      isLoading: false,
      isError: false,
    })
  })

  it('prioritizes image call count and real chat usage', () => {
    const html = renderPage()

    expect(html).toContain('GPT Image 2 调用')
    expect(html).toContain('>12<')
    expect(html).toContain('豆包总 Token')
    expect(html).toContain('>420<')
    expect(html).toContain('平台核算成本')
    expect(html).toContain('调用统计自本版本上线后开始记录')
  })

  it('renders explicit loading, error, and empty states', () => {
    mockUseAdminOverview.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    })
    expect(renderPage()).toContain('正在加载管理数据')

    mockUseAdminOverview.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    })
    expect(renderPage()).toContain('管理数据加载失败')

    mockUseAdminOverview.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    })
    expect(renderPage()).toContain('暂无管理数据')
  })
})
