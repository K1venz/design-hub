import {
  ImageIcon,
  Loader2Icon,
  LockIcon,
  XIcon,
} from 'lucide-react'

import { ImageUploader } from '@/components/listing/ImageUploader'
import { GradientButton } from '@/components/visual/GradientButton'
import { cn } from '@/lib/utils'
import { estimateCost, type UploadedImage } from '@/lib/listing'
import type { BackgroundWorkbenchState } from '@/lib/image-tools'

interface BackgroundConfigPanelProps {
  state: BackgroundWorkbenchState
  ratio: string | null
  pending: boolean
  onChange: (state: BackgroundWorkbenchState) => void
  onSourceUpload: (image: UploadedImage | null) => void
  onReferenceUpload: (image: UploadedImage | null) => void
  onSourceDimensions: (width: number, height: number) => void
  onGenerate: () => void
}

export function BackgroundConfigPanel({
  state,
  ratio,
  pending,
  onChange,
  onSourceUpload,
  onReferenceUpload,
  onSourceDimensions,
  onGenerate,
}: BackgroundConfigPanelProps) {
  const backgroundReady =
    state.backgroundMode === 'description'
      ? state.description.trim().length > 0
      : state.reference !== null
  const canGenerate = state.source !== null && backgroundReady && !pending

  return (
    <div className="glass-panel flex w-[372px] shrink-0 flex-col overflow-hidden">
      <div className="flex-1 overflow-auto p-5">
        <div className="mb-2 flex items-center justify-between">
          <div>
            <h4 className="text-[13px] font-bold">商品源图</h4>
            <p className="mt-0.5 text-[11.5px] text-wb-ink-7">
              保留商品本身，只替换背景
            </p>
          </div>
          <span className="rounded-full bg-wb-tint-1 px-2 py-0.5 text-[10.5px] font-medium text-wb-brand-deep">
            必填 · 1 张
          </span>
        </div>
        {state.source ? (
          <SelectedImage
            previewUrl={state.source.previewUrl}
            label={
              state.source.kind === 'generated'
                ? '平台生成图'
                : '已上传商品图'
            }
            onRemove={() => onSourceUpload(null)}
            onDimensions={onSourceDimensions}
          />
        ) : (
          <ImageUploader
            max={1}
            onChange={(images) => onSourceUpload(images[0] ?? null)}
          />
        )}

        <h4 className="mb-2.5 mt-5 text-[13px] font-bold">目标背景</h4>
        <div className="grid grid-cols-2 gap-2 rounded-xl bg-wb-surface-4 p-1">
          {(
            [
              ['description', '文字描述'],
              ['reference', '参考背景图'],
            ] as const
          ).map(([mode, label]) => (
            <button
              key={mode}
              type="button"
              onClick={() => onChange({ ...state, backgroundMode: mode })}
              className={cn(
                'rounded-lg px-3 py-2 text-[12.5px] font-medium transition-colors',
                state.backgroundMode === mode
                  ? 'bg-white text-wb-brand-deep shadow-sm'
                  : 'text-wb-ink-6 hover:text-wb-ink-3',
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {state.backgroundMode === 'description' ? (
          <div className="mt-3">
            <textarea
              value={state.description}
              onChange={(event) =>
                onChange({ ...state, description: event.target.value })
              }
              placeholder="例如：明亮的现代咖啡店，暖色自然光，木质桌面，背景轻微虚化"
              className="min-h-28 w-full resize-none rounded-xl border border-wb-line-1 bg-white p-3 text-[13px] leading-relaxed text-wb-ink-2 outline-none focus-visible:border-wb-brand-soft"
            />
          </div>
        ) : (
          <div className="mt-3">
            {state.reference ? (
              <SelectedImage
                previewUrl={state.reference.previewUrl}
                label="背景参考图"
                onRemove={() => onReferenceUpload(null)}
              />
            ) : (
              <ImageUploader
                max={1}
                onChange={(images) =>
                  onReferenceUpload(images[0] ?? null)
                }
              />
            )}
            <textarea
              value={state.instruction}
              onChange={(event) =>
                onChange({ ...state, instruction: event.target.value })
              }
              placeholder="补充要求（选填），例如：商品放在桌面中央，背景轻微虚化"
              className="mt-3 min-h-20 w-full resize-none rounded-xl border border-wb-line-1 bg-white p-3 text-[13px] leading-relaxed text-wb-ink-2 outline-none focus-visible:border-wb-brand-soft"
            />
          </div>
        )}

        <div className="mt-5 rounded-xl border border-wb-line-1 bg-wb-surface-1 p-3">
          <div className="flex items-center justify-between text-[12.5px]">
            <span className="flex items-center gap-1.5 text-wb-ink-5">
              <LockIcon className="size-3.5" /> 输出比例
            </span>
            <span className="font-semibold text-wb-ink-3">
              {ratio ?? '选择商品图后识别'}
            </span>
          </div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-wb-ink-7">
            系统按商品源图选择最接近的支持比例，避免拉伸主体。
          </p>
        </div>
      </div>

      <div className="border-t border-wb-line-1 bg-white/60 p-4">
        <GradientButton
          onClick={onGenerate}
          disabled={!canGenerate}
          className="w-full"
        >
          {pending ? <Loader2Icon className="size-4 animate-spin" /> : null}
          开始换背景
          <span className="ml-2 text-[13px] font-normal opacity-90">
            约 ¥{estimateCost(1).toFixed(2)} · 1 张
          </span>
        </GradientButton>
      </div>
    </div>
  )
}

function SelectedImage({
  previewUrl,
  label,
  onRemove,
  onDimensions,
}: {
  previewUrl?: string
  label: string
  onRemove: () => void
  onDimensions?: (width: number, height: number) => void
}) {
  return (
    <div className="relative flex items-center gap-3 rounded-xl border border-wb-tint-line bg-wb-tint-3 p-3">
      {previewUrl ? (
        <img
          src={previewUrl}
          alt=""
          onLoad={(event) =>
            onDimensions?.(
              event.currentTarget.naturalWidth,
              event.currentTarget.naturalHeight,
            )
          }
          className="size-20 shrink-0 rounded-[10px] border border-wb-line-1 bg-white object-cover"
        />
      ) : (
        <span className="grid size-20 shrink-0 place-items-center rounded-[10px] border border-dashed border-wb-line-3 bg-white text-wb-faint-1">
          <ImageIcon className="size-6" />
        </span>
      )}
      <div className="min-w-0">
        <p className="text-[12.5px] font-semibold text-wb-ink-2">{label}</p>
        <p className="mt-1 text-[11.5px] text-wb-ink-6">
          {previewUrl ? '已准备好' : '提交时将重新校验图片'}
        </p>
      </div>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`移除${label}`}
        className="absolute right-2 top-2 grid size-7 place-items-center rounded-full text-wb-ink-5 hover:bg-white hover:text-wb-ink-2"
      >
        <XIcon className="size-4" />
      </button>
    </div>
  )
}
