import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { InboxIcon } from 'lucide-react'

import { useListingJobs } from '@/api/listing'
import { JobStatusBadge } from '@/components/listing/JobStatusBadge'
import { Skeleton } from '@/components/ui/skeleton'
import { fmtListingTime, fmtListingCost, type ListingJobSummary } from '@/lib/listing'

const LIMIT = 20

export function HistoryPage() {
  const navigate = useNavigate()
  const [offset, setOffset] = useState(0)
  const jobs = useListingJobs(LIMIT, offset)
  const items = jobs.data ?? []

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-semibold tracking-tight text-[#1c1b1a]">出图历史</h2>
        <p className="text-sm text-[#8a857e]">你的每次商品套图出图任务，可回看与重新下载。</p>
      </div>

      {jobs.isLoading ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="aspect-[4/3] rounded-2xl" />
          ))}
        </div>
      ) : jobs.isError ? (
        <div className="rounded-2xl border border-[#ece8e2] bg-white p-10 text-center text-sm text-[#8a857e]">
          加载失败，请稍后重试。
        </div>
      ) : items.length === 0 && offset === 0 ? (
        <div className="flex flex-col items-center justify-center gap-4 rounded-2xl border border-[#ece8e2] bg-white py-20">
          <InboxIcon className="size-12 text-[#cabfb0]" strokeWidth={1.5} />
          <p className="text-sm text-[#8a857e]">还没有出图记录</p>
          <button
            onClick={() => navigate('/')}
            className="rounded-[10px] bg-gradient-to-r from-[#7c6cff] to-[#ff9a62] px-5 py-2 text-[13px] font-medium text-white shadow-[0_8px_20px_-8px_rgba(124,108,255,.55)]"
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
              className="rounded-[10px] border border-[#ece8e2] bg-white px-4 py-1.5 text-[13px] text-[#4a443d] disabled:opacity-40"
            >
              上一页
            </button>
            <span className="text-[13px] text-[#8a857e]">第 {offset / LIMIT + 1} 页</span>
            <button
              disabled={items.length < LIMIT}
              onClick={() => setOffset((o) => o + LIMIT)}
              className="rounded-[10px] border border-[#ece8e2] bg-white px-4 py-1.5 text-[13px] text-[#4a443d] disabled:opacity-40"
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
      className="group overflow-hidden rounded-2xl border border-[#ece8e2] bg-white text-left transition-shadow hover:shadow-[0_12px_30px_-16px_rgba(60,50,40,.25)]"
    >
      <div className="relative aspect-[4/3] bg-[#f1ece5]">
        {job.first_image_url ? (
          <img src={job.first_image_url} alt="" loading="lazy" className="size-full object-cover" />
        ) : (
          <div className="grid size-full place-items-center text-[12px] text-[#bdb6ab]">无图</div>
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
          <span className="font-medium text-[#2c2824]">{job.platform}</span>
          <span className="text-[#8a857e]">{job.ratio} · {job.n}张</span>
        </div>
        <div className="flex items-center justify-between text-[12px] text-[#8a857e]">
          <span>{fmtListingTime(job.created_at)}</span>
          <span>{fmtListingCost(job.total_cost)}</span>
        </div>
      </div>
    </button>
  )
}
