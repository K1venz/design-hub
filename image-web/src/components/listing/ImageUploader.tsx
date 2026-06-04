import { useRef, type ChangeEvent } from 'react'
import { UploadIcon, XIcon } from 'lucide-react'

interface ImageUploaderProps {
  files: File[]
  onChange: (files: File[]) => void
  max?: number
}

/** Local multi-image picker (no asset library): up to `max` files, removable thumbnails. */
export function ImageUploader({ files, onChange, max = 3 }: ImageUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  function onPick(e: ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(e.target.files ?? [])
    onChange([...files, ...picked].slice(0, max))
    e.target.value = ''
  }
  function removeAt(i: number) {
    onChange(files.filter((_, idx) => idx !== i))
  }

  return (
    <div>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={files.length >= max}
        className="flex w-full items-center justify-center gap-2 rounded-2xl border border-dashed border-[#d8d1c6] bg-[#fbfaf8] px-4 py-5 text-[13px] text-[#9b958c] transition-colors hover:border-[#cdbfff] disabled:opacity-50"
      >
        <UploadIcon className="size-4" /> 上传图片（最多 {max} 张）
      </button>
      <input ref={inputRef} type="file" accept="image/*" multiple hidden onChange={onPick} />
      {files.length > 0 && (
        <div className="mt-2.5 flex gap-2">
          {files.map((f, i) => (
            <div key={i} className="relative size-14 overflow-hidden rounded-xl border border-[#ece8e2]">
              <img src={URL.createObjectURL(f)} alt="" className="size-full object-cover" />
              <button
                type="button"
                onClick={() => removeAt(i)}
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
