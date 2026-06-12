import { Outlet } from 'react-router-dom'
import { PlusIcon } from 'lucide-react'
import { toast } from 'sonner'

import { AppTopBar } from '@/components/layout/AppTopBar'
import { WorkbenchRail } from '@/components/listing/WorkbenchRail'
import { newTaskBus } from '@/components/listing/new-task-bus'

/** 全屏工作台外壳：共享顶栏(带「新建任务」) + 左 rail + 内容。 */
export function WorkbenchLayout() {
  return (
    <div className="flex h-svh flex-col bg-wb-surface-3 text-wb-ink-1">
      <AppTopBar>
        <button
          onClick={() => {
            newTaskBus.emit()
            toast('已清空，可开始新任务')
          }}
          className="flex items-center gap-1.5 rounded-[10px] border border-wb-line-1 bg-white px-3 py-1.5 text-[13.5px] text-wb-ink-3"
        >
          <PlusIcon className="size-4" /> 新建任务
        </button>
      </AppTopBar>
      <div className="flex min-h-0 flex-1">
        <WorkbenchRail />
        <Outlet />
      </div>
    </div>
  )
}
