import type { ModelCatalogItem } from '@/api/models'

interface Brand {
  name: string
  logoPath: string | null
}

const KNOWN_BRANDS: Array<{ match: RegExp; brand: Brand }> = [
  {
    match: /nano[- ]?banana|gemini/i,
    brand: { name: 'Google Gemini', logoPath: '/model-brands/gemini.svg' },
  },
  {
    match: /deepseek/i,
    brand: { name: 'DeepSeek', logoPath: '/model-brands/deepseek.svg' },
  },
  {
    match: /doubao|豆包/i,
    brand: { name: '豆包', logoPath: '/model-brands/doubao.svg' },
  },
  {
    match: /gpt|openai/i,
    brand: { name: 'OpenAI', logoPath: '/model-brands/openai.svg' },
  },
  {
    match: /wan|万相/i,
    brand: { name: '通义万相', logoPath: '/model-brands/wan.svg' },
  },
]

export function modelBrand(modelId: string): Brand {
  return (
    KNOWN_BRANDS.find(({ match }) => match.test(modelId))?.brand ?? {
      name: '其他',
      logoPath: null,
    }
  )
}

export function filterModelCatalog(
  models: ModelCatalogItem[],
  query: string,
): ModelCatalogItem[] {
  const normalized = query.trim().toLocaleLowerCase()
  if (!normalized) return models
  return models.filter((model) => {
    const brand = modelBrand(model.id)
    return [model.display_name, model.id, brand.name].some((value) =>
      value.toLocaleLowerCase().includes(normalized),
    )
  })
}
