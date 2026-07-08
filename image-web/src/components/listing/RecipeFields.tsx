import type { ReactNode } from 'react'

import { categoryLabel, IMAGE_TYPE_FIELDS, planTotal, type SetPlan } from '@/lib/listing'

/** modifiers key → 展示名（未知 key 原样）。 */
const MODIFIER_LABELS: Record<string, string> = { platform: '平台', language: '语言', region: '地区' }

/** 配方展示视图模型——归一 job 侧 Recipe 与 showcase 侧 RecipeOut 两种来源，供 RecipeFields 渲染。 */
export interface RecipeView {
  /** 品类（showcase 展示；job 侧省略）。 */
  category?: string
  /** 模式徽标（复刻·xx / 编辑·xx）；套图/单图为 null。 */
  modeBadge?: string | null
  /** 套图图型配比（与 singleN 二选一）。 */
  plan?: SetPlan
  /** 单图张数（与 plan 二选一）。 */
  singleN?: number
  ratio: string
  /** 风格描述（=用户自由文本，绝非内部卡 prompt）。 */
  styling: string
  modifiers: Record<string, string>
}

/**
 * 配方全项定义列表（ISSUE-0053）：品类/图型配比/比例/参数/风格描述——与 /set 生成界面
 * 配置项一一对应。历史「查看配方」与 showcase「查看详情」共用（各自构造 RecipeView）。
 */
export function RecipeFields({ view }: { view: RecipeView }) {
  return (
    <dl className="space-y-3 text-[13px]">
      {view.category && <Row label="品类">{categoryLabel(view.category)}</Row>}

      {view.modeBadge && (
        <Row label="模式">
          <span className="font-medium text-foreground">{view.modeBadge}</span>
        </Row>
      )}

      <Row label={view.plan ? '图型配比' : '张数'}>
        {view.plan ? (
          <div className="flex flex-wrap gap-1.5">
            {IMAGE_TYPE_FIELDS.filter((f) => (view.plan?.[f.key] ?? 0) > 0).map((f) => (
              <span key={f.key} className="rounded-md bg-muted px-2 py-0.5 font-medium text-foreground">
                {f.label} ×{view.plan?.[f.key]}
              </span>
            ))}
            <span className="self-center text-muted-foreground">共 {planTotal(view.plan)} 张</span>
          </div>
        ) : (
          <span className="font-medium text-foreground">{view.singleN ?? 1} 张</span>
        )}
      </Row>

      <Row label="比例">
        <span className="font-medium text-foreground">{view.ratio}</span>
      </Row>

      {Object.keys(view.modifiers).length > 0 && (
        <Row label="参数">
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-foreground">
            {Object.entries(view.modifiers).map(([k, v]) => (
              <span key={k}>
                <span className="text-muted-foreground">{MODIFIER_LABELS[k] ?? k} </span>
                {v}
              </span>
            ))}
          </div>
        </Row>
      )}

      {view.styling.trim() && (
        <Row label="风格描述">
          <span className="whitespace-pre-wrap leading-relaxed text-foreground">{view.styling}</span>
        </Row>
      )}
    </dl>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <dt className="w-16 shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 flex-1">{children}</dd>
    </div>
  )
}
