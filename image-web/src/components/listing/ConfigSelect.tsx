import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select-rich'

interface ConfigSelectProps {
  label: string
  value: string
  options: readonly string[]
  onChange: (value: string) => void
}

/** designkit-style inline labeled dropdown: label left, current value right, opens the Radix rich select. */
export function ConfigSelect({ label, value, options, onChange }: ConfigSelectProps) {
  return (
    <label className="flex items-center justify-between rounded-xl border border-[#ece8e2] bg-white px-3 py-2.5 text-[13px] text-[#7a746c]">
      <span>{label}</span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="h-auto gap-1 border-0 bg-transparent px-0 py-0 font-semibold text-[#2c2824] shadow-none focus-visible:ring-0">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((o) => (
            <SelectItem key={o} value={o}>
              {o}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  )
}
