import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it } from 'vitest'

import { BackgroundConfigPanel } from '@/components/listing/BackgroundConfigPanel'

describe('BackgroundConfigPanel', () => {
  it('sets an honest source-image expectation before background replacement', () => {
    const html = renderToStaticMarkup(
      createElement(
        QueryClientProvider,
        { client: new QueryClient() },
        createElement(BackgroundConfigPanel, {
          state: {
            source: null,
            backgroundMode: 'description',
            description: '',
            reference: null,
            instruction: '',
          },
          ratio: null,
          pending: false,
          onChange: () => undefined,
          onSourceUpload: () => undefined,
          onReferenceUpload: () => undefined,
          onSourceDimensions: () => undefined,
          onGenerate: () => undefined,
        }),
      ),
    )

    expect(html).toContain('主体清晰、背景可分离')
    expect(html).toContain('包装文字会尽量保留')
    expect(html).toContain('海报大段文案和复杂排版可能变化')
  })
})
