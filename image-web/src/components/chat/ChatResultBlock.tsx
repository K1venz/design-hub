import {
  DownloadIcon,
  Loader2Icon,
  ScanSearchIcon,
  SquarePenIcon,
  WallpaperIcon,
} from 'lucide-react'

import type { ResultSlot } from '@/lib/listing'
import { downloadImage } from '@/lib/download'
import {
  editSourceFromSlot,
  previewImageFromSlot,
  type ChatEditSource,
  type ChatJobStatus,
  type ChatPreviewImage,
} from '@/lib/chat'

/** 出图加载中的温柔小字（按已出张数轮换，随进度自然变化）。 */
const LOADING_LINES = [
  '正在为你的商品认真打光…',
  '给画面找一个舒服的角落…',
  '光与影正在赶来…',
  '在调色盘上轻轻搅动…',
]

export function ChatResultBlock({
  slots,
  status,
  done,
  total,
  onPreview,
  onEdit,
  onBackground,
  onReversePrompt,
}: {
  slots: ResultSlot[]
  status: ChatJobStatus
  done: number
  total: number
  onPreview: (image: ChatPreviewImage) => void
  onEdit: (source: ChatEditSource) => void
  onBackground: (source: ChatEditSource) => void
  onReversePrompt: (source: ChatEditSource) => void
}) {
  const generating = status === 'generating' &&
    done < total &&
    slots.some(
      (slot) => !slot.url && !slot.error && !slot.unavailable,
    )
  const terminalLabels: Partial<Record<ChatJobStatus, string>> = {
    idle: '等待任务开始',
    completed: '图片未返回',
    failed: '生成失败',
    interrupted: '连接已中断，任务仍在后台执行',
  }
  // 出图加载中的温柔小字（按已出张数轮换，随进度自然变化）。
  const loadingLine = generating
    ? LOADING_LINES[done % LOADING_LINES.length]
    : null

  return (
    <div className="glass-lite max-w-[88%] rounded-2xl rounded-tl-md p-3">
      <p className="mb-2 px-1 text-[12.5px] font-medium text-wb-ink-3">
        出图结果 <span className="text-wb-ink-6">{done}/{total}</span>
        {generating && (
          <Loader2Icon className="ml-1.5 inline size-3 animate-spin text-wb-brand" />
        )}
      </p>
      {loadingLine && (
        <p className="mb-2 px-1 text-[11.5px] text-wb-ink-7">{loadingLine}</p>
      )}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {slots.map((slot, index) => {
          if (slot.unavailable) {
            return (
              <div
                key={`${slot.imageKey ?? 'unavailable'}-${index}`}
                className="grid aspect-square place-items-center rounded-xl border border-dashed border-wb-line-3 bg-wb-surface-3 p-3 text-center text-[11.5px] text-wb-ink-6"
              >
                该图片暂不可用
              </div>
            )
          }
          if (slot.url) {
            const preview = previewImageFromSlot(slot)
            const editSource = editSourceFromSlot(slot)
            return (
              <div
                key={`${slot.imageKey ?? slot.url}-${index}`}
                className="group relative aspect-square overflow-hidden rounded-xl border border-wb-line-1 bg-white"
              >
                <button
                  type="button"
                  onClick={() => preview && onPreview(preview)}
                  className="size-full"
                  aria-label={`预览第 ${index + 1} 张图片`}
                >
                  <img src={slot.url} alt="" className="size-full object-cover" />
                </button>
                <div className="absolute inset-x-1.5 bottom-1.5 flex flex-wrap justify-end gap-1 opacity-100 sm:opacity-0 sm:transition-opacity sm:group-hover:opacity-100">
                  {editSource ? (
                    <>
                      <button
                        type="button"
                        onClick={() => onEdit(editSource)}
                        className="rounded-lg bg-wb-brand/95 px-2 py-1 text-[11px] text-white"
                      >
                        <SquarePenIcon className="mr-1 inline size-3" />
                        继续编辑
                      </button>
                      <button
                        type="button"
                        onClick={() => onBackground(editSource)}
                        className="rounded-lg bg-wb-brand/95 px-2 py-1 text-[11px] text-white"
                      >
                        <WallpaperIcon className="mr-1 inline size-3" />
                        换背景
                      </button>
                      <button
                        type="button"
                        onClick={() => onReversePrompt(editSource)}
                        className="rounded-lg bg-wb-brand/95 px-2 py-1 text-[11px] text-white"
                      >
                        <ScanSearchIcon className="mr-1 inline size-3" />
                        反推提示词
                      </button>
                    </>
                  ) : <span />}
                  <button
                    type="button"
                    onClick={() => {
                      if (slot.url) {
                        void downloadImage(
                          slot.url,
                          `${slot.imageType ?? 'chat'}-${index + 1}.png`,
                        )
                      }
                    }}
                    className="rounded-lg bg-wb-ink-2/90 px-2 py-1 text-[11px] text-white"
                  >
                    <DownloadIcon className="mr-1 inline size-3" />
                    下载
                  </button>
                </div>
              </div>
            )
          }
          if (slot.error) {
            return (
              <div
                key={index}
                title={slot.error}
                className="grid aspect-square place-items-center rounded-xl border border-dashed border-wb-red-line bg-wb-red-tint p-2 text-center text-[11px] text-wb-red"
              >
                生成失败
              </div>
            )
          }
          const terminalLabel = terminalLabels[status]
          if (terminalLabel) {
            return (
              <div
                key={index}
                className="grid aspect-square place-items-center rounded-xl border border-dashed border-wb-line-3 bg-wb-surface-3 p-3 text-center text-[11.5px] text-wb-ink-6"
              >
                {terminalLabel}
              </div>
            )
          }
          return (
            <div
              key={index}
              role="status"
              aria-label="图片生成中"
              className="grid aspect-square place-items-center rounded-xl border border-dashed border-wb-line-3 bg-wb-surface-1"
            >
              <div className="size-5 animate-spin rounded-full border-2 border-wb-line-2 border-t-wb-brand" />
            </div>
          )
        })}
      </div>
    </div>
  )
}
