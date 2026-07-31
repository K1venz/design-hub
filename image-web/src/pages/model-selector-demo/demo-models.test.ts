import { describe, expect, it } from 'vitest'

import { DEMO_MODELS, brandLogoPath, filterDemoModels } from './demo-models'

describe('model selector demo fixtures', () => {
  it('contains two chat and two image models without pricing fields', () => {
    expect(DEMO_MODELS.filter((model) => model.kind === 'chat')).toHaveLength(2)
    expect(DEMO_MODELS.filter((model) => model.kind === 'image')).toHaveLength(2)
    expect(DEMO_MODELS.every((model) => !('price' in model))).toBe(true)
  })

  it('searches display name, model id, and brand case-insensitively', () => {
    expect(filterDemoModels(DEMO_MODELS, 'deepseek').map((model) => model.id))
      .toEqual(['deepseek-v4-flash'])
    expect(filterDemoModels(DEMO_MODELS, 'GPT IMAGE').map((model) => model.id))
      .toEqual(['gpt-image-2'])
    expect(filterDemoModels(DEMO_MODELS, '通义').map((model) => model.id))
      .toEqual(['wan2.7-image-pro'])
  })

  it('provides a local logo path for every fixture brand', () => {
    expect(
      DEMO_MODELS.every((model) =>
        brandLogoPath(model.brand).startsWith('/model-brands/'),
      ),
    ).toBe(true)
  })
})
