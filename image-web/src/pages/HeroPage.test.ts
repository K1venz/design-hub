import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { HeroPage } from './HeroPage'

const mockUseShowcase = vi.hoisted(() => vi.fn())

vi.mock('@/api/showcase', () => ({ useShowcase: mockUseShowcase }))
vi.mock('@/components/home/MarqueeHero', () => ({
  MarqueeHero: ({ images }: { images: string[] }) =>
    createElement('div', { 'data-images': images.join(',') }, '首页主视觉'),
}))

function renderHero() {
  return renderToStaticMarkup(
    createElement(
      MemoryRouter,
      { initialEntries: ['/'] },
      createElement(HeroPage),
    ),
  )
}

describe('HeroPage showcase', () => {
  beforeEach(() => mockUseShowcase.mockReset())

  it('uses only admin-selected showcase previews in the marquee', () => {
    mockUseShowcase.mockReturnValue({
      data: [
        { url: 'https://img.example.com/preview-1.webp' },
        { url: 'https://img.example.com/preview-2.webp' },
      ],
    })

    const html = renderHero()

    expect(mockUseShowcase).toHaveBeenCalledWith(true)
    expect(html).toContain('preview-1.webp')
    expect(html).toContain('preview-2.webp')
    expect(html).not.toContain('0d92feb99fbab119.jpg')
  })

  it('passes an empty marquee when no image is selected', () => {
    mockUseShowcase.mockReturnValue({ data: [] })

    expect(renderHero()).toContain('data-images=""')
  })
})
