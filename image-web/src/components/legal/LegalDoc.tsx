import { ArrowLeftIcon } from 'lucide-react'
import { Link } from 'react-router-dom'

import { AppShell } from '@/components/layout/AppShell'

export interface LegalSection {
  h: string
  body: string[]
}

/** 法务文档展示（公开可读，Style 4）：标题 + 更新日期 + 分节正文。 */
export function LegalDoc({
  title, updated, intro, sections,
}: {
  title: string
  updated: string
  intro: string
  sections: LegalSection[]
}) {
  return (
    <AppShell>
      <main className="min-h-0 flex-1 overflow-auto pb-8 pr-3">
        <article className="mx-auto w-full max-w-3xl px-4 pt-4">
          <Link
            to="/"
            className="mb-5 inline-flex items-center gap-1.5 text-[13px] text-wb-ink-5 transition-colors hover:text-wb-brand-deep"
          >
            <ArrowLeftIcon className="size-4" /> 返回首页
          </Link>
          <div className="glass-panel rounded-2xl p-6 sm:p-8">
            <h1 className="text-[24px] font-semibold tracking-tight text-wb-ink-1">{title}</h1>
            <p className="mt-1 text-[12.5px] text-wb-ink-6">更新日期：{updated}</p>
            <p className="mt-4 text-[13.5px] leading-relaxed text-wb-ink-4">{intro}</p>

            <div className="mt-6 space-y-6">
              {sections.map((s, i) => (
                <section key={s.h}>
                  <h2 className="text-[15px] font-semibold text-wb-ink-2">
                    {i + 1}. {s.h}
                  </h2>
                  <div className="mt-2 space-y-2">
                    {s.body.map((p, j) => (
                      <p key={j} className="text-[13.5px] leading-relaxed text-wb-ink-4">
                        {p}
                      </p>
                    ))}
                  </div>
                </section>
              ))}
            </div>

            <p className="mt-8 border-t border-wb-line-1 pt-4 text-[12px] leading-relaxed text-wb-faint-1">
              本页为实朴内测期条款占位文本，正式对外发布前将由法务定稿更新。如有疑问请通过产品内反馈入口联系我们。
            </p>
          </div>
        </article>
      </main>
    </AppShell>
  )
}
