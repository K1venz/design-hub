import { useState, type KeyboardEvent } from 'react'
import { XIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

/** 轻量标签输入：回车/逗号添加，Backspace 删末项，点 × 移除. */
export function TagInput({
  value,
  onChange,
  placeholder,
  id,
}: {
  value: string[]
  onChange: (v: string[]) => void
  placeholder?: string
  id?: string
}) {
  const [draft, setDraft] = useState('')

  function add() {
    const t = draft.trim()
    if (t && !value.includes(t)) onChange([...value, t])
    setDraft('')
  }
  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      add()
    } else if (e.key === 'Backspace' && !draft && value.length) {
      onChange(value.slice(0, -1))
    }
  }

  return (
    <div
      className={cn(
        'border-input flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border bg-transparent px-2 py-1.5 text-sm',
        'focus-within:border-ring focus-within:ring-ring/50 focus-within:ring-[3px]',
      )}
    >
      {value.map((t) => (
        <span
          key={t}
          className="bg-secondary text-secondary-foreground flex items-center gap-1 rounded px-1.5 py-0.5 text-xs"
        >
          {t}
          <button
            type="button"
            onClick={() => onChange(value.filter((x) => x !== t))}
            className="hover:text-destructive"
            aria-label={`移除 ${t}`}
          >
            <XIcon className="size-3" />
          </button>
        </span>
      ))}
      <input
        id={id}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={add}
        placeholder={value.length === 0 ? placeholder : ''}
        className="placeholder:text-muted-foreground min-w-24 flex-1 bg-transparent outline-none"
      />
    </div>
  )
}
