import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { useCustomers } from '@/api/customers'
import { useCreateProject } from '@/api/projects'
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

export function CreateProjectDialog({
  trigger,
  defaultCustomerId,
}: {
  trigger: ReactNode
  defaultCustomerId?: number
}) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [customerId, setCustomerId] = useState<string>(
    defaultCustomerId != null ? String(defaultCustomerId) : '',
  )
  const customers = useCustomers()
  const create = useCreateProject()
  const navigate = useNavigate()

  function onOpenChange(next: boolean) {
    setOpen(next)
    // 打开时按入口预选客户（在事件里同步，避免 effect 里 setState）
    if (next && defaultCustomerId != null) setCustomerId(String(defaultCustomerId))
  }

  async function submit() {
    if (!name.trim() || !customerId) return
    try {
      const p = await create.mutateAsync({ customer_id: Number(customerId), name: name.trim() })
      toast.success(`已创建项目「${p.name}」`)
      setOpen(false)
      setName('')
      navigate(`/projects/${p.id}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '创建项目失败')
    }
  }

  const list = customers.data ?? []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>新建项目</DialogTitle>
          <DialogDescription>一单一档：项目挂在客户下，创建后进入项目详情录入需求与出图。</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="proj-customer">
              所属客户 <span className="text-destructive">*</span>
            </Label>
            {list.length === 0 ? (
              <p className="text-muted-foreground rounded-md border border-dashed px-3 py-2.5 text-sm">
                还没有客户，请先在「客户」页新建客户。
              </p>
            ) : (
              <Select value={customerId} onValueChange={setCustomerId}>
                <SelectTrigger id="proj-customer" className="w-full">
                  <SelectValue placeholder="选择客户" />
                </SelectTrigger>
                <SelectContent>
                  {list.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="proj-name">
              项目名称 <span className="text-destructive">*</span>
            </Label>
            <Input
              id="proj-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如：花生618大促主图"
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!name.trim() || !customerId || create.isPending}>
              {create.isPending ? '创建中…' : '创建项目'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
