import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'motion/react'
import { ArrowRightIcon, ImagePlusIcon, SendIcon } from 'lucide-react'

import { AppShell } from '@/components/layout/AppShell'
import { SiteFooter } from '@/components/layout/SiteFooter'
import { ShowcaseDetailDialog } from '@/components/listing/ShowcaseDetailDialog'
import { useShowcase, type ShowcaseItem } from '@/api/showcase'
import { cn } from '@/lib/utils'
import { useInView } from '@/lib/use-in-view'
import { TOOL_BANNERS, TOOL_TILES } from '@/lib/home'
import { showcaseRecipeToPrefill } from '@/lib/recipe'
import { useAuthStore } from '@/stores/auth-store'

/** 实朴项目首页（`/home`，未登录可浏览）：对话入口 + 工具区 + 成果区 + Footer。 */
export function HomePage() {
  return (
    <AppShell>
      <main className="min-h-0 flex-1 overflow-auto pb-6 pr-3">
        <div className="mx-auto w-full max-w-[1060px] px-4 sm:px-6">
          <Hero />
          <ToolSection />
          <ShowcaseSection />
          <SiteFooter className="mt-16" />
        </div>
      </main>
    </AppShell>
  )
}

// The centered chat entry is the only primary action in the Hero.
function Hero() {
  const navigate = useNavigate()
  const [text, setText] = useState('')

  // 「帮我设计」= 登录内测：带首句进 /chat（未登录 → ProtectedRoute 回跳登录后继续）。
  // 首句走 navigate state 承载（不进 URL·隐私），未登录经登录墙由 from.state 恢复。
  function askAgent(q: string) {
    const seed = q.trim()
    navigate('/chat', seed ? { state: { q: seed } } : undefined)
  }

  return (
    <section className="pt-8 text-center sm:pt-12">
      <h1 className="font-display text-[30px] font-semibold leading-[1.12] tracking-tight sm:text-[40px] lg:text-[44px]">
        和我聊聊，<span className="aurora-text">你想要什么设计？</span>
      </h1>

      <div className="glass-panel mx-auto mt-6 flex min-h-[184px] w-full max-w-[920px] flex-col rounded-[22px] p-4 text-left sm:p-5">
        <textarea
          aria-label="描述你的设计需求"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') askAgent(text)
          }}
          placeholder={'用大白话描述你的产品和想要的效果，实朴帮你完成白底、场景、卖点等电商图片。\n例如：帮我的高山七彩花生礼盒出一套电商图，早餐桌场景、暖光…'}
          className="min-h-[112px] w-full flex-1 resize-none bg-transparent px-1 py-1 text-[14.5px] leading-relaxed text-wb-ink-2 outline-none placeholder:text-wb-faint-1"
        />
        <div className="mt-auto flex flex-wrap items-center justify-between gap-3 pt-4">
          <button
            onClick={() => askAgent(text)}
            className="flex items-center gap-1.5 rounded-full border border-wb-line-1 bg-white/70 px-3 py-1.5 text-[12.5px] font-medium text-wb-ink-4 transition-colors hover:border-wb-brand-soft hover:text-wb-brand-deep"
          >
            <ImagePlusIcon className="size-4" /> 添加商品图
          </button>
          <button
            onClick={() => askAgent(text)}
            className="flex items-center gap-1.5 rounded-full bg-gradient-to-r from-wb-grad-from to-wb-grad-to px-4 py-1.5 text-[13px] font-semibold text-white shadow-[0_8px_20px_-8px_rgba(91,91,214,.6)] transition-shadow hover:shadow-[0_10px_24px_-8px_rgba(91,91,214,.75)]"
          >
            发送 <SendIcon className="size-3.5" />
          </button>
        </div>
      </div>
    </section>
  )
}

// Two primary tools and three real utility destinations.
function ToolSection() {
  return (
    <section className="mt-10 sm:mt-12">
      <SectionHead title="用实朴的工具" sub="直达每个出图工作台" />

      <div className="grid gap-3 min-[900px]:grid-cols-2">
        {TOOL_BANNERS.map((b) => (
          <Link
            key={b.key}
            to={b.to}
            className="lift-card group rounded-2xl border border-white/70 bg-gradient-to-br from-wb-tint-1 to-white p-5 shadow-[0_8px_28px_-16px_rgba(91,91,214,.3)] [--lift-shadow:0_16px_36px_-16px_rgba(91,91,214,.45)]"
          >
            <span className="grid size-11 place-items-center rounded-2xl bg-gradient-to-br from-wb-grad-from to-wb-grad-to text-white shadow-[0_8px_20px_-8px_rgba(91,91,214,.6)]">
              <b.icon className="size-5" />
            </span>
            <h3 className="mt-3 flex items-center gap-1.5 text-[16px] font-semibold text-wb-ink-1">
              {b.label}
              <ArrowRightIcon className="size-4 text-wb-brand transition-transform group-hover:translate-x-1" />
            </h3>
            <p className="mt-1.5 max-w-md text-[13px] leading-relaxed text-wb-ink-5">{b.desc}</p>
          </Link>
        ))}
      </div>

      <div className="mt-3 grid gap-3 min-[900px]:grid-cols-4">
        {TOOL_TILES.map((t) => (
          <Link
            key={t.key}
            to={t.to}
            className="lift-card group flex flex-col gap-2 rounded-2xl border border-white/70 bg-white/70 p-3.5 shadow-[0_4px_18px_-12px_rgba(40,40,90,.2)]"
          >
            <span className="grid size-9 place-items-center rounded-xl bg-wb-tint-1 text-wb-brand-deep transition-colors group-hover:bg-wb-brand group-hover:text-white">
              <t.icon className="size-[18px]" />
            </span>
            <span className="text-[13.5px] font-semibold text-wb-ink-2">{t.label}</span>
            <span className="text-[11.5px] text-wb-ink-6">{t.desc}</span>
          </Link>
        ))}
      </div>
    </section>
  )
}

// Load near the viewport, but render the section only after real items arrive.
// 栅格列数与移动端断点一体：手机 1→2 / 平板 3 / 桌面 4。13 张分两批(7+6)，底部哨兵进视口显现下一批。
const SHOWCASE_GRID = 'grid grid-cols-1 gap-4 min-[440px]:grid-cols-2 md:grid-cols-3 xl:grid-cols-4'
const SHOWCASE_BATCH = 7

function ShowcaseSection() {
  const [ref, inView] = useInView<HTMLDivElement>()
  const showcase = useShowcase(inView)
  const real = showcase.data && showcase.data.length > 0 ? showcase.data : null
  const navigate = useNavigate()
  const token = useAuthStore((s) => s.token)
  const [shown, setShown] = useState(SHOWCASE_BATCH)
  const sentinelRef = useRef<HTMLDivElement>(null)

  // 「做同款」：配方→/set 预填；未登录先过登录墙，回跳携配方随行（不带 uploads）。
  function makeSame(recipe: ShowcaseItem['recipe']) {
    const prefill = showcaseRecipeToPrefill(recipe)
    if (token) navigate('/set', { state: { prefill } })
    else navigate('/login', { state: { from: { pathname: '/set' }, prefill } })
  }

  // 纵向分批懒加载：底部哨兵进视口 → 显现下一批（数据已全量拉取，此为渐进显示 + skeleton 占位）。
  const more = real != null && shown < real.length
  useEffect(() => {
    if (!more) return
    const el = sentinelRef.current
    if (!el) return
    const io = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) setShown((s) => s + SHOWCASE_BATCH)
    })
    io.observe(el)
    return () => io.disconnect()
  }, [more])

  if (!real) {
    return <div ref={ref} className="h-px w-full" aria-hidden />
  }

  return (
    <>
      <div ref={ref} className="h-px w-full" aria-hidden />
      <section className="mt-14">
        <SectionHead title="看看实朴出的图" sub="实朴真实出品 · 一键做同款" />
        <div className={SHOWCASE_GRID}>
          {real.slice(0, shown).map((item, index) => (
            <ShowcaseCard
              key={index}
              item={item}
              onMakeSame={() => makeSame(item.recipe)}
            />
          ))}
          {more &&
            Array.from({ length: Math.min(SHOWCASE_BATCH, real.length - shown) }).map((_, index) => (
              <ShowcaseSkeleton key={`sk-${index}`} />
            ))}
        </div>
        {more && <div ref={sentinelRef} className="h-1 w-full" aria-hidden />}
      </section>
    </>
  )
}

function ShowcaseCard({ item, onMakeSame }: { item: ShowcaseItem; onMakeSame: () => void }) {
  const total = Object.values(item.recipe.plan).reduce((a, b) => a + b, 0)
  return (
    <motion.figure
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: 'easeOut' }}
      className="flex flex-col overflow-hidden rounded-2xl border border-white/70 bg-white shadow-[0_6px_24px_-14px_rgba(40,40,90,.2)]"
    >
      <div className="relative aspect-[4/3] bg-wb-surface-3">
        <img src={item.url} alt={item.caption} loading="lazy" className="size-full object-cover" />
        <span className="absolute left-2 top-2 rounded-full bg-white/85 px-2 py-0.5 text-[11px] font-medium text-wb-brand-deep backdrop-blur">
          {item.image_type}
        </span>
      </div>
      <figcaption className="flex flex-1 flex-col gap-2 px-3 py-2.5">
        <p className="text-[12.5px] font-medium text-wb-ink-3">{item.caption}</p>
        <p className="text-[11px] text-wb-ink-6">
          {item.recipe.ratio} · 套图 {total} 张
          {item.recipe.modifiers.platform && ` · ${item.recipe.modifiers.platform}`}
        </p>
        <div className="mt-auto flex gap-2">
          <ShowcaseDetailDialog item={item} onMakeSame={onMakeSame} />
          <button
            onClick={onMakeSame}
            className="flex-1 rounded-lg bg-gradient-to-r from-wb-grad-from to-wb-grad-to px-3 py-1.5 text-[12px] font-semibold text-white transition-opacity hover:opacity-90"
          >
            做同款
          </button>
        </div>
      </figcaption>
    </motion.figure>
  )
}

function ShowcaseSkeleton() {
  return (
    <div className="overflow-hidden rounded-2xl border border-white/70 bg-white shadow-[0_6px_24px_-14px_rgba(40,40,90,.2)]">
      <div className="aspect-[4/3] animate-pulse bg-wb-surface-4" />
      <div className="flex flex-col gap-2 px-3 py-2.5">
        <div className="h-3.5 w-2/3 animate-pulse rounded bg-wb-surface-4" />
        <div className="h-3 w-1/2 animate-pulse rounded bg-wb-surface-4" />
        <div className="mt-1 h-7 w-full animate-pulse rounded-lg bg-wb-surface-4" />
      </div>
    </div>
  )
}

function SectionHead({ title, sub }: { title: string; sub: string }) {
  return (
    <div className="mb-4">
      <h2 className={cn('text-[19px] font-semibold tracking-tight text-wb-ink-1')}>{title}</h2>
      <p className="mt-0.5 text-[13px] text-wb-ink-6">{sub}</p>
    </div>
  )
}
