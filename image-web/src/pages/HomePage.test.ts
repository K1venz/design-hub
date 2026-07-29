import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { HomePage } from './HomePage'

const mockUseShowcase = vi.hoisted(() => vi.fn())

vi.mock('@/api/showcase', () => ({
  useShowcase: mockUseShowcase,
}))

vi.mock('@/components/listing/ShowcaseDetailDialog', () => ({
  ShowcaseDetailDialog: () => null,
}))

function renderHome() {
  return renderToStaticMarkup(
    createElement(
      MemoryRouter,
      { initialEntries: ['/home'] },
      createElement(HomePage),
    ),
  )
}

describe('HomePage', () => {
  beforeEach(() => {
    mockUseShowcase.mockReset()
    mockUseShowcase.mockReturnValue({ data: undefined })
  })

  it('renders one guided chat entry and only real tool destinations', () => {
    const html = renderHome()

    expect(html).toContain('aria-label="描述你的设计需求"')
    expect(html).toContain(
      'placeholder="用大白话描述你的产品和想要的效果，实朴帮你完成白底、场景、卖点等电商图片。',
    )
    expect(html).toContain('添加商品图')
    expect(html).toContain('商品套图')
    expect(html).toContain('爆款图复刻')
    expect(html).toContain('单图出图')
    expect(html).toContain('二次编辑')
    expect(html).toContain('出图历史')
    expect(html).not.toContain('纯白底 · 平台合规主图')
    expect(html).not.toContain('生活使用场景 · 有氛围')
    expect(html).not.toContain('AI 消除')
    expect(html).not.toContain('智能扩图')
  })
})
