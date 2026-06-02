import { useState } from 'react'
import { toast } from 'sonner'

import { useUpdateProjectStatus, type Project } from '@/api/projects'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { ALLOWED_TRANSITIONS, transitionLabel, type ProjectStatus } from '@/lib/project-status'
import { isManager, useCurrentUser } from '@/stores/auth-store'

export function ProjectStatusControl({ project }: { project: Project }) {
  const user = useCurrentUser()
  const update = useUpdateProjectStatus()
  const [forceOpen, setForceOpen] = useState(false)
  const targets = ALLOWED_TRANSITIONS[project.status]

  async function go(target: ProjectStatus) {
    try {
      await update.mutateAsync({ projectId: project.id, status: target })
      toast.success(`已流转至「${target}」`)
    } catch (e) {
      const msg = e instanceof Error ? e.message : '状态流转失败'
      // 交付强校验：有未完成改稿条目 → 管理者可强制
      if (target === '已交付' && msg.includes('改稿') && isManager(user.role)) {
        setForceOpen(true)
        return
      }
      toast.error(msg)
    }
  }

  async function forceDeliver() {
    setForceOpen(false)
    try {
      await update.mutateAsync({ projectId: project.id, status: '已交付', force: true })
      toast.success('已强制交付')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '强制交付失败')
    }
  }

  if (targets.length === 0) {
    return <p className="text-sm text-muted-foreground">项目已交付，流程结束。</p>
  }

  return (
    <>
      <div className="flex flex-wrap gap-2">
        {targets.map((target, i) => {
          const isRollback = project.status === '客户审稿' && target === '设计中'
          return (
            <Button
              key={target}
              variant={i === 0 && !isRollback ? 'default' : 'outline'}
              size="sm"
              disabled={update.isPending}
              onClick={() => void go(target)}
            >
              {transitionLabel(project.status, target)}
            </Button>
          )
        })}
      </div>

      <AlertDialog open={forceOpen} onOpenChange={setForceOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>项目存在未完成改稿条目</AlertDialogTitle>
            <AlertDialogDescription>
              仍有改稿条目未勾选完成。作为管理者，你可以强制交付（跳过校验），此操作不可撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={() => void forceDeliver()}>强制交付</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
