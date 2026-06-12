import { ArrowUpRightIcon, Loader2Icon } from 'lucide-react'
import { Link } from 'react-router-dom'

import { GradientButton } from '@/components/visual/GradientButton'
import { ConfigSelect } from '@/components/listing/ConfigSelect'
import { cn } from '@/lib/utils'
import {
  EDIT_MODES, EDIT_OVERLAY_NOTICE, IMAGE_TYPE_FIELDS, MODIFIER_FIELDS, RATIOS,
  estimateCost, type EditModeKey, type Ratio,
} from '@/lib/listing'

export interface EditConfig {
  editMode: EditModeKey
  prompt: string
  /** full 档生效；delta 档仅展示「跟随原图」（builder 省略字段）。 */
  ratio: Ratio
  modifiers: Record<string, string>
}

/** 编辑页源图上下文（页内只读不可换——换图=回历史/结果区另起新编辑）。 */
export interface EditSource {
  /** 源图预览 url（父详情签名 url）。 */
  url: string
  /** 父张图型（白底/场景/卖点）；单图旧产物为空。 */
  imageType?: string
  /** 父 job id（「来源任务 ↗」+ 即未来的 parent_job_id，仅前端上下文用）。 */
  jobId: string
  /** 父 job 比例（delta 继承展示）。 */
  parentRatio: string
}

interface EditConfigPanelProps {
  config: EditConfig
  /** null = 源图不可用（详情中无此 key / 读模型未含 key）。 */
  source: EditSource | null
  pending: boolean
  onConfigChange: (next: EditConfig) => void
  onGenerate: () => void
}

/** 二次编辑配置栏：源图只读区 + 微调/重做档位卡（#651 定稿文案）+ 必填新要求 + ratio 继承。 */
export function EditConfigPanel(props: EditConfigPanelProps) {
  const { config, source, pending, onConfigChange, onGenerate } = props
  const setModifier = (key: string, value: string) =>
    onConfigChange({ ...config, modifiers: { ...config.modifiers, [key]: value } })
  const activeMode = EDIT_MODES.find((m) => m.key === config.editMode) ?? EDIT_MODES[0]
  const sourceTypeLabel = source?.imageType
    ? (IMAGE_TYPE_FIELDS.find((f) => f.key === source.imageType)?.label ?? source.imageType)
    : null
  // E-⑤ prompt 必填：空白 CTA 禁用（后端 min_length=1 → 422 双层）
  const canGenerate = source !== null && config.prompt.trim().length > 0 && !pending

  return (
    <div className="glass-panel flex w-[372px] shrink-0 flex-col overflow-hidden">
      <div className="flex-1 overflow-auto p-5">
        <h4 className="mb-1 text-[13px] font-bold">源图（只读 · 不可换）</h4>
        <p className="mb-2 text-[11.5px] text-wb-ink-7">要换一张？回历史或结果区重新选</p>
        {source ? (
          <div className="flex items-start gap-3 rounded-xl border border-wb-line-1 bg-wb-surface-1 p-3">
            <img
              src={source.url}
              alt=""
              className="size-20 shrink-0 rounded-[10px] border border-wb-line-1 object-cover"
            />
            <div className="flex min-w-0 flex-col gap-1.5 pt-0.5">
              {sourceTypeLabel && (
                <span className="w-fit rounded-md border border-wb-tint-line bg-wb-tint-2 px-2 py-0.5 text-[11.5px] font-medium text-wb-brand-deep">
                  改自 · {sourceTypeLabel}
                </span>
              )}
              <Link
                to={`/history/${source.jobId}`}
                className="flex w-fit items-center gap-0.5 text-[12px] text-wb-ink-4 transition-colors hover:text-wb-brand-deep"
              >
                来源任务 <ArrowUpRightIcon className="size-3.5" />
              </Link>
            </div>
          </div>
        ) : (
          <div className="grid h-24 place-items-center rounded-xl border border-dashed border-wb-line-3 bg-wb-surface-1 text-[12.5px] text-wb-ink-7">
            源图不可用或已失效
          </div>
        )}

        <h4 className="mb-2.5 mt-5 text-[13px] font-bold">编辑方式</h4>
        <div className="space-y-2">
          {EDIT_MODES.map((m) => {
            const on = config.editMode === m.key
            return (
              <button
                key={m.key}
                type="button"
                onClick={() => onConfigChange({ ...config, editMode: m.key })}
                className={cn(
                  'w-full rounded-xl border p-3 text-left transition-colors',
                  on ? 'border-wb-brand-mid bg-wb-tint-3' : 'border-wb-line-1 hover:border-wb-brand-soft',
                )}
              >
                <span className={cn('text-[13px] font-semibold', on ? 'text-wb-brand-deep' : 'text-wb-ink-2')}>
                  {m.label}
                  {m.key === 'delta' && (
                    <span className="ml-1.5 text-[11px] font-normal text-wb-ink-7">默认</span>
                  )}
                </span>
                <p className="mt-1 text-[11.5px] leading-relaxed text-wb-ink-6">{m.desc}</p>
                {m.note && <p className="mt-1 text-[11px] leading-relaxed text-wb-faint-1">{m.note}</p>}
              </button>
            )
          })}
        </div>

        <h4 className="mb-2.5 mt-5 text-[13px] font-bold">
          新要求 <span className="font-normal text-wb-red">*</span>
        </h4>
        <textarea
          value={config.prompt}
          onChange={(e) => onConfigChange({ ...config, prompt: e.target.value })}
          placeholder={activeMode.placeholder}
          className="min-h-[84px] w-full resize-none rounded-xl border border-wb-line-1 p-3 text-[13.5px] leading-relaxed text-wb-ink-2 outline-none focus-visible:border-wb-brand-soft"
        />
        {source?.imageType === '卖点' && (
          <p className="mt-1.5 text-[11.5px] leading-relaxed text-wb-amber">{EDIT_OVERLAY_NOTICE}</p>
        )}

        <h4 className="mb-2.5 mt-5 text-[13px] font-bold">生成设置</h4>
        <div className="grid grid-cols-2 gap-2.5">
          {MODIFIER_FIELDS.map((f) => (
            <ConfigSelect
              key={f.key}
              label={f.label}
              value={config.modifiers[f.key] ?? f.options[0]}
              options={f.options}
              onChange={(v) => setModifier(f.key, v)}
              className={f.key === 'platform' ? 'col-span-2' : undefined}
            />
          ))}
          {config.editMode === 'delta' ? (
            // 终契约：delta 继承父 ratio（显式传→400），UI 只读展示
            <div className="flex items-center justify-between rounded-xl border border-wb-line-1 bg-wb-surface-1 px-3 py-2.5 text-[13px] text-wb-ink-5">
              <span>比例</span>
              <span className="font-semibold text-wb-ink-6">
                跟随原图 · {source?.parentRatio ?? config.ratio}
              </span>
            </div>
          ) : (
            <ConfigSelect
              label="比例"
              value={config.ratio}
              options={RATIOS}
              onChange={(v) => onConfigChange({ ...config, ratio: v as Ratio })}
            />
          )}
        </div>
      </div>

      <div className="border-t border-wb-line-1 bg-white/60 p-4">
        <GradientButton onClick={onGenerate} disabled={!canGenerate} className="w-full">
          {pending ? <Loader2Icon className="size-4 animate-spin" /> : null}
          开始编辑
          <span className="ml-2 text-[13px] font-normal opacity-90">约 ¥{estimateCost(1).toFixed(2)} · 1 张</span>
        </GradientButton>
      </div>
    </div>
  )
}
