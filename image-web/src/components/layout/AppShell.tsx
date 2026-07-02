import type { ReactNode } from 'react'

import { AppTopBar } from '@/components/layout/AppTopBar'
import { SideNav } from '@/components/layout/SideNav'

/**
 * 全局外壳：左 SideNav（全高）+ 右列（顶栏 + 内容）。公开态兼容（未登录可渲染）。
 * `topbarLeft` = 顶栏左侧上下文槽（如工作台「新建任务」）；`children` = 内容主区。
 */
export function AppShell({ topbarLeft, children }: { topbarLeft?: ReactNode; children: ReactNode }) {
  return (
    <div className="canvas-blobs flex h-svh gap-3 bg-background p-3 text-wb-ink-1">
      <SideNav />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <AppTopBar>{topbarLeft}</AppTopBar>
        {children}
      </div>
    </div>
  )
}
