import { Outlet, useLocation } from 'react-router-dom'
import { PlusIcon } from 'lucide-react'
import { motion } from 'motion/react'
import { toast } from 'sonner'

import { AppShell } from '@/components/layout/AppShell'
import { newTaskBus } from '@/components/listing/new-task-bus'

/** 出图工作台外壳：全局 SideNav（AppShell）+ 顶栏「新建任务」+ 内容（路由切换轻过渡）。 */
export function WorkbenchLayout() {
  const location = useLocation()
  return (
    <AppShell
      topbarLeft={
        <button
          onClick={() => {
            newTaskBus.emit()
            toast('已清空，可开始新任务')
          }}
          className="flex items-center gap-1.5 rounded-full border border-white/70 bg-white/80 px-3.5 py-1.5 text-[13px] font-medium text-wb-ink-3 shadow-sm transition-shadow hover:shadow"
        >
          <PlusIcon className="size-4" /> 新建任务
        </button>
      }
    >
      <motion.div
        key={location.pathname}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.22, ease: 'easeOut' }}
        className="flex min-h-0 min-w-0 flex-1 flex-col gap-3 overflow-y-auto px-3 pb-3 md:flex-row md:overflow-visible md:px-0 md:pr-3"
      >
        <Outlet />
      </motion.div>
    </AppShell>
  )
}
