import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { AppShell } from './AppShell'
import { AppTopBar } from './AppTopBar'

function renderTopBar() {
  return renderToStaticMarkup(
    createElement(
      MemoryRouter,
      { initialEntries: ['/home'] },
      createElement(AppTopBar),
    ),
  )
}

describe('top navigation implementation contract', () => {
  it('uses the approved centered frame and external brand destination', () => {
    const html = renderTopBar()

    expect(html).toContain('data-global-nav-frame="true"')
    expect(html).not.toContain('max-w-[840px]')
    expect(html).toContain('grid-cols-[1fr_auto_1fr]')
    expect(html).toContain('href="https://image.sepaitech.com/"')
    expect(html).toContain('h-[30px] w-[26px]')
  })

  it('supports icon label expansion and mobile menu access', () => {
    const html = renderTopBar()

    expect(html).toContain('md:inline')
    expect(html).toContain('hover:bg-wb-tint-1')
    expect(html).toContain('hover:text-wb-brand-deep')
    expect(html).toContain('hover:-translate-y-0.5')
    expect(html).toContain('transition-[color,background-color,box-shadow,translate]')
    expect(html).toContain('aria-label="打开导航菜单"')
    expect(html).toContain('aria-label="主导航"')
  })

  it('removes retired beta and avatar UI', () => {
    const html = renderToStaticMarkup(
      createElement(
        MemoryRouter,
        { initialEntries: ['/home'] },
        createElement(AppShell, null, createElement('main')),
      ),
    )

    expect(html).not.toContain('内测免费')
    expect(html).not.toContain('data-slot="avatar"')
    expect(html).not.toContain('w-[212px]')
  })

  it('keeps application content above the ambient background scene', () => {
    const html = renderToStaticMarkup(
      createElement(
        MemoryRouter,
        { initialEntries: ['/home'] },
        createElement(AppShell, null, createElement('main', null, 'content')),
      ),
    )

    expect(html).toContain('data-ambient-background="true"')
    expect(html).toContain('relative z-10 flex min-h-0 flex-1 flex-col')
  })
})
