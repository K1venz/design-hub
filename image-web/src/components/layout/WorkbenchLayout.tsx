import { Outlet, useLocation } from 'react-router-dom'
import { PlusIcon } from 'lucide-react'
import { motion } from 'motion/react'
import { toast } from 'sonner'

import { AppTopBar } from '@/components/layout/AppTopBar'
import { WorkbenchRail } from '@/components/listing/WorkbenchRail'
import { newTaskBus } from '@/components/listing/new-task-bus'

/** 全屏工作台外壳：共享顶栏(带「新建任务」) + 左 rail + 内容（路由切换轻过渡）。 */
export function WorkbenchLayout() {
  const location = useLocation()
  return (
    <div className="canvas-blobs flex h-svh flex-col bg-background text-wb-ink-1">
      <AppTopBar>
        <button
          onClick={() => {
            newTaskBus.emit()
            toast('已清空，可开始新任务')
          }}
          className="flex items-center gap-1.5 rounded-full border border-white/70 bg-white/80 px-3.5 py-1.5 text-[13px] font-medium text-wb-ink-3 shadow-sm transition-shadow hover:shadow"
        >
          <PlusIcon className="size-4" /> 新建任务
        </button>
      </AppTopBar>
      <div className="flex min-h-0 flex-1 gap-4 px-4 pb-4 pt-2">
        <WorkbenchRail />
        <motion.div
          key={location.pathname}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, ease: 'easeOut' }}
          className="flex min-h-0 min-w-0 flex-1 gap-4"
        >
          <Outlet />
        </motion.div>
      </div>
    </div>
  )
}
