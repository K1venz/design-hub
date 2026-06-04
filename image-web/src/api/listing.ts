import { useEffect, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'

import {
  LISTING_EVENT_TYPES, buildListingBody, parseListingEvent,
  type ListingEvent, type ListingGenerateInput, type UploadedImage,
} from '@/lib/listing'
import { useAuthStore } from '@/stores/auth-store'

/** POST /uploads (multipart, single file field `file`, Bearer) -> { id, url }. fail-fast. */
export function useUploadImage() {
  return useMutation({
    mutationFn: async (file: File): Promise<UploadedImage> => {
      const token = useAuthStore.getState().token
      const fd = new FormData()
      fd.append('file', file)
      const res = await fetch('/api/uploads', {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      })
      if (!res.ok) throw new Error(`上传失败（${res.status}）：${await res.text()}`)
      return res.json() as Promise<UploadedImage>
    },
  })
}

/** POST /listing/generate (JSON body, upload_ids) -> { job_id }. fail-fast: non-2xx throws. */
export function useListingGenerate() {
  return useMutation({
    mutationFn: async (input: ListingGenerateInput): Promise<{ job_id: string }> => {
      const token = useAuthStore.getState().token
      const res = await fetch('/api/listing/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(buildListingBody(input)),
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
  useEffect(() => {
    cb.current = onEvent
  })
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
