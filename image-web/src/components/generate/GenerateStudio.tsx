import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from 'react'
import {
  CalculatorIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ImageIcon,
  Loader2Icon,
  PlusIcon,
  SendHorizontalIcon,
  Settings2Icon,
  StarIcon,
} from 'lucide-react'
import { toast } from 'sonner'

import { useAssets, useUploadAsset, type Asset } from '@/api/assets'
import {
  useCostPreview,
  useProjectGenerate,
  useProjectJobs,
  type GenerateConfig,
} from '@/api/generation'
import { useBrief, useUpsertBrief } from '@/api/brief'
import { CandidateGrid } from '@/components/generate/CandidateGrid'
import { ImageThumb } from '@/components/generate/ImageThumb'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select-rich'
import { GradientButton } from '@/components/visual/GradientButton'
import { cn } from '@/lib/utils'
import { yuan } from '@/lib/format'

type Opt = { value: string; label: string }

const PLAYS: { v: GenerateConfig['subscene']; emoji: string; label: string }[] = [
  { v: 'S1', emoji: '🖼️', label: '换背景' },
  { v: 'S3', emoji: '🏞️', label: '场景图' },
  { v: 'S4', emoji: '🔄', label: '多角度' },
]
const SUBSCENES: Opt[] = [
  { value: 'S1', label: 'S1 换背景' },
  { value: 'S3', label: 'S3 场景图' },
  { value: 'S4', label: 'S4 多角度' },
]
const FAMILIES: Opt[] = ['family_3', 'family_4', 'family_5', 'family_7'].map((v) => ({ value: v, label: v }))
const CATEGORIES: Opt[] = ['3C数码', '服饰配件', '美妆护肤', '食品', '含人物', '镜面玻璃'].map((v) => ({ value: v, label: v }))
const TIERS: Opt[] = [
  { value: 'draft', label: '草稿' },
  { value: 'standard', label: '标准' },
  { value: 'refine', label: '精修' },
]
const STYLES: Opt[] = ['高端轻奢', '极简北欧', '国潮中式', '科技未来', '清新自然', '运动机能', '喜庆节日'].map((v) => ({ value: v, label: v }))
const COUNTS: Opt[] = ['1', '2', '4', '6', '8', '12'].map((v) => ({ value: v, label: `${v} 张` }))
const SIZES: { value: string; w: number; h: number }[] = [
  { value: '1024×1024', w: 1024, h: 1024 },
  { value: '800×1200', w: 800, h: 1200 },
  { value: '1200×800', w: 1200, h: 800 },
  { value: '1080×1920', w: 1080, h: 1920 },
  { value: '1024×576', w: 1024, h: 576 },
]

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

const LOADING_TEXTS = ['正在解析参考图…', '匹配品牌风格…', '渲染候选画面…', '收尾微调…']

export function GenerateStudio({
  projectId,
  customerName,
}: {
  projectId: number
  customerName: string
}) {
  const [cfg, setCfg] = useState<GenerateConfig>(DEFAULT_CONFIG)
  const [prompt, setPrompt] = useState('')
  const [assetIds, setAssetIds] = useState<number[]>([])
  const [showAdv, setShowAdv] = useState(false)
  const [activeJob, setActiveJob] = useState<string | null>(null)

  const brief = useBrief(projectId)
  const assets = useAssets(projectId)
  const jobs = useProjectJobs(projectId)
  const preview = useCostPreview()
  const generate = useProjectGenerate(projectId)
  const upsertBrief = useUpsertBrief(projectId)
  const upload = useUploadAsset(projectId)
  const fileRef = useRef<HTMLInputElement>(null)

  // 载入需求单后把已存描述预填进聊天框（仅一次，不覆盖用户编辑）
  const inited = useRef(false)
  useEffect(() => {
    if (!inited.current && brief.data) {
      setPrompt(brief.data.copy_text ?? '')
      inited.current = true
    }
  }, [brief.data])

  function set<K extends keyof GenerateConfig>(k: K, v: GenerateConfig[K]) {
    setCfg((c) => ({ ...c, [k]: v }))
  }

  async function onPickFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) {
      try {
        await upload.mutateAsync({ file, kind: '产品图' })
        toast.success(`已添加参考图 ${file.name}`)
      } catch (err) {
        toast.error(err instanceof Error ? err.message : '上传失败')
      }
    }
    if (fileRef.current) fileRef.current.value = ''
  }

  function toggleRef(a: Asset) {
    const has = assetIds.includes(a.id)
    setAssetIds(has ? assetIds.filter((x) => x !== a.id) : [...assetIds, a.id])
    if (!has) {
      const line = `参考${a.kind}#${a.id} 的构图与质感`
      setPrompt((t) => (t.includes(line) ? t : t ? `${t}\n${line}` : line))
    }
  }

  async function estimate() {
    try {
      await preview.mutateAsync({ ...cfg, asset_ids: assetIds, customer: customerName })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '成本预估失败')
    }
  }

  async function run() {
    // 最佳努力把描述持久化到 brief.copy_text（保留其余字段），不阻塞出图
    const b = brief.data
    void upsertBrief
      .mutateAsync({
        material_types: b?.material_types ?? [],
        sizes: b?.sizes ?? [],
        styles: b?.styles ?? [],
        resolution: b?.resolution ?? null,
        bleed: b?.bleed ?? null,
        copy_text: prompt.trim() || (b?.copy_text ?? null),
        taboo: b?.taboo ?? null,
      })
      .catch(() => undefined)
    try {
      const res = await generate.mutateAsync({ ...cfg, asset_ids: assetIds })
      toast.success(`出图完成：${res.images.length} 张（${yuan(res.total_cost)}）`)
      setActiveJob(res.job_id)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '出图失败')
    }
  }

  const currentJob = activeJob ?? jobs.data?.[0]?.job_id ?? null

  return (
    <div className="space-y-6">
      {/* hero · 大聊天框 */}
      <section className="border-border/70 bg-card relative overflow-hidden rounded-3xl border p-8 sm:px-20 sm:py-16">
        <div
          aria-hidden
          className="from-primary/15 via-violet-500/15 to-highlight/15 pointer-events-none absolute -top-16 left-1/2 h-44 w-[60%] -translate-x-1/2 rounded-full bg-gradient-to-r opacity-60 blur-3xl"
        />
        <div className="relative mx-auto max-w-4xl space-y-7">
          <div className="text-center">
            <h2 className="text-foreground text-[1.85rem] font-semibold tracking-tight">想要什么样的图？</h2>
          </div>

          {/* 玩法胶囊 → 子场景 */}
          <div className="flex flex-wrap justify-center gap-2.5">
            {PLAYS.map((p) => (
              <button
                key={p.v}
                onClick={() => set('subscene', p.v)}
                className={cn(
                  'bg-card rounded-full border px-4 py-2 text-sm font-medium shadow-sm transition-colors',
                  cfg.subscene === p.v ? 'border-primary/50 text-primary' : 'border-border text-foreground hover:bg-accent/40',
                )}
              >
                <span className="mr-1.5">{p.emoji}</span>
                {p.label}
              </button>
            ))}
          </div>

          {/* 大聊天框 */}
          <div className="border-border bg-card flex min-h-[272px] flex-col rounded-[1.75rem] border shadow-[0_16px_48px_-20px_oklch(0.45_0.05_255_/_0.22)]">
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="描述你想要的画面，例如：清新自然的花生礼盒，浅木色桌面，晨光柔和，俯拍构图…（也可点下方参考图自动填入，或只选玩法直接出图）"
              className="placeholder:text-muted-foreground/70 text-foreground flex-1 resize-none bg-transparent p-6 text-base leading-relaxed outline-none"
            />
            <div className="flex items-center justify-between gap-2 px-4 pb-4">
              <div className="flex items-center gap-1.5">
                <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => void onPickFile(e)} />
                <button
                  onClick={() => fileRef.current?.click()}
                  disabled={upload.isPending}
                  className="border-border text-foreground hover:bg-accent/50 inline-flex h-10 items-center gap-1.5 rounded-full border px-3.5 text-sm disabled:opacity-50"
                >
                  <PlusIcon className="size-4" /> {upload.isPending ? '上传中…' : '添加参考图'}
                </button>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => void estimate()}
                  disabled={preview.isPending}
                  className="text-muted-foreground hover:bg-accent/50 inline-flex h-10 items-center gap-1.5 rounded-full px-3 text-sm disabled:opacity-50"
                >
                  <CalculatorIcon className="size-4" />
                  {preview.isPending ? '预估中…' : '成本预估'}
                  {preview.data && <span className="text-foreground font-semibold">{yuan(preview.data.estimated_cost)}</span>}
                </button>
                <GradientButton onClick={() => void run()} disabled={generate.isPending} className="rounded-full px-6">
                  {generate.isPending ? <Loader2Icon className="size-4 animate-spin" /> : <SendHorizontalIcon className="size-4" />}
                  {generate.isPending ? '出图中…' : '开始出图'}
                </GradientButton>
              </div>
            </div>
          </div>

          {/* 高级设置（默认折叠） */}
          <div className="flex flex-col items-center gap-3">
            <button
              onClick={() => setShowAdv((v) => !v)}
              className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 text-sm"
            >
              <Settings2Icon className="size-4" /> 高级设置{showAdv ? ' ▴' : ' ▾'}
            </button>
            {showAdv && (
              <div className="flex flex-wrap items-center justify-center gap-3">
                <AdvSelect label="子场景" value={cfg.subscene} options={SUBSCENES} onChange={(v) => set('subscene', v as GenerateConfig['subscene'])} />
                <AdvSelect label="模板族" value={cfg.family} options={FAMILIES} onChange={(v) => set('family', v as GenerateConfig['family'])} />
                <AdvSelect label="品类" value={cfg.category} options={CATEGORIES} onChange={(v) => set('category', v as GenerateConfig['category'])} />
                <AdvSelect label="档位" value={cfg.tier} options={TIERS} onChange={(v) => set('tier', v as GenerateConfig['tier'])} />
                <AdvSelect label="风格" value={cfg.style} options={STYLES} onChange={(v) => set('style', v as GenerateConfig['style'])} />
                <AdvSelect label="数量" value={String(cfg.n)} options={COUNTS} onChange={(v) => set('n', Number(v))} />
                <AdvSelect
                  label="尺寸"
                  value={`${cfg.width}×${cfg.height}`}
                  options={SIZES.map((s) => ({ value: s.value, label: s.value }))}
                  onChange={(v) => {
                    const s = SIZES.find((x) => x.value === v)
                    if (s) setCfg((c) => ({ ...c, width: s.w, height: s.h }))
                  }}
                />
              </div>
            )}
          </div>
        </div>
      </section>

      {/* 参考图（可选）：点图选作图生图源 + 回显参考提示 */}
      <ImageRow title="参考图（可选）" hint="点图把它选作图生图源并回显参考提示 · 再点取消">
        {assets.isLoading ? (
          <p className="text-muted-foreground py-8 text-sm">载入素材…</p>
        ) : assets.data && assets.data.length > 0 ? (
          assets.data.map((a) => {
            const on = assetIds.includes(a.id)
            return (
              <div
                key={a.id}
                role="button"
                tabIndex={0}
                onClick={() => toggleRef(a)}
                title="点按：选作图生图源并回显参考提示"
                className={cn(
                  'group relative w-40 shrink-0 cursor-pointer overflow-hidden rounded-xl border transition-colors',
                  on ? 'border-primary ring-primary/30 ring-2' : 'border-border/70 hover:border-primary/50',
                )}
              >
                <ImageThumb url={a.url} className="aspect-square w-full" />
                <span className={cn('absolute top-1.5 left-1.5 rounded-full border px-1.5 py-0.5 text-[10px]', a.kind === '产品图' ? 'border-teal-200 bg-teal-50 text-teal-700' : 'border-amber-200 bg-amber-50 text-amber-700')}>
                  {a.kind}
                </span>
                <span className={cn('absolute top-1.5 right-1.5 inline-flex size-6 items-center justify-center rounded-full border backdrop-blur', on ? 'border-primary bg-primary text-white' : 'border-white/70 bg-white/70 text-muted-foreground')}>
                  <StarIcon className={cn('size-3.5', on && 'fill-current')} />
                </span>
              </div>
            )
          })
        ) : (
          <div className="text-muted-foreground flex w-full items-center gap-2 rounded-xl border border-dashed px-4 py-8 text-sm">
            <ImageIcon className="size-5" /> 还没有素材，点上方「添加参考图」上传产品图，即可选作图生图源。
          </div>
        )}
      </ImageRow>

      {/* 候选选稿 / 出图中 */}
      {generate.isPending ? (
        <GenLoading />
      ) : jobs.data && jobs.data.length > 0 ? (
        <section className="border-border/70 bg-card space-y-4 rounded-2xl border p-5">
          <h3 className="text-foreground text-sm font-semibold">候选选稿</h3>
          <div className="flex flex-wrap gap-2">
            {jobs.data.map((j) => {
              const on = j.job_id === currentJob
              return (
                <button
                  key={j.job_id}
                  type="button"
                  onClick={() => setActiveJob(j.job_id)}
                  className={cn(
                    'rounded-lg border px-3 py-2 text-left text-xs transition-colors',
                    on ? 'border-primary bg-primary/5' : 'border-border/70 hover:bg-accent/40',
                  )}
                >
                  <div className="text-foreground font-medium">第 {j.round_no} 轮 · {j.subscene}</div>
                  <div className="text-muted-foreground mt-0.5 font-mono">{j.used_model} · {j.candidate_count} 张 · {yuan(j.total_cost)}</div>
                </button>
              )
            })}
          </div>
          {currentJob && (
            <div className="border-border/60 border-t pt-4">
              <CandidateGrid jobId={currentJob} />
            </div>
          )}
        </section>
      ) : null}
    </div>
  )
}

function AdvSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: Opt[]
  onChange: (v: string) => void
}) {
  return (
    <Select value={value} onValueChange={onChange} indicatorPosition="right">
      <SelectTrigger size="lg" className="border-border bg-card hover:border-primary/40 h-auto w-auto gap-2 rounded-xl px-4 py-3">
        <span className="text-muted-foreground">{label}</span>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

function ImageRow({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const nudge = (dir: number) => ref.current?.scrollBy({ left: dir * 320, behavior: 'smooth' })
  return (
    <section className="border-border/70 bg-card space-y-3 rounded-2xl border p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="space-y-0.5">
          <h3 className="text-foreground text-sm font-semibold">{title}</h3>
          {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => nudge(-1)} className="border-border hover:bg-accent/50 flex size-7 items-center justify-center rounded-full border">
            <ChevronLeftIcon className="size-4" />
          </button>
          <button onClick={() => nudge(1)} className="border-border hover:bg-accent/50 flex size-7 items-center justify-center rounded-full border">
            <ChevronRightIcon className="size-4" />
          </button>
        </div>
      </div>
      <div ref={ref} className="flex gap-3 overflow-x-auto pb-1 [scrollbar-width:thin]">
        {children}
      </div>
    </section>
  )
}

function GenLoading() {
  const [progress, setProgress] = useState(8)
  const [ti, setTi] = useState(0)
  useEffect(() => {
    const p = setInterval(() => setProgress((v) => (v >= 96 ? 96 : v + 1.4)), 60)
    const t = setInterval(() => setTi((v) => (v + 1) % LOADING_TEXTS.length), 1400)
    return () => {
      clearInterval(p)
      clearInterval(t)
    }
  }, [])
  return (
    <div className="border-border/70 bg-card flex flex-col items-center gap-4 rounded-2xl border p-10">
      <div className="relative size-16">
        <Loader2Icon className="size-full animate-spin text-violet-500" />
        <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-transparent to-fuchsia-500/15" />
      </div>
      <p className="text-foreground text-sm font-medium">{LOADING_TEXTS[ti]}</p>
      <div className="bg-muted h-2 w-full max-w-md overflow-hidden rounded-full">
        <div className="from-primary h-full rounded-full bg-gradient-to-r via-violet-500 to-fuchsia-500 transition-[width] duration-300 ease-linear" style={{ width: `${progress}%` }} />
      </div>
      <p className="text-muted-foreground text-xs">真实出图中，请稍候…</p>
    </div>
  )
}
