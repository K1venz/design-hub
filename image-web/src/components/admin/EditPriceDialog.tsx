import { useState, type ReactNode } from 'react'
import { toast } from 'sonner'

import { useUpdateModel, type ModelConfig } from '@/api/admin'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export function EditPriceDialog({
  model,
  trigger,
}: {
  model: ModelConfig
  trigger: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const [price, setPrice] = useState(model.unit_cost)
  const update = useUpdateModel()

  function onOpenChange(next: boolean) {
    setOpen(next)
    if (next) setPrice(model.unit_cost)
  }

  async function submit() {
    const n = Number(price)
    if (!Number.isFinite(n) || n < 0) {
      toast.error('单价需为非负数')
      return
    }
    try {
      await update.mutateAsync({ name: model.name, patch: { unit_cost: n } })
      toast.success(`已更新「${model.name}」单价`)
      setOpen(false)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '更新单价失败')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>调整单价</DialogTitle>
          <DialogDescription>
            <span className="font-mono">{model.name}</span> 的每张出图单价（元），即时注入 Provider。
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="unit-cost">单价（¥ / 张）</Label>
            <Input
              id="unit-cost"
              type="number"
              min="0"
              step="0.01"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? '保存中…' : '保存'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
