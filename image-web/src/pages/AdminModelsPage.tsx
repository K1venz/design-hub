import { useMemo } from 'react'
import { toast } from 'sonner'
import { PlusIcon } from 'lucide-react'

import { useModels, useUpdateModel, type ModelConfig } from '@/api/admin'
import { ModelConfigDialog } from '@/components/admin/ModelConfigDialog'
import { ModelRowActions } from '@/components/admin/ModelRowActions'
import { Badge } from '@/components/ui/badge'
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

  // 默认渠道置顶 → 启用 → 停用，同组按名排。
  const sorted = useMemo(() => {
    return [...(models.data ?? [])].sort((a, b) => {
      if (a.is_default !== b.is_default) return a.is_default ? -1 : 1
      if (a.enabled !== b.enabled) return a.enabled ? -1 : 1
      return a.name.localeCompare(b.name)
    })
  }, [models.data])

  async function toggle(m: ModelConfig, enabled: boolean) {
    try {
      await update.mutateAsync({ name: m.name, patch: { enabled } })
      toast.success(`「${m.name}」已${enabled ? '启用' : '停用'}`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '更新失败')
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-wb-ink-1">模型配置</h1>
          <p className="mt-1 max-w-3xl text-xs text-wb-ink-6">
            配置出图渠道：新增备用中转站、设为默认渠道（断供时切换即恢复）、调价与启停。
            真实密钥仅存服务端环境变量，此处只填「密钥变量」。
          </p>
        </div>
        <ModelConfigDialog
          mode="create"
          trigger={
            <Button size="sm">
              <PlusIcon className="size-3.5" />
              新增模型
            </Button>
          }
        />
      </div>

      <Card className="overflow-hidden border-white/80 bg-white/82 p-0">
        {models.isLoading ? (
          <div className="space-y-3 p-5">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : models.isError ? (
          <div className="py-16 text-center text-sm text-wb-red">
            模型配置加载失败，请稍后重试。
          </div>
        ) : sorted.length > 0 ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>模型</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead>连接</TableHead>
                  <TableHead>密钥变量</TableHead>
                  <TableHead>单价（¥ / 张）</TableHead>
                  <TableHead>启用</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.map((m) => (
                  <TableRow key={m.name}>
                    <TableCell className="font-mono font-medium">
                      <div className="flex items-center gap-2">
                        {m.name}
                        {m.is_default && (
                          <Badge
                            variant="outline"
                            className="border-emerald-200 bg-emerald-50 font-medium text-emerald-700"
                          >
                            默认渠道
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{m.provider_type}</TableCell>
                    <TableCell className="max-w-[220px] text-sm">
                      {m.base_url || m.model ? (
                        <div className="truncate font-mono text-xs text-muted-foreground">
                          <span className="text-foreground">{m.model || '—'}</span>
                          {m.base_url && <span> · {m.base_url}</span>}
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">回落 .env</span>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {m.api_key_env || '—'}
                    </TableCell>
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
                      <ModelRowActions model={m} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <div className="py-16 text-center text-sm text-muted-foreground">
            暂无模型配置。点「新增模型」添加出图渠道。
          </div>
        )}
      </Card>
    </div>
  )
}
