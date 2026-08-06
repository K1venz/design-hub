// @vitest-environment jsdom

import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { postJson, useListingEvents } from '@/api/listing'

class FakeEventSource {
  static instances: FakeEventSource[] = []

  readonly close = vi.fn()
  readonly url: string
  private readonly listeners = new Map<string, EventListener>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: EventListener): void {
    this.listeners.set(type, listener)
  }

  emit(type: string, data = ''): void {
    this.listeners.get(type)?.({ data } as MessageEvent)
  }
}

beforeEach(() => {
  FakeEventSource.instances = []
  vi.stubGlobal('EventSource', FakeEventSource)
})

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

describe('useListingEvents', () => {
  it('closes the stream and reports a contract error for malformed image data', () => {
    const onContractError = vi.fn()
    renderHook(() => useListingEvents('job-1', { onEvent: vi.fn(), onContractError }))
    const stream = FakeEventSource.instances[0]

    stream.emit('image_generated', JSON.stringify({ item_id: 'i1', image_key: 'k1' }))

    expect(onContractError).toHaveBeenCalledWith(
      expect.objectContaining({ message: expect.stringContaining('url must be a non-empty string') }),
    )
    expect(stream.close).toHaveBeenCalledTimes(1)
  })

  it('leaves transport errors to native EventSource reconnection', () => {
    renderHook(() => useListingEvents('job-1', { onEvent: vi.fn(), onContractError: vi.fn() }))
    const stream = FakeEventSource.instances[0]

    stream.emit('error')

    expect(stream.close).not.toHaveBeenCalled()
  })
})
