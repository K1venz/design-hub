import * as React from 'react'

import { cn } from '@/lib/utils'

/** 轻量原生复选框（无新依赖）：紫色 accent，尺寸/圆角对齐 Style 4。 */
export const Checkbox = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    type="checkbox"
    className={cn(
      'border-border size-4 shrink-0 cursor-pointer rounded-[5px] border accent-[#5b5bd6]',
      'focus-visible:ring-ring focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:outline-none',
      className,
    )}
    {...props}
  />
))
Checkbox.displayName = 'Checkbox'
