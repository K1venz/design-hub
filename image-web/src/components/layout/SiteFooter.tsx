import { Link } from 'react-router-dom'
import { MailIcon, MessageCircleIcon } from 'lucide-react'

import { cn } from '@/lib/utils'
import logoUrl from '@/assets/hero/shipu-logo.png'

// 全站公共 Footer（单一事实源）：品牌行 + 联系方式（占位）→ 站内链接 → 独立备案底栏。
// 宿主差异（Index 全宽 vs AppShell 内滚窄容器）由 className 传水平 padding/背景/边距。
const MAIN_LINKS = [
  { label: '首页', to: '/home' },
  { label: '帮我设计', to: '/chat' },
  { label: '商品套图', to: '/set' },
  { label: '爆款复刻', to: '/clone' },
] as const

const LEGAL_LINKS = [
  { label: '用户协议', to: '/terms' },
  { label: '隐私政策', to: '/privacy' },
] as const

// 联系方式占位（待用户提供微信/邮箱后替换 href 与提示）。
const CONTACTS = [
  { icon: MessageCircleIcon, label: '微信（即将提供）' },
  { icon: MailIcon, label: '邮箱（即将提供）' },
] as const

export function SiteFooter({ className }: { className?: string }) {
  return (
    <footer className={cn('text-neutral-950', className)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-lg font-bold">
          <img src={logoUrl} alt="实朴 logo" className="size-9 object-contain" />
          实朴 · 电商图片工作站
        </div>
        <div className="flex items-center gap-3">
          {CONTACTS.map((c) => (
            <button
              key={c.label}
              type="button"
              title={c.label}
              aria-label={c.label}
              className="grid size-10 cursor-default place-items-center rounded-full bg-neutral-100 text-neutral-700"
            >
              <c.icon className="size-4.5" />
            </button>
          ))}
        </div>
      </div>

      <div className="mt-10 border-t border-neutral-200 pt-10">
        <div className="flex flex-col gap-3 md:items-end">
            <nav className="flex flex-wrap gap-x-6 gap-y-2 text-[14px] font-medium">
              {MAIN_LINKS.map((l) => (
                <Link key={l.to} to={l.to} className="text-neutral-950 transition-colors hover:text-wb-brand">
                  {l.label}
                </Link>
              ))}
            </nav>
            <nav className="flex gap-x-6 text-[13.5px] text-neutral-500">
              {LEGAL_LINKS.map((l) => (
                <Link key={l.to} to={l.to} className="transition-colors hover:text-neutral-950">
                  {l.label}
                </Link>
              ))}
            </nav>
        </div>

        <p className="mt-8 border-t border-neutral-200 pt-6 text-center text-[13.5px] leading-relaxed text-neutral-500">
          <a
            href="https://beian.miit.gov.cn"
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-neutral-700 underline-offset-4 transition-colors hover:text-neutral-950 hover:underline"
          >
            浙ICP备2026024031号-1
          </a>
          {' · Copyright © 2026 浙江实朴数据科技有限公司'}
        </p>
      </div>
    </footer>
  )
}
