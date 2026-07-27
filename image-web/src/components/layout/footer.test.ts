import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { SiteFooter } from './SiteFooter'

describe('site footer legal registration', () => {
  it('renders the exact ICP and legal company identity', () => {
    const html = renderToStaticMarkup(
      createElement(
        MemoryRouter,
        null,
        createElement(SiteFooter),
      ),
    )

    expect(html).toContain('href="https://beian.miit.gov.cn"')
    expect(html).toContain('浙ICP备2026024031号-1')
    expect(html).toContain('Copyright © 2026 浙江实朴数据科技有限公司')
    expect(html).not.toContain('公安')
    expect(html).not.toContain('盾牌')
  })
})
