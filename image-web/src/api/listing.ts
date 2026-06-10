import { useEffect, useRef } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'

import {
  LISTING_EVENT_TYPES, buildListingBody, buildSetListingBody, parseListingEvent,
  type ListingEvent, type ListingGenerateInput, type ListingSetGenerateInput, type UploadedImage,
  type ListingJobSummary, type ListingJobDetail,
} from '@/lib/listing'
import { useAuthStore } from '@/stores/auth-store'

/** Authenticated GET helper for listing JSON endpoints. fail-fast on non-2xx. */
async function authGet<T>(path: string): Promise<T> {
  const token = useAuthStore.getState().token
  const res = await fetch(`/api${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error(`请求失败（${res.status}）：${await res.text()}`)
  return res.json() as Promise<T>
}

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
      if (!res.ok) {
        let detail = ''
        try {
          detail = ((await res.json()) as { detail?: string }).detail ?? ''
        } catch {
          // 响应体非 JSON —— 保持空，回退到状态码文案
        }
        throw new Error(detail || `上传失败（${res.status}）`)
      }
      return res.json() as Promise<UploadedImage>
    },
  })
}

async function postGenerate(body: unknown): Promise<{ job_id: string }> {
  const token = useAuthStore.getState().token
  const res = await fetch('/api/listing/generate', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`出图请求失败（${res.status}）：${await res.text()}`)
  return res.json() as Promise<{ job_id: string }>
}

/** POST /listing/generate（单图流，n=1）-> { job_id }. fail-fast: non-2xx throws. */
export function useListingGenerate() {
  return useMutation({
    mutationFn: (input: ListingGenerateInput) => postGenerate(buildListingBody(input)),
  })
}

/** POST /listing/generate（套图流，plan + 可选 overlay_texts）-> { job_id }. */
export function useListingSetGenerate() {
  return useMutation({
    mutationFn: (input: ListingSetGenerateInput) => postGenerate(buildSetListingBody(input)),
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

/** GET /listing/jobs?limit=&offset= → 本人任务列表（裸数组，时间倒序）。 */
export function useListingJobs(limit: number, offset: number) {
  return useQuery({
    queryKey: ['listing', 'jobs', limit, offset],
    queryFn: () => authGet<ListingJobSummary[]>(`/listing/jobs?limit=${limit}&offset=${offset}`),
  })
}

/** GET /listing/jobs/{jobId} → 详情（仅本人；非本人/不存在 → 404 抛错）。 */
export function useListingJob(jobId: string | undefined) {
  return useQuery({
    queryKey: ['listing', 'job', jobId],
    queryFn: () => authGet<ListingJobDetail>(`/listing/jobs/${jobId}`),
    enabled: Boolean(jobId),
  })
}
