import { useState, type ReactNode } from 'react'

import { AppTopBar } from '@/components/layout/AppTopBar'
import { SideNav } from '@/components/layout/SideNav'

/**
 * 全局外壳：左 SideNav（桌面全高 / 移动汉堡抽屉）+ 右列（顶栏 + 内容）。公开态兼容。
 * `topbarLeft` = 顶栏左侧上下文槽（如工作台「新建任务」）；`children` = 内容主区。
 * 移动抽屉开合状态提到本层，顶栏汉堡开、SideNav 渲染抽屉（点导航/遮罩/Esc 关）。
 */
export function AppShell({ topbarLeft, children }: { topbarLeft?: ReactNode; children: ReactNode }) {
  const [navOpen, setNavOpen] = useState(false)
  return (
    <div className="canvas-blobs flex h-svh gap-3 bg-background p-3 text-wb-ink-1">
      <SideNav open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <AppTopBar onMenu={() => setNavOpen(true)}>{topbarLeft}</AppTopBar>
        {children}
      </div>
    </div>
  )
}
