import { useRef, useState, type ChangeEvent } from 'react'
import { UploadIcon, XIcon, Loader2Icon, RotateCwIcon } from 'lucide-react'
import { toast } from 'sonner'

import { useUploadImage } from '@/api/listing'
import type { UploadedImage } from '@/lib/listing'

// 与后端 UploadService 对齐（_MAX_BYTES=10MB；白名单 png/jpeg/webp，见 ISSUE-0028）
const MAX_UPLOAD_BYTES = 10 * 1024 * 1024
const ACCEPT_TYPES = ['image/png', 'image/jpeg', 'image/webp']
const ACCEPT_HINT = '≤10MB · png/jpg/webp'

/** 客户端预校验，返回拒绝原因（合法返 null）——大小/格式不对就别发请求。 */
function rejectReason(file: File): string | null {
  if (!ACCEPT_TYPES.includes(file.type)) return `${file.name}：不支持的格式（仅 png/jpg/webp）`
  if (file.size > MAX_UPLOAD_BYTES) return `${file.name}：超过 10MB`
  return null
}

interface UploadItem {
  key: string
  file: File
  previewUrl: string // local blob: URL — instant preview, not file://
  status: 'uploading' | 'done' | 'error'
  uploaded?: UploadedImage
  error?: string
}

interface ImageUploaderProps {
  /** Called with the currently successfully-uploaded images whenever that set changes. */
  onChange: (uploaded: UploadedImage[]) => void
  max?: number
}

/**
 * Two-step upload (ISSUE-0026): on pick, client-validate then POST each file to /uploads,
 * show blob preview with uploading / error(reason+retry) / done states, deletable;
 * surfaces backend failure reason (ISSUE-0028). Reports done {id,url} upward.
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
      .then((uploaded) => patch(key, { status: 'done', uploaded, error: undefined }))
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : '上传失败'
        patch(key, { status: 'error', error: msg })
        toast.error(msg)
      })
  }

  function onPick(e: ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(e.target.files ?? [])
    e.target.value = ''
    const room = max - items.length
    const valid: File[] = []
    for (const file of picked.slice(0, room)) {
      const reason = rejectReason(file)
      if (reason) toast.error(reason)
      else valid.push(file)
    }
    if (valid.length === 0) return
    const fresh: UploadItem[] = valid.map((file) => ({
      key: crypto.randomUUID(),
      file,
      previewUrl: URL.createObjectURL(file),
      status: 'uploading',
    }))
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
        className="flex w-full flex-col items-center justify-center gap-1 rounded-2xl border border-dashed border-[#d8d1c6] bg-[#fbfaf8] px-4 py-5 text-[13px] text-[#9b958c] transition-colors hover:border-[#cdbfff] disabled:opacity-50"
      >
        <span className="flex items-center gap-2">
          <UploadIcon className="size-4" /> 上传图片（最多 {max} 张）
        </span>
        <span className="text-[11px] text-[#b8b2a8]">{ACCEPT_HINT}</span>
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
                  title={it.error}
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
