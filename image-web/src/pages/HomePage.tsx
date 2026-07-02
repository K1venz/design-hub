import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRightIcon, ImagePlusIcon, SendIcon } from 'lucide-react'

import { AppShell } from '@/components/layout/AppShell'
import { cn } from '@/lib/utils'
import { useInView } from '@/lib/use-in-view'
import {
  QUICK_CARDS, TOOL_BANNERS, TOOL_TILES, COMING_SOON, SHOWCASE_PLACEHOLDERS,
} from '@/lib/home'

/** 实朴新公开首页（`/`，未登录可浏览）：Hero 对话入口 + 工具区 + 成果区 + Footer。 */
export function HomePage() {
  return (
    <AppShell>
      <main className="min-h-0 flex-1 overflow-auto pb-6 pr-3">
        <div className="mx-auto w-full max-w-5xl px-4">
          <Hero />
          <ToolSection />
          <ShowcaseSection />
          <HomeFooter />
        </div>
      </main>
    </AppShell>
  )
}

// ── ① Hero：大聊天框 + 6 快捷卡 ──────────────────────────
function Hero() {
  const navigate = useNavigate()
  const [text, setText] = useState('')

  // 「帮我设计」= 登录内测：带首句进 /chat（未登录 → ProtectedRoute 回跳登录后继续）。
  function askAgent(q: string) {
    const seed = q.trim()
    navigate(seed ? `/chat?q=${encodeURIComponent(seed)}` : '/chat')
  }

  return (
    <section className="pt-6 sm:pt-10">
      <div className="text-center">
        <h1 className="font-display text-[30px] font-semibold leading-tight tracking-tight sm:text-[40px]">
          和我聊聊，<span className="aurora-text">你想要什么设计？</span>
        </h1>
        <p className="mx-auto mt-3 max-w-lg text-[14px] leading-relaxed text-wb-ink-5">
          用大白话描述你的产品和想要的效果，实朴帮你出白底、场景、卖点，一整套电商图。
        </p>
      </div>

      {/* 大聊天框 */}
      <div className="glass-panel mx-auto mt-6 max-w-2xl rounded-[20px] p-3">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') askAgent(text)
          }}
          placeholder="例如：帮我的高山七彩花生礼盒出一套电商图，早餐桌场景、暖光…"
          className="h-[92px] w-full resize-none bg-transparent px-3 py-2 text-[14.5px] leading-relaxed text-wb-ink-2 outline-none placeholder:text-wb-faint-1"
        />
        <div className="flex items-center justify-between px-1 pt-1">
          <button
            onClick={() => askAgent(text)}
            className="flex items-center gap-1.5 rounded-full border border-wb-line-1 bg-white/70 px-3 py-1.5 text-[12.5px] font-medium text-wb-ink-4 transition-colors hover:border-wb-brand-soft hover:text-wb-brand-deep"
          >
            <ImagePlusIcon className="size-4" /> 添加图片
          </button>
          <button
            onClick={() => askAgent(text)}
            className="flex items-center gap-1.5 rounded-full bg-gradient-to-r from-wb-grad-from to-wb-grad-to px-4 py-1.5 text-[13px] font-semibold text-white shadow-[0_8px_20px_-8px_rgba(91,91,214,.6)] transition-shadow hover:shadow-[0_10px_24px_-8px_rgba(91,91,214,.75)]"
          >
            发送 <SendIcon className="size-3.5" />
          </button>
        </div>
      </div>

      {/* 6 快捷卡 */}
      <div className="mx-auto mt-5 grid max-w-3xl grid-cols-2 gap-2.5 sm:grid-cols-3">
        {QUICK_CARDS.map((c) => (
          <button
            key={c.key}
            onClick={() => askAgent(c.intent)}
            className="lift-card group flex items-start gap-2.5 rounded-2xl border border-white/70 bg-white/70 p-3 text-left shadow-[0_4px_18px_-12px_rgba(40,40,90,.2)]"
          >
            <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-wb-tint-1 text-wb-brand-deep transition-colors group-hover:bg-wb-brand group-hover:text-white">
              <c.icon className="size-[18px]" />
            </span>
            <span className="min-w-0">
              <span className="block text-[13.5px] font-semibold text-wb-ink-2">{c.label}</span>
              <span className="block truncate text-[11.5px] text-wb-ink-6">{c.desc}</span>
            </span>
          </button>
        ))}
      </div>
    </section>
  )
}

// ── ② 工具区：双 banner + 宫格 + 即将上线 ───────────────
function ToolSection() {
  return (
    <section className="mt-14">
      <SectionHead title="用实朴的工具" sub="直达每个出图工作台" />

      <div className="grid gap-3 sm:grid-cols-2">
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

      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
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
        {COMING_SOON.map((c) => (
          <div
            key={c.key}
            aria-disabled
            className="pointer-events-none relative flex cursor-not-allowed flex-col gap-2 rounded-2xl border border-dashed border-wb-line-3 bg-wb-surface-2/60 p-3.5"
          >
            <span className="absolute right-2.5 top-2.5 rounded-full bg-wb-surface-5 px-2 py-0.5 text-[10px] font-medium text-wb-ink-6">
              即将上线
            </span>
            <span className="grid size-9 place-items-center rounded-xl bg-wb-surface-4 text-wb-faint-1">
              <c.icon className="size-[18px]" />
            </span>
            <span className="text-[13.5px] font-semibold text-wb-ink-5">{c.label}</span>
            <span className="text-[11.5px] text-wb-faint-1">{c.desc}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

// ── ④ 成果展示区：横向滚动 + 懒加载 ──────────────────────
function ShowcaseSection() {
  const [ref, inView] = useInView<HTMLDivElement>()
  return (
    <section className="mt-14">
      <SectionHead title="看看实朴出的图" sub="真实案例陆续上线" />
      <div ref={ref} className="-mx-4 overflow-x-auto px-4 pb-2">
        <div className="flex gap-4">
          {SHOWCASE_PLACEHOLDERS.map((s) => (
            <figure
              key={s.key}
              className="w-[230px] shrink-0 overflow-hidden rounded-2xl border border-white/70 bg-white shadow-[0_6px_24px_-14px_rgba(40,40,90,.2)]"
            >
              <div className="relative aspect-[4/3] bg-wb-surface-3">
                {inView ? (
                  <div className="grid size-full place-items-center bg-gradient-to-br from-wb-tint-1 to-wb-surface-3 text-[12px] font-medium text-wb-faint-1">
                    案例占位
                  </div>
                ) : (
                  // Static placeholder: IO (rootMargin 120px) swaps in content before
                  // this is ever visible, so an infinite pulse would only burn frames.
                  <div className="size-full bg-wb-surface-4" />
                )}
                <span className="absolute left-2 top-2 rounded-full bg-white/85 px-2 py-0.5 text-[11px] font-medium text-wb-brand-deep backdrop-blur">
                  {s.tag}
                </span>
              </div>
              <figcaption className="px-3 py-2.5 text-[12.5px] font-medium text-wb-ink-3">{s.title}</figcaption>
            </figure>
          ))}
        </div>
      </div>
    </section>
  )
}

// ── ⑤ Footer ────────────────────────────────────────────
function HomeFooter() {
  return (
    <footer className="mt-16 border-t border-wb-line-1 pt-6 text-[12.5px] text-wb-ink-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2 font-semibold text-wb-ink-2">
            <span className="grid size-6 place-items-center rounded-lg bg-gradient-to-br from-wb-grad-from to-wb-grad-to text-[11px] font-bold text-white">
              朴
            </span>
            实朴 · 电商图片工作站
          </div>
          <p className="mt-2 max-w-xs leading-relaxed text-wb-faint-1">
            上传产品图，整套电商图一键出。内测期间免费使用。
          </p>
        </div>
        <div className="flex gap-12">
          <div className="flex flex-col gap-2">
            <span className="font-medium text-wb-ink-3">产品</span>
            <Link to="/set" className="hover:text-wb-brand-deep">商品套图</Link>
            <Link to="/clone" className="hover:text-wb-brand-deep">爆款复刻</Link>
            <Link to="/history" className="hover:text-wb-brand-deep">出图历史</Link>
          </div>
          <div className="flex flex-col gap-2">
            <span className="font-medium text-wb-ink-3">条款</span>
            <Link to="/terms" className="hover:text-wb-brand-deep">用户协议</Link>
            <Link to="/privacy" className="hover:text-wb-brand-deep">隐私政策</Link>
          </div>
        </div>
      </div>
      <div className="mt-6 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] text-wb-faint-1">
        <span>© 2026 实朴</span>
        <span className="text-wb-line-3">·</span>
        <span>ICP 备案号：备案申请中</span>
      </div>
    </footer>
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
