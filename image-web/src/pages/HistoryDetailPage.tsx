import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeftIcon, DownloadIcon } from 'lucide-react'

import { useListingJob } from '@/api/listing'
import { JobStatusBadge } from '@/components/listing/JobStatusBadge'
import { Skeleton } from '@/components/ui/skeleton'
import { downloadImage } from '@/lib/download'
import { fmtListingTime, fmtListingCost } from '@/lib/listing'

export function HistoryDetailPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const q = useListingJob(jobId)
  const d = q.data

  return (
    <div className="space-y-5">
      <button
        onClick={() => navigate('/history')}
        className="flex items-center gap-1.5 text-[13px] text-[#5b554e] transition-colors hover:text-[#4733b8]"
      >
        <ArrowLeftIcon className="size-4" /> 返回历史
      </button>

      {q.isLoading ? (
        <Skeleton className="h-40 rounded-2xl" />
      ) : q.isError || !d ? (
        <div className="rounded-2xl border border-[#ece8e2] bg-white p-10 text-center text-sm text-[#8a857e]">
          任务不存在或无权查看。
        </div>
      ) : (
        <>
          <div className="rounded-2xl border border-[#ece8e2] bg-white p-5">
            <div className="mb-3 flex items-center gap-3">
              <h2 className="text-lg font-semibold text-[#1c1b1a]">
                {d.platform ? `${d.platform} · ${d.ratio}` : d.ratio}
              </h2>
              <JobStatusBadge status={d.status} />
            </div>
            <p className="mb-3 whitespace-pre-wrap text-[14px] leading-relaxed text-[#2c2824]">{d.prompt}</p>
            <div className="flex flex-wrap gap-x-6 gap-y-1 text-[12.5px] text-[#8a857e]">
              <span>尺寸 {d.size}</span>
              <span>张数 {d.n}</span>
              <span>成本 {fmtListingCost(d.total_cost)}</span>
              <span>{fmtListingTime(d.created_at)}</span>
              {Object.entries(d.modifiers).map(([k, v]) => (
                <span key={k}>{v}</span>
              ))}
            </div>
            {d.error && (
              <p className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-[12.5px] text-rose-700">{d.error}</p>
            )}
          </div>

          {d.images.length > 0 && (
            <div>
              <h3 className="mb-2.5 text-[14px] font-bold text-[#1c1b1a]">候选图（{d.images.length}）</h3>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(208px,1fr))] gap-4">
                {d.images.map((img, i) => (
                  <div
                    key={i}
                    className="group relative aspect-square overflow-hidden rounded-2xl border border-[#ece8e2] bg-white"
                  >
                    <img src={img.url} alt="" loading="lazy" className="size-full object-cover" />
                    <button
                      onClick={() => downloadImage(img.url, `${d.platform ?? 'listing'}-${i + 1}.png`)}
                      className="absolute bottom-2.5 right-2.5 rounded-[10px] bg-[#2c2824]/90 px-3 py-1.5 text-[12.5px] text-white opacity-0 transition-opacity group-hover:opacity-100"
                    >
                      <DownloadIcon className="mr-1 inline size-3.5" /> 下载
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {d.input_urls.length > 0 && (
            <div>
              <h3 className="mb-2.5 text-[14px] font-bold text-[#1c1b1a]">输入产品图</h3>
              <div className="flex flex-wrap gap-3">
                {d.input_urls.map((u, i) => (
                  <img
                    key={i}
                    src={u}
                    alt=""
                    loading="lazy"
                    onError={(e) => {
                      e.currentTarget.style.display = 'none'
                    }}
                    className="size-20 rounded-xl border border-[#ece8e2] object-cover"
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
