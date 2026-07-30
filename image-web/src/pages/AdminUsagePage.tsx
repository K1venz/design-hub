import { useMemo, useState } from 'react'
import {
  BotIcon,
  CircleAlertIcon,
  RefreshCcwIcon,
  SparklesIcon,
} from 'lucide-react'
import { useSearchParams } from 'react-router-dom'

import {
  useAdminModelCalls,
  useModelCallSummary,
  type ModelCallFilters,
} from '@/api/admin'
import { AdminMetricCard } from '@/components/admin/AdminMetricCard'
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { adminDateRange } from '@/lib/admin'
import { yuan } from '@/lib/format'

const LIMIT = 20
const number = new Intl.NumberFormat('zh-CN')

function dateTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

export function AdminUsagePage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [anchor] = useState(() => new Date())
  const daysParam = Number(searchParams.get('days') ?? 7)
  const days = daysParam === 1 || daysParam === 30 ? daysParam : 7
  const range = useMemo(
    () => adminDateRange(days, anchor),
    [anchor, days],
  )

  function setParam(key: string, value?: string) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (value) next.set(key, value)
      else next.delete(key)
      if (key !== 'offset') next.delete('offset')
      return next
    })
  }

  const filters: ModelCallFilters = {
    ...range,
    provider: searchParams.get('provider') || undefined,
    model: searchParams.get('model') || undefined,
    modality: searchParams.get('modality') || undefined,
    status: searchParams.get('status') || undefined,
  }
  const summary = useModelCallSummary(filters)
  const calls = useAdminModelCalls({
    ...filters,
    limit: LIMIT,
    offset: Number(searchParams.get('offset') ?? 0) || 0,
  })

  const image = (summary.data?.models ?? []).filter(
    (item) => item.modality === 'image',
  )
  const chat = (summary.data?.models ?? []).filter(
    (item) => item.modality === 'chat',
  )
  const imageCalls = image.reduce((sum, item) => sum + item.calls, 0)
  const imageRetries = image.reduce(
    (sum, item) => sum + item.retries,
    0,
  )
  const imageFailures = image.reduce(
    (sum, item) => sum + item.failed + item.uncertain,
    0,
  )
  const chatCalls = chat.reduce((sum, item) => sum + item.calls, 0)
  const chatTokens = chat.reduce(
    (sum, item) => sum + item.total_tokens,
    0,
  )

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3 px-1">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-wb-ink-1">
            API 用量
          </h1>
          <p className="mt-1 text-xs text-wb-ink-6">
            GPT Image 2 以实际上游调用次数为主；豆包展示实际返回的
            Token。
          </p>
        </div>
        <Select
          value={String(days)}
          onValueChange={(value) => setParam('days', value)}
        >
          <SelectTrigger className="glass-lite h-9 bg-white/75 px-3">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="1">最近 24 小时</SelectItem>
            <SelectItem value="7">最近 7 天</SelectItem>
            <SelectItem value="30">最近 30 天</SelectItem>
          </SelectContent>
        </Select>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <AdminMetricCard
          label="GPT Image 2 调用"
          value={number.format(imageCalls)}
          detail="每次实际 POST 与重试均计数"
          icon={SparklesIcon}
        />
        <AdminMetricCard
          label="GPT Image 重试"
          value={number.format(imageRetries)}
          icon={RefreshCcwIcon}
          tone="warning"
        />
        <AdminMetricCard
          label="失败 / 结果不确定"
          value={number.format(imageFailures)}
          icon={CircleAlertIcon}
          tone={imageFailures > 0 ? 'danger' : 'success'}
        />
        <AdminMetricCard
          label="豆包调用 / 总 Token"
          value={`${number.format(chatCalls)} / ${number.format(chatTokens)}`}
          icon={BotIcon}
        />
      </div>

      <Card className="grid gap-3 border-white/80 bg-white/82 p-3 sm:grid-cols-2 xl:grid-cols-4">
        <Input
          placeholder="供应商"
          value={searchParams.get('provider') ?? ''}
          onChange={(event) =>
            setParam('provider', event.target.value.trim())
          }
        />
        <Input
          placeholder="模型"
          value={searchParams.get('model') ?? ''}
          onChange={(event) =>
            setParam('model', event.target.value.trim())
          }
        />
        <Select
          value={searchParams.get('modality') ?? 'all'}
          onValueChange={(value) =>
            setParam('modality', value === 'all' ? undefined : value)
          }
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="调用类别" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部类别</SelectItem>
            <SelectItem value="image">图片</SelectItem>
            <SelectItem value="chat">Chat</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={searchParams.get('status') ?? 'all'}
          onValueChange={(value) =>
            setParam('status', value === 'all' ? undefined : value)
          }
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="调用状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="succeeded">成功</SelectItem>
            <SelectItem value="failed">失败</SelectItem>
            <SelectItem value="uncertain">结果不确定</SelectItem>
            <SelectItem value="interrupted">中断</SelectItem>
          </SelectContent>
        </Select>
      </Card>

      <Card className="gap-0 bg-white/82 p-0">
        <div className="px-4 py-3">
          <h2 className="font-semibold text-wb-ink-2">按模型汇总</h2>
        </div>
        {summary.isLoading ? (
          <div className="p-4">
            <Skeleton className="h-40 rounded-xl" />
          </div>
        ) : summary.isError ? (
          <p className="border-t border-wb-line-1 py-12 text-center text-sm text-wb-red">
            用量汇总加载失败
          </p>
        ) : summary.data?.models.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>供应商 / 模型</TableHead>
                <TableHead>类别</TableHead>
                <TableHead>调用</TableHead>
                <TableHead>成功</TableHead>
                <TableHead>失败</TableHead>
                <TableHead>重试</TableHead>
                <TableHead>总 Token</TableHead>
                <TableHead className="text-right">平台成本</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {summary.data.models.map((item) => (
                <TableRow
                  key={`${item.provider}-${item.model}-${item.operation_type ?? 'all'}`}
                >
                  <TableCell>
                    <p className="font-medium">{item.provider}</p>
                    <p className="font-mono text-xs text-wb-ink-6">
                      {item.model}
                    </p>
                  </TableCell>
                  <TableCell>{item.modality}</TableCell>
                  <TableCell className="tabular font-semibold">
                    {number.format(item.calls)}
                  </TableCell>
                  <TableCell className="tabular">
                    {number.format(item.succeeded)}
                  </TableCell>
                  <TableCell className="tabular">
                    {number.format(item.failed + item.uncertain)}
                  </TableCell>
                  <TableCell className="tabular">
                    {number.format(item.retries)}
                  </TableCell>
                  <TableCell className="tabular">
                    {item.modality === 'chat'
                      ? number.format(item.total_tokens)
                      : '—'}
                  </TableCell>
                  <TableCell className="text-right">
                    {yuan(item.platform_cost)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="border-t border-wb-line-1 py-12 text-center text-sm text-wb-ink-6">
            当前区间没有模型调用
          </p>
        )}
      </Card>

      <Card className="gap-0 bg-white/82 p-0">
        <div className="px-4 py-3">
          <h2 className="font-semibold text-wb-ink-2">调用明细</h2>
        </div>
        {calls.isLoading ? (
          <div className="p-4">
            <Skeleton className="h-64 rounded-xl" />
          </div>
        ) : calls.isError ? (
          <p className="border-t border-wb-line-1 py-12 text-center text-sm text-wb-red">
            调用明细加载失败
          </p>
        ) : calls.data?.items.length ? (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>时间</TableHead>
                  <TableHead>用户</TableHead>
                  <TableHead>模型</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead>尝试</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>Token</TableHead>
                  <TableHead className="text-right">耗时</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {calls.data.items.map((call) => (
                  <TableRow key={call.call_id}>
                    <TableCell className="tabular text-xs text-wb-ink-6">
                      {dateTime(call.started_at)}
                    </TableCell>
                    <TableCell className="max-w-44 truncate text-xs">
                      {call.user_email}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {call.model}
                    </TableCell>
                    <TableCell className="text-xs">
                      {call.operation_type}
                    </TableCell>
                    <TableCell className="tabular">
                      {call.attempt_no}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          call.status === 'failed'
                            ? 'destructive'
                            : 'outline'
                        }
                      >
                        {call.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="tabular">
                      {call.total_tokens === null
                        ? '—'
                        : number.format(call.total_tokens)}
                    </TableCell>
                    <TableCell className="tabular text-right">
                      {call.latency_ms === null
                        ? '—'
                        : `${(call.latency_ms / 1000).toFixed(2)}s`}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <AdminPagination
              total={calls.data.total}
              limit={calls.data.limit}
              offset={calls.data.offset}
              onOffsetChange={(offset) =>
                setParam('offset', String(offset))
              }
            />
          </>
        ) : (
          <p className="border-t border-wb-line-1 py-12 text-center text-sm text-wb-ink-6">
            当前筛选下没有调用明细
          </p>
        )}
      </Card>
    </div>
  )
}
