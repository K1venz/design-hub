import { useRef, useState } from 'react'
import { ImageUpIcon } from 'lucide-react'

import {
  type ChatImageFileSelection,
  selectChatImageFiles,
} from '@/components/chat/chat-image-files'

function containsFiles(event: React.DragEvent<HTMLDivElement>): boolean {
  return Array.from(event.dataTransfer.types).includes('Files')
}

export function ChatImageDropZone({
  disabled,
  remainingSlots,
  onSelection,
  children,
}: {
  disabled: boolean
  remainingSlots: number
  onSelection: (selection: ChatImageFileSelection) => void
  children: React.ReactNode
}) {
  const dragDepthRef = useRef(0)
  const [receiving, setReceiving] = useState(false)

  function resetDragState() {
    dragDepthRef.current = 0
    setReceiving(false)
  }

  function handleDragEnter(event: React.DragEvent<HTMLDivElement>) {
    if (!containsFiles(event)) return
    event.preventDefault()
    event.stopPropagation()
    if (disabled) {
      resetDragState()
      return
    }

    dragDepthRef.current += 1
    if (remainingSlots > 0) setReceiving(true)
  }

  function handleDragOver(event: React.DragEvent<HTMLDivElement>) {
    if (!containsFiles(event)) return
    event.preventDefault()
    event.stopPropagation()
    if (disabled) resetDragState()
  }

  function handleDragLeave(event: React.DragEvent<HTMLDivElement>) {
    if (!containsFiles(event)) return
    event.preventDefault()
    event.stopPropagation()
    if (disabled) {
      resetDragState()
      return
    }

    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1)
    if (dragDepthRef.current === 0) setReceiving(false)
  }

  function handleDrop(event: React.DragEvent<HTMLDivElement>) {
    if (!containsFiles(event)) return
    event.preventDefault()
    event.stopPropagation()
    resetDragState()
    if (disabled) return

    onSelection(
      selectChatImageFiles(
        Array.from(event.dataTransfer.files),
        remainingSlots,
      ),
    )
  }

  return (
    <div
      data-chat-image-drop-zone
      className="relative"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {children}
      {receiving && !disabled && remainingSlots > 0 && (
        <div
          role="status"
          aria-live="polite"
          className="pointer-events-none absolute inset-0 z-40 grid place-items-center rounded-[20px] border-2 border-dashed border-wb-brand bg-wb-tint-3/95 px-6 text-center backdrop-blur-[2px]"
        >
          <div className="flex flex-col items-center gap-2">
            <span className="grid size-11 place-items-center rounded-2xl bg-white text-wb-brand-deep shadow-sm">
              <ImageUpIcon className="size-5" />
            </span>
            <strong className="text-[14px] font-semibold text-wb-ink-2">
              松开即可上传图片
            </strong>
            <span className="text-[11px] text-wb-ink-6">
              支持 PNG、JPG、WebP · 还可添加 {remainingSlots} 张
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
