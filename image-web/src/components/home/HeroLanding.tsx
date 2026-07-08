import { ArrowRightIcon, PlusIcon, SparklesIcon } from 'lucide-react'

import { RibbonCanvas } from '@/components/home/RibbonCanvas'
import { Button } from '@/components/ui/button'

/**
 * 品牌 Hero 独立首屏（ISSUE-0061）——版式/背景/动效 1:1 照用户参考件
 * （Downloads/生图平台Hero页 demo.tsx）：浅色底、胶囊公告条、边框标题框 +
 * radial-gradient 渐隐 mask + 四角「+」、绿点 ping、双 shadcn 按钮、
 * 全屏 canvas 彩带跟随鼠标（lighter 光带）。
 * 两段式：第一屏 = 胶囊 + 标题框撑满视口（文字大小不变）；滚轮下去 = 副标题/描述/双 CTA。
 */
export function HeroLanding({
  onPrimary,
  onSecondary,
}: {
  /** 主 CTA / 顶部公告条 → 项目首页。 */
  onPrimary: () => void
  /** 副 CTA → 生成案例。 */
  onSecondary: () => void
}) {
  return (
    <section className="relative bg-background text-foreground">
      {/* ── 第一屏：胶囊 + 巨型标题框撑满整屏 ── */}
      <div className="flex h-svh flex-col items-center px-4 text-center">
        <div className="z-10 mt-8 mb-6 sm:justify-center">
          <button
            onClick={onPrimary}
            className="relative flex items-center whitespace-nowrap rounded-full border bg-popover px-3 py-1 text-xs leading-6 text-primary/60"
          >
            <SparklesIcon className="h-5 p-1" /> 全新上线：帮我设计 AI 助手
            <span className="hover:text-wb-brand ml-1 flex items-center font-semibold">
              去体验 <ArrowRightIcon className="h-4 w-4" />
            </span>
          </button>
        </div>

        {/* 标题框：flex-1 撑满第一屏剩余高度；边框 + 径向渐隐 mask + 四角「+」 */}
        <div className="flex w-full flex-1 px-2 pb-10">
          <div className="border-wb-brand relative mx-auto flex w-full max-w-7xl flex-col items-center justify-center border p-6 [mask-image:radial-gradient(800rem_96rem_at_center,white,transparent)] md:px-12">
            <PlusIcon strokeWidth={4} className="text-wb-brand absolute -left-5 -top-5 h-10 w-10" />
            <PlusIcon strokeWidth={4} className="text-wb-brand absolute -bottom-5 -left-5 h-10 w-10" />
            <PlusIcon strokeWidth={4} className="text-wb-brand absolute -right-5 -top-5 h-10 w-10" />
            <PlusIcon strokeWidth={4} className="text-wb-brand absolute -bottom-5 -right-5 h-10 w-10" />
            <h1 className="select-none px-3 py-2 text-center text-5xl font-semibold leading-none tracking-tight md:text-8xl">
              一整套电商图，一句话的事。
            </h1>
            {/* 绿点 ping + 内测免费开放中 */}
            <div className="mt-6 flex items-center justify-center gap-1">
              <span className="relative flex h-3 w-3 items-center justify-center">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-500 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
              </span>
              <p className="text-xs text-green-500">内测免费开放中</p>
            </div>
          </div>
        </div>
      </div>

      {/* ── 第二段：滚轮下去 → 副标题 + 描述 + 双 CTA ── */}
      <div className="flex flex-col items-center px-4 pb-24 pt-10 text-center">
        <h2 className="text-2xl md:text-2xl">
          实朴 · <span className="text-wb-brand font-bold">电商图片工作站</span>
        </h2>
        <p className="md:text-md mx-auto mb-16 mt-2 max-w-2xl px-6 text-sm text-primary/60 sm:px-6 md:max-w-4xl md:px-20 lg:text-lg">
          上传产品图，白底 · 场景 · 卖点一次出齐，还能复刻爆款、文字保真。
        </p>
        <div className="flex justify-center gap-2">
          <Button size="lg" className="h-11 px-8" onClick={onPrimary}>
            开始创作
          </Button>
          <Button variant="outline" size="lg" className="h-11 px-8" onClick={onSecondary}>
            看看实朴出的图
          </Button>
        </div>
      </div>

      {/* 全屏彩带 canvas：fixed 钉在视口，滚动时持续跟随鼠标 */}
      <RibbonCanvas className="pointer-events-none fixed inset-0 mx-auto" />
    </section>
  )
}
