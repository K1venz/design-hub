import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { InboxIcon } from 'lucide-react'

import { useListingJobs } from '@/api/listing'
import { JobStatusBadge } from '@/components/listing/JobStatusBadge'
import { Skeleton } from '@/components/ui/skeleton'
import { editModeLabel, fmtListingTime, fmtListingCost, type ListingJobSummary } from '@/lib/listing'

const LIMIT = 20

export function HistoryPage() {
  const navigate = useNavigate()
  const [offset, setOffset] = useState(0)
  const jobs = useListingJobs(LIMIT, offset)
  const items = jobs.data ?? []

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold tracking-tight text-wb-ink-1">出图历史</h2>
        <p className="text-sm text-wb-ink-6">你的每次商品套图出图任务，可回看与重新下载。</p>
      </div>

      {jobs.isLoading ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="aspect-[4/3] rounded-2xl" />
          ))}
        </div>
      ) : jobs.isError ? (
        <div className="rounded-2xl border border-white/70 bg-white shadow-[0_6px_24px_-10px_rgba(40,40,90,.12)] p-10 text-center text-sm text-wb-ink-6">
          加载失败，请稍后重试。
        </div>
      ) : items.length === 0 && offset === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 rounded-2xl border border-white/70 bg-white shadow-[0_6px_24px_-10px_rgba(40,40,90,.12)] py-20">
          <InboxIcon className="size-12 text-wb-faint-4" strokeWidth={1.5} />
          <p className="text-sm text-wb-ink-6">还没有出图记录</p>
          <button
            onClick={() => navigate('/set')}
            className="rounded-full bg-gradient-to-r from-wb-grad-from to-wb-grad-to px-5 py-2 text-[13px] font-medium text-white shadow-[0_8px_20px_-8px_rgba(91,91,214,.55)] transition-shadow hover:shadow-[0_10px_24px_-8px_rgba(91,91,214,.7)]"
          >
            去出图
          </button>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
            {items.map((j) => (
              <JobCard key={j.job_id} job={j} onClick={() => navigate(`/history/${j.job_id}`)} />
            ))}
          </div>
          <div className="flex items-center justify-center gap-3 pt-2">
            <button
              disabled={offset === 0}
              onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}
              className="rounded-[10px] border border-wb-line-1 bg-white px-4 py-1.5 text-[13px] text-wb-ink-3 disabled:opacity-40"
            >
              上一页
            </button>
            <span className="text-[13px] text-wb-ink-6">第 {offset / LIMIT + 1} 页</span>
            <button
              disabled={items.length < LIMIT}
              onClick={() => setOffset((o) => o + LIMIT)}
              className="rounded-[10px] border border-wb-line-1 bg-white px-4 py-1.5 text-[13px] text-wb-ink-3 disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        </>
      )}
    </div>
  )
}

function JobCard({ job, onClick }: { job: ListingJobSummary; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="group animate-in fade-in slide-in-from-bottom-2 overflow-hidden rounded-2xl border border-white/70 bg-white text-left shadow-[0_6px_24px_-10px_rgba(40,40,90,.12)] duration-300 transition-[box-shadow,transform] hover:-translate-y-0.5 hover:shadow-[0_14px_32px_-12px_rgba(40,40,90,.22)]"
    >
      <div className="relative aspect-[4/3] bg-wb-surface-4">
        {job.first_image_url ? (
          <img src={job.first_image_url} alt="" loading="lazy" className="size-full object-cover" />
        ) : (
          <div className="grid size-full place-items-center p-4 text-center text-[12px] text-wb-faint-3">
            {job.image_count > 0 ? '该图片暂不可用' : '无图'}
          </div>
        )}
        <JobStatusBadge status={job.status} className="absolute left-2 top-2" />
        {job.image_count > 0 && (
          <span className="absolute right-2 top-2 rounded-md bg-black/55 px-2 py-0.5 text-[11px] text-white">
            {job.image_count} 张
          </span>
        )}
      </div>
      <div className="space-y-1 p-3">
        <div className="flex items-center justify-between text-[13px]">
          <span className="flex items-center gap-1.5 font-medium text-wb-ink-2">
            {job.platform ?? '通用'}
            {job.edit_mode && (
              <span className="rounded border border-wb-tint-line bg-wb-tint-2 px-1.5 py-px text-[10.5px] font-medium text-wb-brand-deep">
                ✎ {editModeLabel(job.edit_mode)}
              </span>
            )}
          </span>
          <span className="text-wb-ink-6">{job.ratio} · {job.n}张</span>
        </div>
        <div className="flex items-center justify-between text-[12px] text-wb-ink-6">
          <span>{fmtListingTime(job.created_at)}</span>
          <span>{fmtListingCost(job.total_cost)}</span>
        </div>
      </div>
    </button>
  )
}
