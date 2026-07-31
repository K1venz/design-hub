import { ChevronLeftIcon, ChevronRightIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'

interface AdminPaginationProps {
  total: number
  limit: number
  offset: number
  onOffsetChange: (offset: number) => void
}

export function AdminPagination({
  total,
  limit,
  offset,
  onOffsetChange,
}: AdminPaginationProps) {
  const currentPage = Math.floor(offset / limit) + 1
  const pageCount = Math.max(1, Math.ceil(total / limit))
  const start = total === 0 ? 0 : offset + 1
  const end = Math.min(offset + limit, total)

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-wb-line-1 px-4 py-3">
      <p className="tabular text-xs text-wb-ink-6">
        {start}–{end} / 共 {total} 条
      </p>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label="上一页"
          disabled={offset === 0}
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
        >
          <ChevronLeftIcon className="size-4" />
        </Button>
        <span className="tabular min-w-16 text-center text-xs text-wb-ink-5">
          {currentPage} / {pageCount}
        </span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label="下一页"
          disabled={offset + limit >= total}
          onClick={() => onOffsetChange(offset + limit)}
        >
          <ChevronRightIcon className="size-4" />
        </Button>
      </div>
    </div>
  )
}
