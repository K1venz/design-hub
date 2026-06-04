import { useRef, useState, type ChangeEvent } from 'react'
import { UploadIcon, XIcon, Loader2Icon, RotateCwIcon } from 'lucide-react'

import { useUploadImage } from '@/api/listing'
import type { UploadedImage } from '@/lib/listing'

interface UploadItem {
  key: string
  file: File
  previewUrl: string // local blob: URL — instant preview, not file://
  status: 'uploading' | 'done' | 'error'
  uploaded?: UploadedImage
}

interface ImageUploaderProps {
  /** Called with the currently successfully-uploaded images whenever that set changes. */
  onChange: (uploaded: UploadedImage[]) => void
  max?: number
}

/**
 * Two-step upload (ISSUE-0026): on pick, POST each file to /uploads, show blob preview
 * with uploading / error(retry) / done states, deletable; reports done {id,url} upward.
 */
export function ImageUploader({ onChange, max = 3 }: ImageUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [items, setItems] = useState<UploadItem[]>([])
  const upload = useUploadImage()

  function emit(list: UploadItem[]) {
    onChange(list.filter((i) => i.status === 'done' && i.uploaded).map((i) => i.uploaded!))
  }

  function patch(key: string, p: Partial<UploadItem>) {
    setItems((prev) => {
      const next = prev.map((i) => (i.key === key ? { ...i, ...p } : i))
      emit(next)
      return next
    })
  }

  function start(key: string, file: File) {
    upload
      .mutateAsync(file)
      .then((uploaded) => patch(key, { status: 'done', uploaded }))
      .catch(() => patch(key, { status: 'error' }))
  }

  function onPick(e: ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(e.target.files ?? [])
    e.target.value = ''
    const fresh: UploadItem[] = picked.slice(0, max - items.length).map((file) => ({
      key: crypto.randomUUID(),
      file,
      previewUrl: URL.createObjectURL(file),
      status: 'uploading',
    }))
    if (fresh.length === 0) return
    setItems((prev) => [...prev, ...fresh])
    fresh.forEach((it) => start(it.key, it.file))
  }

  function remove(key: string) {
    setItems((prev) => {
      const it = prev.find((i) => i.key === key)
      if (it) URL.revokeObjectURL(it.previewUrl)
      const next = prev.filter((i) => i.key !== key)
      emit(next)
      return next
    })
  }

  function retry(key: string) {
    const it = items.find((i) => i.key === key)
    if (!it) return
    patch(key, { status: 'uploading' })
    start(key, it.file)
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={items.length >= max}
        className="flex w-full items-center justify-center gap-2 rounded-2xl border border-dashed border-[#d8d1c6] bg-[#fbfaf8] px-4 py-5 text-[13px] text-[#9b958c] transition-colors hover:border-[#cdbfff] disabled:opacity-50"
      >
        <UploadIcon className="size-4" /> 上传图片（最多 {max} 张）
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        multiple
        hidden
        onChange={onPick}
      />
      {items.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-2">
          {items.map((it) => (
            <div key={it.key} className="relative size-16 overflow-hidden rounded-xl border border-[#ece8e2]">
              <img src={it.previewUrl} alt="" className="size-full object-cover" />
              {it.status === 'uploading' && (
                <div className="absolute inset-0 grid place-items-center bg-white/55">
                  <Loader2Icon className="size-5 animate-spin text-[#7c6cff]" />
                </div>
              )}
              {it.status === 'error' && (
                <button
                  type="button"
                  onClick={() => retry(it.key)}
                  className="absolute inset-0 grid place-items-center gap-0.5 bg-[#2c2824]/70 text-[10px] text-white"
                >
                  <RotateCwIcon className="size-4" /> 重传
                </button>
              )}
              <button
                type="button"
                onClick={() => remove(it.key)}
                className="absolute -right-1.5 -top-1.5 grid size-4.5 place-items-center rounded-full bg-[#2c2824] text-white"
              >
                <XIcon className="size-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
