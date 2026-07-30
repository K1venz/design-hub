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
// 两档说明文案与复刻档指令块行为逐条对应，末句预期管理必留。
// 「完全复刻」= ISSUE-0062 改版（用户判决轮拍板）：连构图、机位、道具位一并照搬，
// 与后端 CloneModeRegistry 改版卡同波原子上线。
export const CLONE_MODES = [
  {
    key: '参考风格',
    desc: '学习参考图的整体风格、配色与构图思路，重新设计场景；你的产品原样出现、包装文字不变。',
  },
  {
    key: '完全复刻',
    desc: '完全照搬参考图的版式——构图、机位、道具位置一并复刻，把画面里的产品换成你的；你的产品包装与文字不会被改动，参考图上的产品和文案也不会出现在成品里。个别细节可能仍有细微差异。',
  },
] as const
export type CloneModeKey = (typeof CLONE_MODES)[number]['key']
/** 默认档=参考风格（低风险档，coordinator #551 代拍）。 */
export const DEFAULT_CLONE_MODE: CloneModeKey = '参考风格'
export const CLONE_PRODUCT_MAX = 1
export const CLONE_REFERENCE_MAX = 2

// ── 二次编辑（ISSUE-0040，PRD §3.12.13，终契约 #657/#659）──
// 档位卡文案 = prompt #651 定稿（verbatim，与第六类编辑卡行为逐条对应，回归闸在 listing.test.ts）。
export const EDIT_MODES = [
  {
    key: 'delta',
    label: '微调',
    desc: '只按你的修改要求做最小幅度调整，构图、场景与光线基本保持原图不变；产品包装与文字以最初上传的产品图为准、不会被改动。',
    // 预期管理小字必留：/images/edits 是整图重生成，锚定=尽量一致≠像素冻结，UI 不过度承诺。
    note: '未修改的区域可能有细微差异。',
    placeholder: '背景换成厨房木桌 / 光线再暖一点 / 花生再多一点…',
  },
  {
    key: 'full',
    label: '重做',
    desc: '保留你的产品（包装与文字不变），按新要求重新设计整个场景与构图；画面会明显不同于原图。',
    note: null,
    placeholder: '全新清晨野餐场景：格子布、竹篮、晨光…',
  },
] as const
export type EditModeKey = (typeof EDIT_MODES)[number]['key']
export const DEFAULT_EDIT_MODE: EditModeKey = 'delta'
/** 卖点源预期管理小字（prompt #651 定稿，verbatim）：scope ① 不改图上字 + 路径指引。 */
export const EDIT_OVERLAY_NOTICE =
  '图上文案暂不支持在编辑中修改；要更换文案，请回「商品套图」重新生成卖点图。'

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

// ── 商品品类（ISSUE B 线：注册表制，首批 5 值；卡体系品类特性块 dev 侧 CategoryCardRegistry 驱动）──
// 展示名=中文标签、请求带枚举值。加品类=扩此表 + dev 注册卡（卡↔code 逐字闸）。
export const CATEGORIES = ['FOOD', 'FASHION', 'BEAUTY', 'SHOES', 'DIGITAL'] as const
export type Category = (typeof CATEGORIES)[number]
export const CATEGORY_LABELS: Record<Category, string> = {
  FOOD: '食品',
  FASHION: '服装',
  BEAUTY: '美妆',
  SHOES: '鞋类',
  DIGITAL: '数码',
}
export const DEFAULT_CATEGORY: Category = 'FOOD'
/** category 枚举 → 展示名（未知值原样，兼容后端未来新增品类）。 */
export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category as Category] ?? category
}

export interface ListingConfig {
  mode: WorkbenchMode
  /** 商品品类（驱动品类特性卡；默认食品）。 */
  category: Category
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
  category: DEFAULT_CATEGORY,
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
  category: Category
  modifiers: Record<string, string>
}

/** JSON body for POST /listing/generate — the backend contract (two-step: upload first, reference by id). */
export type ListingGenerateBody = Schemas['ListingGenerateRequest']

/** 复刻/编辑默认品类（未提供品类选择时兜底；套图/单图走用户选择的 category）。 */
export const LISTING_CATEGORY: Category = DEFAULT_CATEGORY

export function buildListingBody(input: ListingGenerateInput): ListingGenerateBody {
  return {
    upload_ids: input.uploadIds,
    prompt: input.prompt,
    ratio: input.ratio,
    n: input.n,
    modifiers: input.modifiers,
    category: input.category,
  }
}

// ── 套图请求（plan 流；与单图共用 ListingGenerateRequest，n/plan 互斥由后端 400 兜底）──
export interface ListingSetGenerateInput {
  uploadIds: string[]
  prompt: string
  ratio: string
  plan: SetPlan
  overlayTexts: string[]
  category: Category
  modifiers: Record<string, string>
}

export function buildSetListingBody(input: ListingSetGenerateInput): ListingGenerateBody {
  const body: ListingGenerateBody = {
    upload_ids: input.uploadIds,
    prompt: input.prompt,
    ratio: input.ratio,
    plan: { ...input.plan },
    modifiers: input.modifiers,
    category: input.category,
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

// ── 编辑请求（POST /listing/edit，终契约 #657/#659）──────────
export interface EditGenerateInput {
  /** 源图稳定 handle（image_key，内容寻址 sha；owner/parent 链由服务端反解）。 */
  sourceImageKey: string
  editMode: EditModeKey
  /** 新要求（E-⑤ 必填：空 → 后端 422；前端 CTA 先禁）。 */
  prompt: string
  /** full 档 UI 选值；delta 档由 builder 省略（终契约：delta 显式传 → 400）。 */
  ratio: string
  modifiers: Record<string, string>
}

export type EditGenerateBody = Schemas['EditRequest']

export function buildEditBody(input: EditGenerateInput): EditGenerateBody {
  const body: EditGenerateBody = {
    source_image_key: input.sourceImageKey,
    edit_mode: input.editMode,
    prompt: input.prompt.trim(),
    modifiers: input.modifiers,
    // R2：编辑不收 category（组装无品类块）——不发；endpoint extra=forbid，误发即 422。
  }
  if (input.editMode === 'full') body.ratio = input.ratio // delta 省略=继承父（显式传→400）
  return body
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

/** 普通 gpt-image-2 固定单价 ¥0.05/张。CTA 估算用，完成后显示真实 total_cost。 */
export const LISTING_UNIT_COST = 0.05
export function estimateCost(n: number): number {
  return n * LISTING_UNIT_COST
}

// ── listing 历史（ISSUE-0030）──────────────────────────────
// 后端已把 image_key/upload_key 拼成完整 url（{IMAGE_PUBLIC_BASE_URL}/img/{key}，复用 ISSUE-0029），前端直接 <img src>。

/** GET /listing/jobs 列表项（裸数组）。 */
export type ListingJobSummary = Schemas['ListingJobSummaryOut']

export type ListingJobImage = Schemas['ListingImageOut']

/** 图片行成功态字面值（backend models.py ListingImageRow.status：成功|失败）。 */
export const IMAGE_SUCCESS_STATUS = '成功'

/** listing_job.status 字面值（backend infrastructure/db/models.py：生成中|完成|部分完成|失败）。
 *  注：当前后端仅在终态落库，「生成中」为设计保留、恢复流程读不到进行中历史行（见 detailToResultSlots）。 */
export const JOB_STATUS = {
  generating: '生成中',
  done: '完成',
  partial: '部分完成',
  failed: '失败',
} as const

/** edit_mode → 列表/详情徽标展示名（✎ 微调/重做）。未知值原样回显。 */
export function editModeLabel(mode: string): string {
  return EDIT_MODES.find((m) => m.key === mode)?.label ?? mode
}

// ── 完成态补拉合并（结果区「基于此图再编辑」入口）──────────
// 失败槽保留 SSE 原因不动；成功槽按图型组内序对位详情同型成功张，
// 取 image_key（挂入口）并刷新为详情新签 url（顺带解决签名过期）。
export interface ResultSlotLike {
  url: string | null
  imageType?: string
  error?: string
  imageKey?: string
  unavailable?: boolean
}

export function mergeSlotsWithDetail<T extends ResultSlotLike>(
  slots: T[],
  images: ListingJobImage[],
): T[] {
  const buckets = new Map<string, ListingJobImage[]>()
  for (const img of images) {
    if (img.status !== IMAGE_SUCCESS_STATUS) continue
    const k = img.image_type ?? ''
    const arr = buckets.get(k) ?? []
    arr.push(img)
    buckets.set(k, arr)
  }
  const cursor = new Map<string, number>()
  return slots.map((s) => {
    if (s.error || s.url === null) return s // 失败槽 / 未出槽不动
    const k = s.imageType ?? ''
    const i = cursor.get(k) ?? 0
    const img = buckets.get(k)?.[i]
    if (!img) return s
    cursor.set(k, i + 1)
    if (!img.available || !img.url) {
      return {
        ...s,
        url: null,
        imageKey: undefined,
        unavailable: true,
      }
    }
    return {
      ...s,
      url: img.url,
      imageKey: img.image_key,
    }
  })
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
export type ListingJobDetail = Schemas['ListingJobDetailOut']

// ── 工作台「恢复最近一单」（2026-07-01 设计稿）────────────────
// 服务端详情（终态权威快照）→ 结果区槽位。逐张映射（不丢失败张）：
//  - 成功张 → 图槽，带 image_key（挂「基于此图再编辑」）+ image_type（套图分组）；
//  - 失败张（部分完成，status='失败'）→ 失败槽，带 image_type + 顶层 error 原因，
//    使分母含失败张 → 结果区可如实呈现「X/N（M 失败）」；
//  - 无图行的整单失败（status='失败'）→ 合成单一失败槽让原因可见；
//  - 其余（无图、非失败）→ 空。
// 进行中（status='生成中'）不在此映射——由 SSE 续播（见 WorkbenchPage 接回逻辑）。
export function detailToResultSlots(detail: ListingJobDetail): ResultSlotLike[] {
  if (detail.images.length > 0) {
    return detail.images.map((im) =>
      im.status === IMAGE_SUCCESS_STATUS
        ? im.available && im.url
          ? {
              url: im.url,
              imageType: im.image_type ?? undefined,
              imageKey: im.image_key,
            }
          : {
              url: null,
              imageType: im.image_type ?? undefined,
              unavailable: true,
            }
        : { url: null, imageType: im.image_type ?? undefined, error: detail.error ?? '生成失败' },
    )
  }
  if (detail.status === JOB_STATUS.failed) {
    return [{ url: null, error: detail.error ?? '出图失败' }]
  }
  return []
}
