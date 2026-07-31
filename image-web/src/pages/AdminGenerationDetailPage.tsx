import { ArrowLeftIcon } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { useAdminJob } from '@/api/admin'
import { ModerationDialog } from '@/components/admin/ModerationDialog'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { yuan } from '@/lib/format'

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

export function AdminGenerationDetailPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const job = useAdminJob(jobId)

  if (job.isLoading) {
    return <Skeleton className="h-[70vh] rounded-xl" />
  }
  if (job.isError || !job.data) {
    return (
      <Card className="py-16 text-center text-sm text-wb-red">
        任务详情加载失败或任务不存在。
      </Card>
    )
  }

  const data = job.data
  return (
    <div className="space-y-4">
      <Link
        to="/admin/generations"
        className="inline-flex items-center gap-1 text-xs text-wb-ink-5 hover:text-wb-brand-deep"
      >
        <ArrowLeftIcon className="size-3.5" />
        返回出图管理
      </Link>

      <Card className="gap-4 border-white/80 bg-white/82 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-mono text-xl font-semibold text-wb-ink-1">
                {data.job_id}
              </h1>
              <Badge variant="outline">{data.status}</Badge>
            </div>
            <p className="mt-1 text-sm text-wb-ink-5">
              {data.user_name} · {data.user_email}
            </p>
          </div>
          <p className="tabular text-sm font-medium">
            平台核算成本 {yuan(data.total_cost)}
          </p>
        </div>
        <div className="grid gap-2 text-xs text-wb-ink-6 sm:grid-cols-2 lg:grid-cols-4">
          <span>功能 {data.operation_type ?? '—'}</span>
          <span>模型 {data.model ?? '—'}</span>
          <span>
            尺寸 {data.size} · {data.ratio}
          </span>
          <span>
            结果 {data.successful_images}/{data.requested_images}
          </span>
          <span>创建 {dateTime(data.created_at)}</span>
          <span>
            完成 {data.completed_at ? dateTime(data.completed_at) : '—'}
          </span>
        </div>
        {data.prompt ? (
          <div className="rounded-xl bg-wb-surface-2 p-3">
            <p className="mb-1 text-xs font-medium text-wb-ink-4">
              用户提示词
            </p>
            <p className="whitespace-pre-wrap text-sm leading-6 text-wb-ink-2">
              {data.prompt}
            </p>
          </div>
        ) : null}
        {data.error ? (
          <p className="rounded-xl bg-wb-red-tint p-3 text-sm text-wb-red">
            {data.error}
          </p>
        ) : null}
      </Card>

      <section>
        <h2 className="mb-2 text-sm font-semibold text-wb-ink-2">
          结果图片（{data.images.length}）
        </h2>
        {data.images.length ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
            {data.images.map((image) => (
              <Card
                key={image.image_id}
                className="gap-3 border-white/80 bg-white/82 p-3"
              >
                <div className="relative overflow-hidden rounded-xl">
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
                </div>
                <div className="text-xs text-wb-ink-6">
                  <p>
                    {image.image_type ?? '结果图'} · {yuan(image.cost)}
                  </p>
                  <p className="mt-1">{dateTime(image.created_at)}</p>
                  {image.moderation_status === 'blocked' ? (
                    <p className="mt-2 text-wb-red">
                      {image.moderation_reason ?? '已屏蔽'}
                      {image.moderation_note
                        ? ` · ${image.moderation_note}`
                        : ''}
                    </p>
                  ) : null}
                </div>
                <ModerationDialog image={image} />
              </Card>
            ))}
          </div>
        ) : (
          <Card className="py-12 text-center text-sm text-wb-ink-6">
            该任务没有结果图片
          </Card>
        )}
      </section>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="gap-3 border-white/80 bg-white/82 p-4">
          <h2 className="text-sm font-semibold text-wb-ink-2">
            输入图片（{data.inputs.length}）
          </h2>
          {data.inputs.length ? (
            <div className="flex flex-wrap gap-3">
              {data.inputs.map((input) => (
                <div key={input.key} className="w-24">
                  <img
                    src={input.url}
                    alt=""
                    loading="lazy"
                    className="aspect-square w-full rounded-xl object-cover ring-1 ring-wb-line-1"
                  />
                  <p className="mt-1 truncate text-[11px] text-wb-ink-6">
                    {input.role ?? '输入图'}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-wb-ink-6">没有输入图记录</p>
          )}
        </Card>

        <Card className="gap-3 border-white/80 bg-white/82 p-4">
          <h2 className="text-sm font-semibold text-wb-ink-2">
            生成明细（{data.generation_items.length}）
          </h2>
          {data.generation_items.length ? (
            <div className="space-y-3">
              {data.generation_items.map((item) => (
                <div
                  key={item.item_id}
                  className="rounded-xl border border-wb-line-1 p-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-mono text-xs">{item.model}</p>
                    <Badge variant="outline">{item.status}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-wb-ink-6">
                    {item.operation_type} · {item.attempt_count} 次尝试
                  </p>
                  {item.final_prompt ? (
                    <p className="mt-2 line-clamp-4 whitespace-pre-wrap text-xs leading-5 text-wb-ink-4">
                      {item.final_prompt}
                    </p>
                  ) : null}
                  {item.error_detail ? (
                    <p className="mt-2 text-xs text-wb-red">
                      {item.error_code ?? 'error'} · {item.error_detail}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-wb-ink-6">没有生成明细</p>
          )}
        </Card>
      </div>
    </div>
  )
}
