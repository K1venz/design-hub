// 「配方」= 用户可复用输入的纯函数域（ISSUE-0053）。
// 铁律：配方只含用户输入（图型配比/比例/风格描述=job.prompt/平台/modifiers），
// 绝不含组装后的内部卡 prompt（没存·核心资产不外泄·展示了也复用不了）。
// 卖点文案(overlay_texts) 未持久化 → 按裁决 (a) 不进配方（用户自填），见 ISSUE-0053。

import {
  DEFAULT_PLAN,
  IMAGE_TYPE_FIELDS,
  RATIOS,
  type ImageTypeKey,
  type ListingConfig,
  type ListingJobDetail,
  type Ratio,
  type SetPlan,
} from '@/lib/listing'

/** 出图种类：套图（可复用）/ 单图 / 复刻 / 编辑（后三者仅展示配方徽标，不做一键复用）。 */
export type RecipeKind = 'set' | 'single' | 'clone' | 'edit'

export interface Recipe {
  kind: RecipeKind
  ratio: string
  /** 用户自由文本（风格描述/要求）——配方核心，非内部卡 prompt。 */
  prompt: string
  platform: string | null
  modifiers: Record<string, string>
  /** 套图图型配比（kind==='set'）。 */
  plan?: SetPlan
  /** 单图张数（kind==='single'）。 */
  n?: number
  cloneMode?: string
  editMode?: string
  /** 能否一键复用配置到 /set。仅套图单（spec §四「复用按钮只做套图单」）。 */
  reusable: boolean
}

const IMAGE_TYPE_KEYS: readonly ImageTypeKey[] = IMAGE_TYPE_FIELDS.map((f) => f.key)
const RATIO_SET: ReadonlySet<string> = new Set(RATIOS)

/** 从 job 详情反推「配方」。套图 → 从每张 image_type 计数还原图型配比。 */
export function jobToRecipe(detail: ListingJobDetail): Recipe {
  const base = {
    ratio: detail.ratio,
    prompt: detail.prompt,
    platform: detail.platform,
    modifiers: detail.modifiers,
  }
  if (detail.clone_mode) return { ...base, kind: 'clone', cloneMode: detail.clone_mode, reusable: false }
  if (detail.edit_mode) return { ...base, kind: 'edit', editMode: detail.edit_mode, reusable: false }
  const plan = deriveSetPlan(detail)
  if (plan) return { ...base, kind: 'set', plan, reusable: true }
  return { ...base, kind: 'single', n: Math.max(detail.n, 1), reusable: false }
}

/** 套图图型配比 = 详情各图型行数（含失败张，忠实还原当初 plan）。非套图 → null。 */
function deriveSetPlan(detail: ListingJobDetail): SetPlan | null {
  const counts: SetPlan = { 白底: 0, 场景: 0, 卖点: 0 }
  let matched = false
  for (const im of detail.images) {
    const t = im.image_type
    if (t && IMAGE_TYPE_KEYS.includes(t as ImageTypeKey)) {
      counts[t as ImageTypeKey] += 1
      matched = true
    }
  }
  return matched ? counts : null
}

/** 配方 → /set 预填（Partial<ListingConfig>）。仅套图可复用；不含 uploads/overlayTexts（用户自传自填）。 */
export function recipeToPrefill(recipe: Recipe): Partial<ListingConfig> | null {
  if (!recipe.reusable) return null
  const ratio: Ratio = RATIO_SET.has(recipe.ratio) ? (recipe.ratio as Ratio) : '1:1'
  return {
    mode: 'set',
    ratio,
    prompt: recipe.prompt,
    plan: { ...(recipe.plan ?? DEFAULT_PLAN) },
    modifiers: { ...recipe.modifiers },
  }
}
