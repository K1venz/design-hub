import { Outlet, useLocation } from 'react-router-dom'
import { motion } from 'motion/react'

import { AppShell } from '@/components/layout/AppShell'
import { DotPattern } from '@/components/visual/DotPattern'

/** 历史/管理页外壳：全局 SideNav（AppShell）+ 居中内容区（路由切换轻过渡）。 */
export function AppLayout() {
  const location = useLocation()
  return (
    <AppShell>
      <main className="relative min-h-0 flex-1 overflow-auto px-4 pb-4 pt-1">
        <DotPattern className="[mask-image:radial-gradient(ellipse_at_top,white,transparent_72%)]" />
        <motion.div
          key={location.pathname}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, ease: 'easeOut' }}
          className="relative mx-auto w-full max-w-5xl"
        >
          <Outlet />
        </motion.div>
      </main>
    </AppShell>
  )
}
