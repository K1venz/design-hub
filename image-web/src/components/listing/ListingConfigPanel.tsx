import type { ReactNode } from 'react'
import { Loader2Icon, MinusIcon, PlusIcon } from 'lucide-react'

import { GradientButton } from '@/components/visual/GradientButton'
import { ConfigSelect } from '@/components/listing/ConfigSelect'
import { ImageUploader } from '@/components/listing/ImageUploader'
import { TagInput } from '@/components/TagInput'
import { cn } from '@/lib/utils'
import {
  IMAGE_TYPE_FIELDS, MODIFIER_FIELDS, OVERLAY_MAX_COUNT, OVERLAY_MAX_LEN,
  PLAN_TOTAL_MAX, PLAN_TOTAL_MIN, RATIOS, estimateCost, planTotal,
  type ImageTypeKey, type ListingConfig, type UploadedImage,
} from '@/lib/listing'

interface ListingConfigPanelProps {
  config: ListingConfig
  uploaded: UploadedImage[]
  pending: boolean
  onConfigChange: (next: ListingConfig) => void
  onUploadedChange: (uploaded: UploadedImage[]) => void
  onGenerate: () => void
}

export function ListingConfigPanel(props: ListingConfigPanelProps) {
  const { config, uploaded, pending, onConfigChange, onUploadedChange, onGenerate } = props
  const setModifier = (key: string, value: string) =>
    onConfigChange({ ...config, modifiers: { ...config.modifiers, [key]: value } })
  const setCount = (key: ImageTypeKey, count: number) =>
    onConfigChange({ ...config, plan: { ...config.plan, [key]: count } })

  const isSet = config.mode === 'set'
  const total = planTotal(config.plan)
  const tooFew = isSet && total < PLAN_TOTAL_MIN
  const atMax = total >= PLAN_TOTAL_MAX
  const nOut = isSet ? total : config.n
  const baseReady = uploaded.length > 0 && config.prompt.trim().length > 0 && !pending
  const canGenerate = baseReady && !tooFew

  return (
    <div className="glass-panel flex w-[372px] shrink-0 flex-col overflow-hidden">
      <div className="flex-1 overflow-auto p-5">
        <h4 className="mb-2.5 text-[13px] font-bold">产品原图（最多 3 张）</h4>
        <ImageUploader onChange={onUploadedChange} max={3} />

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
          <ConfigSelect
            label="比例"
            value={config.ratio}
            options={RATIOS}
            onChange={(v) => onConfigChange({ ...config, ratio: v as ListingConfig['ratio'] })}
          />
        </div>

        <h4 className="mb-2.5 mt-5 text-[13px] font-bold">出图模式</h4>
        <div className="grid grid-cols-2 gap-1 rounded-xl border border-wb-line-1 bg-wb-surface-1 p-1">
          {(
            [
              { mode: 'single', label: '单图 ¥0.40' },
              { mode: 'set', label: '套图' },
            ] as const
          ).map((m) => (
            <button
              key={m.mode}
              type="button"
              onClick={() => onConfigChange({ ...config, mode: m.mode })}
              className={cn(
                'rounded-[9px] py-1.5 text-[13px] text-wb-ink-5 transition-colors',
                config.mode === m.mode && 'bg-white font-semibold text-wb-brand-deep shadow-sm',
              )}
            >
              {m.label}
            </button>
          ))}
        </div>

        {isSet && (
          <>
            <div className="mb-2.5 mt-5 flex items-baseline justify-between">
              <h4 className="text-[13px] font-bold">套图结构</h4>
              <span className="text-[12px] text-wb-ink-6">
                合计 {total} 张 · 约 ¥{estimateCost(total).toFixed(2)}
                {tooFew && <span className="ml-1.5 text-wb-red">至少 {PLAN_TOTAL_MIN} 张</span>}
              </span>
            </div>
            <div className="space-y-1 rounded-xl border border-wb-line-1 p-2.5">
              {IMAGE_TYPE_FIELDS.map((f) => (
                <div key={f.key}>
                  <div className="flex items-center justify-between gap-2 py-1">
                    <div className="min-w-0">
                      <span className="text-[13px] font-medium text-wb-ink-2">{f.label}</span>
                      <span className="ml-2 text-[11.5px] text-wb-ink-7">{f.desc}</span>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      <StepBtn
                        disabled={config.plan[f.key] <= 0}
                        onClick={() => setCount(f.key, config.plan[f.key] - 1)}
                      >
                        <MinusIcon className="size-3.5" />
                      </StepBtn>
                      <span className="w-5 text-center text-[13px] font-semibold tabular-nums">
                        {config.plan[f.key]}
                      </span>
                      <StepBtn disabled={atMax} onClick={() => setCount(f.key, config.plan[f.key] + 1)}>
                        <PlusIcon className="size-3.5" />
                      </StepBtn>
                    </div>
                  </div>
                  {f.key === '卖点' && config.plan.卖点 > 0 && (
                    <div className="mb-1.5 ml-0.5">
                      <TagInput
                        value={config.overlayTexts}
                        onChange={(v) =>
                          onConfigChange({
                            ...config,
                            overlayTexts: v.filter((t) => t.length <= OVERLAY_MAX_LEN).slice(0, OVERLAY_MAX_COUNT),
                          })
                        }
                        placeholder={`图上文案（可选，≤${OVERLAY_MAX_COUNT} 条，每条≤${OVERLAY_MAX_LEN}字）如：高山七彩花生`}
                      />
                      <p className="mt-1 text-[11px] text-wb-faint-2">不填则输出无文字的卖点特写</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}

        <h4 className="mb-2.5 mt-5 text-[13px] font-bold">商品卖点 &amp; 要求</h4>
        <textarea
          value={config.prompt}
          onChange={(e) => onConfigChange({ ...config, prompt: e.target.value })}
          placeholder="描述你想要的画面与卖点…"
          className="min-h-[104px] w-full resize-none rounded-xl border border-wb-line-1 p-3 text-[13.5px] leading-relaxed text-wb-ink-2 outline-none focus-visible:border-wb-brand-soft"
        />
      </div>

      <div className="border-t border-wb-line-1 bg-white/60 p-4">
        <GradientButton onClick={onGenerate} disabled={!canGenerate} className="w-full">
          {pending ? <Loader2Icon className="size-4 animate-spin" /> : null}
          {isSet ? '一键生成套图' : '开始出图'}
          <span className="ml-2 text-[13px] font-normal opacity-90">
            约 ¥{estimateCost(nOut).toFixed(2)} · {nOut} 张
          </span>
        </GradientButton>
      </div>
    </div>
  )
}

function StepBtn({
  disabled,
  onClick,
  children,
}: {
  disabled: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="grid size-6 place-items-center rounded-md border border-wb-line-1 bg-white text-wb-ink-3 transition-colors hover:border-wb-brand-soft disabled:opacity-35 disabled:hover:border-wb-line-1"
    >
      {children}
    </button>
  )
}
