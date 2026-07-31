import { useMemo, useState } from 'react'
import {
  CheckIcon,
  ChevronDownIcon,
  ImagePlusIcon,
  SearchIcon,
  SendIcon,
  SparklesIcon,
} from 'lucide-react'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

import {
  DEMO_MODELS,
  brandLogoPath,
  filterDemoModels,
  type DemoModel,
  type DemoModelKind,
} from './demo-models'

const VARIANTS = [
  {
    id: 'deerflow',
    name: 'A · DeerFlow 极简型',
    description: '最像成熟 AI 对话产品，信息密度高，入口紧邻发送。',
  },
  {
    id: 'brand-card',
    name: 'B · 品牌卡片型',
    description: '品牌识别更强，模型项更舒展，适合强调不同模型能力。',
  },
  {
    id: 'dual-compact',
    name: 'C · 双模型紧凑型',
    description: '入口直接展示文本与图片模型，当前状态最透明。',
  },
] as const

type VariantId = (typeof VARIANTS)[number]['id']

interface SelectionProps {
  chatModelId: string
  imageModelId: string
  busy: boolean
  onChatModelChange: (modelId: string) => void
  onImageModelChange: (modelId: string) => void
}

export function ModelSelectorDemoPage() {
  const [chatModelId, setChatModelId] = useState('deepseek-v4-flash')
  const [imageModelId, setImageModelId] = useState('gpt-image-2')
  const [busy, setBusy] = useState(false)

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#f3f4f8] px-4 py-8 text-wb-ink-2 sm:px-8 sm:py-12">
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-[420px] opacity-70"
        style={{
          background:
            'radial-gradient(520px 260px at 18% 0%, rgba(91,91,214,.14), transparent 72%), radial-gradient(480px 260px at 88% 8%, rgba(123,108,240,.10), transparent 72%)',
        }}
      />

      <header className="relative mx-auto max-w-5xl">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-[0.18em] text-wb-brand-deep">
              <SparklesIcon className="size-3.5" /> Model picker study
            </p>
            <h1 className="mt-2.5 text-2xl font-semibold tracking-[-0.03em] sm:text-[30px]">
              统一模型入口 · 三种交互风格
            </h1>
            <p className="mt-2 max-w-2xl text-[13px] leading-6 text-wb-ink-6 sm:text-sm">
              三款使用同一组模型与选择状态，便于只比较入口和下拉层级。点击任意一款切换模型，另外两款会同步更新。
            </p>
          </div>
          <label className="inline-flex w-fit cursor-pointer items-center gap-2.5 rounded-full border border-white/85 bg-white/75 px-3 py-2 text-[12px] font-medium text-wb-ink-5 shadow-sm backdrop-blur-xl">
            <input
              type="checkbox"
              checked={busy}
              onChange={(event) => setBusy(event.target.checked)}
              className="size-3.5 accent-wb-brand"
            />
            模拟生成中（锁定选择器）
          </label>
        </div>
      </header>

      <section className="relative mx-auto mt-8 grid max-w-5xl gap-6">
        {VARIANTS.map((variant, index) => (
          <SelectorPreview
            key={variant.id}
            index={index + 1}
            variant={variant}
            chatModelId={chatModelId}
            imageModelId={imageModelId}
            busy={busy}
            onChatModelChange={setChatModelId}
            onImageModelChange={setImageModelId}
          />
        ))}
      </section>
    </main>
  )
}

function SelectorPreview({
  index,
  variant,
  ...selection
}: SelectionProps & {
  index: number
  variant: (typeof VARIANTS)[number]
}) {
  return (
    <article className="rounded-[24px] border border-white/80 bg-white/58 p-4 shadow-[0_22px_70px_-42px_rgba(40,40,90,.44)] backdrop-blur-xl sm:p-6">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <span className="grid size-8 shrink-0 place-items-center rounded-[10px] bg-wb-tint-1 text-[12px] font-bold text-wb-brand-deep">
            0{index}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-[14px] font-semibold tracking-[-0.01em] sm:text-[15px]">
                {variant.name}
              </h2>
              {variant.id === 'deerflow' && (
                <span className="rounded-full bg-wb-tint-1 px-2 py-0.5 text-[10px] font-semibold text-wb-brand-deep">
                  推荐基线
                </span>
              )}
            </div>
            <p className="mt-1 text-[12px] leading-5 text-wb-ink-6">
              {variant.description}
            </p>
          </div>
        </div>
        <span className="hidden shrink-0 rounded-full border border-wb-line-1 bg-white/75 px-2.5 py-1 text-[10px] font-medium text-wb-ink-7 sm:inline-flex">
          可交互
        </span>
      </div>

      <ComposerMock variant={variant.id} {...selection} />
    </article>
  )
}

function ComposerMock({ variant, ...selection }: SelectionProps & { variant: VariantId }) {
  return (
    <div className="rounded-[22px] border border-white/90 bg-white/82 p-3 shadow-[0_18px_50px_-30px_rgba(40,40,90,.38)] backdrop-blur-xl">
      <textarea
        readOnly
        value="帮我生成一组适合电商首页的产品场景图"
        aria-label="示例消息"
        className="h-[74px] w-full resize-none bg-transparent px-2 py-1 text-[13px] leading-6 text-wb-ink-3 outline-none sm:text-sm"
      />
      <div className="flex items-center justify-between gap-2 px-1">
        <button
          type="button"
          className="flex shrink-0 items-center gap-1.5 rounded-full border border-wb-line-1 bg-white/75 px-2.5 py-1.5 text-[11px] font-medium text-wb-ink-5 transition-colors hover:border-wb-brand-soft hover:text-wb-brand-deep sm:px-3 sm:text-xs"
        >
          <ImagePlusIcon className="size-3.5" />
          <span className="hidden min-[360px]:inline">添加图片</span>
        </button>
        <div className="flex min-w-0 items-center justify-end gap-2">
          <UnifiedDemoSelector variant={variant} {...selection} />
          <button
            type="button"
            className="grid size-8 shrink-0 place-items-center rounded-full bg-wb-brand text-white shadow-[0_7px_18px_-8px_rgba(91,91,214,.8)] transition-transform hover:scale-[1.03]"
            aria-label="发送"
          >
            <SendIcon className="size-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}

function UnifiedDemoSelector({
  variant,
  chatModelId,
  imageModelId,
  busy,
  onChatModelChange,
  onImageModelChange,
}: SelectionProps & { variant: VariantId }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const chatModel = requireDemoModel(chatModelId)
  const imageModel = requireDemoModel(imageModelId)
  const filtered = useMemo(() => filterDemoModels(DEMO_MODELS, query), [query])

  function selectModel(model: DemoModel) {
    if (model.kind === 'chat') onChatModelChange(model.id)
    else onImageModelChange(model.id)
  }

  return (
    <DropdownMenu
      open={open}
      onOpenChange={(nextOpen) => {
        setOpen(nextOpen)
        if (!nextOpen) setQuery('')
      }}
    >
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          disabled={busy}
          aria-label={`选择模型，当前文本模型 ${chatModel.displayName}，图片模型 ${imageModel.displayName}`}
          className={triggerClass(variant)}
        >
          <SelectorTriggerContent
            variant={variant}
            chatModel={chatModel}
            imageModel={imageModel}
          />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        side="top"
        align="end"
        sideOffset={10}
        className={cn(
          'w-[min(360px,calc(100vw-32px))] rounded-2xl border border-white/90 bg-white/96 p-2 shadow-[0_24px_70px_-28px_rgba(35,38,47,.42)] backdrop-blur-xl',
          variant === 'brand-card' && 'p-2.5',
        )}
      >
        <div className="relative mb-1.5">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-wb-ink-7" />
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => event.stopPropagation()}
            placeholder="搜索模型"
            aria-label="搜索模型"
            className="h-9 w-full rounded-xl border border-wb-line-1 bg-wb-surface-2 pl-9 pr-3 text-xs text-wb-ink-3 outline-none transition-colors placeholder:text-wb-faint-1 focus:border-wb-brand-soft"
          />
        </div>
        <ModelGroup
          label="文本模型"
          kind="chat"
          models={filtered}
          selectedId={chatModelId}
          variant={variant}
          onSelect={selectModel}
        />
        <DropdownMenuSeparator className="my-1.5" />
        <ModelGroup
          label="图片模型"
          kind="image"
          models={filtered}
          selectedId={imageModelId}
          variant={variant}
          onSelect={selectModel}
        />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function SelectorTriggerContent({
  variant,
  chatModel,
  imageModel,
}: {
  variant: VariantId
  chatModel: DemoModel
  imageModel: DemoModel
}) {
  if (variant === 'dual-compact') {
    return (
      <>
        <span className="flex min-w-0 items-center gap-1.5 px-1.5">
          <BrandLogo model={chatModel} size="sm" />
          <span className="max-w-24 truncate">{chatModel.displayName}</span>
        </span>
        <span className="h-4 w-px shrink-0 bg-wb-line-1" />
        <span className="flex min-w-0 items-center gap-1.5 px-1.5">
          <BrandLogo model={imageModel} size="sm" />
          <span className="hidden max-w-24 truncate sm:inline">
            {imageModel.displayName}
          </span>
        </span>
        <ChevronDownIcon className="size-3.5 shrink-0 text-wb-ink-7" />
      </>
    )
  }

  return (
    <>
      <span className={cn('relative shrink-0', variant === 'brand-card' && 'rounded-lg bg-white p-1 shadow-sm')}>
        <BrandLogo model={chatModel} size={variant === 'brand-card' ? 'md' : 'sm'} />
        <span className="absolute -bottom-1 -right-1 rounded-full bg-white p-[2px] shadow-sm ring-1 ring-wb-line-1">
          <BrandLogo model={imageModel} size="xs" />
        </span>
      </span>
      <span className="min-w-0 flex-1 truncate text-left">
        {chatModel.displayName}
      </span>
      <ChevronDownIcon className="size-3.5 shrink-0 text-wb-ink-7" />
    </>
  )
}

function ModelGroup({
  label,
  kind,
  models,
  selectedId,
  variant,
  onSelect,
}: {
  label: string
  kind: DemoModelKind
  models: DemoModel[]
  selectedId: string
  variant: VariantId
  onSelect: (model: DemoModel) => void
}) {
  const group = models.filter((model) => model.kind === kind)

  return (
    <div>
      <DropdownMenuLabel className="px-2 pb-1 pt-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-wb-ink-7">
        {label}
      </DropdownMenuLabel>
      {group.length === 0 ? (
        <p className="px-2 py-3 text-center text-[11px] text-wb-ink-7">
          没有匹配的模型
        </p>
      ) : (
        group.map((model) => {
          const selected = model.id === selectedId
          return (
            <DropdownMenuItem
              key={model.id}
              onSelect={() => onSelect(model)}
              className={cn(
                'min-h-11 cursor-pointer gap-2.5 rounded-xl px-2.5 py-2 focus:bg-wb-tint-3',
                selected && 'bg-wb-tint-3 text-wb-brand-deep',
                variant === 'brand-card' && 'my-0.5 min-h-[54px] px-2',
              )}
            >
              <span
                className={cn(
                  'grid size-7 shrink-0 place-items-center rounded-lg border border-wb-line-1 bg-white',
                  variant === 'brand-card' && 'size-9 rounded-xl shadow-sm',
                )}
              >
                <BrandLogo model={model} size={variant === 'brand-card' ? 'md' : 'sm'} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[12px] font-semibold text-wb-ink-3">
                  {model.displayName}
                </span>
                <span className="mt-0.5 block truncate font-mono text-[9.5px] text-wb-ink-7">
                  {model.id}
                </span>
              </span>
              {selected ? (
                <>
                  <CheckIcon className="size-4 shrink-0 text-wb-brand-deep" />
                  <span className="sr-only">已选择</span>
                </>
              ) : (
                <span className="size-4 shrink-0" />
              )}
            </DropdownMenuItem>
          )
        })
      )}
    </div>
  )
}

function BrandLogo({
  model,
  size,
}: {
  model: DemoModel
  size: 'xs' | 'sm' | 'md'
}) {
  return (
    <img
      src={brandLogoPath(model.brand)}
      alt={`${model.brandName} Logo`}
      className={cn(
        'object-contain',
        size === 'xs' && 'size-2.5',
        size === 'sm' && 'size-4',
        size === 'md' && 'size-5',
      )}
    />
  )
}

function requireDemoModel(modelId: string): DemoModel {
  const model = DEMO_MODELS.find((candidate) => candidate.id === modelId)
  if (!model) throw new Error(`未知 Demo 模型：${modelId}`)
  return model
}

function triggerClass(variant: VariantId): string {
  const base =
    'flex min-w-0 items-center gap-2 text-[11px] font-medium outline-none transition-[border-color,background-color,box-shadow] focus-visible:ring-2 focus-visible:ring-wb-brand-soft disabled:cursor-not-allowed disabled:opacity-45 sm:text-xs'
  if (variant === 'brand-card') {
    return cn(
      base,
      'h-9 max-w-[210px] rounded-xl border border-wb-brand-soft bg-wb-tint-3 px-2.5 text-wb-brand-deep hover:bg-wb-tint-1 sm:max-w-[250px]',
    )
  }
  if (variant === 'dual-compact') {
    return cn(
      base,
      'h-8 max-w-[260px] gap-0.5 rounded-full border border-wb-line-1 bg-white/85 px-1.5 text-wb-ink-4 hover:border-wb-brand-soft sm:max-w-[360px]',
    )
  }
  return cn(
    base,
    'h-8 max-w-[190px] rounded-full border border-transparent bg-wb-surface-2 px-2.5 text-wb-ink-4 hover:border-wb-line-1 hover:bg-white sm:max-w-[240px]',
  )
}
