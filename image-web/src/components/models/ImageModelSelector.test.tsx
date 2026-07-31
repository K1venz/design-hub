import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import type { ImageModelSelection } from '@/components/models/image-model-context'
import { ImageModelSelector } from '@/components/models/ImageModelSelector'

const models = [
  { id: 'gpt-image-2', display_name: 'GPT Image 2', is_default: true },
]

function render(
  state: ImageModelSelection['state'],
  overrides: Partial<ImageModelSelection> = {},
) {
  const selection: ImageModelSelection = {
    modelId: state === 'ready' ? 'gpt-image-2' : null,
    models: state === 'empty' ? [] : models,
    state,
    select: vi.fn(),
    retry: vi.fn(),
    ...overrides,
  }
  return renderToStaticMarkup(
    createElement(ImageModelSelector, { selection }),
  )
}

describe('ImageModelSelector', () => {
  it('renders a distinct accessible loading state', () => {
    const html = render('loading')
    expect(html).toContain('role="status"')
    expect(html).toContain('正在加载可用图片模型')
  })

  it('renders an error with an explicit retry action', () => {
    const html = render('error')
    expect(html).toContain('role="alert"')
    expect(html).toContain('图片模型加载失败')
    expect(html).toContain('重试')
  })

  it('renders an explicit empty catalog state', () => {
    const html = render('empty')
    expect(html).toContain('当前没有可用的图片模型')
    expect(html).toContain('联系管理员')
  })

  it('renders stale selection guidance without selecting another model', () => {
    const html = render('selection_required')
    expect(html).toContain('请选择图片模型')
    expect(html).toContain('之前选择的模型已不可用')
    expect(html).not.toContain('selected=""')
  })

  it('exposes a native labelled selector with help text and runtime locking', () => {
    const selection: ImageModelSelection = {
      modelId: 'gpt-image-2',
      models,
      state: 'ready',
      select: vi.fn(),
      retry: vi.fn(),
    }
    const html = renderToStaticMarkup(
      createElement(ImageModelSelector, { selection, disabled: true }),
    )
    expect(html).toContain('for="image-model-selector"')
    expect(html).toContain('aria-describedby="image-model-help"')
    expect(html).toContain('disabled=""')
    expect(html).toContain('任务运行期间不能切换模型')
  })
})
