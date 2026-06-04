import { useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'

import {
  LISTING_EVENT_TYPES, buildListingFormData, parseListingEvent,
  type ListingEvent, type ListingGenerateInput,
} from '@/lib/listing'
import { useAuthStore } from '@/stores/auth-store'

/** POST /listing/generate (multipart) -> { job_id }. fail-fast: non-2xx throws. */
export function useListingGenerate() {
  return useMutation({
    mutationFn: async (input: ListingGenerateInput): Promise<{ job_id: string }> => {
      const token = useAuthStore.getState().token
      const res = await fetch('/api/listing/generate', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: buildListingFormData(input),
      })
      if (!res.ok) throw new Error(`出图请求失败（${res.status}）：${await res.text()}`)
      return res.json() as Promise<{ job_id: string }>
    },
  })
}

/**
 * Subscribe to GET /listing/{jobId}/events (SSE). No-op when jobId is null.
 * Backend emits NAMED events (event: <type>), so we must addEventListener per type;
 * onmessage never fires for named events. Disconnects on unmount / job change;
 * closes on completed/failed.
 */
export function useListingEvents(jobId: string | null, onEvent: (e: ListingEvent) => void) {
  const cb = useRef(onEvent)
  cb.current = onEvent
  useEffect(() => {
    if (!jobId) return
    const token = useAuthStore.getState().token ?? ''
    const url = `/api/listing/${jobId}/events?access_token=${encodeURIComponent(token)}`
    const es = new EventSource(url)
    for (const type of LISTING_EVENT_TYPES) {
      es.addEventListener(type, (ev: MessageEvent) => {
        const parsed = parseListingEvent(type, ev.data)
        cb.current(parsed)
        if (parsed.kind === 'completed' || parsed.kind === 'failed') es.close()
      })
    }
    return () => es.close()
  }, [jobId])
}
