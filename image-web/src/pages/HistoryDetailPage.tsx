import { Link, useParams, useNavigate } from 'react-router-dom'
import { ArrowLeftIcon, ArrowUpRightIcon, DownloadIcon, SquarePenIcon } from 'lucide-react'

import { useListingJob } from '@/api/listing'
import { JobStatusBadge } from '@/components/listing/JobStatusBadge'
import { RecipeDrawer } from '@/components/listing/RecipeDrawer'
import { Skeleton } from '@/components/ui/skeleton'
import { downloadImage } from '@/lib/download'
import {
  IMAGE_SUCCESS_STATUS, IMAGE_TYPE_FIELDS, editModeLabel, fmtListingTime,
  type ListingJobImage,
} from '@/lib/listing'

export function HistoryDetailPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const q = useListingJob(jobId)
  const d = q.data

  return (
    <div className="space-y-5">
      <button
        onClick={() => navigate('/history')}
        className="flex items-center gap-1.5 text-[13px] text-wb-ink-4 transition-colors hover:text-wb-brand-deep"
      >
        <ArrowLeftIcon className="size-4" /> 返回历史
      </button>

      {q.isLoading ? (
        <Skeleton className="h-40 rounded-2xl" />
      ) : q.isError || !d ? (
        <div className="rounded-2xl border border-white/70 bg-white shadow-[0_6px_24px_-10px_rgba(40,40,90,.12)] p-10 text-center text-sm text-wb-ink-6">
          任务不存在或无权查看。
        </div>
      ) : (
        <>
          <div className="rounded-2xl border border-white/70 bg-white shadow-[0_6px_24px_-10px_rgba(40,40,90,.12)] p-5">
            <div className="mb-3 flex items-center gap-3">
              <h2 className="text-lg font-semibold text-wb-ink-1">
                {d.platform ? `${d.platform} · ${d.ratio}` : d.ratio}
              </h2>
              <JobStatusBadge status={d.status} />
              {d.clone_mode && (
                <span className="rounded-md border border-wb-amber-line bg-wb-amber-tint px-2 py-0.5 text-[12px] font-medium text-wb-amber">
                  复刻 · {d.clone_mode}
                </span>
              )}
              {d.edit_mode && (
                <span className="rounded-md border border-wb-tint-line bg-wb-tint-2 px-2 py-0.5 text-[12px] font-medium text-wb-brand-deep">
                  ✎ {editModeLabel(d.edit_mode)}
                </span>
              )}
              <div className="ml-auto">
                <RecipeDrawer detail={d} />
              </div>
            </div>
            <p className="mb-3 whitespace-pre-wrap text-[14px] leading-relaxed text-wb-ink-2">{d.prompt}</p>
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-[12.5px] text-wb-ink-6">
              <span>尺寸 {d.size}</span>
              <span>张数 {d.n}</span>
              <span className="font-mono">模型 {d.model_id ?? '未记录'}</span>
              <span>{fmtListingTime(d.created_at)}</span>
              {Object.entries(d.modifiers).map(([k, v]) => (
                <span key={k}>{v}</span>
              ))}
            </div>
            {d.parent_job_id && (
              <div className="mt-3 flex items-center gap-3 rounded-xl border border-wb-line-1 bg-wb-surface-1 p-2.5">
                {d.source_image_url && (
                  <img
                    src={d.source_image_url}
                    alt=""
                    loading="lazy"
                    onError={(e) => {
                      e.currentTarget.style.display = 'none'
                    }}
                    className="size-14 rounded-[10px] border border-wb-line-1 object-cover"
                  />
                )}
                <div className="flex flex-col gap-1">
                  <span className="text-[12.5px] text-wb-ink-4">
                    改自这张
                    {d.source_image_type && (
                      <span className="ml-1.5 text-[11.5px] text-wb-ink-7">
                        {IMAGE_TYPE_FIELDS.find((f) => f.key === d.source_image_type)?.label ??
                          d.source_image_type}
                      </span>
                    )}
                  </span>
                  <Link
                    to={`/history/${d.parent_job_id}`}
                    className="flex w-fit items-center gap-0.5 text-[12px] text-wb-brand-deep hover:underline"
                  >
                    查看来源任务 <ArrowUpRightIcon className="size-3.5" />
                  </Link>
                </div>
              </div>
            )}
            {d.error && (
              <p className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-[12.5px] text-rose-700">{d.error}</p>
            )}
          </div>

          {d.images.length > 0 &&
            (d.images.some((img) => img.image_type) ? (
              // 套图：按图型分组段（顺序按 IMAGE_TYPE_FIELDS；无标签旧图兜底归「其他」）
              <div className="space-y-5">
                {[
                  ...IMAGE_TYPE_FIELDS.map((f) => ({
                    label: `${f.label}`,
                    prefix: f.key,
                    images: d.images.filter((img) => img.image_type === f.key),
                  })),
                  {
                    label: '其他',
                    prefix: 'listing',
                    images: d.images.filter(
                      (img) => !img.image_type || !IMAGE_TYPE_FIELDS.some((f) => f.key === img.image_type),
                    ),
                  },
                ]
                  .filter((g) => g.images.length > 0)
                  .map((g) => (
                    <div key={g.label}>
                      <h3 className="mb-2.5 text-[14px] font-bold text-wb-ink-1">
                        {g.label}
                        <span className="ml-1.5 text-[12px] font-normal text-wb-ink-6">{g.images.length}</span>
                      </h3>
                      <ImageGrid images={g.images} namePrefix={g.prefix} jobId={d.job_id} />
                    </div>
                  ))}
              </div>
            ) : (
              <div>
                <h3 className="mb-2.5 text-[14px] font-bold text-wb-ink-1">候选图（{d.images.length}）</h3>
                <ImageGrid images={d.images} namePrefix={d.platform ?? 'listing'} jobId={d.job_id} />
              </div>
            ))}

          {d.input_urls.length > 0 && (
            <div>
              <h3 className="mb-2.5 text-[14px] font-bold text-wb-ink-1">
                {d.clone_mode ? '输入图（产品 / 参考）' : '输入产品图'}
              </h3>
              <div className="flex flex-wrap gap-3">
                {d.input_urls.map((u, i) => {
                  const role = d.input_roles?.[i]
                  const roleLabel = role === 'product' ? '产品图' : role === 'reference' ? '参考图' : null
                  return (
                    <div key={i} className="flex flex-col items-center gap-1">
                      <img
                        src={u}
                        alt=""
                        loading="lazy"
                        onError={(e) => {
                          e.currentTarget.style.display = 'none'
                        }}
                        className="size-20 rounded-xl border border-wb-line-1 object-cover"
                      />
                      {roleLabel && <span className="text-[11px] text-wb-ink-7">{roleLabel}</span>}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function ImageGrid({
  images, namePrefix, jobId,
}: { images: ListingJobImage[]; namePrefix: string; jobId: string }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(208px,1fr))] gap-4">
      {images.map((img, i) => (
        <div
          key={i}
          className="group relative aspect-square overflow-hidden rounded-2xl border border-white/70 bg-white shadow-[0_6px_24px_-10px_rgba(40,40,90,.12)] transition-[box-shadow,transform] hover:-translate-y-0.5 hover:shadow-[0_14px_32px_-12px_rgba(40,40,90,.22)]"
        >
          {img.available && img.url ? (
            <>
              <img
                src={img.url}
                alt=""
                loading="lazy"
                className="size-full object-cover"
              />
              {img.status === IMAGE_SUCCESS_STATUS ? (
                <Link
                  to={`/edit/${jobId}/${img.image_key}`}
                  className="absolute bottom-2.5 left-2.5 rounded-[10px] bg-wb-ink-2/90 px-3 py-1.5 text-[12.5px] text-white opacity-0 transition-opacity group-hover:opacity-100"
                >
                  <SquarePenIcon className="mr-1 inline size-3.5" />{' '}
                  基于此图再编辑
                </Link>
              ) : null}
              <button
                type="button"
                onClick={() => {
                  if (img.url) {
                    void downloadImage(
                      img.url,
                      `${namePrefix}-${i + 1}.png`,
                    )
                  }
                }}
                className="absolute bottom-2.5 right-2.5 rounded-[10px] bg-wb-ink-2/90 px-3 py-1.5 text-[12.5px] text-white opacity-0 transition-opacity group-hover:opacity-100"
              >
                <DownloadIcon className="mr-1 inline size-3.5" /> 下载
              </button>
            </>
          ) : (
            <div className="grid size-full place-items-center bg-wb-surface-3 p-4 text-center text-[12.5px] text-wb-ink-6">
              {img.status === IMAGE_SUCCESS_STATUS
                ? '该图片暂不可用'
                : '生成失败'}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
