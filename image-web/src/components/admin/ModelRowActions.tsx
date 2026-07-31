import { toast } from 'sonner'
import { PencilIcon, Trash2Icon, ZapIcon } from 'lucide-react'

import { useDeleteModel, useSetDefaultModel, type ModelConfig } from '@/api/admin'
import { ModelConfigDialog } from '@/components/admin/ModelConfigDialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'

/** 单行模型的操作簇：设为默认渠道 / 编辑 / 删除（ISSUE-0057）。 */
export function ModelRowActions({ model }: { model: ModelConfig }) {
  const setDefault = useSetDefaultModel()
  const del = useDeleteModel()

  async function doSetDefault() {
    try {
      await setDefault.mutateAsync(model.name)
      toast.success(`已将「${model.display_name}」设为类型默认模型，立即生效`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '设为默认渠道失败')
    }
  }

  async function doDelete() {
    try {
      await del.mutateAsync(model.name)
      toast.success(`已删除「${model.name}」`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '删除失败')
    }
  }

  return (
    <div className="flex items-center justify-end gap-1">
      {!model.is_default && (
        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="ghost" size="sm" disabled={setDefault.isPending}>
              <ZapIcon className="size-3.5" />
              设为默认
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>切换类型默认模型？</AlertDialogTitle>
              <AlertDialogDescription>
                未保存过个人选择的用户将优先使用「{model.display_name}」。
                已有选择不会被静默切换。
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>取消</AlertDialogCancel>
              <AlertDialogAction onClick={() => void doSetDefault()}>确认切换</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}

      <ModelConfigDialog
        mode="edit"
        model={model}
        trigger={
          <Button variant="ghost" size="sm">
            <PencilIcon className="size-3.5" />
            编辑
          </Button>
        }
      />

      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive hover:text-destructive"
            disabled={del.isPending}
          >
            <Trash2Icon className="size-3.5" />
            删除
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除「{model.name}」？</AlertDialogTitle>
            <AlertDialogDescription>
              删除后该模型渠道配置将从系统移除，不可恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => void doDelete()}>
              删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
