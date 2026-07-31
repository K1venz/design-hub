import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { RuntimeLogDetail, RuntimeLogListItem } from '@/api/admin'
import {
  AdminRuntimeLogsPage,
  RuntimeLogDetailContent,
} from './AdminRuntimeLogsPage'

const mockUseRuntimeLogs = vi.hoisted(() => vi.fn())
const mockUseRuntimeLogDetail = vi.hoisted(() => vi.fn())
const mockUseRuntimeLogTrace = vi.hoisted(() => vi.fn())

vi.mock('@/api/admin', () => ({
  useRuntimeLogs: mockUseRuntimeLogs,
  useRuntimeLogDetail: mockUseRuntimeLogDetail,
  useRuntimeLogTrace: mockUseRuntimeLogTrace,
}))

const row: RuntimeLogListItem = {
  event_id: 'event-2',
  timestamp: '2026-07-31T09:00:00Z',
  level: 'warning',
  service: 'worker',
  chain: 'image_generation',
  event: 'generation_provider_rejected',
  action: '模型拒绝业务请求',
  logger: 'design_hub.application.tasking.worker',
  function: '_fail_provider_rejected',
  trace_id: 'trace-1',
  job_id: 'job-1',
  model: 'gpt-image-2',
  status: 'rejected',
  duration_ms: 120,
}

const detail: RuntimeLogDetail = {
  ...row,
  request_id: 'request-1',
  item_id: 'item-1',
  operation_id: 'operation-1',
  provider: 'gpt-image-2',
  error_code: 'DomainError',
  error_type: null,
  error_summary: null,
  prompt: '完整提示词，只能在展开详情中看到',
}

describe('AdminRuntimeLogsPage', () => {
  beforeEach(() => {
    mockUseRuntimeLogs.mockReset()
    mockUseRuntimeLogDetail.mockReset()
    mockUseRuntimeLogTrace.mockReset()
    mockUseRuntimeLogs.mockReturnValue({
      data: { items: [row], total: 1, limit: 20, offset: 0 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    })
    mockUseRuntimeLogDetail.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    })
    mockUseRuntimeLogTrace.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    })
  })

  it('renders business severity, location, action and context without prompt', () => {
    const html = renderToStaticMarkup(
      createElement(
        MemoryRouter,
        { initialEntries: ['/admin/logs'] },
        createElement(AdminRuntimeLogsPage),
      ),
    )

    expect(html).toContain('运行日志')
    expect(html).toContain('业务问题')
    expect(html).toContain('worker')
    expect(html).toContain('image_generation')
    expect(html).toContain(
      'design_hub.application.tasking.worker._fail_provider_rejected',
    )
    expect(html).toContain('模型拒绝业务请求')
    expect(html).toContain('gpt-image-2')
    expect(html).toContain('rejected')
    expect(html).toContain('120 ms')
    expect(html).not.toContain('完整提示词')
  })

  it('renders complete prompt and ascending trace only in expanded content', () => {
    const trace: RuntimeLogDetail[] = [
      { ...detail, event_id: 'event-1', timestamp: '2026-07-31T08:59:00Z' },
      detail,
    ]
    const html = renderToStaticMarkup(
      createElement(RuntimeLogDetailContent, {
        detail,
        trace,
        selectedEventId: 'event-2',
      }),
    )

    expect(html).toContain('完整提示词，只能在展开详情中看到')
    expect(html.indexOf('event-1')).toBeLessThan(html.indexOf('event-2'))
    expect(html).toContain('当前事件')
  })

  it('renders retry action for API errors', () => {
    mockUseRuntimeLogs.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
    })

    const html = renderToStaticMarkup(
      createElement(
        MemoryRouter,
        { initialEntries: ['/admin/logs?level=error'] },
        createElement(AdminRuntimeLogsPage),
      ),
    )

    expect(html).toContain('运行日志加载失败')
    expect(html).toContain('重试')
  })
})
