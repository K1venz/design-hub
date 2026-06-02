import { StarIcon } from 'lucide-react'

import { cn } from '@/lib/utils'

/** 1-5 星评分（≥4 星 = 可用）. */
export function StarRating({
  value,
  onChange,
  disabled,
}: {
  value: number | null
  onChange: (n: number) => void
  disabled?: boolean
}) {
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          disabled={disabled}
          onClick={() => onChange(n)}
          aria-label={`${n} 星`}
          className="disabled:opacity-50"
        >
          <StarIcon
            className={cn(
              'size-4 transition-colors',
              (value ?? 0) >= n
                ? 'fill-highlight text-highlight'
                : 'text-muted-foreground/40 hover:text-highlight/60',
            )}
          />
        </button>
      ))}
    </div>
  )
}
