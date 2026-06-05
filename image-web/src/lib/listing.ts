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

/** Result of POST /uploads — `id` is the storage key, `url` the proxy GET /uploads/{id}. */
export interface UploadedImage {
  id: string
  url: string
}

export interface ListingGenerateInput {
  uploadIds: string[]
  prompt: string
  ratio: string
  n: number
  modifiers: Record<string, string>
}

/** JSON body for POST /listing/generate (two-step: upload first, reference by id). */
export interface ListingGenerateBody {
  upload_ids: string[]
  prompt: string
  ratio: string
  n: number
  modifiers: Record<string, string>
}

export function buildListingBody(input: ListingGenerateInput): ListingGenerateBody {
  return {
    upload_ids: input.uploadIds,
    prompt: input.prompt,
    ratio: input.ratio,
    n: input.n,
    modifiers: input.modifiers,
  }
}

/** TaskEventType values emitted by backend (design_hub/domain/enums.py). */
export const LISTING_EVENT_TYPES = [
  'task_started', 'model_called', 'image_generated', 'task_completed', 'task_failed',
] as const

export type ListingEvent =
  | { kind: 'image'; url: string; seed?: number }
  | { kind: 'completed'; totalCost?: string }
  | { kind: 'failed'; error: string }
  | { kind: 'meta' } // task_started / model_called — nothing to render
  | { kind: 'unknown' }

/**
 * Map a named SSE event to a typed ListingEvent.
 * `type` = SSE `event:` line; `rawData` = `data:` line JSON (payload only, NO type field).
 * Backend contract: routes/listing.py `_sse()` + application/listing/commands.py.
 */
export function parseListingEvent(type: string, rawData: string): ListingEvent {
  const d = JSON.parse(rawData) as Record<string, unknown>
  switch (type) {
    case 'image_generated':
      // Backend sends no index; caller fills slots in arrival order.
      return { kind: 'image', url: String(d.url ?? ''), seed: d.seed == null ? undefined : Number(d.seed) }
    case 'task_completed':
      return { kind: 'completed', totalCost: d.total_cost == null ? undefined : String(d.total_cost) }
    case 'task_failed':
      return { kind: 'failed', error: String(d.error ?? '出图失败') }
    case 'task_started':
    case 'model_called':
      return { kind: 'meta' }
    default:
      return { kind: 'unknown' }
  }
}

/** ⚠️ Placeholder unit price pending PM/backend (ISSUE-0021). CTA estimate only; show total_cost on completion. */
export const LISTING_UNIT_COST = 1.19
export function estimateCost(n: number): number {
  return n * LISTING_UNIT_COST
}

// ── listing 历史（ISSUE-0030）──────────────────────────────
// 后端已把 image_key/upload_key 拼成完整 url（{IMAGE_PUBLIC_BASE_URL}/img/{key}，复用 ISSUE-0029），前端直接 <img src>。

/** GET /listing/jobs 列表项（裸数组）。 */
export interface ListingJobSummary {
  job_id: string
  status: string
  platform: string
  ratio: string
  n: number
  total_cost: string | number
  created_at: string
  first_image_url: string | null
  image_count: number
}

export interface ListingJobImage {
  url: string
  seed: number | null
  cost: string | number
  status: string
}

/** 历史展示用格式化（纯函数）。 */
export function fmtListingTime(s: string): string {
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? s : d.toLocaleString('zh-CN', { hour12: false })
}
export function fmtListingCost(c: string | number): string {
  const n = Number(c)
  return Number.isNaN(n) ? String(c) : `¥${n.toFixed(2)}`
}

/** GET /listing/jobs/{id} 详情。 */
export interface ListingJobDetail {
  job_id: string
  prompt: string
  modifiers: Record<string, string>
  platform: string
  ratio: string
  size: string
  n: number
  status: string
  total_cost: string | number
  error: string | null
  created_at: string
  completed_at: string | null
  images: ListingJobImage[]
  input_urls: string[]
}
