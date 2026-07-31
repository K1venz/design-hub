export type DemoModelKind = 'chat' | 'image'
export type DemoBrand = 'deepseek' | 'doubao' | 'openai' | 'alibaba'

export interface DemoModel {
  id: string
  displayName: string
  brand: DemoBrand
  brandName: string
  kind: DemoModelKind
}

export const DEMO_MODELS: DemoModel[] = [
  {
    id: 'deepseek-v4-flash',
    displayName: 'DeepSeek V4 Flash',
    brand: 'deepseek',
    brandName: 'DeepSeek',
    kind: 'chat',
  },
  {
    id: 'doubao-chat',
    displayName: 'Doubao',
    brand: 'doubao',
    brandName: '豆包',
    kind: 'chat',
  },
  {
    id: 'gpt-image-2',
    displayName: 'GPT Image 2.0',
    brand: 'openai',
    brandName: 'OpenAI',
    kind: 'image',
  },
  {
    id: 'wan2.7-image-pro',
    displayName: 'Wan 2.7 Image Pro',
    brand: 'alibaba',
    brandName: '通义万相',
    kind: 'image',
  },
]

const LOGO_PATH: Record<DemoBrand, string> = {
  deepseek: '/model-brands/deepseek.svg',
  doubao: '/model-brands/doubao.svg',
  openai: '/model-brands/openai.svg',
  alibaba: '/model-brands/wan.svg',
}

export function brandLogoPath(brand: DemoBrand): string {
  return LOGO_PATH[brand]
}

export function filterDemoModels(
  models: DemoModel[],
  query: string,
): DemoModel[] {
  const normalized = query.trim().toLocaleLowerCase()
  if (!normalized) return models
  return models.filter((model) =>
    [model.displayName, model.id, model.brandName, model.brand].some((value) =>
      value.toLocaleLowerCase().includes(normalized),
    ),
  )
}
