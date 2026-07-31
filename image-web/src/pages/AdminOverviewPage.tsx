import { useMemo, useState } from 'react'
import {
  ActivityIcon,
  BotIcon,
  CircleAlertIcon,
  CoinsIcon,
  ImageIcon,
  ImagesIcon,
  RefreshCcwIcon,
  UsersRoundIcon,
} from 'lucide-react'
import { Link } from 'react-router-dom'

import {
  useAdminImages,
  useAdminModelCalls,
  useAdminOverview,
} from '@/api/admin'
import { AdminMetricCard } from '@/components/admin/AdminMetricCard'
import { Card } from '@/components/ui/card'
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
import { percent, yuan } from '@/lib/format'

const number = new Intl.NumberFormat('zh-CN')

function dateTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

export function AdminOverviewPage() {
  const [days, setDays] = useState(7)
  const [anchor] = useState(() => new Date())
  const range = useMemo(
    () => adminDateRange(days, anchor),
    [anchor, days],
  )
  const overview = useAdminOverview(range)
  const failedCalls = useAdminModelCalls({
    ...range,
    status: 'failed',
    limit: 5,
    offset: 0,
  })
  const blockedImages = useAdminImages({
    ...range,
    moderation_status: 'blocked',
    limit: 4,
    offset: 0,
  })

  if (overview.isLoading) {
    return (
      <div
        aria-label="正在加载管理数据"
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
      >
        <span className="sr-only">正在加载管理数据</span>
        {Array.from({ length: 8 }, (_, index) => (
          <Skeleton key={index} className="h-32 rounded-xl" />
        ))}
      </div>
    )
  }

  if (overview.isError) {
    return (
      <Card className="mt-4 items-center py-16 text-center">
        <CircleAlertIcon className="size-8 text-wb-red" />
        <div>
          <h1 className="text-lg font-semibold">管理数据加载失败</h1>
          <p className="mt-1 text-sm text-wb-ink-6">请稍后刷新页面重试。</p>
        </div>
      </Card>
    )
  }

  if (!overview.data) {
    return (
      <Card className="mt-4 items-center py-16 text-center">
        <p className="text-sm text-wb-ink-6">暂无管理数据</p>
      </Card>
    )
  }

  const data = overview.data
  const callsWithOutcome =
    data.image_succeeded + data.image_failed + data.image_uncertain
  const succeededWidth =
    callsWithOutcome > 0
      ? (data.image_succeeded / callsWithOutcome) * 100
      : 0
  const failedWidth =
    callsWithOutcome > 0 ? (data.image_failed / callsWithOutcome) * 100 : 0

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3 px-1 py-1">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-wb-ink-1">
            管理后台
          </h1>
          <p className="mt-1 text-xs text-wb-ink-6">
            调用统计自本版本上线后开始记录，不含历史反推数据。
          </p>
        </div>
        <Select
          value={String(days)}
          onValueChange={(value) => setDays(Number(value))}
        >
          <SelectTrigger
            aria-label="统计时间范围"
            className="glass-lite h-9 bg-white/75 px-3"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="1">最近 24 小时</SelectItem>
            <SelectItem value="7">最近 7 天</SelectItem>
            <SelectItem value="30">最近 30 天</SelectItem>
          </SelectContent>
        </Select>
      </header>

      <section
        aria-label="核心指标"
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 2xl:grid-cols-8"
      >
        <AdminMetricCard
          label="注册用户"
          value={number.format(data.registered_users)}
          icon={UsersRoundIcon}
        />
        <AdminMetricCard
          label="活跃用户"
          value={number.format(data.active_users)}
          icon={ActivityIcon}
        />
        <AdminMetricCard
          label="出图任务"
          value={number.format(data.jobs)}
          icon={ImagesIcon}
        />
        <AdminMetricCard
          label="成功图片"
          value={number.format(data.successful_images)}
          icon={ImageIcon}
          tone="success"
        />
        <AdminMetricCard
          label="GPT Image 2 调用"
          value={number.format(data.image_calls)}
          detail={`${data.image_retries} 次重试`}
          icon={RefreshCcwIcon}
        />
        <AdminMetricCard
          label="豆包总 Token"
          value={number.format(data.chat_total_tokens)}
          detail={`${number.format(data.chat_calls)} 次调用`}
          icon={BotIcon}
        />
        <AdminMetricCard
          label="平台核算成本"
          value={yuan(data.platform_cost)}
          detail="按平台配置单价核算"
          icon={CoinsIcon}
          tone="warning"
        />
        <AdminMetricCard
          label="失败率"
          value={percent(data.failure_rate, 1)}
          icon={CircleAlertIcon}
          tone={data.failure_rate > 0.05 ? 'danger' : 'success'}
        />
      </section>

      <Card className="gap-3 border-white/80 bg-white/82 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="font-semibold text-wb-ink-2">GPT Image 调用状态</h2>
            <p className="mt-0.5 text-xs text-wb-ink-6">
              调用次数包含实际发往上游的重试，不含轮询和结果下载。
            </p>
          </div>
          <p className="tabular text-xs text-wb-ink-6">
            平均耗时{' '}
            {data.average_latency_ms === null
              ? '—'
              : `${(data.average_latency_ms / 1000).toFixed(2)}s`}
          </p>
        </div>
        <div
          className="flex h-2 overflow-hidden rounded-full bg-wb-surface-5"
          aria-label="GPT Image 调用结果分布"
        >
          <span
            className="bg-emerald-500"
            style={{ width: `${succeededWidth}%` }}
          />
          <span
            className="bg-wb-red"
            style={{ width: `${failedWidth}%` }}
          />
          <span className="min-w-0 flex-1 bg-wb-amber" />
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-wb-ink-5">
          <span>成功 {number.format(data.image_succeeded)}</span>
          <span>失败 {number.format(data.image_failed)}</span>
          <span>结果不确定 {number.format(data.image_uncertain)}</span>
          <span>重试 {number.format(data.image_retries)}</span>
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(440px,.9fr)]">
        <Card className="gap-0 border-white/80 bg-white/82 p-0">
          <div className="flex items-center justify-between px-4 py-3">
            <h2 className="font-semibold text-wb-ink-2">最近失败调用</h2>
            <Link
              to="/admin/usage"
              className="text-xs font-medium text-wb-brand hover:text-wb-brand-deep"
            >
              查看全部
            </Link>
          </div>
          {failedCalls.data?.items.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>时间</TableHead>
                  <TableHead>用户</TableHead>
                  <TableHead>模型</TableHead>
                  <TableHead>类型</TableHead>
                  <TableHead className="text-right">耗时</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {failedCalls.data.items.map((call) => (
                  <TableRow key={call.call_id}>
                    <TableCell className="tabular text-xs text-wb-ink-6">
                      {dateTime(call.started_at)}
                    </TableCell>
                    <TableCell className="max-w-36 truncate text-xs">
                      {call.user_email}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {call.model}
                    </TableCell>
                    <TableCell className="text-xs text-wb-ink-5">
                      {call.operation_type}
                    </TableCell>
                    <TableCell className="tabular text-right text-xs">
                      {call.latency_ms === null
                        ? '—'
                        : `${(call.latency_ms / 1000).toFixed(2)}s`}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="border-t border-wb-line-1 px-4 py-12 text-center text-sm text-wb-ink-6">
              当前区间没有失败调用
            </div>
          )}
        </Card>

        <Card className="gap-0 border-white/80 bg-white/82 p-0">
          <div className="flex items-center justify-between px-4 py-3">
            <h2 className="font-semibold text-wb-ink-2">最近屏蔽图片</h2>
            <Link
              to="/admin/generations?moderation_status=blocked"
              className="text-xs font-medium text-wb-brand hover:text-wb-brand-deep"
            >
              前往复核
            </Link>
          </div>
          {blockedImages.data?.items.length ? (
            <div className="grid grid-cols-2 gap-3 border-t border-wb-line-1 p-4 sm:grid-cols-4 xl:grid-cols-2 2xl:grid-cols-4">
              {blockedImages.data.items.map((image) => (
                <Link
                  key={image.image_id}
                  to={`/admin/generations/${image.job_id}`}
                  className="group min-w-0 outline-none"
                >
                  <img
                    src={image.url}
                    alt=""
                    loading="lazy"
                    className="aspect-square w-full rounded-xl bg-wb-surface-4 object-cover ring-1 ring-wb-line-1 transition-transform group-hover:-translate-y-0.5"
                  />
                  <p className="mt-2 truncate text-xs font-medium text-wb-ink-3">
                    {image.user_name}
                  </p>
                  <p className="mt-0.5 truncate text-[11px] text-wb-ink-6">
                    {image.moderation_reason ?? '待复核'} ·{' '}
                    {dateTime(image.created_at)}
                  </p>
                </Link>
              ))}
            </div>
          ) : (
            <div className="border-t border-wb-line-1 px-4 py-12 text-center text-sm text-wb-ink-6">
              当前区间没有屏蔽图片
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
