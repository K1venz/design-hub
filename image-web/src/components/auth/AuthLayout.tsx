import type { ReactNode } from 'react'

import { BrandMark, Wordmark } from '@/components/brand/Wordmark'
import { AuroraBackground } from '@/components/visual/AuroraBackground'
import { BorderBeam } from '@/components/visual/BorderBeam'

/** 登录/注册共用的分屏外壳：左品牌面板（流动极光）+ 右表单卡（流光描边）. */
export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-svh bg-background lg:grid-cols-[1.05fr_1fr]">
      {/* 品牌面板（大屏）：灰白底 + 流动极光 + 流光标题 */}
      <aside className="border-border/60 relative hidden overflow-hidden border-r lg:flex lg:flex-col lg:justify-between lg:p-14">
        <AuroraBackground />
        <div className="paper-grain pointer-events-none absolute inset-0 opacity-50" />

        <div className="animate-in fade-in slide-in-from-left-2 relative flex items-center gap-3 duration-700">
          <BrandMark className="size-9" />
          <span className="font-display text-foreground/80 text-lg tracking-[0.16em]">
            STUDIO COPILOT
          </span>
        </div>

        <div className="animate-in fade-in slide-in-from-left-3 relative max-w-md space-y-5 duration-700">
          <h1 className="font-display text-[3rem] leading-[1.06] tracking-tight">
            <span className="text-foreground">设计师的</span>
            <br />
            <span className="aurora-text">AI 副驾驶</span>
          </h1>
          <p className="text-muted-foreground max-w-sm text-[15px] leading-relaxed">
            产品图 → 高质量电商图。一单一档管理客户与项目，出图、选稿、改稿、交付一条线贯通。
          </p>
        </div>

        <div className="relative flex items-end justify-between">
          <span className="text-muted-foreground/70 font-mono text-xs">
            design_hub · 图生图引擎 v0.1
          </span>
        </div>
      </aside>

      {/* 表单（灰白底）：卡片 + 流光描边 */}
      <main className="bg-background flex items-center justify-center px-6 py-12">
        <div className="animate-in fade-in slide-in-from-bottom-2 bg-card border-border/70 relative w-full max-w-sm overflow-hidden rounded-2xl border p-7 shadow-[0_18px_50px_-24px_oklch(0.45_0.07_240_/_0.35)] duration-500">
          <BorderBeam size={90} duration={8} />
          <BorderBeam size={90} duration={8} delay={4} />
          <div className="relative space-y-7">
            <div className="lg:hidden">
              <Wordmark />
            </div>
            {children}
          </div>
        </div>
      </main>
    </div>
  )
}
