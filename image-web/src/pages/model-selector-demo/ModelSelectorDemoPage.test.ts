import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { ModelSelectorDemoPage } from './ModelSelectorDemoPage'

describe('ModelSelectorDemoPage', () => {
  it('renders the three comparable selector styles in one shared study', () => {
    const html = renderToStaticMarkup(createElement(ModelSelectorDemoPage))

    expect(html).toContain('A · DeerFlow 极简型')
    expect(html).toContain('B · 品牌卡片型')
    expect(html).toContain('C · 双模型紧凑型')
    expect(html).toContain('三款使用同一组模型与选择状态')
    expect(html).toContain('模拟生成中')
  })
})
