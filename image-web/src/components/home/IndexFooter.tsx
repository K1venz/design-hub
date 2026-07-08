import { Link } from 'react-router-dom'
import { MailIcon, MessageCircleIcon } from 'lucide-react'

import logoUrl from '@/assets/hero/shipu-logo.png'

// Index 页 Footer（footer 参考版式的实朴适配）：上行=品牌 | 联系方式（占位）；
// 分隔线；下行=版权+备案（占位）| 主链接行 + 法务链接行。
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

export function IndexFooter() {
  return (
    <footer className="bg-white px-8 pb-16 pt-20 text-neutral-950 md:px-16">
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
        <div className="flex flex-col gap-10 md:flex-row md:items-start md:justify-between">
          <div className="text-[13.5px] leading-relaxed text-neutral-500">
            <p>© 2026 实朴</p>
            <p className="mt-1">ICP 备案号：备案申请中</p>
          </div>
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
        </div>
      </div>
    </footer>
  )
}
