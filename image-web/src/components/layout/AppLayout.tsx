import { Outlet, useLocation } from 'react-router-dom'
import { motion } from 'motion/react'

import { AppTopBar } from '@/components/layout/AppTopBar'
import { DotPattern } from '@/components/visual/DotPattern'

/** 管理页外壳：与工作台共用顶栏导航，内容区居中（路由切换轻过渡）。 */
export function AppLayout() {
  const location = useLocation()
  return (
    <div className="canvas-blobs flex min-h-svh flex-col bg-background">
      <AppTopBar />
      <main className="relative flex-1 px-6 py-6">
        <DotPattern className="[mask-image:radial-gradient(ellipse_at_top,white,transparent_72%)]" />
        <motion.div
          key={location.pathname}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, ease: 'easeOut' }}
          className="relative mx-auto w-full max-w-6xl"
        >
          <Outlet />
        </motion.div>
      </main>
    </div>
  )
}
