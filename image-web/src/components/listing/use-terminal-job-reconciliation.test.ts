import { describe, expect, it, vi } from 'vitest'

import { createTerminalJobReconciler } from '@/components/listing/use-terminal-job-reconciliation'
import type { ListingJobDetail } from '@/lib/listing'

const detail = { id: 'job-1', images: [] } as unknown as ListingJobDetail

describe('createTerminalJobReconciler', () => {
  it('fetches and applies each terminal job at most once', async () => {
    const fetchJob = vi.fn().mockResolvedValue(detail)
    const applyDetail = vi.fn()
    const reconciler = createTerminalJobReconciler(fetchJob, applyDetail)

    await reconciler.reconcile('job-1')
    await reconciler.reconcile('job-1')

    expect(fetchJob).toHaveBeenCalledTimes(1)
    expect(applyDetail).toHaveBeenCalledTimes(1)
  })

  it('does not retry a failed reconciliation implicitly', async () => {
    const fetchJob = vi.fn().mockRejectedValue(new Error('network'))
    const reconciler = createTerminalJobReconciler(fetchJob, vi.fn())

    await expect(reconciler.reconcile('job-1')).rejects.toThrow('network')
    await reconciler.reconcile('job-1')

    expect(fetchJob).toHaveBeenCalledTimes(1)
  })

  it('can explicitly reset the handled job set for a new task', async () => {
    const fetchJob = vi.fn().mockResolvedValue(detail)
    const reconciler = createTerminalJobReconciler(fetchJob, vi.fn())

    await reconciler.reconcile('job-1')
    reconciler.reset()
    await reconciler.reconcile('job-1')

    expect(fetchJob).toHaveBeenCalledTimes(2)
  })
})
