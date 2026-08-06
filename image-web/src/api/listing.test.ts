import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  listingJobQueryKey,
  listingJobRefetchInterval,
  postJson,
} from '@/api/listing'
import { JOB_STATUS } from '@/lib/listing'

describe('postJson', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends an idempotency key with every listing submission', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ job_id: 'job-1' }), {
        status: 202,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await postJson('/listing/generate', { prompt: 'product image' })

    const headers = fetchMock.mock.calls[0]?.[1]?.headers as Record<string, string>
    expect(headers['Idempotency-Key']).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    )
  })

  it('polls only while a job is generating', () => {
    expect(listingJobRefetchInterval(JOB_STATUS.generating)).toBe(1500)
    expect(listingJobRefetchInterval(JOB_STATUS.done)).toBe(false)
    expect(listingJobRefetchInterval(JOB_STATUS.partial)).toBe(false)
    expect(listingJobRefetchInterval(JOB_STATUS.failed)).toBe(false)
    expect(listingJobRefetchInterval(undefined)).toBe(false)
  })

  it('uses one stable query key for live and restored jobs', () => {
    expect(listingJobQueryKey('job-1')).toEqual(['listing', 'job', 'job-1'])
  })
})
