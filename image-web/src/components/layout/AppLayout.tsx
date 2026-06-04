import { Outlet } from 'react-router-dom'

import { AppTopBar } from '@/components/layout/AppTopBar'
import { DotPattern } from '@/components/visual/DotPattern'

/** 管理页外壳：与工作台共用顶栏导航，内容区居中。 */
export function AppLayout() {
  return (
    <div className="flex min-h-svh flex-col bg-[#f6f4f1]">
      <AppTopBar />
      <main className="relative flex-1 px-6 py-7">
        <DotPattern className="[mask-image:radial-gradient(ellipse_at_top,white,transparent_72%)]" />
        <div className="relative mx-auto w-full max-w-6xl">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
