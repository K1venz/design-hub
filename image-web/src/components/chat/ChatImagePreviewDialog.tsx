import { useState } from 'react'
import { DownloadIcon, SquarePenIcon } from 'lucide-react'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'
import type { ChatEditSource, ChatPreviewImage } from '@/lib/chat'
import { downloadImage } from '@/lib/download'

export function ChatImagePreviewDialog({
  image,
  onOpenChange,
  onEdit,
}: {
  image: ChatPreviewImage | null
  onOpenChange: (open: boolean) => void
  onEdit: (source: ChatEditSource) => void
}) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null)
  const loadFailed = image !== null && failedUrl === image.url

  return (
    <Dialog open={image !== null} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[calc(100dvh-2rem)] max-w-[calc(100vw-2rem)] flex-col gap-3 bg-black/90 p-3 text-white sm:max-w-5xl">
        <DialogTitle className="sr-only">图片预览</DialogTitle>
        <DialogDescription className="sr-only">
          按图片原始比例完整预览生成结果
        </DialogDescription>
        <div className="grid min-h-0 flex-1 place-items-center overflow-hidden">
          {image && !loadFailed ? (
            <img
              src={image.url}
              alt={image.imageType ? `${image.imageType}生成结果` : '生成结果'}
              onError={() => setFailedUrl(image.url)}
              className="max-h-[calc(100dvh-8rem)] max-w-full object-contain"
            />
          ) : (
            <p className="py-20 text-sm text-white/75">图片加载失败</p>
          )}
        </div>
        {image && (
          <div className="flex justify-center gap-2">
            {image.imageKey && (
              <button
                type="button"
                onClick={() => {
                  onEdit({
                    url: image.url,
                    imageKey: image.imageKey!,
                    imageType: image.imageType,
                  })
                  onOpenChange(false)
                }}
                className="rounded-full bg-wb-brand px-4 py-2 text-sm font-semibold text-white"
              >
                <SquarePenIcon className="mr-1 inline size-4" />
                继续编辑
              </button>
            )}
            <button
              type="button"
              onClick={() => void downloadImage(image.url, 'chat-result.png')}
              className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-wb-ink-2"
            >
              <DownloadIcon className="mr-1 inline size-4" />
              下载
            </button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
