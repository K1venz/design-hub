import { Loader2Icon } from 'lucide-react'

import { GradientButton } from '@/components/visual/GradientButton'
import { ConfigSelect } from '@/components/listing/ConfigSelect'
import { ImageUploader } from '@/components/listing/ImageUploader'
import {
  MODIFIER_FIELDS, RATIOS, N_MIN, N_MAX, estimateCost, type ListingConfig,
} from '@/lib/listing'

interface ListingConfigPanelProps {
  config: ListingConfig
  files: File[]
  pending: boolean
  onConfigChange: (next: ListingConfig) => void
  onFilesChange: (files: File[]) => void
  onGenerate: () => void
}

const N_OPTIONS = Array.from({ length: N_MAX - N_MIN + 1 }, (_, i) => String(N_MIN + i))

export function ListingConfigPanel(props: ListingConfigPanelProps) {
  const { config, files, pending, onConfigChange, onFilesChange, onGenerate } = props
  const setModifier = (key: string, value: string) =>
    onConfigChange({ ...config, modifiers: { ...config.modifiers, [key]: value } })
  const canGenerate = files.length > 0 && config.prompt.trim().length > 0 && !pending

  return (
    <div className="flex w-[392px] shrink-0 flex-col border-r border-[#ece8e2] bg-white">
      <div className="flex-1 overflow-auto p-5">
        <h4 className="mb-2.5 text-[13px] font-bold">产品原图（最多 3 张）</h4>
        <ImageUploader files={files} onChange={onFilesChange} max={3} />

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
            onChange={(v) => onConfigChange({ ...config, ratio: v as ListingConfig['ratio'] })}
          />
          <ConfigSelect
            label="张数"
            value={String(config.n)}
            options={N_OPTIONS}
            onChange={(v) => onConfigChange({ ...config, n: Number(v) })}
          />
        </div>

        <h4 className="mb-2.5 mt-5 text-[13px] font-bold">商品卖点 &amp; 要求</h4>
        <textarea
          value={config.prompt}
          onChange={(e) => onConfigChange({ ...config, prompt: e.target.value })}
          placeholder="描述你想要的画面与卖点…"
          className="min-h-[104px] w-full resize-none rounded-xl border border-[#ece8e2] p-3 text-[13.5px] leading-relaxed text-[#2c2824] outline-none focus-visible:border-[#cdbfff]"
        />
      </div>

      <div className="border-t border-[#ece8e2] bg-white p-4">
        <GradientButton onClick={onGenerate} disabled={!canGenerate} className="w-full">
          {pending ? <Loader2Icon className="size-4 animate-spin" /> : null}
          开始出图
          <span className="ml-2 text-[13px] font-normal opacity-90">
            约 ¥{estimateCost(config.n).toFixed(2)} · {config.n} 张
          </span>
        </GradientButton>
      </div>
    </div>
  )
}
