import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import type { ImageModelSelection } from '@/components/models/image-model-context'
import { ImageModelSelector } from '@/components/models/ImageModelSelector'

const models = [
  { id: 'gpt-image-2', display_name: 'GPT Image 2', is_default: true },
]

function render(state: ImageModelSelection['state']) {
  const selection: ImageModelSelection = {
    modelId: state === 'ready' ? 'gpt-image-2' : null,
    models: state === 'empty' ? [] : models,
    state,
    select: vi.fn(),
    retry: vi.fn(),
  }
  return renderToStaticMarkup(
    createElement(ImageModelSelector, { selection }),
  )
}

describe('ImageModelSelector', () => {
  it('renders explicit catalog states for standalone image tools', () => {
    expect(render('loading')).toContain('正在加载可用图片模型')
    expect(render('error')).toContain('图片模型加载失败')
    expect(render('empty')).toContain('当前没有可用的图片模型')
    expect(render('selection_required')).toContain('请选择图片模型')
  })
})
