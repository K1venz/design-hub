import type { ReactNode } from 'react'

import { BrandMark, Wordmark } from '@/components/brand/Wordmark'

/** 登录/注册共用的分屏外壳：左品牌面板 + 右表单插槽（DRY）. */
export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-svh lg:grid-cols-[1.05fr_1fr]">
      {/* 品牌面板（大屏）：青墨底 + 纸纹 + 叠帧意象 */}
      <aside className="bg-primary text-primary-foreground relative hidden overflow-hidden lg:flex lg:flex-col lg:justify-between lg:p-14">
        <div className="paper-grain pointer-events-none absolute inset-0 opacity-[0.12]" />
        <div className="animate-in fade-in slide-in-from-left-2 relative flex items-center gap-3 duration-700">
          <BrandMark className="size-9" />
          <span className="font-display text-lg tracking-[0.16em]">STUDIO COPILOT</span>
        </div>

        <div className="animate-in fade-in slide-in-from-left-3 relative max-w-md space-y-5 duration-700">
          <h1 className="font-display text-[2.7rem] leading-[1.08] tracking-tight">
            设计师的
            <br />
            AI 副驾驶
          </h1>
          <p className="text-primary-foreground/72 text-[15px] leading-relaxed">
            产品图 → 高质量电商图。一单一档管理客户与项目，出图、选稿、改稿、交付一条线贯通。
          </p>
        </div>

        <div className="relative flex items-end justify-between">
          <span className="text-primary-foreground/55 font-mono text-xs">
            design_hub · 图生图引擎 v0.1
          </span>
          <div className="pointer-events-none absolute -right-6 -bottom-2 opacity-30">
            <div className="border-primary-foreground/40 size-24 rounded-xl border" />
            <div className="border-primary-foreground/55 absolute top-4 left-4 size-24 rounded-xl border" />
            <div className="bg-highlight absolute top-[3.4rem] left-[3.4rem] size-3 rounded-full" />
          </div>
        </div>
      </aside>

      {/* 表单（暖纸底） */}
      <main className="paper-grain flex items-center justify-center bg-background px-6 py-12">
        <div className="animate-in fade-in slide-in-from-bottom-2 w-full max-w-sm space-y-7 duration-500">
          <div className="lg:hidden">
            <Wordmark />
          </div>
          {children}
        </div>
      </main>
    </div>
  )
}
