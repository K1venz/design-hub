import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { HomePage } from './HomePage'

const mockUseShowcase = vi.hoisted(() => vi.fn())
const realShowcaseItem = {
  image_id: 18,
  url: 'https://img.example.com/peanut.png',
  image_type: '场景',
  caption: '花生礼盒早餐场景',
  prompt: '用户输入的暖色早餐桌商品摄影提示词',
  download_allowed: true,
  width: 1200,
  height: 800,
  recipe: {
    category: '食品',
    ratio: '1:1',
    plan: { scene: 1 },
    styling: '自然暖光',
    modifiers: {},
  },
}

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

function setShowcaseState(state: Record<string, unknown>) {
  mockUseShowcase.mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
    ...state,
  })
}

describe('HomePage', () => {
  beforeEach(() => {
    mockUseShowcase.mockReset()
    setShowcaseState({ isLoading: true })
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

  it.each([
    ['loading', { isLoading: true }],
    ['empty', { data: [] }],
    ['error', { isError: true, error: new Error('showcase unavailable') }],
  ])('hides the showcase when its state is %s', (_name, state) => {
    setShowcaseState(state)

    const html = renderHome()

    expect(html).not.toContain('看看实朴出的图')
    expect(html).not.toContain('案例即将上线')
  })

  it('renders the showcase when real content exists', () => {
    setShowcaseState({ data: [realShowcaseItem] })

    const html = renderHome()

    expect(html).toContain('看看实朴出的图')
    expect(html).toContain('花生礼盒早餐场景')
    expect(html).toContain('用户输入的暖色早餐桌商品摄影提示词')
    expect(html).toContain('下载原图')
    expect(html).toContain('break-inside-avoid')
    expect(html).toContain('columns-1')
    expect(html).not.toContain('aspect-[4/3]')
    expect(html).not.toContain('案例即将上线')
  })

  it('does not offer an original download when the admin disabled it', () => {
    setShowcaseState({
      data: [{ ...realShowcaseItem, download_allowed: false }],
    })

    expect(renderHome()).not.toContain('下载原图')
  })
})
