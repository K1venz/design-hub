import { useMemo, useState } from 'react'
import { PlusIcon } from 'lucide-react'

import { useModels } from '@/api/admin'
import { ModelConfigDialog } from '@/components/admin/ModelConfigDialog'
import { ModelRowActions } from '@/components/admin/ModelRowActions'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

type ModelFilter = 'all' | 'image' | 'chat'

const FILTERS: { value: ModelFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'image', label: '图片模型' },
  { value: 'chat', label: 'Chat 模型' },
]

export function AdminModelsPage() {
  const models = useModels()
  const [filter, setFilter] = useState<ModelFilter>('all')

  const rows = useMemo(() => {
    const filtered =
      filter === 'all'
        ? models.data ?? []
        : (models.data ?? []).filter((model) => model.model_type === filter)
    return [...filtered].sort((left, right) => {
      const type = left.model_type.localeCompare(right.model_type)
      if (type !== 0) return type
      if (left.is_default !== right.is_default) {
        return left.is_default ? -1 : 1
      }
      return left.name.localeCompare(right.name)
    })
  }, [filter, models.data])

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-wb-ink-1">
            模型配置
          </h1>
          <p className="mt-1 max-w-3xl text-xs text-wb-ink-6">
            管理图片与 Chat 模型的运行时连接。配置必须通过真实能力测试，
            保存后立即生效。
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

      <div
        aria-label="模型类型筛选"
        className="flex w-fit gap-1 rounded-xl border border-wb-line-1 bg-white/70 p-1"
      >
        {FILTERS.map((item) => (
          <button
            key={item.value}
            type="button"
            aria-pressed={filter === item.value}
            onClick={() => setFilter(item.value)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
              filter === item.value
                ? 'bg-wb-tint-2 text-wb-brand-deep'
                : 'text-wb-ink-6 hover:text-wb-ink-2'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <Card className="overflow-hidden border-white/80 bg-white/82 p-0">
        {models.isLoading ? (
          <div className="space-y-3 p-5">
            {[0, 1, 2].map((item) => (
              <Skeleton key={item} className="h-12 w-full" />
            ))}
          </div>
        ) : models.isError ? (
          <div className="py-16 text-center text-sm text-wb-red">
            模型配置加载失败，请稍后重试。
          </div>
        ) : rows.length > 0 ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>模型</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead>Provider</TableHead>
                  <TableHead>验证状态</TableHead>
                  <TableHead>内部单价</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((model) => (
                  <TableRow key={model.name}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div>
                          <p className="font-medium">{model.display_name}</p>
                          <p className="font-mono text-[11px] text-muted-foreground">
                            {model.name}
                          </p>
                        </div>
                        {model.is_default ? (
                          <Badge
                            variant="outline"
                            className="border-emerald-200 bg-emerald-50 font-medium text-emerald-700"
                          >
                            类型默认
                          </Badge>
                        ) : null}
                      </div>
                    </TableCell>
                    <TableCell>
                      {model.model_type === 'image' ? '图片' : 'Chat'}
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {model.provider_type}
                    </TableCell>
                    <TableCell>
                      {model.verified_at ? (
                        <div>
                          <p className="text-xs font-medium text-emerald-700">
                            已验证
                          </p>
                          <p className="text-[11px] text-muted-foreground">
                            {new Date(model.verified_at).toLocaleString('zh-CN', {
                              hour12: false,
                            })}
                          </p>
                        </div>
                      ) : (
                        <span className="text-xs text-wb-amber">未验证</span>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-sm">
                      ¥{Number(model.unit_cost).toFixed(4)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={model.enabled ? 'default' : 'secondary'}>
                        {model.enabled ? '已启用' : '已停用'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <ModelRowActions model={model} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <div className="py-16 text-center text-sm text-muted-foreground">
            当前筛选下没有模型配置。
          </div>
        )}
      </Card>
    </div>
  )
}
