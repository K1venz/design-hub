import { useSearchParams } from 'react-router-dom'

import { useAdminAuditLogs } from '@/api/admin'
import { AdminPagination } from '@/components/admin/AdminPagination'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'

const LIMIT = 20

function dateTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

function actionLabel(value: string): string {
  const labels: Record<string, string> = {
    'user.role.update': '调整用户角色',
    'user.status.update': '调整用户状态',
    'image.moderation.update': '更新图片审核',
    'model.create': '新增模型配置',
    'model.update': '修改模型配置',
    'model.delete': '删除模型配置',
    'model.default.set': '切换默认模型',
  }
  return labels[value] ?? value
}

function Snapshot({
  label,
  value,
}: {
  label: string
  value: Record<string, unknown> | null
}) {
  if (!value) return null
  return (
    <div className="min-w-0">
      <p className="mb-1 text-[11px] font-medium text-wb-ink-6">
        {label}
      </p>
      <pre className="overflow-x-auto rounded-lg bg-wb-surface-2 p-2 text-[11px] leading-5 text-wb-ink-4">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  )
}

export function AdminAuditPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  function setParam(key: string, value?: string) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (value) next.set(key, value)
      else next.delete(key)
      if (key !== 'offset') next.delete('offset')
      return next
    })
  }

  const logs = useAdminAuditLogs({
    actor_user_id: (() => {
      const value = Number(searchParams.get('actor_user_id'))
      return value > 0 ? value : undefined
    })(),
    action: searchParams.get('action') || undefined,
    target_type: searchParams.get('target_type') || undefined,
    limit: LIMIT,
    offset: Number(searchParams.get('offset') ?? 0) || 0,
  })

  return (
    <div className="space-y-4">
      <header className="px-1">
        <h1 className="text-2xl font-semibold tracking-tight text-wb-ink-1">
          操作记录
        </h1>
        <p className="mt-1 text-xs text-wb-ink-6">
          记录用户、图片和模型配置的关键管理动作；不保存 API Key、密码或完整提示词。
        </p>
      </header>

      <Card className="grid gap-3 border-white/80 bg-white/82 p-3 sm:grid-cols-3">
        <Input
          inputMode="numeric"
          placeholder="操作者用户 ID"
          value={searchParams.get('actor_user_id') ?? ''}
          onChange={(event) =>
            setParam('actor_user_id', event.target.value.trim())
          }
        />
        <Select
          value={searchParams.get('action') ?? 'all'}
          onValueChange={(value) =>
            setParam('action', value === 'all' ? undefined : value)
          }
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="动作" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部动作</SelectItem>
            <SelectItem value="user.role.update">调整用户角色</SelectItem>
            <SelectItem value="user.status.update">调整用户状态</SelectItem>
            <SelectItem value="image.moderation.update">更新图片审核</SelectItem>
            <SelectItem value="model.create">新增模型配置</SelectItem>
            <SelectItem value="model.update">修改模型配置</SelectItem>
            <SelectItem value="model.delete">删除模型配置</SelectItem>
            <SelectItem value="model.default.set">切换默认模型</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={searchParams.get('target_type') ?? 'all'}
          onValueChange={(value) =>
            setParam(
              'target_type',
              value === 'all' ? undefined : value,
            )
          }
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="目标类型" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部目标</SelectItem>
            <SelectItem value="user">用户</SelectItem>
            <SelectItem value="image">图片</SelectItem>
            <SelectItem value="model">模型配置</SelectItem>
          </SelectContent>
        </Select>
      </Card>

      {logs.isLoading ? (
        <Skeleton className="h-[60vh] rounded-xl" />
      ) : logs.isError ? (
        <Card className="py-16 text-center text-sm text-wb-red">
          操作记录加载失败
        </Card>
      ) : logs.data?.items.length ? (
        <Card className="gap-0 bg-white/82 p-0">
          <div className="divide-y divide-wb-line-1">
            {logs.data.items.map((entry) => (
              <article
                key={entry.audit_id}
                className="grid gap-3 p-4 lg:grid-cols-[220px_minmax(0,1fr)]"
              >
                <div>
                  <Badge variant="outline">
                    {actionLabel(entry.action)}
                  </Badge>
                  <p className="mt-2 text-sm font-medium text-wb-ink-2">
                    {entry.actor_email}
                  </p>
                  <p className="mt-1 text-xs text-wb-ink-6">
                    {entry.target_type} · {entry.target_id}
                  </p>
                  <p className="mt-1 tabular text-[11px] text-wb-ink-7">
                    {dateTime(entry.created_at)}
                  </p>
                  {entry.reason ? (
                    <p className="mt-2 text-xs text-wb-ink-5">
                      原因：{entry.reason}
                    </p>
                  ) : null}
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <Snapshot label="修改前" value={entry.before} />
                  <Snapshot label="修改后" value={entry.after} />
                </div>
              </article>
            ))}
          </div>
          <AdminPagination
            total={logs.data.total}
            limit={logs.data.limit}
            offset={logs.data.offset}
            onOffsetChange={(offset) =>
              setParam('offset', String(offset))
            }
          />
        </Card>
      ) : (
        <Card className="py-16 text-center text-sm text-wb-ink-6">
          当前筛选下没有操作记录
        </Card>
      )}
    </div>
  )
}
