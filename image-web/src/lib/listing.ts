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

/** 去下拉但仍随请求固定下发的值（地区固定中国 / 单图张数固定 1）。 */
export const FIXED_REGION = '中国'
export const FIXED_N = 1

// ── 套图（需求 #1，PRD §3.12.14 终值）────────────────────
// 中文 key 工作假设（dev+frontend 两票，契约落地若变只改此表）：展示名=key 零映射。
export const IMAGE_TYPE_FIELDS = [
  { key: '白底', label: '白底图', desc: '白底主图，呈现商品细节' },
  { key: '场景', label: '场景图', desc: '生活使用场景展示' },
  { key: '卖点', label: '卖点图', desc: '核心卖点与细节特写' },
] as const
export type ImageTypeKey = (typeof IMAGE_TYPE_FIELDS)[number]['key']
/** 图型 → 张数。 */
export type SetPlan = Record<ImageTypeKey, number>
export const DEFAULT_PLAN: SetPlan = { 白底: 1, 场景: 2, 卖点: 2 }
export const PLAN_TOTAL_MIN = 3
export const PLAN_TOTAL_MAX = 10
export const OVERLAY_MAX_COUNT = 2
export const OVERLAY_MAX_LEN = 12

export function planTotal(plan: SetPlan): number {
  return Object.values(plan).reduce((a, b) => a + b, 0)
}

/** 工作台出图模式：单图（现行 verified n=1 流）/ 套图（plan 流）。默认套图（三方对裁决二）。 */
export type WorkbenchMode = 'single' | 'set'

// ── 爆款图复刻（需求 #2，PRD §3.13）────────────────────
// 两档说明文案 = prompt #549 定稿版（与复刻档指令块行为逐条对应，末句预期管理必留）。
export const CLONE_MODES = [
  {
    key: '参考风格',
    desc: '学习参考图的整体风格、配色与构图思路，重新设计场景；你的产品原样出现、包装文字不变。',
  },
  {
    key: '高度复刻',
    desc: '按参考图的版式与构图复刻，把画面里的产品换成你的；你的产品包装与文字不会被改动，参考图上的产品和文案也不会出现在成品里。场景细节可能与参考图略有差异。',
  },
] as const
export type CloneModeKey = (typeof CLONE_MODES)[number]['key']
/** 默认档=参考风格（低风险档，coordinator #551 代拍）。 */
export const DEFAULT_CLONE_MODE: CloneModeKey = '参考风格'
export const CLONE_PRODUCT_MAX = 1
export const CLONE_REFERENCE_MAX = 2

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
  mode: WorkbenchMode
  modifiers: Record<string, string>
  ratio: Ratio
  /** 单图模式张数（固定 1）。 */
  n: number
  /** 套图模式结构（图型 → 张数）。 */
  plan: SetPlan
  /** 卖点图「图上文案」（≤2 条、每条 ≤12 字；卖点=0 时提交剥离）。 */
  overlayTexts: string[]
  prompt: string
}

export const DEFAULT_LISTING_CONFIG: ListingConfig = {
  mode: 'set',
  modifiers: { platform: '淘宝天猫1688', region: FIXED_REGION, language: '中文' },
  ratio: '1:1',
  n: FIXED_N,
  plan: DEFAULT_PLAN,
  overlayTexts: [],
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

// ── 套图请求（plan 流；与单图共用 ListingGenerateRequest，n/plan 互斥由后端 400 兜底）──
export interface ListingSetGenerateInput {
  uploadIds: string[]
  prompt: string
  ratio: string
  plan: SetPlan
  overlayTexts: string[]
  modifiers: Record<string, string>
}

export function buildSetListingBody(input: ListingSetGenerateInput): ListingGenerateBody {
  const body: ListingGenerateBody = {
    upload_ids: input.uploadIds,
    prompt: input.prompt,
    ratio: input.ratio,
    plan: { ...input.plan },
    modifiers: input.modifiers,
    category: LISTING_CATEGORY,
  }
  if (input.plan.卖点 > 0 && input.overlayTexts.length > 0) {
    body.overlay_texts = input.overlayTexts
  }
  return body
}

// ── 复刻请求（POST /listing/clone，schema 派生）──────────
export interface CloneGenerateInput {
  productUploadIds: string[] // ==1
  referenceUploadIds: string[] // 1..2
  cloneMode: CloneModeKey
  /** 统一复刻要求（选填，空=合法——不发字段，后端默认 ""，组装跳过用户文本层）。 */
  prompt: string
  ratio: string
  modifiers: Record<string, string>
}

export type CloneGenerateBody = Schemas['CloneRequest']

export function buildCloneBody(input: CloneGenerateInput): CloneGenerateBody {
  return {
    product_upload_ids: input.productUploadIds,
    reference_upload_ids: input.referenceUploadIds,
    clone_mode: input.cloneMode,
    ratio: input.ratio,
    // 选填：空=发空串（后端默认 ""，strip 后跳过用户文本层；dev #564 两种形态等价）
    prompt: input.prompt.trim(),
    modifiers: input.modifiers,
    category: LISTING_CATEGORY,
  }
}

/** TaskEventType values emitted by backend (design_hub/domain/enums.py).
 *  image_failed = 套图单张失败事件（dev #490 契约：payload {image_type, error}）。 */
export const LISTING_EVENT_TYPES = [
  'task_started', 'model_called', 'image_generated', 'image_failed', 'task_completed', 'task_failed',
] as const

export type ListingEvent =
  | { kind: 'image'; url: string; seed?: number; imageType?: string }
  | { kind: 'image_failed'; imageType?: string; error: string }
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
      // 单图流无 index 按到达序填槽；套图流带 image_type 落对应组。
      return {
        kind: 'image',
        url: String(d.url ?? ''),
        seed: d.seed == null ? undefined : Number(d.seed),
        imageType: d.image_type == null ? undefined : String(d.image_type),
      }
    case 'image_failed':
      return {
        kind: 'image_failed',
        imageType: d.image_type == null ? undefined : String(d.image_type),
        error: String(d.error ?? '该张生成失败'),
      }
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
