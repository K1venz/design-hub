import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select-rich'

import { cn } from '@/lib/utils'

interface ConfigSelectProps {
  label: string
  value: string
  options: readonly string[]
  onChange: (value: string) => void
  className?: string
  /** 可选：值 → 展示名映射（如品类 FOOD→食品）；缺省显示值本身。 */
  optionLabels?: Record<string, string>
}

/** designkit-style inline labeled dropdown: label left, current value right, opens the Radix rich select. */
export function ConfigSelect({ label, value, options, onChange, className, optionLabels }: ConfigSelectProps) {
  return (
    <label
      className={cn(
        'flex items-center justify-between rounded-xl border border-wb-line-1 bg-white px-3 py-2.5 text-[13px] text-wb-ink-5 transition-colors hover:border-wb-brand-soft',
        className,
      )}
    >
      <span className="whitespace-nowrap">{label}</span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="h-auto justify-end gap-1 border-0 bg-transparent px-0 py-0 font-semibold text-wb-ink-2 shadow-none focus-visible:ring-0">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o} value={o}>
              {optionLabels?.[o] ?? o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  )
}
