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

        <div className="animate-in fade-in slide-in-from-left-2 motion-reduce:animate-none relative flex items-center gap-3 duration-700">
          <BrandMark className="size-9" />
          <span className="text-foreground/85 text-lg font-semibold tracking-[0.02em]">
            实朴
            <span className="text-muted-foreground ml-2 text-[13px] font-normal tracking-[0.12em]">电商图片工作站</span>
          </span>
        </div>

        <div className="animate-in fade-in slide-in-from-left-3 motion-reduce:animate-none relative max-w-md space-y-5 duration-700">
          <h1 className="font-display text-[3.4rem] font-semibold leading-[1.06] tracking-tight">
            <span className="text-foreground">上传产品图，</span>
            <br />
            <span className="aurora-text">整套电商图一键出</span>
          </h1>
          <p className="text-muted-foreground max-w-sm text-[15px] leading-relaxed">
            白底、场景、卖点图一次出齐，还能复刻爆款版式、对结果二次微调——产品与包装文字始终保真。
          </p>
        </div>

        <div className="relative flex items-end justify-between">
          <span className="text-muted-foreground/70 font-mono text-xs">
            SHIPU · AI 出图引擎
          </span>
        </div>
      </aside>

      {/* 表单（灰白底）：卡片 + 流光描边 */}
      <main className="bg-background flex items-center justify-center px-6 py-12">
        <div className="animate-in fade-in slide-in-from-bottom-2 motion-reduce:animate-none bg-card border-border/70 relative w-full max-w-sm overflow-hidden rounded-2xl border p-7 shadow-[0_30px_80px_-30px_oklch(0.42_0.08_250_/_0.5),0_10px_28px_-18px_oklch(0.42_0.08_250_/_0.32)] duration-500">
          <BorderBeam size={110} duration={8} borderWidth={2} />
          <BorderBeam size={110} duration={8} delay={4} borderWidth={2} />
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
