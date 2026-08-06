import { useEffect, useState } from 'react'

import { fetchListingJob } from '@/api/listing'
import type { ListingJobDetail } from '@/lib/listing'

interface TerminalJobReconciler {
  reconcile: (jobId: string) => Promise<void>
  reset: () => void
}

export function createTerminalJobReconciler(
  fetchJob: (jobId: string) => Promise<ListingJobDetail>,
  applyDetail: (detail: ListingJobDetail) => void,
): TerminalJobReconciler {
  const handled = new Set<string>()
  return {
    async reconcile(jobId) {
      if (handled.has(jobId)) return
      handled.add(jobId)
      applyDetail(await fetchJob(jobId))
    },
    reset() {
      handled.clear()
    },
  }
}

export function useTerminalJobReconciliation(
  applyDetail: (detail: ListingJobDetail) => void,
): TerminalJobReconciler {
  const [state] = useState(() => {
    let currentApplyDetail = applyDetail
    return {
      reconciler: createTerminalJobReconciler(
        fetchListingJob,
        (detail) => currentApplyDetail(detail),
      ),
      updateApplyDetail(next: (detail: ListingJobDetail) => void) {
        currentApplyDetail = next
      },
    }
  })
  useEffect(() => {
    state.updateApplyDetail(applyDetail)
  }, [applyDetail, state])
  return state.reconciler
}
