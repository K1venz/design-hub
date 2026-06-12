import { Loader2Icon } from 'lucide-react'

import { GradientButton } from '@/components/visual/GradientButton'
import { ConfigSelect } from '@/components/listing/ConfigSelect'
import { ImageUploader } from '@/components/listing/ImageUploader'
import { cn } from '@/lib/utils'
import {
  CLONE_MODES, CLONE_PRODUCT_MAX, CLONE_REFERENCE_MAX, MODIFIER_FIELDS, RATIOS,
  estimateCost, type CloneModeKey, type Ratio, type UploadedImage,
} from '@/lib/listing'

export interface CloneConfig {
  modifiers: Record<string, string>
  ratio: Ratio
  cloneMode: CloneModeKey
  prompt: string
}

interface CloneConfigPanelProps {
  config: CloneConfig
  product: UploadedImage[]
  references: UploadedImage[]
  pending: boolean
  onConfigChange: (next: CloneConfig) => void
  onProductChange: (v: UploadedImage[]) => void
  onReferencesChange: (v: UploadedImage[]) => void
  onGenerate: () => void
}

/** 爆款图复刻配置栏：双角色上传（语义钉死防传反）+ 两档复刻程度卡 + 统一要求（选填）。 */
export function CloneConfigPanel(props: CloneConfigPanelProps) {
  const {
    config, product, references, pending,
    onConfigChange, onProductChange, onReferencesChange, onGenerate,
  } = props
  const setModifier = (key: string, value: string) =>
    onConfigChange({ ...config, modifiers: { ...config.modifiers, [key]: value } })
  // 统一要求选填：启用条件只看双角色图齐（PRD §3.13①，prompt 空=合法）
  const canGenerate = product.length >= 1 && references.length >= 1 && !pending

  return (
    <div className="flex w-[392px] shrink-0 flex-col border-r border-wb-line-1 bg-white">
      <div className="flex-1 overflow-auto p-5">
        <h4 className="mb-1 text-[13px] font-bold">产品原图（你的商品 · 1 张）</h4>
        <p className="mb-2 text-[11.5px] text-wb-ink-7">将原样保真出现在成品里</p>
        <ImageUploader onChange={onProductChange} max={CLONE_PRODUCT_MAX} />

        <h4 className="mb-1 mt-5 text-[13px] font-bold">参考爆款图（想复刻的模板 · 最多 {CLONE_REFERENCE_MAX} 张）</h4>
        <p className="mb-2 text-[11.5px] text-wb-ink-7">只借它的结构与风格，模板上的产品与文案不会出现在成品</p>
        <ImageUploader onChange={onReferencesChange} max={CLONE_REFERENCE_MAX} />

        <h4 className="mb-2.5 mt-5 text-[13px] font-bold">生成设置</h4>
        <div className="grid grid-cols-2 gap-2.5">
          {MODIFIER_FIELDS.map((f) => (
            <ConfigSelect
              key={f.key}
              label={f.label}
              value={config.modifiers[f.key] ?? f.options[0]}
              options={f.options}
              onChange={(v) => setModifier(f.key, v)}
            />
          ))}
          <ConfigSelect
            label="比例"
            value={config.ratio}
            options={RATIOS}
            onChange={(v) => onConfigChange({ ...config, ratio: v as Ratio })}
          />
        </div>

        <h4 className="mb-2.5 mt-5 text-[13px] font-bold">复刻程度</h4>
        <div className="space-y-2">
          {CLONE_MODES.map((m) => {
            const on = config.cloneMode === m.key
            return (
              <button
                key={m.key}
                type="button"
                onClick={() => onConfigChange({ ...config, cloneMode: m.key })}
                className={cn(
                  'w-full rounded-xl border p-3 text-left transition-colors',
                  on ? 'border-wb-brand-mid bg-wb-tint-3' : 'border-wb-line-1 hover:border-wb-brand-soft',
                )}
              >
                <span className={cn('text-[13px] font-semibold', on ? 'text-wb-brand-deep' : 'text-wb-ink-2')}>
                  {m.key}
                </span>
                <p className="mt-1 text-[11.5px] leading-relaxed text-wb-ink-6">{m.desc}</p>
              </button>
            )
          })}
        </div>

        <h4 className="mb-2.5 mt-5 text-[13px] font-bold">
          统一复刻要求 <span className="font-normal text-wb-ink-7">（选填）</span>
        </h4>
        <textarea
          value={config.prompt}
          onChange={(e) => onConfigChange({ ...config, prompt: e.target.value })}
          placeholder="如：文案统一中文 / 只换商品其余不变…"
          className="min-h-[84px] w-full resize-none rounded-xl border border-wb-line-1 p-3 text-[13.5px] leading-relaxed text-wb-ink-2 outline-none focus-visible:border-wb-brand-soft"
        />
      </div>

      <div className="border-t border-wb-line-1 bg-white p-4">
        <GradientButton onClick={onGenerate} disabled={!canGenerate} className="w-full">
          {pending ? <Loader2Icon className="size-4 animate-spin" /> : null}
          开始复刻
          <span className="ml-2 text-[13px] font-normal opacity-90">约 ¥{estimateCost(1).toFixed(2)} · 1 张</span>
        </GradientButton>
      </div>
    </div>
  )
}
