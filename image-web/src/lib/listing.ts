// Domain types & pure helpers for the listing one-shot generation flow.
// No React, no IO — unit-tested in listing.test.ts.

export const PLATFORMS = [
  '亚马逊', '淘宝天猫1688', '拼多多', '京东', 'Temu', 'TikTok Shop', '抖音电商',
] as const
export const REGIONS = ['中国', '美国', '欧洲', '俄罗斯', '东南亚'] as const
export const LANGUAGES = ['英文', '中文', '俄语', '西语'] as const
export const RATIOS = ['1:1', '3:4', '9:16', '16:9'] as const
export type Ratio = (typeof RATIOS)[number]

export const N_MIN = 1
export const N_MAX = 7

/** A dropdown that maps into the generic `modifiers` bag. Add a dropdown = add here. */
export interface ModifierField {
  key: string
  label: string
  options: readonly string[]
}
export const MODIFIER_FIELDS: ModifierField[] = [
  { key: 'platform', label: '电商平台', options: PLATFORMS },
  { key: 'region', label: '国家地区', options: REGIONS },
  { key: 'language', label: '语言', options: LANGUAGES },
]

export interface ListingConfig {
  modifiers: Record<string, string>
  ratio: Ratio
  n: number
  prompt: string
}

export const DEFAULT_LISTING_CONFIG: ListingConfig = {
  modifiers: { platform: '亚马逊', region: '美国', language: '英文' },
  ratio: '1:1',
  n: 6,
  prompt: '',
}

export function buildModifiers(config: ListingConfig): string {
  return JSON.stringify(config.modifiers)
}
