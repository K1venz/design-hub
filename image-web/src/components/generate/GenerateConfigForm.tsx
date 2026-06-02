import { useState } from 'react'
import { CalculatorIcon, SparklesIcon } from 'lucide-react'
import { toast } from 'sonner'

import { useAssets } from '@/api/assets'
import {
  useCostPreview,
  useProjectGenerate,
  type GenerateConfig,
} from '@/api/generation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { yuan } from '@/lib/format'

const SUBSCENES = [
  { v: 'S1', label: 'S1 换背景' },
  { v: 'S3', label: 'S3 场景图' },
  { v: 'S4', label: 'S4 多角度' },
] as const
const FAMILIES = ['family_3', 'family_4', 'family_5', 'family_7'] as const
const TIERS = [
  { v: 'draft', label: '草稿' },
  { v: 'standard', label: '标准' },
  { v: 'refine', label: '精修' },
] as const
const STYLES = ['高端轻奢', '极简北欧', '国潮中式', '科技未来', '清新自然', '运动机能', '喜庆节日']
const CATEGORIES = ['3C数码', '服饰配件', '美妆护肤', '食品', '含人物', '镜面玻璃']

const DEFAULT_CONFIG: GenerateConfig = {
  subscene: 'S1',
  family: 'family_4',
  category: '食品',
  tier: 'standard',
  style: '清新自然',
  width: 1024,
  height: 1024,
  n: 6,
  asset_ids: [],
}

export function GenerateConfigForm({
  projectId,
  customerName,
  onGenerated,
}: {
  projectId: number
  customerName: string
  onGenerated: (jobId: string) => void
}) {
  const [cfg, setCfg] = useState<GenerateConfig>(DEFAULT_CONFIG)
  const [assetIds, setAssetIds] = useState<number[]>([])
  const assets = useAssets(projectId)
  const preview = useCostPreview()
  const generate = useProjectGenerate(projectId)

  function set<K extends keyof GenerateConfig>(k: K, v: GenerateConfig[K]) {
    setCfg((c) => ({ ...c, [k]: v }))
  }
  const payload: GenerateConfig = { ...cfg, asset_ids: assetIds }

  async function estimate() {
    try {
      await preview.mutateAsync({ ...payload, customer: customerName })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '成本预估失败')
    }
  }
  async function run() {
    try {
      const res = await generate.mutateAsync(payload)
      toast.success(`出图完成：${res.images.length} 张（${yuan(res.total_cost)}）`)
      onGenerated(res.job_id)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '出图失败')
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-3">
        <Field label="子场景">
          <Picker value={cfg.subscene} onChange={(v) => set('subscene', v as GenerateConfig['subscene'])} options={SUBSCENES.map((s) => ({ v: s.v, label: s.label }))} />
        </Field>
        <Field label="模板族">
          <Picker value={cfg.family} onChange={(v) => set('family', v as GenerateConfig['family'])} options={FAMILIES.map((f) => ({ v: f, label: f }))} />
        </Field>
        <Field label="品类">
          <Picker value={cfg.category} onChange={(v) => set('category', v as GenerateConfig['category'])} options={CATEGORIES.map((c) => ({ v: c, label: c }))} />
        </Field>
        <Field label="档位">
          <Picker value={cfg.tier} onChange={(v) => set('tier', v as GenerateConfig['tier'])} options={TIERS.map((t) => ({ v: t.v, label: t.label }))} />
        </Field>
        <Field label="风格">
          <Picker value={cfg.style} onChange={(v) => set('style', v as GenerateConfig['style'])} options={STYLES.map((s) => ({ v: s, label: s }))} />
        </Field>
        <Field label="数量">
          <Input
            type="number"
            min={1}
            max={12}
            value={cfg.n}
            onChange={(e) => set('n', Math.max(1, Math.min(12, Number(e.target.value) || 1)))}
          />
        </Field>
        <Field label="宽 (px)">
          <Input type="number" value={cfg.width} onChange={(e) => set('width', Number(e.target.value) || 0)} />
        </Field>
        <Field label="高 (px)">
          <Input type="number" value={cfg.height} onChange={(e) => set('height', Number(e.target.value) || 0)} />
        </Field>
      </div>

      {assets.data && assets.data.length > 0 && (
        <div className="space-y-2">
          <Label>参考素材（选中走图生图保真）</Label>
          <div className="flex flex-wrap gap-2">
            {assets.data.map((a) => {
              const on = assetIds.includes(a.id)
              return (
                <button
                  key={a.id}
                  type="button"
                  onClick={() =>
                    setAssetIds((p) => (on ? p.filter((x) => x !== a.id) : [...p, a.id]))
                  }
                  className={cn(
                    'rounded-full border px-3 py-1 text-xs transition-colors',
                    on
                      ? 'border-primary bg-primary/10 text-primary'
                      : 'border-border text-muted-foreground hover:bg-accent/50',
                  )}
                >
                  {a.kind} #{a.id}
                </button>
              )
            })}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button variant="outline" onClick={() => void estimate()} disabled={preview.isPending}>
          <CalculatorIcon className="size-4" />
          {preview.isPending ? '预估中…' : '成本预估'}
        </Button>
        <Button onClick={() => void run()} disabled={generate.isPending}>
          <SparklesIcon className="size-4" />
          {generate.isPending ? '出图中…' : '开始出图'}
        </Button>
        {preview.data && (
          <span className="text-sm text-muted-foreground">
            预估 <span className="text-foreground font-semibold">{yuan(preview.data.estimated_cost)}</span>
            <span className="text-muted-foreground/60"> · </span>
            {preview.data.model} · {preview.data.candidate_count} 张
            <span className="text-muted-foreground/60"> · </span>
            本月已用 {yuan(preview.data.month_used)}/{yuan(preview.data.month_budget)}
          </span>
        )}
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  )
}

function Picker({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (v: string) => void
  options: { v: string; label: string }[]
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.v} value={o.v}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
