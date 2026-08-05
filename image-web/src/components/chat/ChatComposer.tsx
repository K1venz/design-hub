import { useRef, useState } from 'react'
import {
  ChevronDownIcon,
  ChevronUpIcon,
  ImagePlusIcon,
  InfoIcon,
  Loader2Icon,
  Maximize2Icon,
  Minimize2Icon,
  ScanSearchIcon,
  SendIcon,
  SparklesIcon,
  Trash2Icon,
  XIcon,
} from 'lucide-react'

import { UnifiedChatModelSelector } from '@/components/models/UnifiedChatModelSelector'
import type { ModelSelection } from '@/components/models/model-selection'
import {
  type ChatImageCount,
  type ChatImageOptionDraft,
  type ChatImageRatio,
  type ChatRenderTier,
  chatImageRatiosFor,
} from '@/lib/chat-image-options'
import { shouldSubmitChatInput, type ChatEditSource } from '@/lib/chat'
import type { UploadedImage } from '@/lib/listing'
import { uploadPreviewUrl } from '@/lib/upload'
import { cn } from '@/lib/utils'

const COUNTS: ChatImageCount[] = ['auto', 1, 2, 3, 4, 5, 6, 7]

interface ChatComposerProps {
  draft: string
  onDraftChange: (value: string) => void
  attached: UploadedImage[]
  selectedEditSource: ChatEditSource | null
  token: string | null
  busy: boolean
  modelsReady: boolean
  uploadPending: boolean
  imageOptions: ChatImageOptionDraft
  onImageOptionsChange: (options: ChatImageOptionDraft) => void
  chatSelection: ModelSelection
  imageSelection: ModelSelection
  onPickFiles: (files: FileList | null) => void
  onRemoveAttachment: (index: number) => void
  onCancelEdit: () => void
  onReversePrompt: () => void
  onClear: () => void
  onSend: () => void
}

export function ChatComposer({
  draft,
  onDraftChange,
  attached,
  selectedEditSource,
  token,
  busy,
  modelsReady,
  uploadPending,
  imageOptions,
  onImageOptionsChange,
  chatSelection,
  imageSelection,
  onPickFiles,
  onRemoveAttachment,
  onCancelEdit,
  onReversePrompt,
  onClear,
  onSend,
}: ChatComposerProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [collapsed, setCollapsed] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [enterToSend, setEnterToSend] = useState(true)
  const fourKAvailable = imageSelection.modelId === 'gpt-image-2'
  const fourK = imageOptions.renderTier === '4k'
  const ratios = chatImageRatiosFor(
    imageSelection.modelId,
    imageOptions.renderTier,
  )
  const canSend = !busy && modelsReady && draft.trim().length > 0

  function updateRenderTier(renderTier: ChatRenderTier) {
    onImageOptionsChange({ ...imageOptions, renderTier })
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    const submit = enterToSend
      ? shouldSubmitChatInput({
          key: event.key,
          shiftKey: event.shiftKey,
          isComposing: event.nativeEvent.isComposing,
        })
      : event.key === 'Enter' && event.ctrlKey && !event.nativeEvent.isComposing
    if (!submit) return
    event.preventDefault()
    onSend()
  }

  const textarea = (
    <textarea
      value={draft}
      onChange={(event) => onDraftChange(event.target.value)}
      onKeyDown={handleKeyDown}
      disabled={busy}
      aria-label="图片创作提示词"
      placeholder={
        busy
          ? '请等待当前对话完成…'
          : selectedEditSource
            ? '描述你希望如何修改这张图片…'
            : '描述画面主体、场景、风格、光线和文字排版…'
      }
      className={cn(
        'w-full resize-none bg-transparent text-[14px] leading-7 text-wb-ink-2 outline-none placeholder:text-wb-faint-1 disabled:opacity-60',
        expanded ? 'min-h-[50vh]' : 'min-h-24',
      )}
    />
  )

  return (
    <>
      <section
        data-testid="chat-composer"
        className="w-full min-w-0 overflow-hidden rounded-[20px] border border-wb-brand-soft bg-white/92 shadow-[0_24px_70px_-34px_rgba(39,45,88,.45)] backdrop-blur-xl"
      >
        <header className="flex min-h-9 items-center gap-2 border-b border-wb-line-1 px-3.5">
          <span className="size-2 rounded-full bg-wb-brand shadow-[0_0_0_4px_var(--wb-tint-1)]" />
          <span className="text-[12.5px] font-semibold text-wb-ink-2">图片创作</span>
          <span className="text-[10.5px] text-wb-ink-6">支持 1–3 张参考图</span>
          <span className="ml-auto hidden rounded-full bg-wb-amber-tint px-2 py-0.5 text-[10px] font-medium text-wb-amber sm:inline">
            参数随分辨率联动
          </span>
          <button
            type="button"
            onClick={() => setCollapsed((value) => !value)}
            className="grid size-7 place-items-center rounded-lg text-wb-ink-6 hover:bg-wb-surface-2 hover:text-wb-ink-3"
            aria-label={collapsed ? '展开输入台' : '收起输入台'}
          >
            {collapsed ? <ChevronUpIcon className="size-3.5" /> : <ChevronDownIcon className="size-3.5" />}
          </button>
          <button
            type="button"
            onClick={onClear}
            disabled={!draft && attached.length === 0 && !selectedEditSource}
            className="grid size-7 place-items-center rounded-lg text-wb-ink-6 hover:bg-wb-red-tint hover:text-wb-red disabled:opacity-35"
            aria-label="清空输入"
          >
            <Trash2Icon className="size-3.5" />
          </button>
        </header>

        {!collapsed && (
          <>
            <div className="flex min-h-[132px] gap-3 px-3.5 py-3">
              <div className="flex w-16 shrink-0 flex-col items-center gap-1.5">
                {selectedEditSource ? (
                  <ReferenceThumbnail
                    src={selectedEditSource.url}
                    label="编辑底图"
                    onRemove={onCancelEdit}
                  />
                ) : attached.length > 0 ? (
                  <div className="flex flex-wrap justify-center gap-1.5">
                    {attached.map((image, index) => (
                      <ReferenceThumbnail
                        key={image.id}
                        src={uploadPreviewUrl(image.url, token)}
                        label={index === 0 ? '参考图' : `${index + 1}`}
                        compact={attached.length > 1}
                        onRemove={() => onRemoveAttachment(index)}
                      />
                    ))}
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => fileRef.current?.click()}
                    disabled={busy || uploadPending}
                    className="group grid h-16 w-14 place-items-center rounded-xl border border-dashed border-wb-line-4 bg-wb-surface-2 text-wb-ink-6 transition-colors hover:border-wb-brand-soft hover:bg-wb-tint-3 hover:text-wb-brand-deep disabled:opacity-50"
                    aria-label="添加参考图"
                  >
                    {uploadPending ? <Loader2Icon className="size-4 animate-spin" /> : <ImagePlusIcon className="size-4" />}
                  </button>
                )}
                <span className="text-[10px] text-wb-ink-6">
                  {selectedEditSource ? '编辑底图' : '参考图'}
                </span>
              </div>

              <div className="min-w-0 flex-1">
                {textarea}
                <div className="mt-1 flex flex-wrap items-center gap-1.5">
                  {(attached.length > 0 || selectedEditSource) && attached.length < 3 && !selectedEditSource && (
                    <button
                      type="button"
                      onClick={() => fileRef.current?.click()}
                      disabled={busy || uploadPending}
                      className="inline-flex items-center gap-1 rounded-full border border-wb-line-1 px-2.5 py-1 text-[10.5px] text-wb-ink-5 hover:border-wb-brand-soft hover:text-wb-brand-deep"
                    >
                      <ImagePlusIcon className="size-3" /> 继续添加
                    </button>
                  )}
                  {attached.length === 1 && (
                    <button
                      type="button"
                      onClick={onReversePrompt}
                      disabled={busy || !modelsReady}
                      className="inline-flex items-center gap-1 rounded-full border border-wb-brand-soft bg-wb-tint-3 px-2.5 py-1 text-[10.5px] font-medium text-wb-brand-deep disabled:opacity-45"
                    >
                      <ScanSearchIcon className="size-3" /> 反推提示词
                    </button>
                  )}
                </div>
              </div>
            </div>

            <div className="mx-3.5 flex items-center gap-2 rounded-lg bg-wb-surface-2 px-3 py-1.5 text-[10.5px] text-wb-ink-6">
              <InfoIcon className="size-3 shrink-0 text-wb-brand" />
              <span className="truncate">
                {fourK
                  ? '4K 固定输出 3840×2160、16:9；数量可指定 1–7 张，仅 GPT Image 2.0 可用。'
                  : imageSelection.modelId === 'gpt-image-2'
                    ? 'GPT Image 2 标准档支持 1:1（1024×1024）与 3:2（1536×1024）；数量可指定 1–7 张。'
                    : '标准档数量可自动判断或指定 1–7 张。'}
              </span>
            </div>
          </>
        )}

        <footer className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-wb-line-1 px-2.5 py-2">
          <UnifiedChatModelSelector
            chatSelection={chatSelection}
            imageSelection={imageSelection}
            disabled={busy}
          />
          <ParameterSelect
            ariaLabel="分辨率模式"
            value={imageOptions.renderTier}
            disabled={busy}
            onChange={(value) => updateRenderTier(value as ChatRenderTier)}
          >
            <option value="auto">自动判断</option>
            <option value="standard">标准档</option>
            <option value="4k" disabled={!fourKAvailable}>4K 超高清</option>
          </ParameterSelect>
          <ParameterSelect
            ariaLabel="生成数量"
            value={String(imageOptions.count)}
            disabled={busy}
            onChange={(value) =>
              onImageOptionsChange({
                ...imageOptions,
                count: value === 'auto' ? 'auto' : Number(value) as ChatImageCount,
              })
            }
          >
            {COUNTS.map((count) => (
              <option key={count} value={count}>
                {count === 'auto' ? '数量自适应' : `${count} 张`}
              </option>
            ))}
          </ParameterSelect>
          <ParameterSelect
            ariaLabel="图片比例"
            value={fourK ? '16:9' : imageOptions.ratio}
            disabled={busy || fourK}
            onChange={(value) =>
              onImageOptionsChange({ ...imageOptions, ratio: value as ChatImageRatio })
            }
          >
            {ratios.map((ratio) => (
              <option key={ratio} value={ratio}>
                {ratio === 'auto' ? '比例自适应' : ratio}
              </option>
            ))}
          </ParameterSelect>

          <div className="ml-auto flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setEnterToSend((value) => !value)}
              className="hidden rounded-lg px-2 py-1.5 text-[10.5px] text-wb-ink-6 hover:bg-wb-surface-2 sm:block"
              aria-label="切换发送快捷键"
              title={enterToSend ? 'Enter 发送，Shift+Enter 换行' : 'Ctrl+Enter 发送，Enter 换行'}
            >
              {enterToSend ? 'Enter 发送' : 'Ctrl+Enter 发送'}
            </button>
            <button
              type="button"
              onClick={() => setExpanded(true)}
              className="grid size-8 place-items-center rounded-lg border border-wb-line-1 text-wb-ink-5 hover:border-wb-brand-soft hover:text-wb-brand-deep"
              aria-label="全屏编辑提示词"
            >
              <Maximize2Icon className="size-3.5" />
            </button>
            <button
              type="button"
              onClick={onSend}
              disabled={!canSend}
              className="grid size-9 place-items-center rounded-full bg-gradient-to-r from-wb-grad-from to-wb-grad-to text-white shadow-[0_9px_22px_-9px_rgba(91,91,214,.68)] transition-transform hover:scale-[1.03] disabled:scale-100 disabled:opacity-40"
              aria-label="发送并生成"
            >
              {busy ? <Loader2Icon className="size-4 animate-spin" /> : <SendIcon className="size-4" />}
            </button>
          </div>
        </footer>
      </section>

      <input
        ref={fileRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        multiple
        hidden
        onChange={(event) => {
          onPickFiles(event.target.files)
          event.target.value = ''
        }}
      />

      {expanded && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-wb-ink-1/35 p-4 backdrop-blur-sm">
          <div className="w-full max-w-3xl rounded-3xl border border-white/90 bg-white p-4 shadow-2xl">
            <div className="mb-3 flex items-center gap-2">
              <SparklesIcon className="size-4 text-wb-brand" />
              <h2 className="text-sm font-semibold text-wb-ink-2">全屏编辑提示词</h2>
              <button
                type="button"
                onClick={() => setExpanded(false)}
                className="ml-auto grid size-8 place-items-center rounded-lg text-wb-ink-5 hover:bg-wb-surface-2"
                aria-label="退出全屏编辑"
              >
                <Minimize2Icon className="size-4" />
              </button>
            </div>
            <div className="rounded-2xl border border-wb-line-1 bg-wb-surface-2 p-4">
              {textarea}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function ParameterSelect({
  ariaLabel,
  value,
  disabled,
  onChange,
  children,
}: {
  ariaLabel: string
  value: string
  disabled: boolean
  onChange: (value: string) => void
  children: React.ReactNode
}) {
  return (
    <label className="relative">
      <span className="sr-only">{ariaLabel}</span>
      <select
        aria-label={ariaLabel}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="h-8 appearance-none rounded-lg border border-wb-line-1 bg-white pl-2.5 pr-7 text-[11px] font-medium text-wb-ink-4 outline-none transition-colors hover:border-wb-brand-soft focus:border-wb-brand focus:ring-2 focus:ring-wb-brand-soft disabled:bg-wb-surface-2 disabled:text-wb-ink-7"
      >
        {children}
      </select>
      <ChevronDownIcon className="pointer-events-none absolute right-2 top-1/2 size-3 -translate-y-1/2 text-wb-ink-7" />
    </label>
  )
}

function ReferenceThumbnail({
  src,
  label,
  compact = false,
  onRemove,
}: {
  src: string
  label: string
  compact?: boolean
  onRemove: () => void
}) {
  return (
    <span className="relative inline-flex flex-col items-center gap-1">
      <img
        src={src}
        alt={label}
        className={cn(
          'rounded-xl border border-wb-line-1 object-cover',
          compact ? 'size-7' : 'h-16 w-14',
        )}
      />
      {!compact && <span className="sr-only">{label}</span>}
      <button
        type="button"
        onClick={onRemove}
        className="absolute -right-1.5 -top-1.5 grid size-4 place-items-center rounded-full bg-wb-ink-2 text-white shadow"
        aria-label={`移除${label}`}
      >
        <XIcon className="size-2.5" />
      </button>
    </span>
  )
}
