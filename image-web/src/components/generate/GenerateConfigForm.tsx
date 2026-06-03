import { useState, type ReactNode } from 'react'
import {
  CalculatorIcon,
  GaugeIcon,
  HashIcon,
  LayersIcon,
  type LucideIcon,
  MoveHorizontalIcon,
  MoveVerticalIcon,
  PaletteIcon,
  SparklesIcon,
  SquareStackIcon,
  TagIcon,
} from 'lucide-react'
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
import { GradientButton } from '@/components/visual/GradientButton'
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
    <section className="group/card border-border/70 bg-card relative overflow-hidden rounded-2xl border p-6 shadow-[0_1px_2px_oklch(0.2_0.02_255_/_0.04)] transition-shadow duration-300 hover:shadow-[0_18px_44px_-22px_oklch(0.45_0.07_255_/_0.28)]">
      {/* 顶角渐变光晕（ai-gen 同款氛围） */}
      <div
        aria-hidden
        className="pointer-events-none absolute -top-24 -right-16 size-64 rounded-full bg-gradient-to-br from-violet-500/15 via-fuchsia-500/10 to-transparent blur-2xl"
      />

      <header className="relative mb-5 flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h3 className="flex items-center gap-2 text-base font-semibold text-foreground">
            <span className="from-primary inline-flex size-7 items-center justify-center rounded-lg bg-gradient-to-br to-violet-500 text-white shadow-sm">
              <SparklesIcon className="size-4" />
            </span>
            AI 出图
          </h3>
          <p className="text-muted-foreground text-xs">
            配置参数 → 先成本预估再开始出图（草稿 / family_3 走 Mock，免费）。
          </p>
        </div>
        <span className="border-border/70 text-muted-foreground hidden shrink-0 rounded-full border px-2.5 py-1 font-mono text-[11px] sm:inline-block">
          {customerName}
        </span>
      </header>

      <div className="relative grid gap-x-4 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field icon={LayersIcon} label="子场景">
          <Picker value={cfg.subscene} onChange={(v) => set('subscene', v as GenerateConfig['subscene'])} options={SUBSCENES.map((s) => ({ v: s.v, label: s.label }))} />
        </Field>
        <Field icon={SquareStackIcon} label="模板族">
          <Picker value={cfg.family} onChange={(v) => set('family', v as GenerateConfig['family'])} options={FAMILIES.map((f) => ({ v: f, label: f }))} />
        </Field>
        <Field icon={TagIcon} label="品类">
          <Picker value={cfg.category} onChange={(v) => set('category', v as GenerateConfig['category'])} options={CATEGORIES.map((c) => ({ v: c, label: c }))} />
        </Field>
        <Field icon={GaugeIcon} label="档位">
          <Picker value={cfg.tier} onChange={(v) => set('tier', v as GenerateConfig['tier'])} options={TIERS.map((t) => ({ v: t.v, label: t.label }))} />
        </Field>
        <Field icon={PaletteIcon} label="风格">
          <Picker value={cfg.style} onChange={(v) => set('style', v as GenerateConfig['style'])} options={STYLES.map((s) => ({ v: s, label: s }))} />
        </Field>
        <Field icon={HashIcon} label="数量">
          <Input
            type="number"
            min={1}
            max={12}
            value={cfg.n}
            onChange={(e) => set('n', Math.max(1, Math.min(12, Number(e.target.value) || 1)))}
          />
        </Field>
        <Field icon={MoveHorizontalIcon} label="宽 (px)">
          <Input type="number" value={cfg.width} onChange={(e) => set('width', Number(e.target.value) || 0)} />
        </Field>
        <Field icon={MoveVerticalIcon} label="高 (px)">
          <Input type="number" value={cfg.height} onChange={(e) => set('height', Number(e.target.value) || 0)} />
        </Field>
      </div>

      {assets.data && assets.data.length > 0 && (
        <div className="relative mt-5 space-y-2">
          <Label className="text-muted-foreground text-xs">参考素材（选中走图生图保真）</Label>
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

      <div className="border-border/60 relative mt-6 flex flex-wrap items-center gap-3 border-t pt-5">
        <Button variant="outline" onClick={() => void estimate()} disabled={preview.isPending}>
          <CalculatorIcon className="size-4" />
          {preview.isPending ? '预估中…' : '成本预估'}
        </Button>
        <GradientButton onClick={() => void run()} disabled={generate.isPending}>
          <SparklesIcon className="size-4" />
          {generate.isPending ? '出图中…' : '开始出图'}
        </GradientButton>
        {preview.data && (
          <span className="text-muted-foreground text-sm">
            预估 <span className="text-foreground font-semibold">{yuan(preview.data.estimated_cost)}</span>
            <span className="text-muted-foreground/60"> · </span>
            {preview.data.model} · {preview.data.candidate_count} 张
            <span className="text-muted-foreground/60"> · </span>
            本月已用 {yuan(preview.data.month_used)}/{yuan(preview.data.month_budget)}
          </span>
        )}
      </div>
    </section>
  )
}

function Field({ icon: Icon, label, children }: { icon: LucideIcon; label: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-muted-foreground flex items-center gap-1.5 text-xs">
        <Icon className="size-3.5 opacity-70" />
        {label}
      </Label>
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
