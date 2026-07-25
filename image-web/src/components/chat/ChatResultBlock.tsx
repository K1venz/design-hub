import {
  DownloadIcon,
  Loader2Icon,
  SquarePenIcon,
} from 'lucide-react'

import type { ResultSlot } from '@/components/listing/ResultGallery'
import { downloadImage } from '@/lib/download'
import {
  editSourceFromSlot,
  previewImageFromSlot,
  type ChatEditSource,
  type ChatPreviewImage,
} from '@/lib/chat'

export function ChatResultBlock({
  slots,
  done,
  total,
  onPreview,
  onEdit,
}: {
  slots: ResultSlot[]
  done: number
  total: number
  onPreview: (image: ChatPreviewImage) => void
  onEdit: (source: ChatEditSource) => void
}) {
  const generating = done < total && slots.some((slot) => !slot.url && !slot.error)

  return (
    <div className="glass-lite max-w-[88%] rounded-2xl rounded-tl-md p-3">
      <p className="mb-2 px-1 text-[12.5px] font-medium text-wb-ink-3">
        出图结果 <span className="text-wb-ink-6">{done}/{total}</span>
        {generating && (
          <Loader2Icon className="ml-1.5 inline size-3 animate-spin text-wb-brand" />
        )}
      </p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {slots.map((slot, index) => {
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
                <div className="absolute inset-x-1.5 bottom-1.5 flex justify-between gap-1 opacity-100 sm:opacity-0 sm:transition-opacity sm:group-hover:opacity-100">
                  {editSource ? (
                    <button
                      type="button"
                      onClick={() => onEdit(editSource)}
                      className="rounded-lg bg-wb-brand/95 px-2 py-1 text-[11px] text-white"
                    >
                      <SquarePenIcon className="mr-1 inline size-3" />
                      继续编辑
                    </button>
                  ) : <span />}
                  <button
                    type="button"
                    onClick={() =>
                      void downloadImage(
                        slot.url!,
                        `${slot.imageType ?? 'chat'}-${index + 1}.png`,
                      )
                    }
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
          return (
            <div
              key={index}
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
