import { createElement, type ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import type { ModelConfig } from '@/api/admin'
import {
  filterModelsByType,
  modelTypeLabel,
} from '@/lib/admin-models'

vi.mock('@/api/admin', () => ({
  useModels: () => ({
    data: [
      {
        name: 'doubao-vision',
        display_name: '豆包 Seed 2.0 Lite 视觉',
        model_type: 'vision',
        provider_type: 'openai_compat_chat',
        base_url: 'https://ark.example.test/api/v3',
        model: 'doubao-seed-2-0-lite-260428',
        unit_cost: '0.0000',
        enabled: false,
        is_default: true,
        revision: 1,
        verified_at: null,
        extra: { thinking_disabled: true },
        credentials: {
          has_credentials: true,
          configured_fields: { api_key: true },
        },
      },
    ] satisfies ModelConfig[],
    isLoading: false,
    isError: false,
  }),
}))

vi.mock('@/components/admin/ModelConfigDialog', () => ({
  ModelConfigDialog: ({ trigger }: { trigger: ReactNode }) => trigger,
}))

vi.mock('@/components/admin/ModelRowActions', () => ({
  ModelRowActions: () => createElement('span', null, '模型操作'),
}))

import { AdminModelsPage } from '@/pages/AdminModelsPage'

describe('admin visual model management', () => {
  it('renders the visual model filter and type label', () => {
    const html = renderToStaticMarkup(createElement(AdminModelsPage))

    expect(html).toContain('视觉模型')
    expect(html).toContain('豆包 Seed 2.0 Lite 视觉')
    expect(html).toContain('>视觉<')
  })

  it('filters visual models independently from Chat models', () => {
    const models = [
      { name: 'doubao-chat', model_type: 'chat' },
      { name: 'doubao-vision', model_type: 'vision' },
    ] as ModelConfig[]

    expect(filterModelsByType(models, 'vision').map((model) => model.name)).toEqual([
      'doubao-vision',
    ])
    expect(modelTypeLabel('vision')).toBe('视觉')
  })
})
