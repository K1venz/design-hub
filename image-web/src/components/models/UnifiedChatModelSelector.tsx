import { useMemo, useState } from 'react'
import {
  BotIcon,
  CheckIcon,
  ChevronDownIcon,
  Loader2Icon,
  RefreshCwIcon,
  SearchIcon,
  TriangleAlertIcon,
} from 'lucide-react'

import type { ModelCatalogItem } from '@/api/models'
import type { ModelSelection } from '@/components/models/model-selection'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'

interface Brand {
  name: string
  logoPath: string | null
}

const KNOWN_BRANDS: Array<{ match: RegExp; brand: Brand }> = [
  {
    match: /deepseek/i,
    brand: { name: 'DeepSeek', logoPath: '/model-brands/deepseek.svg' },
  },
  {
    match: /doubao|豆包/i,
    brand: { name: '豆包', logoPath: '/model-brands/doubao.svg' },
  },
  {
    match: /gpt|openai/i,
    brand: { name: 'OpenAI', logoPath: '/model-brands/openai.svg' },
  },
  {
    match: /wan|万相/i,
    brand: { name: '通义万相', logoPath: '/model-brands/wan.svg' },
  },
]

export function modelBrand(modelId: string): Brand {
  return (
    KNOWN_BRANDS.find(({ match }) => match.test(modelId))?.brand ?? {
      name: '其他',
      logoPath: null,
    }
  )
}

export function filterModelCatalog(
  models: ModelCatalogItem[],
  query: string,
): ModelCatalogItem[] {
  const normalized = query.trim().toLocaleLowerCase()
  if (!normalized) return models
  return models.filter((model) => {
    const brand = modelBrand(model.id)
    return [model.display_name, model.id, brand.name].some((value) =>
      value.toLocaleLowerCase().includes(normalized),
    )
  })
}

export function UnifiedChatModelSelector({
  chatSelection,
  imageSelection,
  disabled = false,
}: {
  chatSelection: ModelSelection
  imageSelection: ModelSelection
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const filteredChat = useMemo(
    () => filterModelCatalog(chatSelection.models, query),
    [chatSelection.models, query],
  )
  const filteredImage = useMemo(
    () => filterModelCatalog(imageSelection.models, query),
    [imageSelection.models, query],
  )
  const chatModel = selectedModel(chatSelection)
  const imageModel = selectedModel(imageSelection)

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
          disabled={disabled}
          aria-label="选择文本和图片模型"
          className="flex h-8 min-w-0 max-w-[260px] items-center gap-0.5 rounded-full border border-wb-line-1 bg-white/85 px-1.5 text-[11px] font-medium text-wb-ink-4 outline-none transition-[border-color,background-color,box-shadow] hover:border-wb-brand-soft focus-visible:ring-2 focus-visible:ring-wb-brand-soft disabled:cursor-not-allowed disabled:opacity-45 sm:max-w-[360px] sm:text-xs"
        >
          <TriggerSegment
            kind="chat"
            model={chatModel}
            state={chatSelection.state}
          />
          <span className="h-4 w-px shrink-0 bg-wb-line-1" />
          <TriggerSegment
            kind="image"
            model={imageModel}
            state={imageSelection.state}
            collapseLabel
          />
          <ChevronDownIcon className="size-3.5 shrink-0 text-wb-ink-7" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        side="top"
        align="end"
        sideOffset={10}
        className="w-[min(360px,calc(100vw-32px))] rounded-2xl border border-white/90 bg-white/96 p-2 shadow-[0_24px_70px_-28px_rgba(35,38,47,.42)] backdrop-blur-xl"
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
          selection={chatSelection}
          filteredModels={filteredChat}
        />
        <DropdownMenuSeparator className="my-1.5" />
        <ModelGroup
          label="图片模型"
          selection={imageSelection}
          filteredModels={filteredImage}
        />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function TriggerSegment({
  kind,
  model,
  state,
  collapseLabel = false,
}: {
  kind: 'chat' | 'image'
  model: ModelCatalogItem | null
  state: ModelSelection['state']
  collapseLabel?: boolean
}) {
  const label = triggerLabel(kind, model, state)
  return (
    <span className="flex min-w-0 items-center gap-1.5 px-1.5">
      <BrandLogo modelId={model?.id ?? null} />
      <span
        className={cn(
          'max-w-24 truncate',
          collapseLabel && 'hidden sm:inline',
          state !== 'ready' && 'text-wb-amber',
        )}
      >
        {label}
      </span>
    </span>
  )
}

function triggerLabel(
  kind: 'chat' | 'image',
  model: ModelCatalogItem | null,
  state: ModelSelection['state'],
): string {
  if (state === 'ready' && model) return model.display_name
  const label = kind === 'chat' ? '文本' : '图片'
  if (state === 'loading') return `${label}模型加载中`
  if (state === 'error') return `${label}模型异常`
  if (state === 'empty') return `无${label}模型`
  return `选择${label}模型`
}

function ModelGroup({
  label,
  selection,
  filteredModels,
}: {
  label: string
  selection: ModelSelection
  filteredModels: ModelCatalogItem[]
}) {
  return (
    <div>
      <DropdownMenuLabel className="flex items-center justify-between px-2 pb-1 pt-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-wb-ink-7">
        {label}
        {selection.state === 'selection_required' && (
          <span className="normal-case tracking-normal text-wb-amber">需重选</span>
        )}
      </DropdownMenuLabel>
      <GroupState selection={selection} />
      {(selection.state === 'ready' ||
        selection.state === 'selection_required') &&
        (filteredModels.length === 0 ? (
          <p className="px-2 py-3 text-center text-[11px] text-wb-ink-7">
            没有匹配的模型
          </p>
        ) : (
          filteredModels.map((model) => {
            const selected = model.id === selection.modelId
            return (
              <DropdownMenuItem
                key={model.id}
                onSelect={() => selection.select(model.id)}
                className={cn(
                  'min-h-11 cursor-pointer gap-2.5 rounded-xl px-2.5 py-2 focus:bg-wb-tint-3',
                  selected && 'bg-wb-tint-3 text-wb-brand-deep',
                )}
              >
                <span className="grid size-7 shrink-0 place-items-center rounded-lg border border-wb-line-1 bg-white">
                  <BrandLogo modelId={model.id} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12px] font-semibold text-wb-ink-3">
                    {model.display_name}
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
        ))}
    </div>
  )
}

function GroupState({ selection }: { selection: ModelSelection }) {
  if (selection.state === 'loading') {
    return (
      <p className="flex items-center gap-2 px-2 py-3 text-[11px] text-wb-ink-7">
        <Loader2Icon className="size-3.5 animate-spin" /> 正在加载…
      </p>
    )
  }
  if (selection.state === 'error') {
    return (
      <button
        type="button"
        onClick={selection.retry}
        className="mx-1 flex w-[calc(100%-8px)] items-center justify-center gap-1.5 rounded-lg border border-wb-red-line bg-wb-red-tint px-2 py-2 text-[11px] text-wb-red"
      >
        <RefreshCwIcon className="size-3.5" /> 加载失败，点击重试
      </button>
    )
  }
  if (selection.state === 'empty') {
    return (
      <p className="flex items-start gap-1.5 px-2 py-3 text-[11px] leading-5 text-wb-amber">
        <TriangleAlertIcon className="mt-0.5 size-3.5 shrink-0" />
        当前没有可用模型，请联系管理员完成配置。
      </p>
    )
  }
  return null
}

function BrandLogo({ modelId }: { modelId: string | null }) {
  const brand = modelId ? modelBrand(modelId) : null
  if (!brand?.logoPath) {
    return (
      <span
        data-brand="unknown"
        className="grid size-4 shrink-0 place-items-center rounded-full bg-wb-surface-2 text-wb-ink-6"
      >
        <BotIcon className="size-3" />
      </span>
    )
  }
  return (
    <img
      src={brand.logoPath}
      alt={`${brand.name} Logo`}
      className="size-4 shrink-0 object-contain"
    />
  )
}

function selectedModel(selection: ModelSelection): ModelCatalogItem | null {
  return (
    selection.models.find((model) => model.id === selection.modelId) ?? null
  )
}
