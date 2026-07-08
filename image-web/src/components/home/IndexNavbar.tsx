import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'motion/react'
import {
  ChevronDownIcon,
  FileTextIcon,
  FlameIcon,
  HistoryIcon,
  LayersIcon,
  MenuIcon,
  ShieldIcon,
  SparklesIcon,
  XIcon,
  type LucideIcon,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/auth-store'
import logoUrl from '@/assets/hero/shipu-logo.png'

// Index 页顶部导航（navbar1 参考版式）：左 logo / 中菜单（hover 下拉=图标+标题+描述卡）/
// 右登录注册（已登录 → 进入工作台）。移动端汉堡 + 全屏面板。零新依赖（motion/lucide 现成）。

interface SubItem {
  label: string
  desc: string
  to: string
  icon: LucideIcon
}

interface MenuGroup {
  label: string
  items: SubItem[]
}

const PRODUCT_MENU: MenuGroup = {
  label: '产品功能',
  items: [
    { label: '帮我设计', desc: '用大白话说需求，AI 帮你出整套图', to: '/chat', icon: SparklesIcon },
    { label: '商品套图', desc: '白底、场景、卖点一次出齐', to: '/set', icon: LayersIcon },
    { label: '爆款复刻', desc: '上传参考图，复刻同款风格', to: '/clone', icon: FlameIcon },
    { label: '出图历史', desc: '回看每次出图，可再编辑与下载', to: '/history', icon: HistoryIcon },
  ],
}

const HELP_MENU: MenuGroup = {
  label: '帮助',
  items: [
    { label: '用户协议', desc: '使用实朴前请先阅读', to: '/terms', icon: FileTextIcon },
    { label: '隐私政策', desc: '我们如何保护你的数据', to: '/privacy', icon: ShieldIcon },
  ],
}

export function IndexNavbar() {
  const token = useAuthStore((s) => s.token)
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <header className="absolute inset-x-0 top-0 z-20">
      <nav className="flex h-16 items-center justify-between px-4 md:h-20 md:px-6">
        {/* 左：logo + 品牌名 + 紧随的桌面菜单（navbar1 同侧排法） */}
        <div className="flex items-center gap-8">
          <Link to="/" className="flex items-center gap-2 font-bold text-neutral-950">
            <img src={logoUrl} alt="实朴 logo" className="size-8 object-contain" />
            实朴
          </Link>
          <div className="hidden items-center gap-1 md:flex">
            <NavFlat to="/home" label="首页" />
            <NavDropdown group={PRODUCT_MENU} />
            <NavDropdown group={HELP_MENU} />
          </div>
        </div>

        {/* 右：桌面登录区（已登录 → 进入工作台） */}
        <div className="hidden items-center gap-2 md:flex">
          {token ? (
            <Button className="h-9 rounded-lg bg-neutral-900 px-4 text-white hover:bg-neutral-800" onClick={() => navigate('/home')}>
              进入工作台
            </Button>
          ) : (
            <>
              <Button variant="outline" className="h-9 rounded-lg px-4" onClick={() => navigate('/login')}>
                登录
              </Button>
              <Button className="h-9 rounded-lg bg-neutral-900 px-4 text-white hover:bg-neutral-800" onClick={() => navigate('/register')}>
                免费注册
              </Button>
            </>
          )}
        </div>

        {/* 移动端汉堡 */}
        <button
          className="grid size-10 place-items-center rounded-lg border border-neutral-200 md:hidden"
          aria-label={mobileOpen ? '关闭菜单' : '打开菜单'}
          onClick={() => setMobileOpen((v) => !v)}
        >
          {mobileOpen ? <XIcon className="size-5" /> : <MenuIcon className="size-5" />}
        </button>
      </nav>

      {/* 移动端全屏面板 */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            className="mx-4 rounded-2xl border border-neutral-200 bg-white p-4 shadow-xl md:hidden"
          >
            <Link to="/home" className="block rounded-lg px-3 py-2 text-[15px] font-semibold" onClick={() => setMobileOpen(false)}>
              首页
            </Link>
            {[PRODUCT_MENU, HELP_MENU].map((g) => (
              <div key={g.label} className="mt-2">
                <p className="px-3 py-1 text-xs font-medium text-neutral-400">{g.label}</p>
                {g.items.map((it) => (
                  <MenuCard key={it.to} item={it} onNavigate={() => setMobileOpen(false)} />
                ))}
              </div>
            ))}
            <div className="mt-4 flex flex-col gap-2 border-t border-neutral-100 pt-4">
              {token ? (
                <Button className="w-full bg-neutral-900 text-white" onClick={() => navigate('/home')}>
                  进入工作台
                </Button>
              ) : (
                <>
                  <Button variant="outline" className="w-full" onClick={() => navigate('/login')}>
                    登录
                  </Button>
                  <Button className="w-full bg-neutral-900 text-white" onClick={() => navigate('/register')}>
                    免费注册
                  </Button>
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  )
}

function NavFlat({ to, label }: { to: string; label: string }) {
  return (
    <Link
      to={to}
      className="rounded-lg px-4 py-2 text-[14px] font-medium text-neutral-700 transition-colors hover:bg-neutral-100 hover:text-neutral-950"
    >
      {label}
    </Link>
  )
}

/** hover 下拉（navbar1 同款交互）：触发器悬停展开图标+标题+描述卡。 */
function NavDropdown({ group }: { group: MenuGroup }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="relative" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        className={`flex items-center gap-1 rounded-lg px-4 py-2 text-[14px] font-medium transition-colors ${
          open ? 'bg-neutral-100 text-neutral-950' : 'text-neutral-700 hover:bg-neutral-100 hover:text-neutral-950'
        }`}
      >
        {group.label}
        <ChevronDownIcon className={`size-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            className="absolute left-0 top-full w-[340px] pt-2"
          >
            <div className="rounded-xl border border-neutral-200 bg-white p-2 shadow-xl">
              {group.items.map((it) => (
                <MenuCard key={it.to} item={it} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function MenuCard({ item, onNavigate }: { item: SubItem; onNavigate?: () => void }) {
  return (
    <Link
      to={item.to}
      onClick={onNavigate}
      className="flex gap-3 rounded-lg p-3 transition-colors hover:bg-neutral-100"
    >
      <item.icon className="mt-0.5 size-5 shrink-0 text-neutral-900" />
      <span className="min-w-0">
        <span className="block text-[14px] font-semibold text-neutral-950">{item.label}</span>
        <span className="mt-0.5 block text-[13px] leading-snug text-neutral-500">{item.desc}</span>
      </span>
    </Link>
  )
}
