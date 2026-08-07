import { Grid2X2Icon, ListIcon } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

import {
  useAdminImages,
  useAdminJobs,
  type AdminImageFilters,
  type AdminJobFilters,
} from '@/api/admin'
import { AdminPagination } from '@/components/admin/AdminPagination'
import { ModerationDialog } from '@/components/admin/ModerationDialog'
import { ShowcaseDialog } from '@/components/admin/ShowcaseDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import { yuan } from '@/lib/format'

const LIMIT = 20

function numberParam(value: string | null): number | undefined {
  if (!value) return undefined
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined
}

function operationLabel(value: string | null): string {
  switch (value) {
    case 'image_generation':
      return '商品出图'
    case 'image_edit':
      return '二次编辑'
    case 'replace_background':
      return '换背景'
    default:
      return value ?? '—'
  }
}

function dateTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(value))
}

export function AdminGenerationsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const view = searchParams.get('view') === 'jobs' ? 'jobs' : 'images'
  const moderationStatus = searchParams.get('moderation_status')
  const showcaseStatus = searchParams.get('showcase_status')

  function setParam(key: string, value?: string) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      if (value) next.set(key, value)
      else next.delete(key)
      if (key !== 'offset') next.delete('offset')
      return next
    })
  }

  const common = {
    user_id: numberParam(searchParams.get('user_id')),
    model: searchParams.get('model') || undefined,
    operation_type:
      searchParams.get('operation_type') || undefined,
    status: searchParams.get('status') || undefined,
    limit: LIMIT,
    offset: Number(searchParams.get('offset') ?? 0) || 0,
  }

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3 px-1">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-wb-ink-1">
            出图管理
          </h1>
          <p className="mt-1 text-xs text-wb-ink-6">
            图片审核仅在管理后台显示；普通用户不会看到审核原因。
          </p>
        </div>
        <div className="flex rounded-xl bg-white/75 p-1 ring-1 ring-wb-line-1">
          <Button
            type="button"
            size="sm"
            variant={view === 'images' ? 'default' : 'ghost'}
            onClick={() => setParam('view', 'images')}
          >
            <Grid2X2Icon className="size-3.5" />
            图片审核
          </Button>
          <Button
            type="button"
            size="sm"
            variant={view === 'jobs' ? 'default' : 'ghost'}
            onClick={() => setParam('view', 'jobs')}
          >
            <ListIcon className="size-3.5" />
            任务列表
          </Button>
        </div>
      </header>

      <Card className="grid gap-3 border-white/80 bg-white/82 p-3 sm:grid-cols-2 xl:grid-cols-6">
        <Input
          inputMode="numeric"
          aria-label="按用户 ID 筛选"
          placeholder="用户 ID"
          value={searchParams.get('user_id') ?? ''}
          onChange={(event) =>
            setParam('user_id', event.target.value.trim())
          }
        />
        <Input
          aria-label="按模型筛选"
          placeholder="模型，如 gpt-image-2"
          value={searchParams.get('model') ?? ''}
          onChange={(event) =>
            setParam('model', event.target.value.trim())
          }
        />
        <Select
          value={searchParams.get('operation_type') ?? 'all'}
          onValueChange={(value) =>
            setParam(
              'operation_type',
              value === 'all' ? undefined : value,
            )
          }
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="功能类型" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部功能</SelectItem>
            <SelectItem value="image_generation">商品出图</SelectItem>
            <SelectItem value="image_edit">二次编辑</SelectItem>
            <SelectItem value="replace_background">换背景</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={searchParams.get('status') ?? 'all'}
          onValueChange={(value) =>
            setParam('status', value === 'all' ? undefined : value)
          }
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="生成状态" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部状态</SelectItem>
            <SelectItem value="成功">成功</SelectItem>
            <SelectItem value="失败">失败</SelectItem>
            <SelectItem value="完成">完成</SelectItem>
            <SelectItem value="部分完成">部分完成</SelectItem>
          </SelectContent>
        </Select>
        {view === 'images' ? (
          <>
            <Select
              value={searchParams.get('moderation_status') ?? 'all'}
              onValueChange={(value) =>
                setParam(
                  'moderation_status',
                  value === 'all' ? undefined : value,
                )
              }
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="审核状态" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部审核状态</SelectItem>
                <SelectItem value="normal">正常</SelectItem>
                <SelectItem value="blocked">已屏蔽</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={searchParams.get('showcase_status') ?? 'all'}
              onValueChange={(value) =>
                setParam(
                  'showcase_status',
                  value === 'all' ? undefined : value,
                )
              }
            >
              <SelectTrigger
                className="w-full"
                aria-label="全部展示状态：公开展示或未展示"
              >
                <SelectValue placeholder="展示状态" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部展示状态</SelectItem>
                <SelectItem value="public">公开展示</SelectItem>
                <SelectItem value="private">未展示</SelectItem>
              </SelectContent>
            </Select>
          </>
        ) : (
          <Button
            type="button"
            variant="outline"
            onClick={() => setSearchParams({ view: 'jobs' })}
          >
            清空筛选
          </Button>
        )}
      </Card>

      {view === 'images' ? (
        <ImageReview
          filters={{
            ...common,
            moderation_status:
              moderationStatus === 'normal' ||
              moderationStatus === 'blocked'
                ? moderationStatus
                : undefined,
            showcase_status:
              showcaseStatus === 'public' || showcaseStatus === 'private'
                ? showcaseStatus
                : undefined,
          }}
          onOffsetChange={(offset) =>
            setParam('offset', String(offset))
          }
        />
      ) : (
        <JobReview
          filters={common}
          onOffsetChange={(offset) =>
            setParam('offset', String(offset))
          }
        />
      )}
    </div>
  )
}

function ImageReview({
  filters,
  onOffsetChange,
}: {
  filters: AdminImageFilters
  onOffsetChange: (offset: number) => void
}) {
  const images = useAdminImages(filters)
  if (images.isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {Array.from({ length: 8 }, (_, index) => (
          <Skeleton key={index} className="aspect-[4/5] rounded-xl" />
        ))}
      </div>
    )
  }
  if (images.isError) {
    return (
      <Card className="py-16 text-center text-sm text-wb-red">
        图片列表加载失败，请稍后重试。
      </Card>
    )
  }
  if (!images.data?.items.length) {
    return (
      <Card className="py-16 text-center text-sm text-wb-ink-6">
        当前筛选下没有图片
      </Card>
    )
  }
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        {images.data.items.map((image) => (
          <Card
            key={image.image_id}
            className="gap-3 border-white/80 bg-white/82 p-3"
          >
            <Link
              to={`/admin/generations/${image.job_id}`}
              className="relative block overflow-hidden rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-wb-brand-soft"
            >
              <img
                src={image.url}
                alt=""
                loading="lazy"
                className="aspect-square w-full bg-wb-surface-4 object-cover"
              />
              <Badge
                variant={
                  image.moderation_status === 'blocked'
                    ? 'destructive'
                    : 'secondary'
                }
                className="absolute left-2 top-2"
              >
                {image.moderation_status === 'blocked'
                  ? '已屏蔽'
                  : '正常'}
              </Badge>
              {image.is_public_showcase ? (
                <div className="absolute right-2 top-2 flex gap-1">
                  <Badge className="bg-wb-brand text-white">展示中</Badge>
                  {image.showcase_download_allowed ? (
                    <Badge variant="secondary">允许下载</Badge>
                  ) : null}
                </div>
              ) : null}
            </Link>
            <div className="min-w-0">
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-sm font-medium text-wb-ink-2">
                  {image.user_name}
                </p>
                <span className="text-xs text-wb-ink-6">
                  {yuan(image.cost)}
                </span>
              </div>
              <p className="mt-1 truncate text-xs text-wb-ink-6">
                {operationLabel(image.operation_type)} ·{' '}
                {image.model ?? '—'}
              </p>
              <p className="mt-1 text-[11px] text-wb-ink-7">
                {dateTime(image.created_at)}
              </p>
              <p className="mt-2 line-clamp-3 whitespace-pre-wrap text-xs leading-5 text-wb-ink-4">
                {image.prompt || '无用户提示词'}
              </p>
              {image.moderation_status === 'blocked' ? (
                <p className="mt-2 line-clamp-2 text-xs text-wb-red">
                  {image.moderation_reason ?? '已屏蔽'}
                  {image.moderation_note
                    ? ` · ${image.moderation_note}`
                    : ''}
                </p>
              ) : null}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <ShowcaseDialog image={image} />
              <ModerationDialog image={image} />
            </div>
          </Card>
        ))}
      </div>
      <Card className="mt-4 gap-0 bg-white/82 p-0">
        <AdminPagination
          total={images.data.total}
          limit={images.data.limit}
          offset={images.data.offset}
          onOffsetChange={onOffsetChange}
        />
      </Card>
    </>
  )
}

function JobReview({
  filters,
  onOffsetChange,
}: {
  filters: AdminJobFilters
  onOffsetChange: (offset: number) => void
}) {
  const jobs = useAdminJobs(filters)
  if (jobs.isLoading) {
    return <Skeleton className="h-96 rounded-xl" />
  }
  if (jobs.isError) {
    return (
      <Card className="py-16 text-center text-sm text-wb-red">
        任务列表加载失败，请稍后重试。
      </Card>
    )
  }
  if (!jobs.data?.items.length) {
    return (
      <Card className="py-16 text-center text-sm text-wb-ink-6">
        当前筛选下没有任务
      </Card>
    )
  }
  return (
    <Card className="gap-0 bg-white/82 p-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>创建时间</TableHead>
            <TableHead>用户</TableHead>
            <TableHead>功能</TableHead>
            <TableHead>模型</TableHead>
            <TableHead>状态</TableHead>
            <TableHead>结果</TableHead>
            <TableHead className="text-right">成本</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobs.data.items.map((job) => (
            <TableRow key={job.job_id}>
              <TableCell className="tabular text-xs text-wb-ink-6">
                {dateTime(job.created_at)}
              </TableCell>
              <TableCell>
                <p className="text-sm font-medium">{job.user_name}</p>
                <p className="text-xs text-wb-ink-6">{job.user_email}</p>
              </TableCell>
              <TableCell>{operationLabel(job.operation_type)}</TableCell>
              <TableCell className="font-mono text-xs">
                {job.model ?? '—'}
              </TableCell>
              <TableCell>
                <Badge variant="outline">{job.status}</Badge>
              </TableCell>
              <TableCell className="tabular">
                {job.successful_images}/{job.requested_images}
              </TableCell>
              <TableCell className="text-right">
                <Link
                  to={`/admin/generations/${job.job_id}`}
                  className="font-medium text-wb-brand hover:underline"
                >
                  {yuan(job.total_cost)}
                </Link>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <AdminPagination
        total={jobs.data.total}
        limit={jobs.data.limit}
        offset={jobs.data.offset}
        onOffsetChange={onOffsetChange}
      />
    </Card>
  )
}
