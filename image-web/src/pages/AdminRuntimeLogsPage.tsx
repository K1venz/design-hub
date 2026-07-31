import { useSearchParams } from 'react-router-dom'

import {
  type RuntimeLogDetail,
  type RuntimeLogListItem,
  useRuntimeLogDetail,
  useRuntimeLogs,
  useRuntimeLogTrace,
} from '@/api/admin'
import { AdminPagination } from '@/components/admin/AdminPagination'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

const LIMIT = 20

const SEVERITY = {
  info: {
    label: '正常',
    className: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  },
  warning: {
    label: '业务问题',
    className: 'border-wb-amber-line bg-wb-amber-tint text-wb-amber',
  },
  error: {
    label: '系统问题',
    className: 'border-wb-red/30 bg-wb-red/10 text-wb-red',
  },
} as const

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

function optionalValue(value: string | number | null): string {
  return value === null ? '—' : String(value)
}

function LogSeverity({ level }: { level: RuntimeLogListItem['level'] }) {
  const severity = SEVERITY[level]
  return (
    <Badge variant="outline" className={severity.className}>
      {severity.label}
    </Badge>
  )
}

function DetailField({
  label,
  value,
}: {
  label: string
  value: string | number | null
}) {
  return (
    <div className="min-w-0 rounded-lg bg-wb-surface-2 px-3 py-2">
      <dt className="text-[11px] text-wb-ink-6">{label}</dt>
      <dd className="mt-1 break-all text-xs font-medium text-wb-ink-3">
        {optionalValue(value)}
      </dd>
    </div>
  )
}

export function RuntimeLogDetailContent({
  detail,
  trace,
  selectedEventId,
}: {
  detail: RuntimeLogDetail
  trace: RuntimeLogDetail[]
  selectedEventId: string
}) {
  const sortedTrace = [...trace].sort((left, right) =>
    left.timestamp.localeCompare(right.timestamp),
  )

  return (
    <div className="space-y-5">
      <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <DetailField label="链路 ID" value={detail.trace_id} />
        <DetailField label="任务 ID" value={detail.job_id} />
        <DetailField label="请求 ID" value={detail.request_id} />
        <DetailField label="条目 ID" value={detail.item_id} />
        <DetailField label="操作 ID" value={detail.operation_id} />
        <DetailField label="模型" value={detail.model} />
        <DetailField label="Provider" value={detail.provider} />
        <DetailField label="状态" value={detail.status} />
        <DetailField
          label="耗时"
          value={
            detail.duration_ms === null ? null : `${detail.duration_ms} ms`
          }
        />
        <DetailField label="错误码" value={detail.error_code} />
        <DetailField label="错误类型" value={detail.error_type} />
      </dl>

      {detail.error_summary ? (
        <section>
          <h3 className="text-xs font-semibold text-wb-ink-3">错误摘要</h3>
          <p className="mt-2 whitespace-pre-wrap break-words rounded-lg bg-wb-red/5 p-3 text-xs leading-5 text-wb-red">
            {detail.error_summary}
          </p>
        </section>
      ) : null}

      {detail.prompt ? (
        <section>
          <h3 className="text-xs font-semibold text-wb-ink-3">完整提示词</h3>
          <pre className="mt-2 max-h-56 select-text overflow-auto whitespace-pre-wrap break-words rounded-lg bg-wb-surface-2 p-3 text-xs leading-5 text-wb-ink-3">
            {detail.prompt}
          </pre>
        </section>
      ) : null}

      <section>
        <h3 className="text-xs font-semibold text-wb-ink-3">
          同一链路 · {sortedTrace.length} 条
        </h3>
        <ol className="mt-2 space-y-2">
          {sortedTrace.map((entry) => {
            const isCurrent = entry.event_id === selectedEventId
            return (
              <li
                key={entry.event_id}
                className={cn(
                  'rounded-lg border p-3',
                  isCurrent
                    ? 'border-wb-brand/30 bg-wb-brand-soft/30'
                    : 'border-wb-line-1 bg-white',
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <LogSeverity level={entry.level} />
                  {isCurrent ? <Badge>当前事件</Badge> : null}
                  <span className="tabular text-[11px] text-wb-ink-6">
                    {dateTime(entry.timestamp)}
                  </span>
                </div>
                <p className="mt-2 text-xs font-medium text-wb-ink-2">
                  {entry.action}
                </p>
                <p className="mt-1 break-all font-mono text-[11px] text-wb-ink-6">
                  {entry.event_id}
                </p>
              </li>
            )
          })}
        </ol>
      </section>
    </div>
  )
}

export function AdminRuntimeLogsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedEventId = searchParams.get('event') || undefined

  function setParam(key: string, value?: string) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (value) next.set(key, value)
      else next.delete(key)
      if (key !== 'offset' && key !== 'event') next.delete('offset')
      return next
    })
  }

  const level = searchParams.get('level')
  const service = searchParams.get('service')
  const logs = useRuntimeLogs({
    level:
      level === 'info' || level === 'warning' || level === 'error'
        ? level
        : undefined,
    service: service === 'api' || service === 'worker' ? service : undefined,
    chain: searchParams.get('chain') || undefined,
    job_id: searchParams.get('job_id') || undefined,
    limit: LIMIT,
    offset: Number(searchParams.get('offset') ?? 0) || 0,
  })
  const detail = useRuntimeLogDetail(selectedEventId)
  const trace = useRuntimeLogTrace(selectedEventId)

  return (
    <div className="space-y-4">
      <header className="px-1">
        <h1 className="text-2xl font-semibold tracking-tight text-wb-ink-1">
          运行日志
        </h1>
        <p className="mt-1 text-xs text-wb-ink-6">
          查看代码中明确记录的业务链路；正常、业务问题和系统问题按日志级别区分。
        </p>
      </header>

      <Card className="grid gap-3 border-white/80 bg-white/82 p-3 sm:grid-cols-2 xl:grid-cols-4">
        <Select
          value={level ?? 'all'}
          onValueChange={(value) =>
            setParam('level', value === 'all' ? undefined : value)
          }
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="日志级别" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部级别</SelectItem>
            <SelectItem value="info">正常</SelectItem>
            <SelectItem value="warning">业务问题</SelectItem>
            <SelectItem value="error">系统问题</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={service ?? 'all'}
          onValueChange={(value) =>
            setParam('service', value === 'all' ? undefined : value)
          }
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="服务" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部服务</SelectItem>
            <SelectItem value="api">api</SelectItem>
            <SelectItem value="worker">worker</SelectItem>
          </SelectContent>
        </Select>
        <Input
          placeholder="链路名称"
          value={searchParams.get('chain') ?? ''}
          onChange={(event) => setParam('chain', event.target.value.trim())}
        />
        <Input
          placeholder="任务 ID"
          value={searchParams.get('job_id') ?? ''}
          onChange={(event) => setParam('job_id', event.target.value.trim())}
        />
      </Card>

      {logs.isLoading ? (
        <Skeleton className="h-[60vh] rounded-xl" />
      ) : logs.isError ? (
        <Card className="flex flex-col items-center gap-3 py-16 text-center text-sm text-wb-red">
          <p>运行日志加载失败</p>
          <Button
            type="button"
            variant="outline"
            onClick={() => void logs.refetch()}
          >
            重试
          </Button>
        </Card>
      ) : logs.data?.items.length ? (
        <Card className="gap-0 overflow-hidden bg-white/82 p-0">
          <div className="divide-y divide-wb-line-1">
            {logs.data.items.map((entry) => (
              <button
                key={entry.event_id}
                type="button"
                className="grid w-full gap-3 p-4 text-left outline-none transition-colors hover:bg-wb-surface-2 focus-visible:bg-wb-brand-soft/30 lg:grid-cols-[170px_180px_minmax(0,1fr)_180px]"
                onClick={() => setParam('event', entry.event_id)}
              >
                <div>
                  <LogSeverity level={entry.level} />
                  <p className="mt-2 tabular text-[11px] text-wb-ink-6">
                    {dateTime(entry.timestamp)}
                  </p>
                </div>
                <div className="min-w-0 text-xs">
                  <p className="font-medium text-wb-ink-3">{entry.service}</p>
                  <p className="mt-1 truncate text-wb-ink-6">{entry.chain}</p>
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-wb-ink-2">
                    {entry.action}
                  </p>
                  <p className="mt-1 break-all font-mono text-[11px] text-wb-ink-6">
                    {entry.logger}.{entry.function}
                  </p>
                </div>
                <div className="min-w-0 text-xs text-wb-ink-5">
                  <p className="truncate">{optionalValue(entry.model)}</p>
                  <p className="mt-1 truncate">{optionalValue(entry.status)}</p>
                  <p className="mt-1 tabular">
                    {entry.duration_ms === null ? '—' : `${entry.duration_ms} ms`}
                  </p>
                </div>
              </button>
            ))}
          </div>
          <AdminPagination
            total={logs.data.total}
            limit={logs.data.limit}
            offset={logs.data.offset}
            onOffsetChange={(offset) => setParam('offset', String(offset))}
          />
        </Card>
      ) : (
        <Card className="py-16 text-center text-sm text-wb-ink-6">
          当前筛选下没有运行日志
        </Card>
      )}

      <Dialog
        open={Boolean(selectedEventId)}
        onOpenChange={(open) => {
          if (!open) setParam('event')
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>日志详情</DialogTitle>
            <DialogDescription>
              完整提示词仅在管理员主动展开详情后显示。
            </DialogDescription>
          </DialogHeader>
          {detail.isLoading || trace.isLoading ? (
            <Skeleton className="h-96 rounded-xl" />
          ) : detail.isError || trace.isError ? (
            <div className="py-16 text-center text-sm text-wb-red">
              日志详情加载失败
            </div>
          ) : detail.data && trace.data && selectedEventId ? (
            <RuntimeLogDetailContent
              detail={detail.data}
              trace={trace.data}
              selectedEventId={selectedEventId}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  )
}
