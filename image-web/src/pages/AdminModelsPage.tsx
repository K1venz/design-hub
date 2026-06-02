import { toast } from 'sonner'
import { PencilIcon } from 'lucide-react'

import { useModels, useUpdateModel, type ModelConfig } from '@/api/admin'
import { EditPriceDialog } from '@/components/admin/EditPriceDialog'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

export function AdminModelsPage() {
  const models = useModels()
  const update = useUpdateModel()

  async function toggle(m: ModelConfig, enabled: boolean) {
    try {
      await update.mutateAsync({ name: m.name, patch: { enabled } })
      toast.success(`「${m.name}」已${enabled ? '启用' : '停用'}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '更新失败')
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h2 className="text-xl font-semibold tracking-tight text-foreground">模型配置</h2>
        <p className="text-sm text-muted-foreground">启停模型、调整单价（即时注入 Provider）。仅管理者可见。</p>
      </div>

      <Card className="overflow-hidden p-0">
        {models.isLoading ? (
          <div className="space-y-3 p-5">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : models.data && models.data.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>模型</TableHead>
                <TableHead>单价（¥ / 张）</TableHead>
                <TableHead>启用</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {models.data.map((m) => (
                <TableRow key={m.name}>
                  <TableCell className="font-mono font-medium">{m.name}</TableCell>
                  <TableCell className="tabular font-mono text-sm">
                    ¥{Number(m.unit_cost).toFixed(2)}
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={m.enabled}
                      disabled={update.isPending}
                      onCheckedChange={(v) => void toggle(m, v)}
                    />
                  </TableCell>
                  <TableCell className="text-right">
                    <EditPriceDialog
                      model={m}
                      trigger={
                        <Button variant="ghost" size="sm">
                          <PencilIcon className="size-3.5" />
                          改价
                        </Button>
                      }
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="py-16 text-center text-sm text-muted-foreground">暂无模型配置。</div>
        )}
      </Card>
    </div>
  )
}
