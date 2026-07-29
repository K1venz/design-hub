import { afterEach, describe, expect, it, vi } from 'vitest'

import { postJson } from '@/api/listing'

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
})
