import { Loader2Icon } from 'lucide-react'

import { useListingJob } from '@/api/listing'
import { ChatResultBlock } from '@/components/chat/ChatResultBlock'
import type {
  ChatEditSource,
  ChatPreviewImage,
} from '@/lib/chat'
import {
  JOB_STATUS,
  detailToResultSlots,
  settledSlotCount,
  type ListingJobDetail,
} from '@/lib/listing'

export interface ChatJobResultProps {
  jobId: string
  onPreview: (image: ChatPreviewImage) => void
  onEdit: (source: ChatEditSource) => void
  onBackground: (source: ChatEditSource) => void
  onReversePrompt: (source: ChatEditSource) => void
}

export interface ChatJobResultViewProps
  extends Omit<ChatJobResultProps, 'jobId'> {
  detail: ListingJobDetail | undefined
  loading: boolean
  error: boolean
}

export function ChatJobResult(props: ChatJobResultProps) {
  const { jobId, ...viewProps } = props
  const query = useListingJob(jobId, 'interactive')
  return (
    <ChatJobResultView
      detail={query.data}
      loading={query.isLoading}
      error={Boolean(query.error)}
      {...viewProps}
    />
  )
}

export function ChatJobResultView({
  detail,
  loading,
  error,
  onPreview,
  onEdit,
  onBackground,
  onReversePrompt,
}: ChatJobResultViewProps) {
  if (loading) {
    return (
      <div className="glass-lite flex max-w-[88%] items-center gap-2 rounded-2xl rounded-tl-md px-4 py-3 text-[12.5px] text-wb-ink-6">
        <Loader2Icon className="size-3.5 animate-spin" /> 正在载入出图结果…
      </div>
    )
  }
  if (error || !detail) {
    return (
      <div className="glass-lite max-w-[88%] rounded-2xl rounded-tl-md px-4 py-3 text-[12.5px] text-wb-ink-6">
        出图结果已失效或无法载入
      </div>
    )
  }
  const slots = detailToResultSlots(detail)
  if (slots.length === 0) return null
  return (
    <ChatResultBlock
      slots={slots}
      status={
        detail.status === JOB_STATUS.generating
          ? 'generating'
          : detail.status === JOB_STATUS.failed
            ? 'failed'
            : 'completed'
      }
      done={settledSlotCount(slots)}
      total={slots.length}
      onPreview={onPreview}
      onEdit={onEdit}
      onBackground={onBackground}
      onReversePrompt={onReversePrompt}
    />
  )
}
