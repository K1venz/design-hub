// Domain types & pure helpers for the listing one-shot generation flow.
// No React, no IO — unit-tested in listing.test.ts.
// Request/response shapes are derived from the generated OpenAPI schema (single
// source of truth); only frontend-only shapes (form input, SSE events) stay local.

import type { components } from '@/api/schema'

type Schemas = components['schemas']

// 收窄轮（PRD §3.12.2/§3.12.12）：平台 4 国内、语言 {中文,英文}；地区固定中国、张数固定 1（去下拉、请求固定带值，后端只收窄枚举不做默认注入）。
export const PLATFORMS = ['淘宝天猫1688', '拼多多', '京东', '抖音电商'] as const
export const LANGUAGES = ['中文', '英文'] as const
export const RATIOS = ['1:1', '3:4', '9:16', '16:9'] as const
export type Ratio = (typeof RATIOS)[number]

/** 去下拉但仍随请求固定下发的值（地区固定中国 / 张数固定 1）。 */
export const FIXED_REGION = '中国'
export const FIXED_N = 1

/** A dropdown that maps into the generic `modifiers` bag. Add a dropdown = add here. */
export interface ModifierField {
  key: string
  label: string
  options: readonly string[]
}
export const MODIFIER_FIELDS: ModifierField[] = [
  { key: 'platform', label: '电商平台', options: PLATFORMS },
  { key: 'language', label: '语言', options: LANGUAGES },
]

export interface ListingConfig {
  modifiers: Record<string, string>
  ratio: Ratio
  n: number
  prompt: string
}

export const DEFAULT_LISTING_CONFIG: ListingConfig = {
  modifiers: { platform: '淘宝天猫1688', region: FIXED_REGION, language: '中文' },
  ratio: '1:1',
  n: FIXED_N,
  prompt: '',
}

export function buildModifiers(config: ListingConfig): string {
  return JSON.stringify(config.modifiers)
}

/** POST /uploads 响应（具名 UploadResponse{id,url}）：id=存储 key，url=预览代理 GET /uploads/{id}. */
export type UploadedImage = Schemas['UploadResponse']

export interface ListingGenerateInput {
  uploadIds: string[]
  prompt: string
  ratio: string
  n: number
  modifiers: Record<string, string>
}

/** JSON body for POST /listing/generate — the backend contract (two-step: upload first, reference by id). */
export type ListingGenerateBody = Schemas['ListingGenerateRequest']

/**
 * MVP 单品类：listing 当前只做花生 / FOOD，category 硬编码 FOOD（后端 default 也是 FOOD，
 * 驱动花生保真卡）。将来扩多品类 = 加品类选择 UI 并把它提到 ListingGenerateInput。
 */
export const LISTING_CATEGORY = 'FOOD'

export function buildListingBody(input: ListingGenerateInput): ListingGenerateBody {
  return {
    upload_ids: input.uploadIds,
    prompt: input.prompt,
    ratio: input.ratio,
    n: input.n,
    modifiers: input.modifiers,
    category: LISTING_CATEGORY,
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

/** base gpt-image-2 单价 ¥0.40/张（PM 拍板 / 后端 model_config）。CTA 估算用，完成后显示真实 total_cost。 */
export const LISTING_UNIT_COST = 0.4
export function estimateCost(n: number): number {
  return n * LISTING_UNIT_COST
}

// ── listing 历史（ISSUE-0030）──────────────────────────────
// 后端已把 image_key/upload_key 拼成完整 url（{IMAGE_PUBLIC_BASE_URL}/img/{key}，复用 ISSUE-0029），前端直接 <img src>。

/** GET /listing/jobs 列表项（裸数组）。 */
export type ListingJobSummary = Schemas['ListingJobSummaryOut']

export type ListingJobImage = Schemas['ListingImageOut']

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
export type ListingJobDetail = Schemas['ListingJobDetailOut']
