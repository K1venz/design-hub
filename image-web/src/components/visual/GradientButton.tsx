import { forwardRef, type ButtonHTMLAttributes } from 'react'

import { cn } from '@/lib/utils'

/**
 * 渐变流光 CTA：蓝紫同族渐变底（Style 4 单 accent） + 悬停时背景位移 + 一道斜扫高光（sheen）。
 * 用在关键号召按钮（开始出图 / 新建项目 等）。非悬停态零动画，省电。
 */
export const GradientButton = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement>>(
  function GradientButton({ className, children, ...props }, ref) {
    return (
      <button
        ref={ref}
        className={cn(
          'group relative inline-flex h-11 items-center justify-center gap-2 overflow-hidden rounded-[13px] px-5 text-sm font-medium text-white',
          'bg-gradient-to-r from-wb-grad-from via-wb-grad-via to-wb-grad-to bg-[length:200%_100%] bg-left',
          'shadow-[0_10px_26px_-10px] shadow-wb-brand/55 transition-[background-position,box-shadow] duration-500',
          'hover:bg-right hover:shadow-wb-brand/70 focus-visible:ring-ring/60 focus-visible:ring-2 focus-visible:outline-none',
          'disabled:pointer-events-none disabled:opacity-55',
          className,
        )}
        {...props}
      >
        <span className="pointer-events-none absolute inset-0 -translate-x-full bg-gradient-to-r from-transparent via-white/30 to-transparent transition-transform duration-700 ease-out group-hover:translate-x-full" />
        <span className="relative inline-flex items-center gap-2">{children}</span>
      </button>
    )
  },
)
