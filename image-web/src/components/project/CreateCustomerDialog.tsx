import { useState, type ReactNode } from 'react'
import { toast } from 'sonner'

import { useCreateCustomer } from '@/api/customers'
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

export function CreateCustomerDialog({ trigger }: { trigger: ReactNode }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [contact, setContact] = useState('')
  const [industry, setIndustry] = useState('')
  const [brandColor, setBrandColor] = useState('')
  const create = useCreateCustomer()

  function reset() {
    setName('')
    setContact('')
    setIndustry('')
    setBrandColor('')
  }

  async function submit() {
    if (!name.trim()) return
    try {
      const c = await create.mutateAsync({
        name: name.trim(),
        contact: contact.trim() || null,
        industry: industry.trim() || null,
        brand_color: brandColor.trim() || null,
      })
      toast.success(`已创建客户「${c.name}」`)
      setOpen(false)
      reset()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '创建客户失败')
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>新建客户</DialogTitle>
          <DialogDescription>客户档案可跨项目复用，后续可在客户页补全风格 / 禁忌 / 尺寸。</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="cust-name">
              客户名称 <span className="text-destructive">*</span>
            </Label>
            <Input
              id="cust-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="如：花生食品旗舰店"
              autoFocus
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <Label htmlFor="cust-contact">联系人</Label>
              <Input id="cust-contact" value={contact} onChange={(e) => setContact(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cust-industry">行业</Label>
              <Input
                id="cust-industry"
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                placeholder="如：食品"
              />
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="cust-color">品牌色</Label>
            <Input
              id="cust-color"
              value={brandColor}
              onChange={(e) => setBrandColor(e.target.value)}
              placeholder="如：#C8442B"
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!name.trim() || create.isPending}>
              {create.isPending ? '创建中…' : '创建客户'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
